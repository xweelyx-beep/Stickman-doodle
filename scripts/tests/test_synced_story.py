#!/usr/bin/env python3
"""Tests for the per-line synchronised assembler.

The invariant: a frame's duration is the measured duration of its narration
line, so picture and voice cannot drift apart.

    python3 scripts/tests/test_synced_story.py
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "core"))

import assemble_synced_story as ass  # noqa: E402
import assemble_video as av  # noqa: E402
import timeline as tl  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
HAVE_ESPEAK = bool(shutil.which("espeak-ng"))


def call(root, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        try:
            code = ass.main(["--root", root] + list(argv))
        except SystemExit as e:
            return (e.code if isinstance(e.code, int) else 1), buf.getvalue() + str(e)
    return code, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "r")
        shutil.copytree(ROOT, self.root,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "output"))
        tl.paths._cache.pop(self.root, None)
        self.frames = os.path.join(self.root, "output", "frames")
        os.makedirs(self.frames, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def script_file(self):
        return os.path.join(self.root, "audio", "voiceover",
                            "storyboard_script_157.json")

    def load(self):
        with open(self.script_file(), encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, rows):
        with open(self.script_file(), "w", encoding="utf-8") as fh:
            json.dump(rows, fh)

    def make_frames(self, n, w=320, h=180):
        if not HAVE_FFMPEG:
            self.skipTest("ffmpeg absent")
        for i in range(n):
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "color=c=0x%06x:size=%dx%d" % (0x223344 + i * 8192, w, h),
                 "-frames:v", "1", os.path.join(self.frames, "%03d.png" % i)],
                check=True)


class TheNarrationScript(Base):
    def test_it_is_committed_and_has_one_line_per_frame(self):
        rows = self.load()
        self.assertEqual(len(rows), 157)
        self.assertEqual(len(tl.build(self.root)), 157)

    def test_frames_are_numbered_in_order_from_zero(self):
        self.assertEqual([r["frame"] for r in self.load()], list(range(157)))

    def test_every_line_has_text(self):
        for r in self.load():
            self.assertTrue(r["text"].strip(), "frame %d is empty" % r["frame"])

    def test_timestamps_match_the_prompt_file(self):
        shots = tl.build(self.root)
        for row, shot in zip(self.load(), shots):
            self.assertEqual(row["timestamp"], shot["timestamp"])

    def test_a_wrong_line_count_is_refused(self):
        rows = self.load()
        self.save(rows[:-1])
        code, out = call(self.root, "--dry-run")
        self.assertNotEqual(code, 0)
        self.assertIn("one to one", out)

    def test_out_of_order_frames_are_refused(self):
        rows = self.load()
        rows[5], rows[6] = rows[6], rows[5]
        self.save(rows)
        code, out = call(self.root, "--dry-run")
        self.assertNotEqual(code, 0)
        self.assertIn("frame order", out)

    def test_an_empty_line_is_refused(self):
        rows = self.load()
        rows[10]["text"] = "   "
        self.save(rows)
        code, out = call(self.root, "--dry-run")
        self.assertNotEqual(code, 0)
        self.assertIn("no text", out)

    def test_a_missing_script_names_the_expected_shape(self):
        os.remove(self.script_file())
        code, out = call(self.root, "--dry-run")
        self.assertNotEqual(code, 0)
        self.assertIn("storyboard_script_157.json", out)
        self.assertIn('"frame"', out)

    def test_the_closer_does_not_borrow_a_sibling_channel_sign_off(self):
        """docs/channel-bible.md section 7: the sign-off must be this channel's."""
        last = self.load()[-1]["text"].lower()
        self.assertNotIn("you're welcome", last)
        self.assertNotIn("youre welcome", last)


class DurationsComeFromAudio(Base):
    @unittest.skipUnless(HAVE_ESPEAK and HAVE_FFMPEG, "needs espeak-ng and ffmpeg")
    def test_a_longer_line_yields_a_longer_clip(self):
        rows = self.load()
        rows[0]["text"] = "Short."
        rows[1]["text"] = ("A considerably longer sentence, with several clauses "
                           "in it, which must take more time to say aloud.")
        self.save(rows)
        self.make_frames(2)
        code, out = call(self.root, "--engine", "espeak", "--start", "0", "--end", "1",
                         "--preset", "ultrafast", "--crf", "40")
        self.assertEqual(code, 0, out)
        lines = os.path.join(self.root, "output", "voice_lines")
        d0 = av.probe_duration(os.path.join(lines, "000.m4a"))
        d1 = av.probe_duration(os.path.join(lines, "001.m4a"))
        self.assertLess(d0, d1)

    @unittest.skipUnless(HAVE_ESPEAK and HAVE_FFMPEG, "needs espeak-ng and ffmpeg")
    def test_each_frame_matches_its_line_duration(self):
        self.make_frames(3)
        code, out = call(self.root, "--engine", "espeak", "--start", "0", "--end", "2",
                         "--preset", "ultrafast", "--crf", "40")
        self.assertEqual(code, 0, out)
        lines = os.path.join(self.root, "output", "voice_lines")
        shots = os.path.join(self.root, "output", "shots_synced")
        for i in range(3):
            a = av.probe_duration(os.path.join(lines, "%03d.m4a" % i))
            v = av.probe_duration(os.path.join(shots, "%03d.mp4" % i))
            self.assertAlmostEqual(a, v, delta=0.08,
                                   msg="frame %d: audio %.3f vs video %.3f" % (i, a, v))

    @unittest.skipUnless(HAVE_ESPEAK and HAVE_FFMPEG, "needs espeak-ng and ffmpeg")
    def test_the_finished_file_has_matching_streams(self):
        self.make_frames(3)
        out_path = os.path.join(self.root, "output", "t.mp4")
        code, out = call(self.root, "--engine", "espeak", "--start", "0", "--end", "2",
                         "--preset", "ultrafast", "--crf", "40", "--out", out_path)
        self.assertEqual(code, 0, out)
        self.assertEqual(av.probe_size(out_path), (3840, 2160))
        self.assertIn("drift", out)

    @unittest.skipUnless(HAVE_ESPEAK and HAVE_FFMPEG, "needs espeak-ng and ffmpeg")
    def test_concatenated_audio_equals_the_sum_of_its_parts(self):
        """Zero silence between lines: the total must not exceed the sum."""
        self.make_frames(3)
        code, out = call(self.root, "--engine", "espeak", "--start", "0", "--end", "2",
                         "--preset", "ultrafast", "--crf", "40")
        self.assertEqual(code, 0, out)
        lines = os.path.join(self.root, "output", "voice_lines")
        parts = sum(av.probe_duration(os.path.join(lines, "%03d.m4a" % i))
                    for i in range(3))
        whole = av.probe_duration(os.path.join(self.root, "output",
                                               "narration_full.m4a"))
        self.assertAlmostEqual(parts, whole, delta=0.15)


class Windowing(Base):
    def test_a_bad_window_is_refused(self):
        code, _ = call(self.root, "--start", "10", "--end", "2", "--dry-run")
        self.assertNotEqual(code, 0)

    def test_dry_run_writes_nothing(self):
        code, out = call(self.root, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        self.assertFalse(os.path.exists(
            os.path.join(self.root, "output", "voice_lines")))

    def test_the_default_engine_is_the_one_specified(self):
        code, out = call(self.root, "--dry-run")
        self.assertIn("engine     : edge", out)
        self.assertIn("en-US-AvaNeural", out)
        self.assertIn("+5%", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
