#!/usr/bin/env python3
"""Generation backends for scripts/auto_generate.py.

One interface, several implementations. The driver knows nothing about any
provider; it asks a backend to turn a prompt plus a reference image into PNG
bytes and hands the result to the verifier.

    class Backend:
        name          str
        paid          bool
        takes_reference   bool   - False means it cannot condition on the mascot
        preflight()          raise SystemExit with a fixable message, or return
        generate(prompt, reference_bytes) -> bytes

Everything here is stdlib. HTTP goes through urllib rather than requests so the
repository keeps its zero-dependency property; Playwright is imported lazily and
only by the one backend that needs it.

Request and response shapes come from scripts/config/generation.json rather than
being hard-coded, because provider APIs and model ids move. Where a default is
shipped it is the provider's documented shape, and the model id carries
model_verified: false until a human checks it against current docs.
"""

import base64
import json
import os
import random
import time
import urllib.error
import urllib.request

USER_AGENT = "stickman-doodle-auto-generate/1.0"


class BackendError(Exception):
    """A generation attempt failed. Carries whether a retry could help."""

    def __init__(self, message, retryable=False, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


# ------------------------------------------------------------------ helpers

def dig(obj, path):
    """Walk a dotted path, treating integer segments as list indices."""
    cur = obj
    for part in path.split("."):
        if part.isdigit():
            if not isinstance(cur, (list, tuple)) or int(part) >= len(cur):
                raise BackendError("response has no %s (at %r)" % (path, part))
            cur = cur[int(part)]
        else:
            if not isinstance(cur, dict) or part not in cur:
                raise BackendError("response has no %s (at %r)" % (path, part))
            cur = cur[part]
    return cur


def plant(obj, path, value):
    """Set a dotted path, creating dicts and growing lists as needed."""
    parts = path.split(".")
    cur = obj
    for i, part in enumerate(parts[:-1]):
        nxt = parts[i + 1]
        if part.isdigit():
            idx = int(part)
            while len(cur) <= idx:
                cur.append([] if nxt.isdigit() else {})
            cur = cur[idx]
        else:
            if part not in cur or not isinstance(cur[part], (dict, list)):
                cur[part] = [] if nxt.isdigit() else {}
            cur = cur[part]
    last = parts[-1]
    if last.isdigit():
        idx = int(last)
        while len(cur) <= idx:
            cur.append(None)
        cur[idx] = value
    else:
        cur[last] = value


def merge(base, extra):
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


def backoff_delay(attempt, base, cap):
    """Exponential with full jitter, so parallel retries do not resonate."""
    return random.uniform(0, min(cap, base * (2 ** attempt)))


# ------------------------------------------------------------------ base

class Backend(object):
    name = "?"
    paid = True
    takes_reference = True

    def __init__(self, cfg, limits):
        self.cfg = cfg
        self.limits = limits

    def preflight(self):
        return

    def generate(self, prompt, reference_bytes):
        raise NotImplementedError

    def close(self):
        return


# ------------------------------------------------------------------ mock

class MockBackend(Backend):
    """Local, free, deterministic. Exercises the harness without spending.

    Renders a valid PNG whose pixel content is derived from the prompt, so two
    different frames produce two different files and the verifier has something
    real to check.
    """

    name = "mock"
    paid = False
    takes_reference = True

    def generate(self, prompt, reference_bytes):
        import struct
        import zlib
        w = h = 64
        seed = zlib.crc32(prompt.encode("utf-8"))
        r, g, b = (seed >> 16) & 0xFF, (seed >> 8) & 0xFF, seed & 0xFF
        raw = b"".join(b"\x00" + bytes([r, g, b]) * w for _ in range(h))

        def chunk(typ, data):
            return (struct.pack(">I", len(data)) + typ + data
                    + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

        png = (b"\x89PNG\r\n\x1a\n"
               + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw))
               + chunk(b"IEND", b""))
        # Pad past the driver's 4 KB floor using a tEXt chunk, so the file stays
        # a structurally valid PNG rather than a PNG with junk stapled on.
        pad = max(0, 5000 - len(png))
        if pad:
            note = b"Comment\x00" + b"mock render " * (pad // 12 + 1)
            png = png[:-12] + chunk(b"tEXt", note) + png[-12:]
        return png


# ------------------------------------------------------------------ http

class HTTPBackend(Backend):
    """Any provider reachable with one JSON POST, optionally then polling."""

    def __init__(self, name, cfg, limits):
        Backend.__init__(self, cfg, limits)
        self.name = name
        self.paid = cfg.get("paid", True)
        self.takes_reference = bool(cfg.get("request", {}).get("reference_path"))

    # -- setup ------------------------------------------------------------

    def preflight(self):
        env = self.cfg.get("api_key_env")
        if not env:
            raise SystemExit("error: backend %r declares no api_key_env" % self.name)
        if not os.environ.get(env):
            raise SystemExit(
                "error: $%s is not set. %s needs it to authenticate.\n"
                "  export %s=... and re-run. The key is read from the "
                "environment and never written to disk." % (env, self.name, env))
        if "{model}" in self.cfg.get("endpoint", "") and not self.cfg.get("model"):
            raise SystemExit(
                "error: backend %r has model: null but its endpoint needs one. "
                "Set it in scripts/config/generation.json." % self.name)
        if self.cfg.get("request", {}).get("version_path") and not self.cfg.get("model"):
            raise SystemExit(
                "error: backend %r needs a version id in `model` "
                "(Replicate wants the 64-char version hash, not a model name). "
                "Set it in scripts/config/generation.json." % self.name)
        if not self.cfg.get("model_verified", False):
            print("  ! %s model %r carries model_verified: false — nobody has "
                  "checked it against current provider docs."
                  % (self.name, self.cfg.get("model")))

    # -- request ----------------------------------------------------------

    def _headers(self):
        key = os.environ[self.cfg["api_key_env"]]
        auth = self.cfg.get("auth", {})
        h = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if auth.get("header"):
            h[auth["header"]] = auth.get("format", "{key}").format(key=key)
        return h

    def _body(self, prompt, reference_bytes):
        req = self.cfg.get("request", {})
        body = json.loads(json.dumps(req.get("static") or {}))
        plant(body, req["prompt_path"], prompt)
        if req.get("version_path"):
            plant(body, req["version_path"], self.cfg["model"])
        if reference_bytes and req.get("reference_path"):
            b64 = base64.b64encode(reference_bytes).decode("ascii")
            if req.get("reference_encoding") == "data_uri":
                b64 = "data:image/png;base64," + b64
            plant(body, req["reference_path"], b64)
        return json.dumps(body).encode("utf-8")

    def _call(self, url, data=None, headers=None, method=None):
        req = urllib.request.Request(url, data=data,
                                     headers=headers or self._headers(),
                                     method=method or ("POST" if data else "GET"))
        timeout = self.limits.get("request_timeout_seconds", 180)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:400]
            except Exception:
                pass
            retry_after = e.headers.get("Retry-After") if e.headers else None
            try:
                retry_after = float(retry_after) if retry_after else None
            except ValueError:
                retry_after = None
            raise BackendError(
                "HTTP %s from %s: %s" % (e.code, self.name, detail or e.reason),
                retryable=e.code in (408, 409, 425, 429, 500, 502, 503, 504),
                retry_after=retry_after)
        except urllib.error.URLError as e:
            raise BackendError("network error talking to %s: %s"
                               % (self.name, e.reason), retryable=True)
        except json.JSONDecodeError:
            raise BackendError("%s returned a non-JSON body" % self.name,
                               retryable=True)

    # -- response ---------------------------------------------------------

    def _fetch_image(self, url):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(
                    req, timeout=self.limits.get("request_timeout_seconds", 180)) as r:
                return r.read()
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            raise BackendError("could not download the result: %s" % e,
                               retryable=True)

    def _poll(self, payload):
        resp = self.cfg["response"]
        url = dig(payload, resp["poll_url_path"])
        deadline = time.time() + self.limits.get("request_timeout_seconds", 180)
        while time.time() < deadline:
            state = self._call(url)
            status = str(dig(state, resp["status_path"])).lower()
            if status in ("succeeded", "success", "completed"):
                return state
            if status in ("failed", "canceled", "cancelled", "error"):
                raise BackendError("%s reported %s: %s"
                                   % (self.name, status,
                                      str(state.get("error"))[:200]),
                                   retryable=False)
            time.sleep(2.0)
        raise BackendError("%s did not finish within the timeout" % self.name,
                           retryable=True)

    def generate(self, prompt, reference_bytes):
        payload = self._call(self.cfg["endpoint"].format(model=self.cfg.get("model")),
                             data=self._body(prompt, reference_bytes))
        resp = self.cfg.get("response", {})
        if resp.get("poll"):
            payload = self._poll(payload)
        if resp.get("image_b64_path"):
            try:
                return base64.b64decode(dig(payload, resp["image_b64_path"]))
            except (ValueError, TypeError) as e:
                raise BackendError("could not decode the returned image: %s" % e)
        if resp.get("image_url_path"):
            return self._fetch_image(dig(payload, resp["image_url_path"]))
        raise BackendError("backend %r declares no way to read the image out of "
                           "the response" % self.name)


# ------------------------------------------------------------------ flow

class PlaywrightBackend(Backend):
    """Drive Google Flow in a real browser.

    Flow has no public API. This types the prompt into the live page, attaches
    the mascot reference, submits, and reads the result image back out. It needs
    a Chromium profile already signed in to Google — see docs/auto-generation.md,
    including the terms-of-service risk, before using it.
    """

    name = "flow"
    paid = True
    takes_reference = True

    def __init__(self, cfg, limits):
        Backend.__init__(self, cfg, limits)
        self._pw = None
        self._ctx = None
        self._page = None
        self._ref_path = None

    def preflight(self):
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            raise SystemExit(
                "error: the flow backend needs Playwright.\n"
                "  pip install playwright\n"
                "  (Chromium is already present at $PLAYWRIGHT_BROWSERS_PATH; "
                "do not run `playwright install`.)")
        if not self.cfg.get("profile_dir"):
            raise SystemExit(
                "error: flow.profile_dir is null in scripts/config/generation.json.\n"
                "  Flow requires a signed-in Google session. Point profile_dir at a\n"
                "  Chromium user-data directory you have logged into once by hand.")
        missing = [k for k, v in (self.cfg.get("selectors") or {}).items() if not v]
        if missing:
            raise SystemExit(
                "error: flow selectors are unset: %s\n"
                "  Flow's DOM is not a stable public API, so these cannot be "
                "shipped as defaults.\n"
                "  Fill them in scripts/config/generation.json from the live page."
                % ", ".join(sorted(missing)))

    def _ensure(self, reference_bytes):
        if self._page:
            return
        from playwright.sync_api import sync_playwright
        import tempfile
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            self.cfg["profile_dir"], headless=False,
            executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM")
            or "/opt/pw-browsers/chromium")
        self._page = self._ctx.new_page()
        self._page.goto(self.cfg["url"], wait_until="domcontentloaded")
        if reference_bytes:
            fd, self._ref_path = tempfile.mkstemp(suffix=".png")
            with os.fdopen(fd, "wb") as fh:
                fh.write(reference_bytes)

    def generate(self, prompt, reference_bytes):
        self._ensure(reference_bytes)
        sel = self.cfg["selectors"]
        page = self._page
        try:
            if self._ref_path:
                page.set_input_files(sel["reference_upload"], self._ref_path)
            page.fill(sel["prompt_input"], prompt)
            page.click(sel["submit"])
            img = page.wait_for_selector(
                sel["result_image"],
                timeout=self.limits.get("request_timeout_seconds", 180) * 1000)
            src = img.get_attribute("src") or ""
        except Exception as e:
            raise BackendError("flow interaction failed: %s" % e, retryable=True)
        if src.startswith("data:"):
            return base64.b64decode(src.split(",", 1)[1])
        resp = page.request.get(src)
        if not resp.ok:
            raise BackendError("could not fetch the result image from Flow",
                               retryable=True)
        return resp.body()

    def close(self):
        for closer in (self._ctx, self._pw):
            try:
                if closer:
                    (closer.close if hasattr(closer, "close") else closer.stop)()
            except Exception:
                pass
        if self._ref_path and os.path.exists(self._ref_path):
            os.remove(self._ref_path)


# ------------------------------------------------------------------ factory

def build(name, config):
    """Return a ready Backend, or exit with a message naming the fix."""
    backends = config.get("backends") or {}
    if name not in backends:
        raise SystemExit("error: unknown backend %r; configured: %s"
                         % (name, ", ".join(sorted(backends))))
    cfg = backends[name]
    limits = config.get("limits") or {}
    kind = cfg.get("kind")
    if kind == "local":
        return MockBackend(cfg, limits)
    if kind == "http":
        return HTTPBackend(name, cfg, limits)
    if kind == "playwright":
        return PlaywrightBackend(cfg, limits)
    raise SystemExit("error: backend %r has unknown kind %r" % (name, kind))
