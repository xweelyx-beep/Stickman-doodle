#!/usr/bin/env python3
"""One command: frames -> validation -> audio bed -> 4K master.

    python3 scripts/build_full_video.py --backend mock --execute

Chains the four stages that already exist as separate tools, so the whole film
is one invocation:

    1. generate   scripts/auto_generate.py   renders any missing frames
    2. validate   scripts/generate_frames.py verifies every frame on disk
    3. audio      builds the music bed from audio/music_bed_cues.md and mixes
                  the voiceover over it
    4. assemble   scripts/assemble_video.py  renders the 4K master

Each stage is skippable, so a re-run after a failure does not redo the
expensive parts. Every stage is also still runnable on its own; this only
sequences them.

THE AUDIO STAGE NEEDS FILES THAT DO NOT EXIST YET
--------------------------------------------------
`audio/music_bed_cues.md` is a cue sheet: seven movements, their time ranges and
their moods. It is not audio. Neither the music tracks nor the voiceover are in
the repository, and the channel bible records tempo, key, instrumentation and
licence as undecided.

So this stage builds the mix — timing, movement order, crossfades, ducking —
from the cue sheet, and tells you exactly which files it is missing. Give it
the tracks and it runs. Without them it renders a silent 4K master, which is
the correct intermediate, and says so rather than pretending.

Expected layout:

    audio/voiceover/why-you-check-your-phone.wav     (or .mp3/.m4a, or --vo)
    audio/music/01.wav .. 07.wav                     one per movement, in order
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "core"))

import paths  # noqa: E402
import timeline as tl  # noqa: E402

CUE_ROW = re.compile(
    r"^\|\s*(\d)\s*\|\s*`\[(\d\d:\d\d)\]`[–-]`\[(\d\d:\d\d)\]`\s*\|\s*\*\*(.+?)\*\*")
AUDIO_EXT = (".wav", ".flac", ".m4a", ".mp3", ".aac")
EPISODE = "why-you-check-your-phone"
DUCK_DB = -15.0   # music sits this far under the voiceover
XFADE = 1.0       # seconds of overlap between movements


def die(msg):
    raise SystemExit("error: " + msg)


def secs(mmss):
    m, s = mmss.split(":")
    return int(m) * 60 + int(s)


def run(cmd, what):
    r = subprocess.run(cmd)
    if r.returncode != 0:
        die("%s failed (exit %d): %s" % (what, r.returncode, " ".join(cmd[:6])))


# ------------------------------------------------------------------ audio

def read_cues(root):
    path = os.path.join(root, paths.manifest(root)["layout"]["audio"],
                        "music_bed_cues.md")
    if not os.path.isfile(path):
        die("cue sheet not found at %s" % path)
    movements = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = CUE_ROW.match(line.strip())
            if m:
                n, a, b, name = m.groups()
                movements.append({"n": int(n), "start": secs(a), "end": secs(b),
                                  "name": name,
                                  "seconds": secs(b) - secs(a) + 1})
    if len(movements) != 7:
        die("expected 7 movements in the cue sheet, parsed %d" % len(movements))
    for i in range(len(movements) - 1):
        if movements[i + 1]["start"] != movements[i]["end"] + 1:
            die("movements %d and %d are not contiguous in the cue sheet"
                % (i + 1, i + 2))
    return movements


def find_audio(directory, stem=None):
    if not os.path.isdir(directory):
        return None
    for ext in AUDIO_EXT:
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith(ext):
                continue
            if stem is None or os.path.splitext(name)[0] == stem:
                return os.path.join(directory, name)
    return None


def audio_inputs(root, vo_override):
    a = os.path.join(root, paths.manifest(root)["layout"]["audio"])
    vo = vo_override or find_audio(os.path.join(a, "voiceover"), EPISODE) \
        or find_audio(os.path.join(a, "voiceover"))
    music_dir = os.path.join(a, "music")
    tracks = []
    for n in range(1, 8):
        tracks.append(find_audio(music_dir, "%02d" % n))
    return vo, tracks


def build_audio(root, movements, vo, tracks, out_path, runtime):
    """Music bed cut to the cue sheet, voiceover mixed over it."""
    present = [t for t in tracks if t]
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    parts = []

    if present:
        # One trimmed, faded segment per movement, then crossfade them in order.
        for i, (mv, track) in enumerate(zip(movements, tracks)):
            if not track:
                die("movement %d (%s) has no track at audio/music/%02d.*"
                    % (mv["n"], mv["name"], mv["n"]))
            cmd += ["-stream_loop", "-1", "-i", track]
            parts.append("[%d:a]atrim=0:%.3f,asetpts=N/SR/TB,"
                         "afade=t=in:st=0:d=%.2f,afade=t=out:st=%.3f:d=%.2f[m%d]"
                         % (i, mv["seconds"] + XFADE, XFADE,
                            max(mv["seconds"] - XFADE, 0.0), XFADE, i))
        chain = "".join("[m%d]" % i for i in range(len(movements)))
        parts.append("%sconcat=n=%d:v=0:a=1[bed]" % (chain, len(movements)))
        parts.append("[bed]volume=%.1fdB[bedq]" % DUCK_DB)

    if vo:
        vo_idx = len(movements) if present else 0
        cmd += ["-i", vo]
        if present:
            parts.append("[%d:a][bedq]amix=inputs=2:duration=first:"
                         "dropout_transition=0,alimiter=limit=0.95[out]" % vo_idx)
        else:
            parts.append("[%d:a]alimiter=limit=0.95[out]" % vo_idx)
    elif present:
        parts.append("[bedq]alimiter=limit=0.95[out]")
    else:
        return None

    cmd += ["-filter_complex", ";".join(parts), "-map", "[out]",
            "-t", "%.3f" % runtime, "-c:a", "aac", "-b:a", "320k", out_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die("audio build failed: %s" % (r.stderr or "").strip()[-400:])
    return out_path


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="scripts/build_full_video.py",
        description="Generate, validate, mix and assemble the whole film.")
    ap.add_argument("--backend", help="generation backend; omit to skip stage 1")
    ap.add_argument("--execute", action="store_true",
                    help="actually generate; without it stage 1 is a dry run")
    ap.add_argument("--approve-spend", type=int, default=None)
    ap.add_argument("--vo", help="voiceover file (default: audio/voiceover/)")
    ap.add_argument("--fps", type=int, default=30, choices=(30, 60))
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--tail-seconds", type=float, default=tl.TAIL_DEFAULT)
    ap.add_argument("--out", default=None)
    ap.add_argument("--skip-generate", action="store_true")
    ap.add_argument("--skip-assemble", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--root")
    args = ap.parse_args(argv)

    root = args.root or paths.find_root()
    shots = tl.build(root, args.tail_seconds)
    runtime = tl.total_seconds(shots)
    out_root = paths.output_dir(root, create=True)
    out_path = args.out or os.path.join(out_root, "final_video_4k.mp4")
    py = sys.executable

    movements = read_cues(root)
    vo, tracks = audio_inputs(root, args.vo)
    have_music = sum(1 for t in tracks if t)

    print("=" * 70)
    print("FULL BUILD — %s" % EPISODE)
    print("=" * 70)
    print("shots      : %d   runtime %s" % (len(shots), tl.hhmmss(runtime)))
    print("movements  : %d parsed from audio/music_bed_cues.md" % len(movements))
    print("voiceover  : %s" % (os.path.relpath(vo, root) if vo else "MISSING"))
    print("music      : %d of 7 movement tracks present" % have_music)
    print("output     : %s" % os.path.relpath(out_path, root))
    print()

    # ---- stage 1: generate ---------------------------------------------
    if args.skip_generate or not args.backend:
        print("[1/4] generate  — skipped (%s)"
              % ("--skip-generate" if args.skip_generate else "no --backend"))
    else:
        print("[1/4] generate  — backend %s" % args.backend)
        cmd = [py, os.path.join(HERE, "auto_generate.py"),
               "--root", root, "--backend", args.backend]
        if args.execute and not args.dry_run:
            cmd.append("--execute")
            if args.approve_spend is not None:
                cmd += ["--approve-spend", str(args.approve_spend)]
        run(cmd, "generation")

    # ---- stage 2: validate ---------------------------------------------
    print("\n[2/4] validate")
    if args.dry_run:
        print("  skipped in --dry-run")
    else:
        run([py, os.path.join(HERE, "generate_frames.py"), "--root", root, "verify"],
            "validation")

    # ---- stage 3: audio -------------------------------------------------
    print("\n[3/4] audio")
    audio_path = None
    if not vo and not have_music:
        print("  no voiceover and no music tracks — building a SILENT master.")
        print("  The cue sheet is a plan, not audio. Supply:")
        print("    audio/voiceover/%s.wav" % EPISODE)
        print("    audio/music/01.wav .. 07.wav   (one per movement, in order)")
    elif have_music and have_music < 7:
        missing = [m["n"] for m, t in zip(movements, tracks) if not t]
        die("music is partial: movements %s have no track. Supply all seven or "
            "none — a bed with holes is worse than no bed." % missing)
    elif args.dry_run:
        print("  skipped in --dry-run")
    else:
        if not shutil.which("ffmpeg"):
            die("ffmpeg is not on PATH; the audio stage needs it")
        audio_path = build_audio(root, movements, vo, tracks,
                                 os.path.join(out_root, "master_audio.m4a"), runtime)
        print("  wrote %s" % os.path.relpath(audio_path, root))
        for mv in movements:
            print("    %d %-30s %s-%s  %3ds"
                  % (mv["n"], mv["name"], tl.hhmmss(mv["start"]),
                     tl.hhmmss(mv["end"]), mv["seconds"]))
        if vo and have_music:
            print("  music ducked %.0f dB under the voiceover, %.1fs crossfades"
                  % (abs(DUCK_DB), XFADE))

    # ---- stage 4: assemble ----------------------------------------------
    print("\n[4/4] assemble")
    if args.skip_assemble:
        print("  skipped (--skip-assemble)")
        return 0
    cmd = [py, os.path.join(HERE, "assemble_video.py"), "--root", root,
           "--fps", str(args.fps), "--crf", str(args.crf), "--preset", args.preset,
           "--tail-seconds", str(args.tail_seconds), "--out", out_path]
    if audio_path:
        cmd += ["--audio", audio_path]
    if args.dry_run:
        cmd.append("--dry-run")
    run(cmd, "assembly")

    if not args.dry_run and os.path.isfile(out_path):
        print("\n" + "=" * 70)
        print("DONE — %s  (%.1f MB)"
              % (os.path.relpath(out_path, root), os.path.getsize(out_path) / 1e6))
        if not audio_path:
            print("Silent master. Add the audio files above and re-run to get sound.")
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
