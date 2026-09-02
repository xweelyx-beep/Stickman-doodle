#!/usr/bin/env python3
"""Status line: model, branch, and how full the context window is.

The status line is the only surface Claude Code hands live context-window
usage to — hooks do not get it. Reads the session JSON on stdin and prints one
line. Standard library only, so there is no jq dependency.

Bar turns to a word at 70% and to a demand at 85%:
    [Opus 4.5] main  ▓▓▓▓▓▓░░░░  62%
    [Opus 4.5] main  ▓▓▓▓▓▓▓▓▓░  88% compact soon
"""

import json
import os
import subprocess
import sys

WIDTH = 10
WARN, URGENT = 70, 85


def branch(cwd):
    try:
        out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True, timeout=3, cwd=cwd)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def bar(pct):
    filled = int(round(pct / 100.0 * WIDTH))
    return "▓" * filled + "░" * (WIDTH - filled)


def main():
    try:
        d = json.load(sys.stdin)
    except Exception:
        return 0

    parts = []
    model = (d.get("model") or {}).get("display_name")
    if model:
        parts.append("[%s]" % model)

    cwd = d.get("cwd") or os.getcwd()
    b = branch(cwd)
    if b:
        parts.append(b)

    # null before the first API call, and again after /compact until the next one
    pct = (d.get("context_window") or {}).get("used_percentage")
    if pct is None:
        parts.append("context —")
    else:
        pct = float(pct)
        note = " compact soon" if pct >= URGENT else (" watch context" if pct >= WARN else "")
        parts.append("%s %d%%%s" % (bar(pct), int(pct), note))

    # Pro/Max only, and only after the first response; absent is normal.
    five = ((d.get("rate_limits") or {}).get("five_hour") or {}).get("used_percentage")
    if five is not None:
        parts.append("5h %d%%" % int(float(five)))

    print("  ".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
