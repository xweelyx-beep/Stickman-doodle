#!/usr/bin/env python3
"""Cross-session memory: where we are, what we have already made, what we learned.

Three stores under automation/memory/, all plain JSON so a human can read and
correct them:

  session_state.json  active channel, episode and stage — survives a session ending
  topic_history.json  every topic, title and search term already published or in
                      flight, per platform, so the same idea is not shipped twice
  learnings.json      retention fixes that were approved, applied to future scripts

The deduplication check is deliberately conservative. It rejects an exact repeat
and flags a near match for a human to judge; it never silently rewrites a topic
to dodge its own check.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canon import CHANNELS, repo_root  # noqa: E402
from state_manager import utcnow, write_atomic  # noqa: E402

PLATFORMS = ("youtube", "tiktok", "instagram")
NEAR_MATCH_THRESHOLD = 0.55  # Jaccard on content words; above this a human decides

# Each entry is (filename, factory). A factory, not a literal: a shared literal
# would hand every caller the same mutable list, so the first append would leak
# into every later load in the same process.
STORES = {
    "session": ("session_state.json", lambda: {"schema": 1, "active": None, "history": []}),
    "topics": ("topic_history.json", lambda: {"schema": 1, "entries": []}),
    "learnings": ("learnings.json", lambda: {"schema": 1, "entries": []}),
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "how", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "their", "they", "this", "to", "up", "was", "what", "when", "why", "will",
    "with", "you", "your", "during", "while", "about", "into", "over", "after",
    "before", "really", "actually",
}


def memory_dir(root):
    path = os.path.join(root, "automation", "memory")
    os.makedirs(path, exist_ok=True)
    return path


def load(root, store):
    name, empty = STORES[store]
    path = os.path.join(memory_dir(root), name)
    if not os.path.isfile(path):
        return empty()
    with open(path, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except ValueError as exc:
            raise SystemExit(f"error: {path} is not valid JSON ({exc}); fix or delete it")


def save(root, store, data):
    name, _ = STORES[store]
    path = os.path.join(memory_dir(root), name)
    write_atomic(path, json.dumps(data, indent=2) + "\n")
    return path


# ------------------------------------------------------------------ session state

def checkpoint(root, channel=None, episode_id=None, stage=None, note=None):
    """Write where we are to disk. Called at every stage boundary so a session
    that runs out of context can be resumed cold from the next one."""
    data = load(root, "session")
    active = data.get("active") or {}
    active.update({k: v for k, v in (("channel", channel), ("episode_id", episode_id),
                                     ("stage", stage)) if v is not None})
    active["updated_utc"] = utcnow()
    if note:
        active["note"] = note
    data["active"] = active
    data.setdefault("history", []).append({
        "utc": active["updated_utc"], "channel": active.get("channel"),
        "episode_id": active.get("episode_id"), "stage": active.get("stage"), "note": note,
    })
    data["history"] = data["history"][-200:]
    save(root, "session", data)
    return active


def resume(root):
    return (load(root, "session") or {}).get("active")


def clear_session(root):
    data = load(root, "session")
    data["active"] = None
    save(root, "session", data)


# ------------------------------------------------------------- topic deduplication

def _words(text):
    return {w for w in re.findall(r"[a-z0-9']+", (text or "").lower()) if w not in STOPWORDS}


def similarity(a, b):
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / float(len(wa | wb))


def check_topic(root, topic, channel=None, platforms=None):
    """Exact repeat -> blocked. Near match -> flagged, a human decides."""
    data = load(root, "topics")
    platforms = [p.lower() for p in (platforms or PLATFORMS)]
    exact, near = [], []
    norm = " ".join(sorted(_words(topic)))
    for entry in data.get("entries", []):
        if entry.get("platforms") and not set(entry["platforms"]) & set(platforms):
            continue
        if " ".join(sorted(_words(entry.get("topic", "")))) == norm:
            exact.append(entry)
            continue
        score = max(similarity(topic, entry.get("topic", "")),
                    max([similarity(topic, t) for t in entry.get("titles", [])] or [0.0]))
        if score >= NEAR_MATCH_THRESHOLD:
            near.append(dict(entry, similarity=round(score, 3)))
    near.sort(key=lambda e: -e["similarity"])
    return {
        "topic": topic,
        "channel": channel,
        "platforms": platforms,
        "duplicate": bool(exact),
        "exact_matches": exact,
        "near_matches": near[:5],
        "verdict": ("blocked — already made" if exact else
                    "review — close to %d past topic(s)" % len(near) if near else "clear"),
    }


def record_topic(root, topic, channel, episode_id=None, titles=None, search_terms=None,
                 platforms=None, published_utc=None):
    data = load(root, "topics")
    data.setdefault("entries", []).append({
        "topic": topic,
        "channel": channel,
        "episode_id": episode_id,
        "titles": titles or [],
        "search_terms": search_terms or [],
        "platforms": [p.lower() for p in (platforms or PLATFORMS)],
        "recorded_utc": utcnow(),
        "published_utc": published_utc,
    })
    save(root, "topics", data)
    return data["entries"][-1]


# ------------------------------------------------------------------------ learnings

def record_learning(root, channel, finding, fix, source, metric=None, approved_by=None):
    data = load(root, "learnings")
    entry = {
        "id": "L%03d" % (len(data.get("entries", [])) + 1),
        "channel": channel,
        "finding": finding,
        "fix": fix,
        "metric": metric,
        "source": source,
        "approved_by": approved_by,
        "recorded_utc": utcnow(),
        "applied_count": 0,
    }
    data.setdefault("entries", []).append(entry)
    save(root, "learnings", data)
    return entry


def learnings_for(root, channel):
    """Everything the pipeline has been told to do differently on this channel."""
    return [e for e in load(root, "learnings").get("entries", [])
            if e.get("channel") in (channel, "all")]


def mark_applied(root, ids):
    data = load(root, "learnings")
    for entry in data.get("entries", []):
        if entry["id"] in ids:
            entry["applied_count"] = entry.get("applied_count", 0) + 1
            entry["last_applied_utc"] = utcnow()
    save(root, "learnings", data)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Cross-session memory, dedup and learnings.")
    sub = ap.add_subparsers(dest="action", required=True)

    p = sub.add_parser("resume", help="print the active channel/episode/stage")
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("checkpoint", help="write the active position to disk")
    p.add_argument("--channel", choices=CHANNELS)
    p.add_argument("--episode")
    p.add_argument("--stage")
    p.add_argument("--note")
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("check-topic", help="is this topic already made?")
    p.add_argument("--topic", required=True)
    p.add_argument("--channel", choices=CHANNELS)
    p.add_argument("--platform", action="append", dest="platforms", choices=PLATFORMS)
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("record-topic", help="add a topic to the anti-duplication history")
    p.add_argument("--topic", required=True)
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--episode")
    p.add_argument("--title", action="append", dest="titles")
    p.add_argument("--platform", action="append", dest="platforms", choices=PLATFORMS)
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("learnings", help="list learnings that apply to a channel")
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    root = args.root or repo_root()

    if args.action == "resume":
        active = resume(root)
        print(json.dumps(active, indent=2) if args.json else
              ("no active episode" if not active else
               "%s / %s  stage=%s  (%s)" % (active.get("channel"), active.get("episode_id"),
                                            active.get("stage"), active.get("updated_utc"))))
    elif args.action == "checkpoint":
        active = checkpoint(root, args.channel, args.episode, args.stage, args.note)
        print(json.dumps(active, indent=2) if args.json else
              "checkpointed: %s / %s stage=%s" % (active.get("channel"),
                                                  active.get("episode_id"), active.get("stage")))
    elif args.action == "check-topic":
        result = check_topic(root, args.topic, args.channel, args.platforms)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("%s: %s" % (result["topic"], result["verdict"]))
            for m in result["near_matches"]:
                print("  near %.0f%%  %s (%s)" % (m["similarity"] * 100, m["topic"], m["channel"]))
        return 2 if result["duplicate"] else 0
    elif args.action == "record-topic":
        entry = record_topic(root, args.topic, args.channel, args.episode,
                             args.titles, None, args.platforms)
        print(json.dumps(entry, indent=2) if args.json else "recorded: %s" % entry["topic"])
    elif args.action == "learnings":
        entries = learnings_for(root, args.channel)
        if args.json:
            print(json.dumps(entries, indent=2))
        else:
            for e in entries:
                print("%s [%s] %s -> %s" % (e["id"], e["channel"], e["finding"], e["fix"]))
            if not entries:
                print("no learnings recorded for %s yet" % args.channel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
