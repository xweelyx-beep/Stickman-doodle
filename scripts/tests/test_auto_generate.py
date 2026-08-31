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


class Validation(Base):
    def test_verify_bytes_matches_the_shared_contract(self):
        self.assertIsNotNone(ag.verify_bytes(b"tiny"))
        self.assertIn("not a PNG", ag.verify_bytes(b"x" * (gfr.MIN_BYTES + 1)))
        good = backends.MockBackend({}, {}).generate("x", None)
        self.assertIsNone(ag.verify_bytes(good))

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
