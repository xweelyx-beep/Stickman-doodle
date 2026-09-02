#!/usr/bin/env python3
"""SessionStart hook: put the position back in front of the agent.

Reads the hook payload on stdin and prints a compact digest as
additionalContext: where the pipeline stopped, what the channel has been told
to do differently, and where the durable notes live. Runs on startup, resume,
clear and — the one that matters — compact, so a compacted session comes back
knowing what it was doing.

Never blocks a session: any failure exits 0 with no context.
"""

import json
import os
import subprocess
import sys

MAX_CHARS = 2000
DIGEST_SECTION = "## Standing decisions"


def repo_root(payload):
    return os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()


def run(root, args, timeout=10):
    """Call the pipeline's own memory CLI rather than re-reading its JSON."""
    try:
        out = subprocess.run(
            [sys.executable, os.path.join(root, "scripts", "core", "memory.py")] + args,
            capture_output=True, text=True, timeout=timeout, cwd=root)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def active_position(root):
    raw = run(root, ["resume", "--json"])
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data or None


def standing_decisions(root):
    """The '## Standing decisions' block of the memory hub, bounded."""
    path = os.path.join(root, ".claude", "memory.md")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ""
    # Match the heading as a whole line. Prose above it mentions the section by
    # name, and a substring search would return that instead.
    out, collecting = [], False
    for line in text.splitlines():
        if line.strip() == DIGEST_SECTION:
            collecting = True
            continue
        if collecting and line.startswith("#"):
            break
        if collecting:
            out.append(line)
    return "\n".join(out).strip()[:MAX_CHARS]


def build(root):
    lines = []
    active = active_position(root)
    if active and active.get("episode_id"):
        lines.append(
            "Pipeline position (memory/session_state.json): %s / %s, stage=%s, "
            "updated %s." % (active.get("channel"), active.get("episode_id"),
                             active.get("stage"), active.get("updated_utc")))
        if active.get("note"):
            lines.append("Last note: %s" % active["note"])
        if active.get("channel") and active.get("episode_id"):
            lines.append("Resume with: python3 scripts/run.py status --channel %s --episode %s"
                         % (active["channel"], active["episode_id"]))
        learnings = run(root, ["learnings", "--channel", active["channel"]]) \
            if active.get("channel") else ""
        if learnings and "no learnings" not in learnings:
            lines.append("Applies to this channel:\n%s" % learnings[:600])
    else:
        lines.append("No active episode checkpointed. Start one with "
                     "`python3 scripts/run.py wizard`.")

    decisions = standing_decisions(root)
    if decisions:
        lines.append("Standing decisions (.claude/memory.md):\n%s" % decisions)

    return "\n".join(lines)[:MAX_CHARS + 800]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    try:
        context = build(repo_root(payload))
    except Exception:
        return 0
    if not context:
        return 0
    json.dump({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
