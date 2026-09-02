#!/usr/bin/env python3
"""PreCompact hook: write the position to disk before context is discarded.

Compaction is the moment work gets lost. This records a dated note in
memory/session_state.json so the SessionStart hook — which fires
again straight after a compact — can hand the position back.

PreCompact cannot inject context (only SessionStart, UserPromptSubmit,
UserPromptExpansion and PostModelSwitch can), so this writes and stays quiet.
Never blocks a compaction: any failure exits 0.
"""

import json
import os
import subprocess
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    root = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or os.getcwd()
    note = "context compacted (%s, %s messages)" % (
        payload.get("trigger", "unknown"), payload.get("message_count", "?"))
    memory_cli = os.path.join(root, "scripts", "core", "memory.py")
    try:
        # Only annotate a position that already exists. Checkpointing with no
        # active episode would write an empty one and invent state.
        current = subprocess.run([sys.executable, memory_cli, "resume", "--json"],
                                 capture_output=True, text=True, timeout=10, cwd=root)
        active = json.loads(current.stdout or "null") if current.returncode == 0 else None
        if not (active and active.get("episode_id")):
            return 0
        subprocess.run([sys.executable, memory_cli, "checkpoint", "--note", note],
                       capture_output=True, text=True, timeout=10, cwd=root)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
