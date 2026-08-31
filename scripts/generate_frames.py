#!/usr/bin/env python3
"""Drive the 157-frame Nano Banana Pro queue for an episode.

WHAT THIS DOES AND DOES NOT DO
------------------------------
It does not generate anything. It cannot: `scripts/config/models.json` locks
Stickman art to Nano Banana Pro on `route: "manual"`, and records why —

    "Google Flow ... and Meta AI are browser surfaces with no API this
     pipeline can reach ... Nothing here submits automatically."

and `credit_safeguard.pipeline_submits` is `false`: "This repository contains
no code that calls a paid endpoint." This script keeps that true. It makes no
network call of any kind.

What it automates is the part that actually costs the operator time across 157
frames: owning the queue. It parses and validates the prompt file, hands out
work in canon-sized batches, watches the output directory, verifies what lands
there is a real image of the right name, records progress durably, and resumes
exactly where it stopped.

WHY IT BATCHES INSTEAD OF LOOPING
---------------------------------
`references/style-rules.md` §1, the house production method, is explicit:

    Concurrency cap   Never output more than three generation prompts at once
    Bulk generation   Forbidden. Prompting a whole script at once is a failure.
    Mandatory halt    Stop and wait for approval after every block. No exceptions.

A loop that fires 157 prompts would break all three. `next` hands out three,
marks them issued, and stops. That is the automation the canon permits.

COMMANDS
--------
    plan     parse, validate, and show the batch plan          (read-only)
    next     emit the next batch as a work sheet               (marks issued)
    verify   scan the output directory and record arrivals     (read-only scan)
    status   progress, per-batch and overall                   (read-only)
    reset    clear queue state, keeping generated files         (destructive)

Stdlib only. Python 3.
"""

import argparse
import datetime
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

import paths  # noqa: E402

PROMPT_FILE = "image_prompts_why_you_check_your_phone_v2.txt"
REFERENCE = "character_ref_body.png"
FRAMES_SUBDIR = "frames"
MANIFEST = "manifest.json"
BATCH_DEFAULT = 3          # the canon's concurrency cap
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MIN_BYTES = 4096           # smaller than this is not a real render

FRAME_RE = re.compile(r"^\[(\d\d:\d\d)\] (.+)$", re.S)
LOCK_KEY = "the same recurring character: a friendly stick-figure man"
PREHISTORIC = ("prehistoric version of the recurring character",
               "recurring character but in prehistoric dress")


def utcnow():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def die(msg):
    raise SystemExit("error: " + msg)


# ---------------------------------------------------------------- inputs

def prompt_path(root):
    return os.path.join(root, paths.manifest(root)["layout"]["prompts"], PROMPT_FILE)


def reference_path(root):
    return os.path.join(root, paths.manifest(root)["layout"]["references"], REFERENCE)


def png_size(path):
    """(width, height) from a PNG header, or None. No third-party imaging."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != PNG_MAGIC or head[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", head[16:24])


def load_reference(root):
    path = reference_path(root)
    if not os.path.isfile(path):
        die("character reference not found at %s; every frame is generated "
            "against it, so the queue will not start without it" % path)
    size = png_size(path)
    if not size:
        die("%s is not a valid PNG" % path)
    return {"path": os.path.relpath(path, root), "width": size[0],
            "height": size[1], "bytes": os.path.getsize(path)}


def load_frames(root):
    """Parse the prompt file into ordered frames, validating as we go."""
    path = prompt_path(root)
    if not os.path.isfile(path):
        die("prompt file not found at %s" % path)
    with open(path, encoding="utf-8") as fh:
        blocks = fh.read().strip().split("\n\n")
    frames, seen = [], set()
    for i, block in enumerate(blocks):
        m = FRAME_RE.match(block)
        if not m:
            die("frame %d in %s has no [MM:SS] marker; the file is malformed"
                % (i + 1, os.path.relpath(path, root)))
        ts, body = m.group(1), m.group(2)
        if "\n" in block:
            die("frame [%s] spans multiple lines; one frame per line is required" % ts)
        if ts in seen:
            die("duplicate timestamp [%s]" % ts)
        seen.add(ts)
        frames.append({
            "index": i,                       # 0-based, matches the filename
            "number": i + 1,                  # 1-based, matches the changelog
            "timestamp": ts,
            "filename": "%03d.png" % i,
            "character": LOCK_KEY in body or any(p in body for p in PREHISTORIC),
            "prompt": block,
        })
    secs = [int(f["timestamp"][:2]) * 60 + int(f["timestamp"][3:]) for f in frames]
    if any(secs[i] >= secs[i + 1] for i in range(len(secs) - 1)):
        die("timestamps are not strictly increasing")
    return frames


# ---------------------------------------------------------------- state

def frames_dir(root, create=False):
    d = os.path.join(paths.output_dir(root), FRAMES_SUBDIR)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def manifest_path(root):
    return os.path.join(frames_dir(root), MANIFEST)


def load_manifest(root, frames, batch_size):
    p = manifest_path(root)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            man = json.load(fh)
        if len(man.get("frames", [])) != len(frames):
            die("manifest has %d frames but the prompt file has %d; the prompt "
                "file changed under a live queue. Reconcile by hand, or run "
                "`reset` to start over."
                % (len(man.get("frames", [])), len(frames)))
        return man
    return {
        "episode": "why-you-check-your-phone",
        "created_utc": utcnow(),
        "updated_utc": utcnow(),
        "batch_size": batch_size,
        "total": len(frames),
        "frames": [{"index": f["index"], "timestamp": f["timestamp"],
                    "filename": f["filename"], "state": "pending",
                    "issued_utc": None, "verified_utc": None,
                    "width": None, "height": None, "bytes": None}
                   for f in frames],
    }


def save_manifest(root, man):
    frames_dir(root, create=True)
    man["updated_utc"] = utcnow()
    tmp = manifest_path(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(man, fh, indent=1)
    os.replace(tmp, manifest_path(root))


def counts(man):
    c = {"pending": 0, "issued": 0, "done": 0}
    for e in man["frames"]:
        c[e["state"]] = c.get(e["state"], 0) + 1
    return c


# ---------------------------------------------------------------- verify

def verify(root, man, quiet=False):
    """Scan the output directory; promote arrivals to done. Reports problems."""
    d = frames_dir(root)
    found, problems = 0, []
    for e in man["frames"]:
        path = os.path.join(d, e["filename"])
        if not os.path.isfile(path):
            if e["state"] == "done":
                e.update(state="issued", verified_utc=None,
                         width=None, height=None, bytes=None)
                problems.append("%s was marked done but is gone" % e["filename"])
            continue
        size = os.path.getsize(path)
        dims = png_size(path)
        if not dims:
            problems.append("%s is not a valid PNG" % e["filename"])
            continue
        if size < MIN_BYTES:
            problems.append("%s is only %d bytes; probably a failed render"
                            % (e["filename"], size))
            continue
        if e["state"] != "done":
            e["verified_utc"] = utcnow()
        e.update(state="done", width=dims[0], height=dims[1], bytes=size)
        found += 1
    if not quiet:
        print("verified %d of %d frames present in %s"
              % (found, man["total"], os.path.relpath(d, root)))
        for p in problems:
            print("  ! " + p)
    return found, problems


# ---------------------------------------------------------------- commands

def cmd_plan(args, root, frames, man):
    ref = load_reference(root)
    bs = man["batch_size"]
    nb = (len(frames) + bs - 1) // bs
    withchar = sum(1 for f in frames if f["character"])
    print("episode        : %s" % man["episode"])
    print("prompt file    : %s" % os.path.relpath(prompt_path(root), root))
    print("frames         : %d   %s -> %s"
          % (len(frames), frames[0]["timestamp"], frames[-1]["timestamp"]))
    print("character in   : %d frames (%.1f%%)" % (withchar, withchar / len(frames) * 100))
    print("reference      : %s  %dx%d  %.1f KB"
          % (ref["path"], ref["width"], ref["height"], ref["bytes"] / 1024))
    print("output         : %s/000.png .. %03d.png"
          % (os.path.relpath(frames_dir(root), root), len(frames) - 1))
    print("batch size     : %d   (canon concurrency cap)" % bs)
    print("batches        : %d" % nb)
    print()
    c = counts(man)
    print("state          : %d pending, %d issued, %d done"
          % (c["pending"], c["issued"], c["done"]))
    print()
    print("This script submits nothing. models.json locks stickman_art to")
    print("route 'manual' and credit_safeguard.pipeline_submits is false.")
    return 0


def cmd_next(args, root, frames, man):
    ref = load_reference(root)
    verify(root, man, quiet=True)
    c = counts(man)
    if c["issued"] and not args.force:
        stuck = [e["filename"] for e in man["frames"] if e["state"] == "issued"]
        print("%d frame(s) are still out: %s" % (len(stuck), ", ".join(stuck[:6])))
        print()
        print("The canon halts after every batch. Drop the returned files into")
        print("%s, then run `verify`." % os.path.relpath(frames_dir(root), root))
        print("To hand out the next batch anyway: --force")
        return 1
    todo = [e for e in man["frames"] if e["state"] == "pending"][:man["batch_size"]]
    if not todo:
        print("nothing pending — all %d frames are done." % man["total"])
        return 0
    by_index = {f["index"]: f for f in frames}
    out = frames_dir(root, create=True)
    print("=" * 78)
    print("BATCH — %d frame(s) of %d remaining" % (len(todo), counts(man)["pending"]))
    print("Model: nano-banana-pro   Route: manual (google-flow or meta-ai)")
    print("Attach as reference image, every frame: %s" % ref["path"])
    print("=" * 78)
    for e in todo:
        f = by_index[e["index"]]
        print()
        print("--- frame %03d  ·  [%s]  ·  save as %s"
              % (f["index"], f["timestamp"], f["filename"]))
        print()
        print(f["prompt"].split("] ", 1)[1])
        e.update(state="issued", issued_utc=utcnow())
    print()
    print("=" * 78)
    print("HALT. Run these %d, save them into %s, then:"
          % (len(todo), os.path.relpath(out, root)))
    print("    python3 scripts/generate_frames.py verify")
    print("=" * 78)
    save_manifest(root, man)
    return 0


def cmd_verify(args, root, frames, man):
    found, problems = verify(root, man)
    save_manifest(root, man)
    c = counts(man)
    print("state: %d pending, %d issued, %d done" % (c["pending"], c["issued"], c["done"]))
    return 1 if problems else 0


def cmd_status(args, root, frames, man):
    verify(root, man, quiet=True)
    save_manifest(root, man)
    c = counts(man)
    done, total = c["done"], man["total"]
    width = 40
    filled = int(width * done / total) if total else 0
    print("[%s%s] %d/%d  %.1f%%"
          % ("#" * filled, "." * (width - filled), done, total, done / total * 100))
    print("pending %d · issued %d · done %d" % (c["pending"], c["issued"], c["done"]))
    if args.verbose:
        print()
        for e in man["frames"]:
            mark = {"pending": " ", "issued": ">", "done": "x"}[e["state"]]
            dims = ("%dx%d" % (e["width"], e["height"])) if e["width"] else ""
            print("  [%s] %s  [%s]  %s" % (mark, e["filename"], e["timestamp"], dims))
    else:
        nxt = [e for e in man["frames"] if e["state"] == "pending"]
        if nxt:
            print("next up: %s" % ", ".join(e["filename"] for e in nxt[:man["batch_size"]]))
    return 0


def cmd_reset(args, root, frames, man):
    if not args.yes:
        die("reset clears all queue state. Re-run with --yes to confirm. "
            "Generated .png files are left alone.")
    p = manifest_path(root)
    if os.path.isfile(p):
        os.remove(p)
        print("removed %s" % os.path.relpath(p, root))
    else:
        print("no manifest to remove")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="scripts/generate_frames.py",
        description="Drive the Nano Banana Pro frame queue. Submits nothing.")
    ap.add_argument("--root", help="repository root (default: auto-detect)")
    ap.add_argument("--batch-size", type=int, default=BATCH_DEFAULT,
                    help="frames per batch (default %d, the canon cap)" % BATCH_DEFAULT)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("plan", help="parse, validate and show the batch plan")
    p = sub.add_parser("next", help="emit the next batch as a work sheet")
    p.add_argument("--force", action="store_true",
                   help="hand out a batch while frames are still outstanding")
    sub.add_parser("verify", help="scan the output directory and record arrivals")
    p = sub.add_parser("status", help="show progress")
    p.add_argument("-v", "--verbose", action="store_true", help="list every frame")
    p = sub.add_parser("reset", help="clear queue state")
    p.add_argument("--yes", action="store_true", help="confirm")
    args = ap.parse_args(argv)
    if not args.cmd:
        ap.print_help()
        return 2

    root = args.root or paths.find_root()
    if args.batch_size < 1:
        die("--batch-size must be at least 1")
    if args.batch_size > BATCH_DEFAULT:
        die("--batch-size %d exceeds the canon concurrency cap of %d "
            "(references/style-rules.md section 1). Bulk generation is a "
            "documented failure mode, not a speed option."
            % (args.batch_size, BATCH_DEFAULT))

    frames = load_frames(root)
    man = load_manifest(root, frames, args.batch_size)
    man["batch_size"] = args.batch_size
    return {"plan": cmd_plan, "next": cmd_next, "verify": cmd_verify,
            "status": cmd_status, "reset": cmd_reset}[args.cmd](args, root, frames, man)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # Piping into `head` closes stdout early. Exit quietly rather than
        # dumping a traceback over the output the user asked for.
        try:
            sys.stdout.close()
        finally:
            os._exit(0)
