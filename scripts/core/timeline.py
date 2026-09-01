#!/usr/bin/env python3
"""The episode timeline: what is on screen, when, for how long, and moving how.

One source of truth shared by the assembler and the master runner, so a shot's
duration cannot mean one thing in the render and another in the report.

DURATIONS COME FROM THE PROMPT FILE, NOT FROM A GUESS
-----------------------------------------------------
Every frame carries an [MM:SS] marker saying when it appears. A shot therefore
runs until the next one starts:

    duration[i] = timestamp[i+1] - timestamp[i]

Across the 157 frames those 156 gaps sum to exactly 682 s, which is the stated
11:22 runtime. That is the VO timing, read off the data rather than estimated.

The last frame is the exception: nothing follows it, so its length is not
derivable. It gets `tail_seconds` (default 3.0, the median gap) and the total
runtime is reported as 11:25 rather than quietly presented as 11:22.

CAMERA MOTION
-------------
`references/style-rules.md` section 1 fixes the vocabulary: slow push-in, slow
pull-back, slow tilt-up, gentle drift, with the rule that no block of three
repeats the same motion throughout. Motion here is assigned from that list, not
invented, and the block rule is enforced and testable.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths  # noqa: E402

PROMPT_FILE = "image_prompts_why_you_check_your_phone_v2.txt"
FRAME_RE = re.compile(r"^\[(\d\d):(\d\d)\] (.+)$", re.S)
TAIL_DEFAULT = 3.0

# references/style-rules.md section 1. Exactly one per shot; a static shot is a
# documented failure.
MOTIONS = ("slow push-in", "slow pull-back", "slow tilt-up", "gentle drift")

# Frames whose prompt describes motion in the picture itself. These are the
# candidates for a generated video clip rather than a panned still; everything
# else reads fine as a still under camera move.
DYNAMIC_CUES = (
    (r"running full tilt|running hard|running toward", "the character is running"),
    (r"spinning fast|reels spinning|coin spinning|mid-rotation", "something is spinning"),
    (r"motion blur|speed lines|motion lines|streaks", "motion is drawn into the frame"),
    (r"steep downward slope|continuing its plunge|plunge even further", "a graph is falling"),
    (r"descend one after another|arrive rapidly|locking into place", "elements are accumulating"),
    (r"needle slammed|slammed hard", "a gauge slams across"),
    (r"melting|dissolving", "the subject is deforming"),
    (r"breaks apart and drifts|drifts away", "the subject is dispersing"),
    (r"being pulled downward|pulling downward|stretched taut", "a pull gesture mid-action"),
    (r"heavier doubled motion lines|blurred after-image", "rapid repetition is drawn in"),
)
# Deliberately NOT cues: "eyebrows drooping" is an expression, not movement, and
# "radiating"/"spilling outward" describes a static glow as often as it does
# motion lines. Both produced false positives on a first pass; the motion-lines
# case is covered above by its own phrase.


def _prompt_path(root):
    return os.path.join(root, paths.manifest(root)["layout"]["prompts"], PROMPT_FILE)


def _classify(body):
    for pattern, why in DYNAMIC_CUES:
        if re.search(pattern, body, re.I):
            return True, why
    return False, None


def _assign_motions(flags):
    """One motion per shot, honouring the canon's no-three-in-a-row rule.

    Preference order per shot: a dynamic shot wants `gentle drift` first, so the
    camera does not fight animation already inside the frame; a static shot
    wants the index-cycled motion, which spreads the vocabulary evenly. Either
    way the first preference that would not make three consecutive shots
    identical is taken, so the rule holds by construction rather than by luck.

    A naive "dynamic always drifts" rule broke exactly here: runs of adjacent
    dynamic shots (the casino reels, the running sequence) all drifted together.
    """
    out = []
    for i, dynamic in enumerate(flags):
        cycled = MOTIONS[i % len(MOTIONS)]
        order = ([ "gentle drift", cycled] if dynamic else [cycled, "gentle drift"])
        order += [m for m in MOTIONS if m not in order]
        for candidate in order:
            if len(out) >= 2 and out[-1] == out[-2] == candidate:
                continue
            out.append(candidate)
            break
    return out


def build(root=None, tail_seconds=TAIL_DEFAULT):
    """Return the ordered shot list. Raises SystemExit on malformed input."""
    root = root or paths.find_root()
    path = _prompt_path(root)
    if not os.path.isfile(path):
        raise SystemExit("error: prompt file not found at %s" % path)
    with open(path, encoding="utf-8") as fh:
        blocks = fh.read().strip().split("\n\n")

    marks, bodies = [], []
    for i, block in enumerate(blocks):
        m = FRAME_RE.match(block)
        if not m:
            raise SystemExit("error: frame %d has no [MM:SS] marker" % (i + 1))
        mm, ss, body = m.group(1), m.group(2), m.group(3)
        marks.append(int(mm) * 60 + int(ss))
        bodies.append(body)
    if any(marks[i] >= marks[i + 1] for i in range(len(marks) - 1)):
        raise SystemExit("error: timestamps are not strictly increasing")
    if tail_seconds <= 0:
        raise SystemExit("error: tail_seconds must be positive")

    classified = [_classify(b) for b in bodies]
    motions = _assign_motions([d for d, _ in classified])

    shots = []
    for i, (start, body) in enumerate(zip(marks, bodies)):
        dur = (marks[i + 1] - start) if i + 1 < len(marks) else float(tail_seconds)
        dynamic, why = classified[i]
        shots.append({
            "index": i,
            "number": i + 1,
            "timestamp": "%02d:%02d" % (start // 60, start % 60),
            "start_s": float(start),
            "duration_s": float(dur),
            "still": "%03d.png" % i,
            "clip": "%03d.mp4" % i,
            "motion": motions[i],
            "dynamic": dynamic,
            "dynamic_reason": why,
            "prompt": body,
        })
    return shots


def total_seconds(shots):
    return sum(s["duration_s"] for s in shots)


def hhmmss(seconds):
    seconds = int(round(seconds))
    return "%d:%02d" % (seconds // 60, seconds % 60)


def check_block_rule(shots, block=3):
    """No run of `block` consecutive shots may share one motion."""
    bad = []
    for i in range(len(shots) - block + 1):
        window = shots[i:i + block]
        if len({s["motion"] for s in window}) == 1:
            bad.append((window[0]["timestamp"], window[0]["motion"]))
    return bad


def summarise(shots):
    from collections import Counter
    motions = Counter(s["motion"] for s in shots)
    dyn = [s for s in shots if s["dynamic"]]
    return {
        "shots": len(shots),
        "runtime_s": total_seconds(shots),
        "runtime": hhmmss(total_seconds(shots)),
        "first": shots[0]["timestamp"],
        "last": shots[-1]["timestamp"],
        "motions": dict(motions),
        "dynamic": len(dyn),
        "dynamic_indices": [s["index"] for s in dyn],
        "block_rule_violations": check_block_rule(shots),
    }


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Inspect the episode timeline.")
    ap.add_argument("--root")
    ap.add_argument("--tail-seconds", type=float, default=TAIL_DEFAULT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dynamic", action="store_true",
                    help="list only the shots flagged for a motion clip")
    args = ap.parse_args(argv)

    shots = build(args.root, args.tail_seconds)
    if args.json:
        print(json.dumps(shots, indent=1))
        return 0
    s = summarise(shots)
    if args.dynamic:
        print("%d of %d shots flagged dynamic:" % (s["dynamic"], s["shots"]))
        for shot in shots:
            if shot["dynamic"]:
                print("  %03d  [%s]  %4.1fs  %s"
                      % (shot["index"], shot["timestamp"], shot["duration_s"],
                         shot["dynamic_reason"]))
        return 0
    print("shots     : %d   [%s] -> [%s]" % (s["shots"], s["first"], s["last"]))
    print("runtime   : %s  (%.0fs)" % (s["runtime"], s["runtime_s"]))
    print("dynamic   : %d flagged for a motion clip" % s["dynamic"])
    print("motions   : " + ", ".join("%s x%d" % kv for kv in sorted(s["motions"].items())))
    print("block rule: %s" % ("OK — no three consecutive share a motion"
                              if not s["block_rule_violations"]
                              else "VIOLATED at %s" % s["block_rule_violations"][:3]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        finally:
            os._exit(0)
