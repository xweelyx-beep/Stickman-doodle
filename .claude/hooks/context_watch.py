#!/usr/bin/env python3
"""UserPromptSubmit hook: warn once when the session is getting long.

Hooks are not given context-window usage — only the status line is (see
.claude/statusline.py). What a hook does get is transcript_path, so this uses
transcript size as a proxy and says so. The number is an estimate of session
length, not a token count.

Fires at most once per threshold per session, so it stays silent until it has
something to say. Never blocks a prompt: any failure exits 0.
"""

import json
import os
import sys

# Transcript megabytes -> what to say. Ordered low to high.
THRESHOLDS = (
    (8.0, "This session's transcript is ~%.0f MB. Wrap up the current step, run "
          "`python3 scripts/core/memory.py checkpoint --note \"<where you are>\"` "
          "to put the position on disk, then /compact."),
    (16.0, "This session's transcript is ~%.0f MB and compaction is close. "
           "Checkpoint now with `python3 scripts/core/memory.py checkpoint` — "
           "finish nothing new until the position is on disk."),
)


def state_path(root, session_id):
    d = os.path.join(root, ".claude", "state")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "context-watch-%s.json" % (session_id or "unknown")[:64])


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    transcript = payload.get("transcript_path")
    if not transcript or not os.path.isfile(transcript):
        return 0

    try:
        mb = os.path.getsize(transcript) / (1024.0 * 1024.0)
    except OSError:
        return 0

    hit = None
    for limit, message in THRESHOLDS:
        if mb >= limit:
            hit = (limit, message % mb)
    if not hit:
        return 0

    path = state_path(root, payload.get("session_id"))
    try:
        fired = json.load(open(path, encoding="utf-8")).get("fired", [])
    except Exception:
        fired = []
    if hit[0] in fired:
        return 0
    fired.append(hit[0])
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"fired": fired}, fh)
    except OSError:
        pass

    json.dump({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": hit[1] + " (Transcript size is a proxy for session "
                                      "length, not a measured token count.)",
    }}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
