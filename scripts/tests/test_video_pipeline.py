#!/usr/bin/env python3
"""Tests for the timeline, the assembler and the master runner.

Everything that does not need ffmpeg runs anywhere. The few tests that do
encode are skipped when ffmpeg is absent rather than failing.

    python3 scripts/tests/test_video_pipeline.py
"""

import io
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

import assemble_video as av  # noqa: E402
import build_full_video as bf  # noqa: E402
import timeline as tl  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def call(mod, root, *argv):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        try:
            code = mod.main(["--root", root] + list(argv))
        except SystemExit as e:
            return (e.code if isinstance(e.code, int) else 1), buf.getvalue() + str(e)
    return code, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = os.path.join(self.tmp, "r")
        # "music" and "voiceover" are excluded so the audio-gating tests start
        # from an empty audio/ regardless of what a developer has locally.
        shutil.copytree(ROOT, self.root,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "output",
                                                      "music", "voiceover"))
        tl.paths._cache.pop(self.root, None)
        self.frames = os.path.join(self.root, "output", "frames")
        os.makedirs(self.frames, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def make_frames(self, n, w=3840, h=2160):
        if not HAVE_FFMPEG:
            self.skipTest("ffmpeg absent")
        for i in range(n):
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                 "color=c=0x%06x:size=%dx%d" % (0x112233 + i * 4096, w, h),
                 "-frames:v", "1", os.path.join(self.frames, "%03d.png" % i)],
                check=True)


class Timing(Base):
    """Durations come from the markers, not from an estimate."""

    def test_durations_are_the_gaps_between_markers(self):
        shots = tl.build(self.root)
        self.assertEqual(len(shots), 157)
        self.assertEqual(shots[0]["duration_s"], 3.0)   # 00:00 -> 00:03
        self.assertEqual(shots[1]["duration_s"], 2.0)   # 00:03 -> 00:05

    def test_gaps_sum_to_the_stated_runtime(self):
        shots = tl.build(self.root)
        without_tail = sum(s["duration_s"] for s in shots[:-1])
        self.assertEqual(without_tail, 682.0)           # 11:22 exactly

    def test_the_last_shot_gets_the_tail_and_it_is_reported(self):
        shots = tl.build(self.root, tail_seconds=5.0)
        self.assertEqual(shots[-1]["duration_s"], 5.0)
        self.assertEqual(tl.total_seconds(shots), 687.0)

    def test_a_non_positive_tail_is_refused(self):
        with self.assertRaises(SystemExit):
            tl.build(self.root, tail_seconds=0)

    def test_shots_are_chronological_and_contiguous(self):
        shots = tl.build(self.root)
        t = 0.0
        for s in shots:
            self.assertAlmostEqual(s["start_s"], t, places=3)
            t += s["duration_s"]


class CameraMotion(Base):
    def test_every_shot_has_a_motion_from_the_canon_vocabulary(self):
        for s in tl.build(self.root):
            self.assertIn(s["motion"], tl.MOTIONS)

    def test_no_three_consecutive_shots_share_a_motion(self):
        """references/style-rules.md section 1."""
        self.assertEqual(tl.check_block_rule(tl.build(self.root)), [])

    def test_all_four_motions_are_actually_used(self):
        used = {s["motion"] for s in tl.build(self.root)}
        self.assertEqual(used, set(tl.MOTIONS))

    def test_assignment_is_deterministic(self):
        a = [s["motion"] for s in tl.build(self.root)]
        b = [s["motion"] for s in tl.build(self.root)]
        self.assertEqual(a, b)


class DynamicSelection(Base):
    def test_the_running_and_reel_shots_are_flagged(self):
        shots = tl.build(self.root)
        by_ts = {s["timestamp"]: s for s in shots}
        for ts in ("04:52", "04:54", "06:04", "08:14"):   # running, reels, graph
            self.assertTrue(by_ts[ts]["dynamic"], "%s should be dynamic" % ts)

    def test_an_expression_is_not_mistaken_for_movement(self):
        """'eyebrows drooping' is a face, not a camera move."""
        shots = tl.build(self.root)
        by_ts = {s["timestamp"]: s for s in shots}
        self.assertFalse(by_ts["00:21"]["dynamic"])

    def test_a_static_diagram_is_not_flagged(self):
        shots = tl.build(self.root)
        by_ts = {s["timestamp"]: s for s in shots}
        self.assertFalse(by_ts["00:32"]["dynamic"])      # struck-through phone

    def test_the_flagged_set_is_a_minority(self):
        shots = tl.build(self.root)
        dyn = sum(1 for s in shots if s["dynamic"])
        self.assertTrue(0 < dyn < len(shots) // 4,
                        "flagged %d of %d — selection is not selective" % (dyn, len(shots)))


class MotionFilters(Base):
    def test_each_motion_builds_a_distinct_filter(self):
        built = {m: av.motion_filter(m, 90) for m in tl.MOTIONS}
        self.assertEqual(len(set(built.values())), len(tl.MOTIONS))

    def test_the_filter_targets_4k(self):
        f = av.motion_filter("slow push-in", 90)
        self.assertIn("s=3840x2160", f)

    def test_an_unknown_motion_is_refused(self):
        with self.assertRaises(SystemExit):
            av.motion_filter("crash zoom", 90)

    def test_a_one_frame_shot_does_not_divide_by_zero(self):
        self.assertIn("zoompan", av.motion_filter("slow tilt-up", 1))


class CueSheet(Base):
    def test_seven_contiguous_movements_are_parsed(self):
        mv = bf.read_cues(self.root)
        self.assertEqual(len(mv), 7)
        self.assertEqual(mv[0]["start"], 0)
        self.assertEqual(mv[-1]["end"], 682)

    def test_a_gap_in_the_cue_sheet_is_caught(self):
        p = os.path.join(self.root, "audio", "music_bed_cues.md")
        with open(p, encoding="utf-8") as fh:
            text = fh.read()
        text = text.replace("`[01:01]`–`[03:45]`", "`[01:05]`–`[03:45]`")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        with self.assertRaises(SystemExit) as cm:
            bf.read_cues(self.root)
        self.assertIn("contiguous", str(cm.exception))

    def test_movement_lengths_cover_the_runtime(self):
        mv = bf.read_cues(self.root)
        self.assertEqual(sum(m["seconds"] for m in mv), 683)   # inclusive bounds


class AudioGating(Base):
    def test_partial_music_is_refused_rather_than_rendered_with_holes(self):
        d = os.path.join(self.root, "audio", "music")
        os.makedirs(d, exist_ok=True)
        for n in ("01", "02"):
            open(os.path.join(d, n + ".wav"), "wb").close()
        code, out = call(bf, self.root, "--skip-assemble")
        self.assertNotEqual(code, 0)
        self.assertIn("partial", out)

    def test_no_audio_at_all_builds_a_silent_master_and_says_so(self):
        code, out = call(bf, self.root, "--skip-assemble", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("SILENT", out)


class Assembly(Base):
    def test_dry_run_writes_nothing(self):
        code, out = call(av, self.root, "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", out)
        self.assertFalse(os.path.exists(
            os.path.join(self.root, "output", "final_video_4k.mp4")))

    def test_missing_frames_stop_the_render(self):
        code, out = call(av, self.root, "--start", "0", "--end", "2")
        self.assertNotEqual(code, 0)
        self.assertIn("no source", out)

    def test_bad_window_is_refused(self):
        code, _ = call(av, self.root, "--start", "10", "--end", "2")
        self.assertNotEqual(code, 0)

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg absent")
    def test_renders_4k_at_the_planned_duration(self):
        self.make_frames(3, w=640, h=360)
        out = os.path.join(self.root, "output", "t.mp4")
        code, log = call(av, self.root, "--start", "0", "--end", "2",
                         "--preset", "ultrafast", "--crf", "35", "--out", out)
        self.assertEqual(code, 0, log)
        self.assertEqual(av.probe_size(out), (3840, 2160))
        shots = tl.build(self.root)
        want = sum(s["duration_s"] for s in shots[:3])
        self.assertAlmostEqual(av.probe_duration(out), want, delta=0.15)

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg absent")
    def test_a_clip_overrides_the_still_and_is_fitted_to_the_slot(self):
        self.make_frames(2, w=640, h=360)
        clips = os.path.join(self.root, "output", "clips")
        os.makedirs(clips, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc=size=320x180:rate=30:duration=0.5",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        os.path.join(clips, "001.mp4")], check=True)
        out = os.path.join(self.root, "output", "t.mp4")
        code, log = call(av, self.root, "--start", "0", "--end", "1",
                         "--preset", "ultrafast", "--crf", "35", "--out", out)
        self.assertEqual(code, 0, log)
        self.assertIn("1 clips used", log)
        shot = os.path.join(self.root, "output", "shots", "001.mp4")
        self.assertAlmostEqual(av.probe_duration(shot), 2.0, delta=0.15)

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg absent")
    def test_rerunning_reuses_cached_shots(self):
        self.make_frames(2, w=320, h=180)
        out = os.path.join(self.root, "output", "t.mp4")
        call(av, self.root, "--start", "0", "--end", "1", "--preset", "ultrafast",
             "--crf", "40", "--out", out)
        code, log = call(av, self.root, "--start", "0", "--end", "1",
                         "--preset", "ultrafast", "--crf", "40", "--out", out)
        self.assertEqual(code, 0, log)
        self.assertIn("2 cached", log)


if __name__ == "__main__":
    unittest.main(verbosity=2)
