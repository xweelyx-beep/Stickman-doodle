#!/usr/bin/env python3
"""Tests for the automated generation driver.

Nothing here touches the network. The HTTP backends are exercised through a
stubbed transport, and the end-to-end runs use the `mock` backend, which is
local by construction.

    python3 scripts/tests/test_auto_generate.py
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "core"))

import auto_generate as ag  # noqa: E402
import backends  # noqa: E402
import generate_frames as gfr  # noqa: E402


def run(root, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        try:
            code = ag.main(["--root", root] + list(argv))
        except SystemExit as e:
            return (e.code if isinstance(e.code, int) else 1), buf.getvalue() + str(e)
    return code, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "r")
        shutil.copytree(ROOT, self.root,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "output"))
        gfr.paths._cache.pop(self.root, None)
        self.frames = os.path.join(self.root, "output", "frames")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def config(self):
        with open(os.path.join(self.root, "scripts", "config",
                               "generation.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def write_config(self, cfg):
        with open(os.path.join(self.root, "scripts", "config",
                               "generation.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=1)


class ToolChoiceStaysTheOperators(Base):
    """The safeguard carried over from models.json."""

    def test_no_default_backend_is_configured(self):
        self.assertIsNone(self.config()["default_backend"])

    def test_backend_is_required(self):
        code, out = run(self.root, "--start", "0", "--end", "1")
        self.assertNotEqual(code, 0)
        self.assertIn("--backend is required", out)

    def test_unknown_backend_names_what_is_configured(self):
        code, out = run(self.root, "--backend", "nope")
        self.assertNotEqual(code, 0)
        self.assertIn("unknown backend", out)


class SpendGate(Base):
    def test_dry_run_is_the_default(self):
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "2")
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        self.assertFalse(os.path.exists(os.path.join(self.frames, "000.png")))

    def test_paid_backend_needs_explicit_approval(self):
        code, out = run(self.root, "--backend", "fal", "--start", "0", "--end", "4",
                        "--execute")
        self.assertNotEqual(code, 0)
        self.assertIn("--approve-spend 5", out)

    def test_approval_must_match_the_real_count(self):
        code, out = run(self.root, "--backend", "fal", "--start", "0", "--end", "4",
                        "--execute", "--approve-spend", "2")
        self.assertNotEqual(code, 0)
        self.assertIn("does not match", out)

    def test_free_backend_needs_no_approval(self):
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "2",
                        "--execute", "--delay", "0")
        self.assertEqual(code, 0)
        self.assertIn("rendered 3", out)


class CostReporting(Base):
    def test_no_invented_price_when_no_sourced_rate(self):
        line = ag.cost_line(self.config(), "fal", 157)
        self.assertIn("157 image(s)", line)
        self.assertIn("No cost estimate", line)
        self.assertNotIn("$", line.split("Fill")[0])

    def test_a_sourced_rate_is_used(self):
        cfg = self.config()
        cfg["rates"]["source"] = "https://example.test/pricing"
        cfg["rates"]["checked_utc"] = "2026-08-29T00:00:00Z"
        cfg["rates"]["usd_per_image"]["fal"] = 0.025
        line = ag.cost_line(cfg, "fal", 100)
        self.assertIn("$2.50", line)
        self.assertIn("example.test", line)

    def test_free_backend_says_free(self):
        self.assertIn("Free backend", ag.cost_line(self.config(), "mock", 10))


class Pacing(Base):
    """Rate limiting exists for provider limits. A local backend has none."""

    def test_free_backend_defaults_to_no_delay(self):
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "2")
        self.assertEqual(code, 0)
        self.assertIn("pacing     : 0.0s", out)

    def test_paid_backend_keeps_the_configured_delay(self):
        code, out = run(self.root, "--backend", "fal", "--start", "0", "--end", "2")
        self.assertEqual(code, 0)
        self.assertIn("pacing     : 3.0s", out)

    def test_an_explicit_delay_wins_on_a_free_backend(self):
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "2",
                        "--delay", "1.5")
        self.assertEqual(code, 0)
        self.assertIn("pacing     : 1.5s", out)

    def test_a_negative_delay_is_refused(self):
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "2",
                        "--delay", "-1")
        self.assertNotEqual(code, 0)
        self.assertIn("cannot be negative", out)


class Rendering(Base):
    def test_renders_the_requested_window_only(self):
        code, out = run(self.root, "--backend", "mock", "--start", "5", "--end", "9",
                        "--execute", "--delay", "0")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(self.frames, "005.png")))
        self.assertFalse(os.path.exists(os.path.join(self.frames, "004.png")))
        self.assertFalse(os.path.exists(os.path.join(self.frames, "010.png")))

    def test_output_passes_the_other_tool_s_verifier(self):
        run(self.root, "--backend", "mock", "--start", "0", "--end", "4",
            "--execute", "--delay", "0")
        frames = gfr.load_frames(self.root)
        man = gfr.load_manifest(self.root, frames, 3)
        found, problems = gfr.verify(self.root, man, quiet=True)
        self.assertEqual(found, 5)
        self.assertEqual(problems, [])

    def test_distinct_prompts_produce_distinct_files(self):
        run(self.root, "--backend", "mock", "--start", "0", "--end", "2",
            "--execute", "--delay", "0")
        blobs = set()
        for n in ("000.png", "001.png", "002.png"):
            with open(os.path.join(self.frames, n), "rb") as fh:
                blobs.add(fh.read())
        self.assertEqual(len(blobs), 3)

    def test_bad_window_is_refused(self):
        code, out = run(self.root, "--backend", "mock", "--start", "10", "--end", "2")
        self.assertNotEqual(code, 0)
        self.assertIn("--start/--end", out)

    def test_end_beyond_the_last_frame_is_refused(self):
        code, _ = run(self.root, "--backend", "mock", "--start", "0", "--end", "999")
        self.assertNotEqual(code, 0)


class Resume(Base):
    def test_existing_good_frames_are_skipped(self):
        run(self.root, "--backend", "mock", "--start", "0", "--end", "4",
            "--execute", "--delay", "0")
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "4",
                        "--execute", "--delay", "0")
        self.assertEqual(code, 0)
        self.assertIn("to render  : 0 of 5", out)

    def test_a_corrupt_frame_is_the_only_one_redone(self):
        run(self.root, "--backend", "mock", "--start", "0", "--end", "4",
            "--execute", "--delay", "0")
        with open(os.path.join(self.frames, "002.png"), "wb") as fh:
            fh.write(b"junk")
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "4",
                        "--execute", "--delay", "0")
        self.assertEqual(code, 0)
        self.assertIn("to render  : 1 of 5", out)
        self.assertIn("002.png", out)

    def test_regenerate_redoes_everything(self):
        run(self.root, "--backend", "mock", "--start", "0", "--end", "4",
            "--execute", "--delay", "0")
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "4",
                        "--execute", "--delay", "0", "--regenerate")
        self.assertIn("to render  : 5 of 5", out)


class FormatDiagnostics(Base):
    """A wrong format must be named, and must never be retried — each retry on a
    paid backend is another billed generation."""

    JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 6000

    def test_jpeg_is_named_not_called_bad_magic(self):
        reason, retryable = ag.verify_bytes(self.JPEG)
        self.assertIn("expected PNG, got JPEG", reason)
        self.assertNotIn("bad magic bytes", reason)

    def test_jpeg_points_at_the_actual_fix(self):
        reason, _ = ag.verify_bytes(self.JPEG)
        self.assertIn("output_format", reason)
        self.assertIn("generation.json", reason)

    def test_a_format_mismatch_is_not_retryable(self):
        _, retryable = ag.verify_bytes(self.JPEG)
        self.assertFalse(retryable)

    def test_a_truncated_png_is_retryable(self):
        short = backends.PNG_MAGIC if hasattr(backends, "PNG_MAGIC") else b"\x89PNG\r\n\x1a\n"
        _, retryable = ag.verify_bytes(short + b"\x00" * 100)
        self.assertTrue(retryable, "a cut-off download is worth one more try")

    def test_a_json_error_body_is_shown_decoded(self):
        body = b'{"detail":"Unauthorized: invalid credentials"}'
        reason, retryable = ag.verify_bytes(body)
        self.assertIn("Unauthorized", reason)
        self.assertFalse(retryable)

    def test_an_html_error_page_is_shown_decoded(self):
        reason, _ = ag.verify_bytes(b"<!doctype html><title>502 Bad Gateway</title>")
        self.assertIn("502", reason)

    def test_the_content_type_header_is_surfaced(self):
        class Stub:
            last_content_type = "image/jpeg"
        reason, _ = ag.verify_bytes(self.JPEG, Stub())
        self.assertIn("image/jpeg", reason)

    def test_a_wrong_format_costs_exactly_one_generation(self):
        state = {"n": 0}

        class ReturnsJpeg(backends.Backend):
            name, paid, takes_reference = "jpeg", False, True

            def generate(self, prompt, reference_bytes):
                state["n"] += 1
                return FormatDiagnostics.JPEG

        real = backends.build
        backends.build = lambda n, c: ReturnsJpeg({}, {})
        try:
            code, out = run(self.root, "--backend", "mock", "--start", "0",
                            "--end", "0", "--execute", "--delay", "0",
                            "--max-retries", "5")
        finally:
            backends.build = real
        self.assertNotEqual(code, 0)
        self.assertEqual(state["n"], 1,
                         "retrying a JPEG response bills five more images for nothing")
        self.assertIn("billed generation", out)


class Sniffing(Base):
    def test_common_formats_are_identified(self):
        cases = {
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 20: "PNG",
            b"\xff\xd8\xff\xe0" + b"\x00" * 20: "JPEG",
            b"GIF89a" + b"\x00" * 20: "GIF",
            b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20: "WEBP",
            b'{"error": 1}': "JSON",
            b"<!doctype html><body>": "HTML",
        }
        for data, want in cases.items():
            self.assertEqual(backends.sniff_format(data), want)

    def test_an_unknown_payload_returns_none(self):
        self.assertIsNone(backends.sniff_format(b"\x01\x02\x03\x04binary junk"))

    def test_describe_shows_text_bodies_readably(self):
        d = backends.describe_bytes(b'{"detail":"quota exceeded"}')
        self.assertIn("quota exceeded", d)
        self.assertIn("JSON", d)

    def test_describe_shows_binary_as_hex(self):
        d = backends.describe_bytes(b"\xff\xd8\xff\xe0" + b"\xab" * 300)
        self.assertIn("JPEG", d)
        self.assertIn("hex", d)

    def test_describe_respects_the_limit(self):
        d = backends.describe_bytes(b"\xff\xd8\xff" + b"\xab" * 5000, limit=200)
        self.assertIn("first 200", d)
        self.assertLess(len(d), 600)


class FalConfig(Base):
    def test_fal_asks_for_png_explicitly(self):
        static = self.config()["backends"]["fal"]["request"]["static"]
        self.assertEqual(static.get("output_format"), "png",
                         "FLUX defaults to JPEG; the driver only accepts PNG")

    def test_gemini_asks_for_png_explicitly(self):
        params = self.config()["backends"]["gemini"]["request"]["static"]["parameters"]
        self.assertEqual(params.get("outputOptions", {}).get("mimeType"), "image/png")

    def test_the_png_request_reaches_the_body(self):
        cfg = self.config()["backends"]["fal"]
        body = json.loads(backends.HTTPBackend("fal", cfg, {})._body("P", b"REF"))
        self.assertEqual(body["output_format"], "png")


class Validation(Base):
    def test_verify_bytes_matches_the_shared_contract(self):
        self.assertIsNotNone(ag.verify_bytes(b"tiny")[0])
        self.assertIn("expected PNG",
                      ag.verify_bytes(b"x" * (gfr.MIN_BYTES + 1))[0])
        good = backends.MockBackend({}, {}).generate("x", None)
        self.assertIsNone(ag.verify_bytes(good)[0])

    def test_a_good_png_is_still_recognised_for_resume(self):
        """The regression guard: verify_bytes returning a tuple must not make
        every existing frame look unrendered."""
        good = backends.MockBackend({}, {}).generate("x", None)
        reason, retryable = ag.verify_bytes(good)
        self.assertIsNone(reason)
        self.assertFalse(retryable)

    def test_a_backend_returning_junk_never_reaches_disk(self):
        class Junk(backends.Backend):
            name, paid, takes_reference = "junk", False, True

            def generate(self, prompt, reference_bytes):
                return b"not a png"

        real = backends.build
        backends.build = lambda n, c: Junk({}, {})
        try:
            code, out = run(self.root, "--backend", "mock", "--start", "0",
                            "--end", "0", "--execute", "--delay", "0",
                            "--max-retries", "1")
        finally:
            backends.build = real
        self.assertNotEqual(code, 0)
        self.assertIn("FAILED", out)
        self.assertFalse(os.path.exists(os.path.join(self.frames, "000.png")))

    def test_no_partial_file_is_left_behind(self):
        class Junk(backends.Backend):
            name, paid, takes_reference = "junk", False, True

            def generate(self, prompt, reference_bytes):
                return b"x" * 10

        real = backends.build
        backends.build = lambda n, c: Junk({}, {})
        try:
            run(self.root, "--backend", "mock", "--start", "0", "--end", "0",
                "--execute", "--delay", "0", "--max-retries", "0")
        finally:
            backends.build = real
        self.assertEqual(
            [f for f in os.listdir(self.frames) if f.endswith(".part")], [])


class ReferenceImage(Base):
    def test_missing_reference_stops_the_run(self):
        os.remove(os.path.join(self.root, "references", "character_ref_body.png"))
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "0")
        self.assertNotEqual(code, 0)
        self.assertIn("character reference not found", out)

    def test_a_backend_that_cannot_take_a_reference_is_refused(self):
        cfg = self.config()
        del cfg["backends"]["fal"]["request"]["reference_path"]
        self.write_config(cfg)
        code, out = run(self.root, "--backend", "fal", "--start", "0", "--end", "0")
        self.assertNotEqual(code, 0)
        self.assertIn("character drift", out)

    def test_no_reference_is_possible_but_flagged(self):
        code, out = run(self.root, "--backend", "mock", "--start", "0", "--end", "0",
                        "--no-reference")
        self.assertEqual(code, 0)
        self.assertIn("DRIFT RISK", out)


class Retry(Base):
    def test_backoff_grows_and_stays_capped(self):
        for attempt in range(1, 9):
            for _ in range(40):
                d = backends.backoff_delay(attempt, 2.0, 60.0)
                self.assertGreaterEqual(d, 0.0)
                self.assertLessEqual(d, 60.0)

    def test_a_retryable_failure_is_retried_then_succeeds(self):
        state = {"n": 0}
        good = backends.MockBackend({}, {}).generate("x", None)

        class Flaky(backends.Backend):
            name, paid, takes_reference = "flaky", False, True

            def generate(self, prompt, reference_bytes):
                state["n"] += 1
                if state["n"] < 3:
                    raise backends.BackendError("503", retryable=True)
                return good

        real = backends.build
        backends.build = lambda n, c: Flaky({}, {})
        try:
            cfg = self.config()
            cfg["limits"]["backoff_base_seconds"] = 0.001
            cfg["limits"]["backoff_max_seconds"] = 0.002
            self.write_config(cfg)
            code, out = run(self.root, "--backend", "mock", "--start", "0",
                            "--end", "0", "--execute", "--delay", "0")
        finally:
            backends.build = real
        self.assertEqual(code, 0)
        self.assertEqual(state["n"], 3)

    def test_a_non_retryable_failure_stops_immediately(self):
        state = {"n": 0}

        class Hard(backends.Backend):
            name, paid, takes_reference = "hard", False, True

            def generate(self, prompt, reference_bytes):
                state["n"] += 1
                raise backends.BackendError("bad request", retryable=False)

        real = backends.build
        backends.build = lambda n, c: Hard({}, {})
        try:
            code, _ = run(self.root, "--backend", "mock", "--start", "0",
                          "--end", "0", "--execute", "--delay", "0",
                          "--max-retries", "5")
        finally:
            backends.build = real
        self.assertNotEqual(code, 0)
        self.assertEqual(state["n"], 1, "a 4xx should not be retried five times")


class ErrorClassification(Base):
    """Retrying is only worth doing when it could possibly work."""

    def test_a_proxy_connect_refusal_is_not_retryable(self):
        """The exact failure seen against fal.run from a restricted container."""
        ok, msg = backends.classify_urlerror(
            "Tunnel connection failed: 403 Forbidden")
        self.assertFalse(ok)
        self.assertIn("egress policy", msg)
        self.assertNotIn("bad key", msg.split("not a bad key")[0])

    def test_a_proxy_429_is_still_retryable(self):
        ok, _ = backends.classify_urlerror("Tunnel connection failed: 429 Too Many")
        self.assertTrue(ok)

    def test_a_proxy_502_is_still_retryable(self):
        ok, _ = backends.classify_urlerror("Tunnel connection failed: 502 Bad Gateway")
        self.assertTrue(ok)

    def test_a_tls_failure_is_not_retryable(self):
        ok, msg = backends.classify_urlerror(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        self.assertFalse(ok)
        self.assertIn("trust store", msg)

    def test_an_unresolvable_host_is_not_retryable(self):
        ok, msg = backends.classify_urlerror(
            "[Errno -2] Name or service not known")
        self.assertFalse(ok)
        self.assertIn("generation.json", msg)

    def test_a_timeout_is_still_retryable(self):
        self.assertTrue(backends.classify_urlerror("timed out")[0])

    def test_a_reset_is_still_retryable(self):
        self.assertTrue(
            backends.classify_urlerror("[Errno 104] Connection reset by peer")[0])

    def test_an_unrecognised_fault_defaults_to_retryable(self):
        """A blip is likelier than a permanent condition; do not fail fast on
        something we have not reasoned about."""
        self.assertTrue(backends.classify_urlerror("something entirely new")[0])

    def test_a_non_retryable_transport_error_is_attempted_once(self):
        state = {"n": 0}

        class Blocked(backends.Backend):
            name, paid, takes_reference = "blocked", False, True

            def generate(self, prompt, reference_bytes):
                state["n"] += 1
                raise backends.BackendError(
                    "proxy refused", retryable=False)

        real = backends.build
        backends.build = lambda n, c: Blocked({}, {})
        try:
            code, out = run(self.root, "--backend", "mock", "--start", "0",
                            "--end", "0", "--execute", "--delay", "0",
                            "--max-retries", "5")
        finally:
            backends.build = real
        self.assertNotEqual(code, 0)
        self.assertEqual(state["n"], 1, "a policy denial must not be retried")
        self.assertIn("not retryable", out)


class AbortAfterConsecutiveFailures(Base):
    def test_a_systemic_fault_stops_the_run_early(self):
        state = {"n": 0}

        class AlwaysFails(backends.Backend):
            name, paid, takes_reference = "dead", False, True

            def generate(self, prompt, reference_bytes):
                state["n"] += 1
                raise backends.BackendError("blocked", retryable=False)

        real = backends.build
        backends.build = lambda n, c: AlwaysFails({}, {})
        try:
            code, out = run(self.root, "--backend", "mock", "--start", "0",
                            "--end", "50", "--execute", "--delay", "0")
        finally:
            backends.build = real
        self.assertNotEqual(code, 0)
        self.assertIn("ABORTED", out)
        self.assertEqual(state["n"], 3, "should stop after 3, not run all 51")

    def test_isolated_failures_do_not_abort(self):
        good = backends.MockBackend({}, {}).generate("x", None)
        state = {"n": 0}

        class EveryOther(backends.Backend):
            name, paid, takes_reference = "flappy", False, True

            def generate(self, prompt, reference_bytes):
                state["n"] += 1
                if state["n"] % 2 == 0:
                    raise backends.BackendError("nope", retryable=False)
                return good

        real = backends.build
        backends.build = lambda n, c: EveryOther({}, {})
        try:
            code, out = run(self.root, "--backend", "mock", "--start", "0",
                            "--end", "5", "--execute", "--delay", "0")
        finally:
            backends.build = real
        self.assertNotIn("ABORTED", out)

    def test_abort_can_be_disabled(self):
        class AlwaysFails(backends.Backend):
            name, paid, takes_reference = "dead", False, True

            def generate(self, prompt, reference_bytes):
                raise backends.BackendError("blocked", retryable=False)

        real = backends.build
        backends.build = lambda n, c: AlwaysFails({}, {})
        try:
            code, out = run(self.root, "--backend", "mock", "--start", "0",
                            "--end", "4", "--execute", "--delay", "0",
                            "--abort-after", "0")
        finally:
            backends.build = real
        self.assertNotIn("ABORTED", out)
        self.assertIn("failed 5", out)


class Preflight(Base):
    """Every paid backend must fail with a message naming the fix."""

    def test_http_backend_without_its_key_says_which_variable(self):
        cfg = self.config()["backends"]["fal"]
        b = backends.HTTPBackend("fal", cfg, {})
        os.environ.pop("FAL_KEY", None)
        with self.assertRaises(SystemExit) as cm:
            b.preflight()
        self.assertIn("FAL_KEY", str(cm.exception))

    def test_replicate_without_a_version_id_is_refused(self):
        cfg = self.config()["backends"]["replicate"]
        b = backends.HTTPBackend("replicate", cfg, {})
        os.environ["REPLICATE_API_TOKEN"] = "test-placeholder"
        try:
            with self.assertRaises(SystemExit) as cm:
                b.preflight()
        finally:
            os.environ.pop("REPLICATE_API_TOKEN", None)
        self.assertIn("version", str(cm.exception).lower())

    def test_flow_without_a_profile_is_refused(self):
        cfg = self.config()["backends"]["flow"]
        b = backends.PlaywrightBackend(cfg, {})
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            self.skipTest("Playwright not installed; preflight exits earlier")
        with self.assertRaises(SystemExit) as cm:
            b.preflight()
        self.assertIn("profile_dir", str(cm.exception))


class RequestShaping(Base):
    """The config-driven body builder, without any network."""

    def test_prompt_and_reference_land_where_config_says(self):
        cfg = self.config()["backends"]["gemini"]
        b = backends.HTTPBackend("gemini", cfg, {})
        body = json.loads(b._body("PROMPT", b"REFBYTES"))
        self.assertEqual(body["instances"][0]["prompt"], "PROMPT")
        self.assertIn("bytesBase64Encoded", body["instances"][0]["image"])
        self.assertEqual(body["parameters"]["sampleCount"], 1)

    def test_data_uri_encoding_is_honoured(self):
        cfg = self.config()["backends"]["fal"]
        b = backends.HTTPBackend("fal", cfg, {})
        body = json.loads(b._body("P", b"REF"))
        self.assertTrue(body["image_url"].startswith("data:image/png;base64,"))

    def test_replicate_sends_the_version(self):
        cfg = dict(self.config()["backends"]["replicate"])
        cfg["model"] = "a" * 64
        b = backends.HTTPBackend("replicate", cfg, {})
        body = json.loads(b._body("P", b"REF"))
        self.assertEqual(body["version"], "a" * 64)
        self.assertEqual(body["input"]["prompt"], "P")

    def test_dig_reads_nested_lists_and_dicts(self):
        self.assertEqual(backends.dig({"a": [{"b": "x"}]}, "a.0.b"), "x")
        with self.assertRaises(backends.BackendError):
            backends.dig({"a": []}, "a.0.b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
