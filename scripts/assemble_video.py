#!/usr/bin/env python3
"""Assemble the 157 shots into one 4K UHD video, in chronological order.

    python3 scripts/assemble_video.py --dry-run
    python3 scripts/assemble_video.py --out output/final_video_4k.mp4

Each shot runs for exactly the gap to the next [MM:SS] marker, so picture stays
locked to the VO timing without a separate sync pass. Stills get continuous 2D
camera motion from the canon's four-move vocabulary; where a generated clip
exists at output/clips/NNN.mp4 it is used instead of the still.

HOW IT RENDERS
--------------
Shot by shot into output/shots/NNN.mp4, then stream-copy concat. That is slower
to start than one enormous filter_complex but it is resumable, parallelisable,
and a single bad shot fails alone instead of taking the whole 11-minute render
with it. Re-running skips shots already rendered at the right duration.

WHAT IT NEEDS
-------------
ffmpeg on PATH, and the frames in output/frames/. Audio is optional: without it
this produces a silent 4K master, which is the correct intermediate. See
scripts/build_full_video.py for the audio-layered end-to-end run.

A NOTE ON 4K
------------
Output is 3840x2160 regardless of source size. If the rendered frames are
smaller than that — the mascot reference is 1348x752 — the result is an upscale
and will look soft. The assembler warns once when it sees this. Generating at
4K, or at least 2K, is a backend setting, not something the assembler can fix.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "core"))

import generate_frames as gfr  # noqa: E402
import paths  # noqa: E402
import timeline as tl  # noqa: E402

WIDTH, HEIGHT = 3840, 2160
# zoompan samples from this working canvas. Keeping it above the output size
# means the maximum zoom still downscales rather than upscaling, which is what
# stops the classic zoompan shimmer.
WORK_W, WORK_H = 4800, 2700
MAX_ZOOM = 1.12


def die(msg):
    raise SystemExit("error: " + msg)


def need_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            die("%s is not on PATH.\n"
                "  macOS:  brew install ffmpeg\n"
                "  Debian: sudo apt-get install ffmpeg\n"
                "  It does the encoding; there is no pure-Python substitute." % tool)


def probe_size(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "json", path],
            capture_output=True, text=True, check=True).stdout
        s = json.loads(out)["streams"][0]
        return int(s["width"]), int(s["height"])
    except Exception:
        return None


def probe_duration(path):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, check=True).stdout.strip()
        return float(out)
    except Exception:
        return None


# ------------------------------------------------------------------ motion

def motion_filter(motion, frames):
    """The zoompan expression for one camera move.

    `on` is the output frame index, so every expression is a function of
    progress through the shot rather than of wall time — the move lands exactly
    at the shot boundary whatever the duration or fps.
    """
    n = max(frames - 1, 1)
    z_in = "1+%.6f*on/%d" % (MAX_ZOOM - 1, n)
    z_out = "%.6f-%.6f*on/%d" % (MAX_ZOOM, MAX_ZOOM - 1, n)
    centre_x = "iw/2-(iw/zoom/2)"
    centre_y = "ih/2-(ih/zoom/2)"

    if motion == "slow push-in":
        z, x, y = z_in, centre_x, centre_y
    elif motion == "slow pull-back":
        z, x, y = z_out, centre_x, centre_y
    elif motion == "slow tilt-up":
        # Hold the zoom, travel the frame from low to high.
        z = "%.6f" % 1.10
        x = centre_x
        y = "(ih-ih/zoom)*(1-on/%d)" % n
    elif motion == "gentle drift":
        z = "%.6f" % 1.08
        x = "(iw-iw/zoom)*(on/%d)" % n
        y = centre_y
    else:
        die("unknown motion %r" % motion)
    return ("scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
            "crop=%d:%d,"
            "zoompan=z='%s':x='%s':y='%s':d=1:s=%dx%d:fps=%%d,"
            "format=yuv420p" % (WORK_W, WORK_H, WORK_W, WORK_H,
                                z, x, y, WIDTH, HEIGHT))


# ------------------------------------------------------------------ render

def shot_cmd(shot, src, out_path, fps, crf, preset, is_clip):
    dur = shot["duration_s"]
    if is_clip:
        # Fit the clip to its slot: pad a short one by holding the last frame,
        # cut a long one. The timeline owns duration, not the clip.
        vf = ("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"
              "pad=%d:%d:(ow-iw)/2:(oh-ih)/2,fps=%d,tpad=stop_mode=clone:"
              "stop_duration=%.3f,format=yuv420p"
              % (WIDTH, HEIGHT, WIDTH, HEIGHT, fps, dur))
        return ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
                "-t", "%.3f" % dur, "-vf", vf, "-an",
                "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                "-pix_fmt", "yuv420p", "-r", str(fps), out_path]

    frames = max(int(round(dur * fps)), 1)
    vf = motion_filter(shot["motion"], frames) % fps
    return ["ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", str(fps), "-t", "%.3f" % dur, "-i", src,
            "-vf", vf, "-an",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-r", str(fps), out_path]


def render_shot(shot, root, dirs, fps, crf, preset, force):
    out_path = os.path.join(dirs["shots"], "%03d.mp4" % shot["index"])
    clip = os.path.join(dirs["clips"], shot["clip"])
    still = os.path.join(dirs["frames"], shot["still"])
    is_clip = os.path.isfile(clip)
    src = clip if is_clip else still

    if not os.path.isfile(src):
        return False, "missing source %s" % os.path.relpath(src, root), is_clip

    if not force and os.path.isfile(out_path):
        have = probe_duration(out_path)
        if have is not None and abs(have - shot["duration_s"]) < 0.08:
            return True, "cached", is_clip

    cmd = shot_cmd(shot, src, out_path, fps, crf, preset, is_clip)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr or "ffmpeg failed").strip().splitlines()[-1][:200], is_clip
    return True, "rendered", is_clip


def concat(dirs, shots, out_path, audio):
    list_path = os.path.join(dirs["work"], "concat.txt")
    with open(list_path, "w", encoding="utf-8") as fh:
        for s in shots:
            fh.write("file '%s'\n" % os.path.join(dirs["shots"], "%03d.mp4" % s["index"]))
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", list_path]
    if audio:
        cmd += ["-i", audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                "-shortest", "-movflags", "+faststart"]
    else:
        cmd += ["-c", "copy", "-movflags", "+faststart"]
    cmd.append(out_path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die("concat failed: %s" % (r.stderr or "").strip()[-400:])


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="scripts/assemble_video.py",
        description="Assemble the 157 shots into one 4K UHD master.")
    ap.add_argument("--root")
    ap.add_argument("--out", default=None, help="output path (default output/final_video_4k.mp4)")
    ap.add_argument("--fps", type=int, default=30, choices=(30, 60))
    ap.add_argument("--crf", type=int, default=18, help="x264 quality, lower is better")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--audio", default=None, help="audio track to mux in")
    ap.add_argument("--tail-seconds", type=float, default=tl.TAIL_DEFAULT,
                    help="length of the final shot, which has no next marker")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--force", action="store_true", help="re-render cached shots")
    ap.add_argument("--dry-run", action="store_true", help="plan only, no ffmpeg")
    args = ap.parse_args(argv)

    root = args.root or paths.find_root()
    shots = tl.build(root, args.tail_seconds)
    end = len(shots) - 1 if args.end is None else args.end
    if not (0 <= args.start <= end <= len(shots) - 1):
        ap.error("--start/--end must satisfy 0 <= start <= end <= %d" % (len(shots) - 1))
    window = shots[args.start:end + 1]

    out_root = paths.output_dir(root, create=True)
    dirs = {"frames": os.path.join(out_root, "frames"),
            "clips": os.path.join(out_root, "clips"),
            "shots": os.path.join(out_root, "shots"),
            "work": out_root}
    for d in ("clips", "shots"):
        os.makedirs(dirs[d], exist_ok=True)
    out_path = args.out or os.path.join(out_root, "final_video_4k.mp4")

    have_still = sum(1 for s in window
                     if os.path.isfile(os.path.join(dirs["frames"], s["still"])))
    have_clip = sum(1 for s in window
                    if os.path.isfile(os.path.join(dirs["clips"], s["clip"])))
    summary = tl.summarise(shots)

    print("shots      : %d of %d  (%03d-%03d)" % (len(window), len(shots), args.start, end))
    print("runtime    : %s  (%.1fs of this window)"
          % (tl.hhmmss(tl.total_seconds(window)), tl.total_seconds(window)))
    print("full film  : %s   [%s] -> [%s]"
          % (summary["runtime"], summary["first"], summary["last"]))
    print("format     : %dx%d @ %dfps, H.264 crf %d, %s"
          % (WIDTH, HEIGHT, args.fps, args.crf, args.preset))
    print("stills     : %d of %d present" % (have_still, len(window)))
    print("clips      : %d present (%d shots flagged dynamic across the film)"
          % (have_clip, summary["dynamic"]))
    print("audio      : %s" % (args.audio or "none — silent master"))
    print("output     : %s" % os.path.relpath(out_path, root))
    print("camera     : " + ", ".join("%s x%d" % kv for kv in sorted(summary["motions"].items())))
    print()

    if args.dry_run:
        for s in window[:6]:
            print("  %03d [%s] %4.1fs  %-14s %s"
                  % (s["index"], s["timestamp"], s["duration_s"], s["motion"],
                     "CLIP" if os.path.isfile(os.path.join(dirs["clips"], s["clip"])) else "still"))
        if len(window) > 6:
            print("  ... %d more" % (len(window) - 6))
        print("\nDRY RUN. No ffmpeg was invoked and nothing was written.")
        return 0

    need_ffmpeg()
    if have_still < len(window) and have_clip < len(window):
        die("%d of %d shots have no source in output/frames/ or output/clips/.\n"
            "  Render them first:  python3 scripts/auto_generate.py --backend <b> --execute"
            % (len(window) - max(have_still, have_clip), len(window)))

    first_still = os.path.join(dirs["frames"], window[0]["still"])
    if os.path.isfile(first_still):
        size = probe_size(first_still)
        if size and (size[0] < WIDTH or size[1] < HEIGHT):
            print("  ! source frames are %dx%d, output is %dx%d — this is an "
                  "upscale and will look soft." % (size[0], size[1], WIDTH, HEIGHT))
            print("    Generate at 4K in the backend if sharpness matters.\n")

    done = cached = failed = clips_used = 0
    for i, s in enumerate(window):
        ok, detail, is_clip = render_shot(s, root, dirs, args.fps, args.crf,
                                          args.preset, args.force)
        if ok:
            cached += detail == "cached"
            done += detail == "rendered"
            clips_used += is_clip
        else:
            failed += 1
            print("  %03d [%s] FAILED — %s" % (s["index"], s["timestamp"], detail))
        if (i + 1) % 20 == 0 or i + 1 == len(window):
            print("  %3d/%3d shots  (%d rendered, %d cached, %d failed)"
                  % (i + 1, len(window), done, cached, failed))

    if failed:
        die("%d shot(s) failed; not concatenating a film with holes in it." % failed)

    print("\nconcatenating %d shots%s..."
          % (len(window), " and muxing audio" if args.audio else ""))
    concat(dirs, window, out_path, args.audio)

    size_mb = os.path.getsize(out_path) / 1e6
    dur = probe_duration(out_path)
    print("wrote %s  —  %.1f MB, %s, %d clips used"
          % (os.path.relpath(out_path, root), size_mb,
             tl.hhmmss(dur) if dur else "?", clips_used))
    if dur:
        want = tl.total_seconds(window)
        drift = abs(dur - want)
        print("timing     : %.2fs rendered vs %.2fs planned  (drift %.2fs)"
              % (dur, want, drift))
        if drift > 0.5:
            print("  ! drift over half a second — check the concat")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            os._exit(0)
