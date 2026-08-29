#!/usr/bin/env python3
"""Regression tests for the standalone layout.

The Business test suite could not travel: it asserted a three-channel tree with
canon in .claude/rules/ and config in automation/. These replace it, and they
exist to catch one specific regression — a path quietly resolving back into a
layout this repository does not have.

    python3 scripts/tests/test_standalone.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CORE = os.path.join(ROOT, "scripts", "core")
RUN = os.path.join(ROOT, "scripts", "run.py")
sys.path.insert(0, CORE)

import paths          # noqa: E402
import canon          # noqa: E402
import scheduler      # noqa: E402


def run(*args, **kw):
    return subprocess.run([sys.executable, RUN] + list(args),
                          capture_output=True, text=True, cwd=kw.get("cwd", ROOT))


class LayoutIsDeclaredNotHardCoded(unittest.TestCase):
    def test_every_layout_key_resolves_to_something_that_exists(self):
        m = paths.manifest(ROOT)
        for key, rel in m["layout"].items():
            if key in ("episodes", "memory"):
                continue  # created on demand
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)),
                            f"layout.{key} -> {rel} does not exist")

    def test_moving_a_directory_needs_no_python_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(ROOT, os.path.join(tmp, "r"),
                            ignore=shutil.ignore_patterns(".git", "__pycache__"))
            r = os.path.join(tmp, "r")
            os.makedirs(os.path.join(r, "canon"), exist_ok=True)
            shutil.move(os.path.join(r, "docs", "channel-bible.md"),
                        os.path.join(r, "canon", "bible.md"))
            mp = os.path.join(r, "channel.json")
            with open(mp, encoding="utf-8") as fh:
                m = json.load(fh)
            m["layout"]["canon"] = "canon/bible.md"
            with open(mp, "w", encoding="utf-8") as fh:
                json.dump(m, fh, indent=2)
            paths._cache.pop(r, None)
            self.assertEqual(paths.canon_path("stickman", r),
                             os.path.join(r, "canon", "bible.md"))
            self.assertTrue(canon.load_canon("stickman", r).title)


class RootResolution(unittest.TestCase):
    def test_found_from_any_working_directory(self):
        for cwd in (ROOT, os.path.join(ROOT, "scripts", "config"), "/", "/tmp"):
            r = subprocess.run([sys.executable, os.path.join(CORE, "paths.py")],
                               capture_output=True, text=True, cwd=cwd)
            self.assertEqual(r.returncode, 0, f"cwd={cwd}: {r.stderr}")
            self.assertIn(f"root     : {ROOT}", r.stdout, f"cwd={cwd}")

    def test_env_var_overrides(self):
        os.environ["STICKMAN_REPO_ROOT"] = ROOT
        try:
            self.assertEqual(paths.find_root(), ROOT)
        finally:
            del os.environ["STICKMAN_REPO_ROOT"]

    def test_env_var_pointing_at_a_non_checkout_fails_loudly(self):
        os.environ["STICKMAN_REPO_ROOT"] = "/etc"
        try:
            with self.assertRaises(SystemExit):
                paths.find_root()
        finally:
            del os.environ["STICKMAN_REPO_ROOT"]

    def test_outside_a_checkout_raises_rather_than_guessing(self):
        with self.assertRaises(SystemExit) as cm:
            paths.find_root("/etc")
        self.assertIn("channel.json", str(cm.exception))


class NoResidualBusinessCoupling(unittest.TestCase):
    """The regression this suite exists for."""

    FORBIDDEN = (
        os.path.join("automation", "config"),
        os.path.join("automation", "memory"),
        os.path.join(".claude", "rules"),
        os.path.join("channels", "stickman"),
    )

    def _sources(self):
        """Production code only. This test file names the forbidden fragments
        itself, so scanning it would always fail."""
        return [RUN] + [os.path.join(CORE, f) for f in sorted(os.listdir(CORE))
                        if f.endswith(".py")]

    def test_no_module_builds_a_business_path(self):
        for src in self._sources():
            with open(src, encoding="utf-8") as fh:
                body = fh.read()
            if os.path.basename(src) == "paths.py":
                body = body.split('"""', 2)[-1]  # its docstring documents the old tree
            for frag in self.FORBIDDEN:
                self.assertNotIn(frag, body,
                                 f"{os.path.relpath(src, ROOT)} still references {frag}")

    def test_channels_tuple_comes_from_the_manifest(self):
        self.assertEqual(canon.CHANNELS, ("stickman",))

    def test_a_foreign_channel_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            canon.load_canon("lilweid", ROOT)
        self.assertIn("stickman", str(cm.exception))


class BrandGate(unittest.TestCase):
    def test_gate_reads_the_declared_brand_path(self):
        st = scheduler.brand_status(ROOT, "stickman")
        self.assertIsNotNone(st)
        self.assertEqual(st["path"], os.path.join("references", "brand.json"))

    def test_locked_character_asset_really_exists_on_disk(self):
        """The gate must fail on a promise, not pass on one."""
        st = scheduler.brand_status(ROOT, "stickman")
        self.assertNotIn("locked_character", st["missing"],
                         "brand.json points at a mascot file that is not on disk")

    def test_longform_stays_blocked_while_brand_items_are_missing(self):
        payload = scheduler.slots(ROOT, "stickman")
        self.assertTrue(payload.get("blocked"))


class CanonParsesTheBible(unittest.TestCase):
    def setUp(self):
        self.c = canon.load_canon("stickman", ROOT)

    def test_blocked_sections_stay_blocked(self):
        d = self.c.to_dict()
        self.assertIsNone(d["seconds_per_scene"])
        self.assertIsNone(d["voice_lock"])
        self.assertTrue(d["architecture_blocked"])

    def test_it_reads_the_migrated_bible_not_a_rule_file(self):
        self.assertTrue(self.c.path.endswith(os.path.join("docs", "channel-bible.md")))


class PipelineRunsStandalone(unittest.TestCase):
    def test_status_runs_with_no_business_checkout_present(self):
        r = run("status", "--channel", "stickman", cwd="/")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_blocked_canon_refuses_to_generate_by_default(self):
        r = run("init", "--channel", "stickman", "--topic", "t", "--keyword", "k",
                "--runtime", "8:30")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("BLOCKED", r.stderr + r.stdout)

    def test_user_facing_commands_name_this_repo_s_entry_point(self):
        r = run("status", "--channel", "stickman")
        self.assertNotIn("automation/run.py", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
