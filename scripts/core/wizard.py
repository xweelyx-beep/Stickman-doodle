#!/usr/bin/env python3
"""The guided flow behind /faceless-studio.

Two numbered questions — which channel, then what to do — and every answer
resolves to the exact command to run next. It holds no state of its own: the
channel list comes from the canon, the resume position comes from
automation/memory/session_state.json, and the gate position comes from the
episode's state.json.

`--json` emits the menu and the resolved command so an agent can render the same
flow it would show a human at a terminal, and neither can drift from the other.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory  # noqa: E402
import scheduler  # noqa: E402
from canon import CHANNELS, load_canon, repo_root  # noqa: E402
from state_manager import GATES, EpisodeState  # noqa: E402

CHANNEL_MENU = (
    ("1", "known-unknowns", "Known Unknowns", "long-form science, 8–11 min"),
    ("2", "lilweid", "Lilweid", "cinematic self-mastery and money, 1:30–3:30"),
    ("3", "stickman", "Stickman", "2D explainer; canon partly blocked"),
)

ACTION_MENU = (
    ("1", "new", "Start New Episode", "topic → SEO → gate 1"),
    ("2", "resume", "Resume Active Episode", "pick up at the open gate"),
    ("3", "metrics", "Ingest & Analyze Metrics", "CTR, retention, AVD → pacing fixes"),
    ("4", "schedule", "View Publishing Schedule", "upcoming slots and today's queue"),
)


def channel_menu(root):
    """Channel options, each annotated with what the canon can and cannot do."""
    out = []
    for key, slug, label, blurb in CHANNEL_MENU:
        canon = load_canon(slug, root)
        blocked = []
        if not canon.voice_lock:
            blocked.append("voice")
        if not canon.beats:
            blocked.append("architecture")
        if canon.visual_blocked:
            blocked.append("visual system")
        out.append({
            "key": key, "channel": slug, "label": label, "blurb": blurb,
            "pace": canon.seconds_per_scene,
            "runtime_range_s": list(canon.runtime_range_s) if canon.runtime_range_s else None,
            "blocked": blocked,
            "ready": not blocked,
        })
    return out


def action_menu(root, channel):
    """Action options, with the ones that cannot run right now marked and why."""
    active = memory.resume(root) or {}
    episodes = list_episodes(root, channel)
    out = []
    for key, action, label, blurb in ACTION_MENU:
        available, reason = True, None
        if action == "resume":
            available = bool(episodes)
            reason = None if available else "no episodes yet on this channel"
        if action == "metrics":
            done = [e for e in episodes if e["state"] in ("RENDERED", "PUBLISHED")]
            available = bool(done)
            reason = None if available else "no episode has reached RENDERED yet"
        out.append({
            "key": key, "action": action, "label": label, "blurb": blurb,
            "available": available, "unavailable_reason": reason,
            "active_here": active.get("channel") == channel and action == "resume",
        })
    return out


def list_episodes(root, channel):
    base = os.path.join(root, "channels", channel, "episodes")
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base)):
        if not os.path.isfile(os.path.join(base, name, "state.json")):
            continue
        state = EpisodeState.load(root, channel, name)
        out.append({"episode_id": name, "state": state.state, "next": state.next_action(),
                    "topic": state.data.get("topic")})
    return out


def next_command(root, channel, action, episode_id=None, topic=None):
    """The literal command line for the chosen action — nothing paraphrased."""
    base = "python automation/run.py"
    if action == "new":
        dup = memory.check_topic(root, topic, channel) if topic else None
        if dup and dup["duplicate"]:
            return {
                "action": action, "blocked": True,
                "reason": "This topic is already in topic_history.json: %s"
                          % dup["exact_matches"][0].get("episode_id", "recorded earlier"),
                "command": None, "duplicate_check": dup,
            }
        return {
            "action": action, "blocked": False,
            "duplicate_check": dup,
            "command": '%s init --channel %s --topic "%s"' % (base, channel, topic or "<topic>"),
            "then": "review 01_ideation_and_seo.md, then approve gate 1 with --title <n>",
        }
    if action == "resume":
        episodes = list_episodes(root, channel)
        target = ([e for e in episodes if e["episode_id"] == episode_id] or episodes)
        if not target:
            return {"action": action, "blocked": True,
                    "reason": "no episodes on %s yet" % channel, "command": None}
        ep = target[-1]
        state = EpisodeState.load(root, channel, ep["episode_id"])
        pending = [k for k in sorted(GATES) if state.gate(k)["status"] == "pending"]
        if pending:
            gate = pending[0]
            extra = {"1": " --title <n>", "2": "", "3": " --credits <n>"}[gate]
            command = "%s approve --channel %s --episode %s --gate %s%s --by <you>" % (
                base, channel, ep["episode_id"], gate, extra)
        else:
            stage = {"DRAFT": "script", "SCRIPT_APPROVED": "prompts",
                     "PROMPTS_STAGED": "package", "RENDERED": "package --publish",
                     "PUBLISHED": None}[state.state]
            command = ("%s %s --channel %s --episode %s" % (base, stage, channel,
                                                            ep["episode_id"])
                       if stage else None)
        return {"action": action, "blocked": False, "episode_id": ep["episode_id"],
                "state": state.state, "command": command, "then": state.next_action()}
    if action == "metrics":
        episodes = [e for e in list_episodes(root, channel)
                    if e["state"] in ("RENDERED", "PUBLISHED")]
        if not episodes:
            return {"action": action, "blocked": True,
                    "reason": "no episode has reached RENDERED", "command": None}
        ep = episode_id or episodes[-1]["episode_id"]
        return {
            "action": action, "blocked": False, "episode_id": ep,
            "command": ('%s analyze --channel %s --episode %s '
                        '--metrics \'{"ctr_percent": <n>, "retention_30s_percent": <n>, '
                        '"average_view_duration_s": <n>}\'' % (base, channel, ep)),
            "then": "writes 06_performance_audit.md; add --record-learning <n> to keep a fix",
        }
    if action == "schedule":
        slots = scheduler.slots(root, channel)
        return {
            "action": action, "blocked": False,
            "cadence": slots["cadence"], "blocked_by_brand": slots["blocked"],
            "next_slots": [s["date"] for s in slots["slots"][:4]],
            "command": "%s schedule --channel %s" % (base, channel),
            "then": "`remind --kind shorts` or `--kind longform` for today's queue",
        }
    raise SystemExit("error: unknown action %r; expected one of %s"
                     % (action, ", ".join(a[1] for a in ACTION_MENU)))


def render_menu(title, rows, key_field="key"):
    L = ["", title, ""]
    for row in rows:
        mark = "" if row.get("available", True) else "  (unavailable — %s)" % row["unavailable_reason"]
        note = ""
        if row.get("blocked"):
            note = "  [blocked: %s]" % ", ".join(row["blocked"])
        L.append("  %s. %s — %s%s%s" % (row[key_field], row["label"], row["blurb"], note, mark))
    return "\n".join(L)


def ask(prompt, valid):
    """Read one numbered choice. Non-interactive input is an error, not a default."""
    try:
        answer = input(prompt).strip()
    except EOFError:
        raise SystemExit("error: no input available; use --channel/--action to run "
                         "the wizard non-interactively")
    if answer not in valid:
        raise SystemExit("error: %r is not one of %s" % (answer, ", ".join(sorted(valid))))
    return answer


def main(argv=None):
    ap = argparse.ArgumentParser(description="Guided flow for the faceless studio pipeline.")
    ap.add_argument("--channel", choices=CHANNELS, help="skip question 1")
    ap.add_argument("--action", choices=[a[1] for a in ACTION_MENU], help="skip question 2")
    ap.add_argument("--episode")
    ap.add_argument("--topic")
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    root = args.root or repo_root()

    channels = channel_menu(root)
    if args.json and not (args.channel and args.action):
        print(json.dumps({
            "step": 1 if not args.channel else 2,
            "channels": channels,
            "actions": action_menu(root, args.channel) if args.channel else None,
            "active": memory.resume(root),
        }, indent=2))
        return 0

    channel = args.channel
    if not channel:
        print(render_menu("Step 1 — select channel", channels))
        key = ask("\n  choice: ", {c["key"] for c in channels})
        channel = [c["channel"] for c in channels if c["key"] == key][0]

    actions = action_menu(root, channel)
    action = args.action
    if not action:
        print(render_menu("Step 2 — select action for %s" % channel, actions))
        key = ask("\n  choice: ", {a["key"] for a in actions})
        chosen = [a for a in actions if a["key"] == key][0]
        if not chosen["available"]:
            raise SystemExit("error: %s is unavailable — %s"
                             % (chosen["label"], chosen["unavailable_reason"]))
        action = chosen["action"]

    topic = args.topic
    if action == "new" and not topic and not args.json:
        try:
            topic = input("\n  topic: ").strip()
        except EOFError:
            topic = None

    result = next_command(root, channel, action, args.episode, topic)
    result["channel"] = channel
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print("")
    if result.get("blocked"):
        print("  BLOCKED: %s" % result["reason"])
        return 1
    dup = result.get("duplicate_check")
    if dup and dup["near_matches"]:
        print("  Near matches in topic history — check before proceeding:")
        for m in dup["near_matches"]:
            print("    %.0f%%  %s" % (m["similarity"] * 100, m["topic"]))
        print("")
    if result.get("command"):
        print("  Run:  %s" % result["command"])
    if result.get("then"):
        print("  Then: %s" % result["then"])
    for key in ("cadence", "next_slots", "state", "episode_id"):
        if result.get(key):
            print("  %-11s %s" % (key + ":", result[key]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
