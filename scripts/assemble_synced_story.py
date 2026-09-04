#!/usr/bin/env python3
"""One narration line per frame, and each frame lasts exactly as long as its line.

    python3 scripts/assemble_synced_story.py --dry-run
    python3 scripts/assemble_synced_story.py            # full build

WHY THIS EXISTS
---------------
`assemble_video.py` takes shot durations from the `[MM:SS]` markers in the
prompt file. That is correct when the narration actually follows those marks.
When it does not — an abridged script spread over 157 frames at a flat 2.08 s
each — picture and voice drift apart and no amount of nudging fixes it, because
the two were never derived from the same thing.

This assembler inverts the dependency. Each frame gets one spoken line, the line
is rendered to audio, the audio is measured, and **the measurement becomes the
frame's duration**. Sync is not corrected afterwards; it is impossible to lose,
because there is only one number and both tracks read it.

WHAT THAT COSTS
---------------
The runtime is no longer 11:22. It is however long 157 spoken lines take, which
also means `audio/music_bed_cues.md` no longer lines up — its seven movements
are mapped to the old timeline. The `[MM:SS]` markers become labels rather than
timing. That is the trade, and it is the right one: a marker that does not match
the voice is worse than no marker.

STAGES
------
    1. script   load audio/voiceover/storyboard_script_157.json, validate 157
    2. speak    render each line to audio, measure it
    3. video    render each frame for exactly its line's duration, with camera move
    4. mux      concatenate audio back to back with zero gaps, mux to 4K H.264/AAC

Every stage is resumable: a clip already rendered at the right duration is
reused. Output: output/final_video_perfect_sync_4k.mp4
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

import assemble_video as av  # noqa: E402
import paths  # noqa: E402
import timeline as tl  # noqa: E402

SCRIPT_JSON = "storyboard_script_157.json"
OUT_NAME = "final_video_perfect_sync_4k.mp4"
VOICE = "en-US-AvaNeural"
RATE = "+5%"
ESPEAK_WPM = 165          # roughly matches AvaNeural at +5%


def die(msg):
    raise SystemExit("error: " + msg)


def need(*tools):
    for t in tools:
        if not shutil.which(t):
            die("%s is not on PATH." % t)


# ------------------------------------------------------------------ script

def script_path(root):
    return os.path.join(root, paths.manifest(root)["layout"]["audio"],
                        "voiceover", SCRIPT_JSON)


def load_script(root, shots):
    path = script_path(root)
    if not os.path.isfile(path):
        die("narration not found at %s\n"
            "  It is one line per frame, in order:\n"
            '  [{"frame": 0, "text": "..."}, ...]' % os.path.relpath(path, root))
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if len(data) != len(shots):
        die("%s has %d lines but there are %d frames — they must be one to one"
            % (os.path.relpath(path, root), len(data), len(shots)))
    for i, row in enumerate(data):
        if row.get("frame") != i:
            die("line %d has frame %r; the file must be in frame order"
                % (i, row.get("frame")))
        if not (row.get("text") or "").strip():
            die("frame %d has no text. Every frame needs a line — that is the "
                "whole basis of the sync." % i)
    return data


# ------------------------------------------------------------------ speech

def speak_edge(text, out_path, voice, rate):
    """Microsoft Edge TTS. Needs network, and a WebSocket the proxy may block."""
    cmd = ["edge-tts", "--voice", voice, "--rate=" + rate,
           "--text", text, "--write-media", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.getsize(out_path or "/dev/null"):
        tail = (r.stderr or "").strip().splitlines()
        hint = ""
        blob = "\n".join(tail)
        if "CERTIFICATE_VERIFY_FAILED" in blob:
            hint = ("\n  edge-tts pins certifi. Behind a TLS-inspecting proxy, "
                    "append its CA to the file certifi.where() reports.")
        elif "WSServerHandshakeError" in blob or "403" in blob:
            hint = ("\n  The WebSocket upgrade was refused. Some egress proxies "
                    "relay HTTPS but not WebSockets; edge-tts is WebSocket-only. "
                    "Run from a machine with direct network access, or use "
                    "--engine espeak.")
        raise RuntimeError((tail[-1] if tail else "edge-tts failed") + hint)


def speak_espeak(text, out_path, voice, rate):
    """Offline fallback. Robotic, but it proves the timing chain without network."""
    wav = out_path + ".wav"
    r = subprocess.run(["espeak-ng", "-v", "en-us", "-s", str(ESPEAK_WPM),
                        "-w", wav, text], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "espeak-ng failed").strip()[:200])
    c = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
                        "-c:a", "aac", "-b:a", "192k", out_path],
                       capture_output=True, text=True)
    os.remove(wav)
    if c.returncode != 0:
        raise RuntimeError((c.stderr or "").strip()[-200:])


ENGINES = {"edge": speak_edge, "espeak": speak_espeak}


def render_speech(root, rows, dirs, args):
    """One audio clip per line. Returns [(index, path, duration)]."""
    speak = ENGINES[args.engine]
    out = []
    for i, row in enumerate(rows):
        path = os.path.join(dirs["lines"], "%03d.m4a" % i)
        if not args.force and os.path.isfile(path) and os.path.getsize(path) > 512:
            d = av.probe_duration(path)
            if d and d > 0.05:
                out.append((i, path, d))
                if (i + 1) % 25 == 0:
                    print("  %3d/%3d  (cached)" % (i + 1, len(rows)), flush=True)
                continue
        try:
            speak(row["text"], path, args.voice, args.rate)
        except Exception as e:
            die("line %d failed to render: %s\n  text: %r" % (i, e, row["text"]))
        d = av.probe_duration(path)
        if not d or d <= 0.05:
            die("line %d produced no measurable audio" % i)
        out.append((i, path, d))
        if (i + 1) % 25 == 0 or i + 1 == len(rows):
            print("  %3d/%3d  last %.2fs" % (i + 1, len(rows), d), flush=True)
    return out


# ------------------------------------------------------------------ assemble

def concat_audio(dirs, clips, out_path):
    """Back to back, zero silence. concat demuxer inserts nothing between."""
    lst = os.path.join(dirs["work"], "audio_concat.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for _, path, _ in clips:
            fh.write("file '%s'\n" % path)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat",
                        "-safe", "0", "-i", lst, "-c:a", "aac", "-b:a", "320k",
                        out_path], capture_output=True, text=True)
    if r.returncode != 0:
        die("audio concat failed: %s" % (r.stderr or "").strip()[-300:])
    return out_path


def render_frames(root, shots, clips, dirs, args):
    done = cached = 0
    for n, (i, _apath, dur) in enumerate(clips):
        shot = dict(shots[i])
        shot["duration_s"] = dur          # the whole point: audio drives picture
        out_path = os.path.join(dirs["shots"], "%03d.mp4" % i)
        if not args.force and os.path.isfile(out_path):
            have = av.probe_duration(out_path)
            if have is not None and abs(have - dur) < 0.05:
                cached += 1
                continue
        src_clip = os.path.join(dirs["clips"], shot["clip"])
        src = src_clip if os.path.isfile(src_clip) else os.path.join(
            dirs["frames"], shot["still"])
        if not os.path.isfile(src):
            die("frame %03d has no source at %s" % (i, os.path.relpath(src, root)))
        cmd = av.shot_cmd(shot, src, out_path, args.fps, args.crf, args.preset,
                          src == src_clip)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            die("frame %03d failed: %s"
                % (i, (r.stderr or "").strip().splitlines()[-1][:200]))
        done += 1
        if (n + 1) % 20 == 0 or n + 1 == len(clips):
            print("  %3d/%3d shots  (%d rendered, %d cached)"
                  % (n + 1, len(clips), done, cached), flush=True)
    return done, cached


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="scripts/assemble_synced_story.py",
        description="Frame durations taken from measured narration audio.")
    ap.add_argument("--root")
    ap.add_argument("--engine", default="edge", choices=sorted(ENGINES),
                    help="edge = Microsoft Edge TTS (needs network); "
                         "espeak = offline, robotic, for verifying the chain")
    ap.add_argument("--voice", default=VOICE)
    ap.add_argument("--rate", default=RATE)
    ap.add_argument("--fps", type=int, default=30, choices=(30, 60))
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    root = args.root or paths.find_root()
    shots = tl.build(root)
    rows = load_script(root, shots)

    end = len(shots) - 1 if args.end is None else args.end
    if not (0 <= args.start <= end <= len(shots) - 1):
        ap.error("--start/--end must satisfy 0 <= start <= end <= %d" % (len(shots) - 1))
    window = list(range(args.start, end + 1))
    rows = [rows[i] for i in window]

    out_root = paths.output_dir(root, create=not args.dry_run)
    dirs = {"frames": os.path.join(out_root, "frames"),
            "clips": os.path.join(out_root, "clips"),
            "shots": os.path.join(out_root, "shots_synced"),
            "lines": os.path.join(out_root, "voice_lines"),
            "work": out_root}
    out_path = args.out or os.path.join(out_root, OUT_NAME)

    words = sum(len(r["text"].split()) for r in rows)
    print("=" * 70)
    print("PERFECT-SYNC BUILD — one line per frame, frame length = line length")
    print("=" * 70)
    print("frames     : %d  (%03d-%03d)" % (len(window), args.start, end))
    print("narration  : %d lines, %d words, %.1f words/line"
          % (len(rows), words, words / len(rows)))
    print("engine     : %s   voice %s   rate %s"
          % (args.engine, args.voice if args.engine == "edge" else "espeak en-us",
             args.rate if args.engine == "edge" else "%d wpm" % ESPEAK_WPM))
    print("format     : %dx%d @ %dfps, H.264 crf %d %s"
          % (av.WIDTH, av.HEIGHT, args.fps, args.crf, args.preset))
    print("output     : %s" % os.path.relpath(out_path, root))
    print()

    if args.dry_run:
        for r in rows[:5]:
            print("  %03d  %s" % (r["frame"], r["text"]))
        print("  ... %d more" % max(0, len(rows) - 5))
        print("\nDRY RUN. No audio rendered, no ffmpeg invoked.")
        return 0

    need("ffmpeg", "ffprobe")
    if args.engine == "espeak":
        need("espeak-ng")
    for k in ("clips", "shots", "lines"):
        os.makedirs(dirs[k], exist_ok=True)

    print("[1/3] speaking %d lines" % len(rows), flush=True)
    clips = render_speech(root, rows, dirs, args)
    total = sum(d for _, _, d in clips)
    shortest = min(clips, key=lambda c: c[2])
    longest = max(clips, key=lambda c: c[2])
    print("  narration total %s  (%.1fs)   shortest %.2fs (%03d)  longest %.2fs (%03d)"
          % (tl.hhmmss(total), total, shortest[2], shortest[0], longest[2], longest[0]))

    print("\n[2/3] rendering %d frames at their line durations" % len(clips), flush=True)
    render_frames(root, shots, clips, dirs, args)

    print("\n[3/3] concatenating and muxing", flush=True)
    audio = concat_audio(dirs, clips, os.path.join(out_root, "narration_full.m4a"))
    a_dur = av.probe_duration(audio)
    print("  audio  %s  (%.2fs)" % (tl.hhmmss(a_dur or 0), a_dur or 0))

    lst = os.path.join(dirs["work"], "synced_concat.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for i, _, _ in clips:
            fh.write("file '%s'\n" % os.path.join(dirs["shots"], "%03d.mp4" % i))
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", lst,
                        "-i", audio, "-c:v", "copy", "-c:a", "aac", "-b:a", "320k",
                        "-movflags", "+faststart", out_path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        die("final mux failed: %s" % (r.stderr or "").strip()[-300:])

    v_dur = av.probe_duration(out_path)
    drift = abs((v_dur or 0) - (a_dur or 0))
    print()
    print("=" * 70)
    print("DONE — %s  (%.1f MB)"
          % (os.path.relpath(out_path, root), os.path.getsize(out_path) / 1e6))
    print("runtime    : %s" % tl.hhmmss(v_dur or 0))
    print("sync       : video %.2fs vs narration %.2fs — drift %.3fs"
          % (v_dur or 0, a_dur or 0, drift))
    if drift > 0.10:
        print("  ! drift above 100 ms; check for a shot that failed to hit its duration")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            os._exit(0)
