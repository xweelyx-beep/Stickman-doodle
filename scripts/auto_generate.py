#!/usr/bin/env python3
"""End-to-end automated rendering of all 157 frames.

    python3 scripts/auto_generate.py --backend mock --execute
    python3 scripts/auto_generate.py --backend fal --start 0 --end 156 --delay 3

Submits every frame to a generation backend, downloads the result, verifies it,
and records progress — resuming across runs, retrying with exponential backoff,
and rate-limiting between requests.

WHAT THIS CHANGES
-----------------
`scripts/generate_frames.py` hands work to a human because
`scripts/config/models.json` put Stickman art on `route: "manual"` and declared
`credit_safeguard.pipeline_submits: false`. This script submits. The operator
authorised that on 2026-08-29; models.json now records the change and names who
made it, rather than being quietly contradicted by code sitting next to it.

Two safeguards from that config are kept, because they are what the config was
protecting rather than incidental to it:

  * The tool is never this script's choice. `--backend` is required and
    `default_backend` in generation.json is deliberately null.
  * Nothing paid runs without an explicit go-ahead. The default is a dry run;
    a paid backend additionally needs `--execute` *and* `--approve-spend`.

The concurrency cap in references/style-rules.md governs human review batches,
not machine submission, but the spirit of it survives as `--delay`: requests are
paced rather than fired in parallel, so a bad run costs a few frames, not 157.

Stdlib only, except Playwright which the `flow` backend imports lazily.
"""

import argparse
import datetime
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "core"))

import backends  # noqa: E402
import generate_frames as gfr  # noqa: E402
import paths  # noqa: E402

CONFIG = "generation.json"


def utcnow():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def load_config(root):
    path = paths.config_path(CONFIG, root)
    if not os.path.isfile(path):
        raise SystemExit("error: %s not found" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def verify_bytes(data):
    """Same contract as generate_frames.verify, applied before anything is saved.

    Returns None when the bytes are a usable render, else why they are not.
    """
    if len(data) < gfr.MIN_BYTES:
        return "only %d bytes (floor is %d) — probably a failed render" % (
            len(data), gfr.MIN_BYTES)
    if data[:8] != gfr.PNG_MAGIC:
        return "not a PNG (bad magic bytes)"
    if data[12:16] != b"IHDR":
        return "PNG header is malformed (no IHDR)"
    return None


def cost_line(config, backend_name, count):
    """Image count always; a money figure only when a sourced rate exists."""
    if not (config.get("backends") or {}).get(backend_name, {}).get("paid", True):
        return "%d image(s). Free backend — nothing is billed." % count
    rates = config.get("rates") or {}
    rate = (rates.get("usd_per_image") or {}).get(backend_name)
    if rate is None or not rates.get("source"):
        return ("%d image(s). No cost estimate: scripts/config/generation.json "
                "carries no sourced rate for %r. Fill rates.usd_per_image.%s "
                "with a source and a date, or price it yourself before "
                "approving." % (count, backend_name, backend_name))
    return ("%d image(s) at $%.4f = $%.2f  (rate from %s, checked %s)"
            % (count, rate, count * rate, rates["source"], rates["checked_utc"]))


def render_one(backend, frame, ref_bytes, out_path, args, limits):
    """One frame, with retries. Returns (ok, detail)."""
    base = limits.get("backoff_base_seconds", 2.0)
    cap = limits.get("backoff_max_seconds", 60.0)
    prompt = frame["prompt"].split("] ", 1)[1]
    last = "no attempt made"
    for attempt in range(args.max_retries + 1):
        if attempt:
            wait = backends.backoff_delay(attempt, base, cap)
            print("      retry %d/%d in %.1fs — %s"
                  % (attempt, args.max_retries, wait, last))
            time.sleep(wait)
        try:
            data = backend.generate(prompt, ref_bytes)
        except backends.BackendError as e:
            last = str(e)
            if not e.retryable:
                return False, last
            if e.retry_after:
                print("      provider asked for %.0fs" % e.retry_after)
                time.sleep(min(e.retry_after, cap))
            continue
        except Exception as e:                      # a backend bug, not a refusal
            return False, "%s: %s" % (type(e).__name__, e)
        bad = verify_bytes(data)
        if bad:
            last = bad
            continue
        tmp = out_path + ".part"
        with open(tmp, "wb") as fh:
            fh.write(data)
        os.replace(tmp, out_path)
        return True, "%d bytes" % len(data)
    return False, "gave up after %d attempts — %s" % (args.max_retries + 1, last)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="scripts/auto_generate.py",
        description="Automated end-to-end rendering of the 157-frame set.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Start with --backend mock to exercise the harness for free.")
    ap.add_argument("--backend", help="which engine to submit to (required). "
                                      "No default: the tool choice is yours.")
    ap.add_argument("--start", type=int, default=0, help="first frame (default 0)")
    ap.add_argument("--end", type=int, default=None, help="last frame, inclusive")
    ap.add_argument("--delay", type=float, default=None,
                    help="seconds between requests (default from config)")
    ap.add_argument("--max-retries", type=int, default=None,
                    help="retries per frame (default from config)")
    ap.add_argument("--execute", action="store_true",
                    help="actually submit; without it this is a dry run")
    ap.add_argument("--approve-spend", metavar="N", type=int, default=None,
                    help="acknowledge submitting N images to a paid backend")
    ap.add_argument("--regenerate", action="store_true",
                    help="re-render frames that already pass verification")
    ap.add_argument("--no-reference", action="store_true",
                    help="run without the mascot reference (invites drift)")
    ap.add_argument("--list-backends", action="store_true")
    ap.add_argument("--root")
    args = ap.parse_args(argv)

    root = args.root or paths.find_root()
    config = load_config(root)
    limits = config.get("limits") or {}

    if args.list_backends:
        for name, cfg in sorted((config.get("backends") or {}).items()):
            print("%-10s %-11s %s" % (name, cfg.get("kind"),
                                      "PAID" if cfg.get("paid") else "free"))
        return 0

    if not args.backend:
        args.backend = config.get("default_backend")
    if not args.backend:
        ap.error("--backend is required. generation.json sets no default on "
                 "purpose — picking a paid tool is the operator's call, not "
                 "this script's. See --list-backends.")

    if args.delay is None:
        args.delay = limits.get("delay_seconds_default", 3.0)
    if args.max_retries is None:
        args.max_retries = limits.get("max_retries_default", 5)
    if args.delay < 0:
        ap.error("--delay cannot be negative")

    frames = gfr.load_frames(root)
    end = len(frames) - 1 if args.end is None else args.end
    if not (0 <= args.start <= end <= len(frames) - 1):
        ap.error("--start/--end must satisfy 0 <= start <= end <= %d"
                 % (len(frames) - 1))
    window = frames[args.start:end + 1]

    out_dir = gfr.frames_dir(root, create=True)
    ref_bytes = None
    if not args.no_reference:
        ref = gfr.load_reference(root)             # exits if missing
        with open(os.path.join(root, ref["path"]), "rb") as fh:
            ref_bytes = fh.read()

    backend = backends.build(args.backend, config)
    if backend.paid and not backend.takes_reference and not args.no_reference:
        raise SystemExit(
            "error: backend %r has no reference_path configured, so it cannot "
            "condition on the mascot.\n"
            "  Generating 157 frames without it is how character drift enters a "
            "set.\n  Configure request.reference_path in generation.json, or pass "
            "--no-reference deliberately." % args.backend)

    todo = []
    for f in window:
        path = os.path.join(out_dir, f["filename"])
        if not args.regenerate and os.path.isfile(path):
            with open(path, "rb") as fh:
                if verify_bytes(fh.read()) is None:
                    continue                        # already good — resume past it
        todo.append(f)

    print("backend    : %s%s" % (args.backend, "  (PAID)" if backend.paid else "  (free)"))
    print("window     : frames %03d-%03d  [%s]-[%s]"
          % (args.start, end, window[0]["timestamp"], window[-1]["timestamp"]))
    print("to render  : %d of %d  (%d already done)"
          % (len(todo), len(window), len(window) - len(todo)))
    print("reference  : %s" % ("none — DRIFT RISK" if args.no_reference
                               else gfr.load_reference(root)["path"]))
    print("pacing     : %.1fs between requests, up to %d retries, "
          "exponential backoff with jitter" % (args.delay, args.max_retries))
    print("output     : %s" % os.path.relpath(out_dir, root))
    print("cost       : %s" % cost_line(config, args.backend, len(todo)))
    print()

    if not todo:
        print("nothing to do — every frame in the window already verifies.")
        return 0

    if not args.execute:
        print("DRY RUN. Nothing was submitted and nothing was written.")
        print("Re-run with --execute to submit%s."
              % (" --approve-spend %d" % len(todo) if backend.paid else ""))
        return 0

    if backend.paid:
        if args.approve_spend is None:
            raise SystemExit(
                "error: %r is a paid backend. Re-run with --approve-spend %d to "
                "acknowledge submitting that many images.\n"
                "  Price it first: %s"
                % (args.backend, len(todo), cost_line(config, args.backend, len(todo))))
        if args.approve_spend != len(todo):
            raise SystemExit(
                "error: --approve-spend %d does not match the %d image(s) this "
                "run would submit. Re-check the window and approve the real "
                "number." % (args.approve_spend, len(todo)))

    backend.preflight()                             # exits with a fixable message
    print()

    done = failed = 0
    started = time.time()
    try:
        for i, f in enumerate(todo):
            path = os.path.join(out_dir, f["filename"])
            print("  [%3d/%3d] %s  [%s]"
                  % (i + 1, len(todo), f["filename"], f["timestamp"]), flush=True)
            ok, detail = render_one(backend, f, ref_bytes, path, args, limits)
            if ok:
                done += 1
                print("      ok — %s" % detail)
            else:
                failed += 1
                print("      FAILED — %s" % detail)
            if i + 1 < len(todo) and args.delay:
                time.sleep(args.delay)
    except KeyboardInterrupt:
        print("\ninterrupted. %d rendered, %d failed. Re-run to resume — frames "
              "that verify are skipped." % (done, failed))
        return 130
    finally:
        backend.close()

    mins = (time.time() - started) / 60.0
    print()
    print("rendered %d, failed %d, in %.1f min" % (done, failed, mins))
    print("verify the whole set:  python3 scripts/generate_frames.py verify")
    if failed:
        print("re-run to retry the failures; frames that verify are skipped.")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            os._exit(0)
