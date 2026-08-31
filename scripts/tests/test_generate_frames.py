#!/usr/bin/env python3
"""Tests for the frame queue driver.

The invariant these exist to protect: this script never submits anything and
never exceeds the canon's concurrency cap.

    python3 scripts/tests/test_generate_frames.py
"""

import io
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "core"))

import generate_frames as gf  # noqa: E402


def fake_png(path, w=1348, h=752, pad=8192):
    """A structurally valid PNG, large enough to pass the size floor."""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    body = (gf.PNG_MAGIC + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"\x00" * pad)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(body + b"\x00" * max(0, gf.MIN_BYTES - len(body)))


def run(root, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            code = gf.main(["--root", root] + list(argv))
        except SystemExit as e:
            return (e.code if isinstance(e.code, int) else 1), buf.getvalue() + str(e)
    return code, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "r")
        shutil.copytree(ROOT, self.root,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "output"))
        gf.paths._cache.pop(self.root, None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def frames_dir(self):
        return os.path.join(self.root, "output", "frames")

    def manifest(self):
        with open(os.path.join(self.frames_dir(), "manifest.json")) as fh:
            return json.load(fh)


class NeverSubmits(Base):
    """The invariant that matters most."""

    def test_source_has_no_network_surface(self):
        with open(os.path.join(ROOT, "scripts", "generate_frames.py")) as fh:
            src = fh.read()
        for bad in ("import socket", "import urllib", "import requests",
                    "urlopen", "http://", "https://"):
            self.assertNotIn(bad, src, f"network surface: {bad}")

    def test_batch_size_above_the_canon_cap_is_refused(self):
        code, out = run(self.root, "--batch-size", "4", "plan")
        self.assertNotEqual(code, 0)
        self.assertIn("concurrency cap", out)

    def test_batch_size_at_the_cap_is_allowed(self):
        code, _ = run(self.root, "--batch-size", "3", "plan")
        self.assertEqual(code, 0)


class Parsing(Base):
    def test_reads_all_157_frames_in_order(self):
        frames = gf.load_frames(self.root)
        self.assertEqual(len(frames), 157)
        self.assertEqual(frames[0]["timestamp"], "00:00")
        self.assertEqual(frames[-1]["timestamp"], "11:22")
        self.assertEqual(frames[0]["filename"], "000.png")
        self.assertEqual(frames[-1]["filename"], "156.png")

    def test_character_presence_matches_the_changelog(self):
        frames = gf.load_frames(self.root)
        self.assertEqual(sum(1 for f in frames if f["character"]), 75)

    def test_malformed_prompt_file_is_refused(self):
        p = os.path.join(self.root, "prompts",
                         "image_prompts_why_you_check_your_phone_v2.txt")
        with open(p, "a") as fh:
            fh.write("\n\nno timestamp on this frame\n")
        with self.assertRaises(SystemExit):
            gf.load_frames(self.root)

    def test_missing_reference_stops_the_queue(self):
        os.remove(os.path.join(self.root, "references", "character_ref_body.png"))
        code, out = run(self.root, "plan")
        self.assertNotEqual(code, 0)
        self.assertIn("character reference not found", out)


class Queue(Base):
    def test_next_issues_exactly_three_then_halts(self):
        code, out = run(self.root, "next")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("--- frame"), 3)
        self.assertIn("HALT", out)
        issued = [e for e in self.manifest()["frames"] if e["state"] == "issued"]
        self.assertEqual(len(issued), 3)

    def test_second_next_refuses_while_frames_are_outstanding(self):
        run(self.root, "next")
        code, out = run(self.root, "next")
        self.assertEqual(code, 1)
        self.assertIn("still out", out)

    def test_force_overrides_the_halt(self):
        run(self.root, "next")
        code, out = run(self.root, "next", "--force")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("--- frame"), 3)

    def test_arrivals_are_verified_and_the_queue_resumes(self):
        run(self.root, "next")
        for i in range(3):
            fake_png(os.path.join(self.frames_dir(), "%03d.png" % i))
        code, _ = run(self.root, "verify")
        self.assertEqual(code, 0)
        self.assertEqual(sum(1 for e in self.manifest()["frames"]
                             if e["state"] == "done"), 3)
        _, out = run(self.root, "next")
        self.assertIn("frame 003", out)
        self.assertNotIn("frame 000", out)

    def test_state_survives_a_restart(self):
        run(self.root, "next")
        for i in range(3):
            fake_png(os.path.join(self.frames_dir(), "%03d.png" % i))
        run(self.root, "verify")
        code, out = run(self.root, "status")
        self.assertEqual(code, 0)
        self.assertIn("3/157", out)


class Verification(Base):
    def test_a_non_png_is_rejected(self):
        run(self.root, "next")
        with open(os.path.join(self.frames_dir(), "000.png"), "w") as fh:
            fh.write("nope")
        code, out = run(self.root, "verify")
        self.assertEqual(code, 1)
        self.assertIn("not a valid PNG", out)

    def test_a_truncated_render_is_rejected(self):
        run(self.root, "next")
        fake_png(os.path.join(self.frames_dir(), "000.png"), pad=1)
        p = os.path.join(self.frames_dir(), "000.png")
        with open(p, "r+b") as fh:
            fh.truncate(64)
        code, out = run(self.root, "verify")
        self.assertEqual(code, 1)

    def test_a_vanished_frame_is_demoted_not_silently_kept(self):
        run(self.root, "next")
        for i in range(3):
            fake_png(os.path.join(self.frames_dir(), "%03d.png" % i))
        run(self.root, "verify")
        os.remove(os.path.join(self.frames_dir(), "001.png"))
        code, out = run(self.root, "verify")
        self.assertEqual(code, 1)
        self.assertIn("marked done but is gone", out)
        states = {e["filename"]: e["state"] for e in self.manifest()["frames"]}
        self.assertEqual(states["001.png"], "issued")

    def test_dimensions_are_recorded(self):
        run(self.root, "next")
        fake_png(os.path.join(self.frames_dir(), "000.png"), w=1920, h=1080)
        run(self.root, "verify")
        e = self.manifest()["frames"][0]
        self.assertEqual((e["width"], e["height"]), (1920, 1080))

    def test_prompt_file_changing_under_a_live_queue_is_caught(self):
        run(self.root, "next")
        p = os.path.join(self.root, "prompts",
                         "image_prompts_why_you_check_your_phone_v2.txt")
        with open(p, encoding="utf-8") as fh:
            text = fh.read().strip().split("\n\n")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n\n".join(text[:-1]) + "\n")
        code, out = run(self.root, "verify")
        self.assertNotEqual(code, 0)
        self.assertIn("manifest has", out)


class Reset(Base):
    def test_reset_needs_confirmation(self):
        run(self.root, "next")
        code, out = run(self.root, "reset")
        self.assertNotEqual(code, 0)
        self.assertIn("--yes", out)

    def test_reset_clears_state_but_keeps_renders(self):
        run(self.root, "next")
        fake_png(os.path.join(self.frames_dir(), "000.png"))
        run(self.root, "verify")
        code, _ = run(self.root, "reset", "--yes")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists(os.path.join(self.frames_dir(), "manifest.json")))
        self.assertTrue(os.path.exists(os.path.join(self.frames_dir(), "000.png")))

    def test_reset_then_verify_rebuilds_progress_from_disk(self):
        run(self.root, "next")
        for i in range(3):
            fake_png(os.path.join(self.frames_dir(), "%03d.png" % i))
        run(self.root, "verify")
        run(self.root, "reset", "--yes")
        code, out = run(self.root, "status")
        self.assertEqual(code, 0)
        self.assertIn("3/157", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
