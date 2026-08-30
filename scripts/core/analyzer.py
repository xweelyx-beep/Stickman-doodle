#!/usr/bin/env python3
"""Retention audit: what the numbers say, and which beats to cut.

Takes real metrics the operator read off YouTube Studio — CTR, 30-second
retention, average view duration, and audience comments — and turns them into
edits with timecodes, by laying the average view duration over the episode's own
beat sheet from state.json. "Viewers leave 41 seconds into beat 5" is a fix;
"improve retention" is not.

Two honesty rules hold throughout. No metric is ever invented or defaulted: a
figure the operator did not supply comes back None and its checks are skipped.
And every threshold prints its source, so a house default never reads as
evidence about these channels.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory  # noqa: E402
from canon import CHANNELS, load_canon, repo_root  # noqa: E402
try:
    import paths
except ImportError:  # imported as a package from run.py
    from . import paths
from seo_engine import timestamp  # noqa: E402
from state_manager import EPISODE_FILES, EpisodeState, utcnow, write_atomic  # noqa: E402

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "had",
    "has", "have", "how", "i", "in", "is", "it", "its", "just", "like", "me",
    "more", "my", "not", "of", "on", "or", "really", "so", "that", "the", "their",
    "them", "then", "there", "they", "this", "to", "too", "very", "was", "were",
    "what", "when", "why", "with", "you", "your", "video", "channel",
}


def load_thresholds(root):
    path = paths.config_path("analytics.json", root)
    if not os.path.isfile(path):
        raise SystemExit(f"error: missing {path}; the analytics config is part of the pipeline")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_path"] = os.path.relpath(path, root)
    return cfg


def load_metrics(spec):
    """Metrics come from a JSON file or inline key=value pairs. Nothing defaults."""
    if not spec:
        return {}
    if os.path.isfile(spec):
        with open(spec, "r", encoding="utf-8") as fh:
            return json.load(fh)
    try:
        return json.loads(spec)
    except ValueError:
        raise SystemExit(
            f"error: --metrics {spec!r} is neither a readable file nor valid JSON. "
            'Expected something like \'{"ctr_percent": 5.2, "retention_30s_percent": 61, '
            '"average_view_duration_s": 214}\''
        )


def check(name, value, spec, higher_is_better=True):
    """One metric against its threshold, with the threshold's provenance attached."""
    if value is None:
        return {"metric": name, "value": None, "verdict": "not supplied",
                "source": spec.get("source"), "floor": spec.get("floor"),
                "target": spec.get("target"),
                "threshold_basis": "not checked — no value supplied"}
    floor, target = spec.get("floor"), spec.get("target")
    if floor is None:
        verdict = "no threshold set"
    elif value < floor:
        verdict = "below floor"
    elif target is not None and value < target:
        verdict = "between floor and target"
    else:
        verdict = "at or above target"
    return {
        "metric": name, "value": value, "floor": floor, "target": target,
        "verdict": verdict,
        "source": spec.get("source"),
        "threshold_basis": spec.get("source") or "house default — not measured on this channel",
    }


def beat_at(beats, seconds):
    """Which beat contains a timecode, and how far into it."""
    for beat in beats:
        if beat["start_s"] <= seconds < beat["end_s"]:
            return beat, int(round(seconds - beat["start_s"]))
    if beats and seconds >= beats[-1]["end_s"]:
        return beats[-1], int(round(seconds - beats[-1]["start_s"]))
    return None, None


def pacing_fixes(beats, drop_seconds, canon_pace, actual_pace):
    """Concrete cuts: which beats to shorten, by how much, to move the drop later."""
    fixes = []
    drop_beat, into = beat_at(beats, drop_seconds) if drop_seconds is not None else (None, None)
    if drop_beat:
        before = [b for b in beats if b["number"] < drop_beat["number"]]
        # Aim to bring the drop point forward by a fifth of the runtime that
        # precedes it — enough to matter, small enough to cut without a rewrite.
        budget = int(round(sum(b["seconds"] for b in before) * 0.2))
        fixes.append({
            "kind": "drop point",
            "detail": "Average viewer leaves at %s, %ss into beat %d (%s)."
                      % (timestamp(drop_seconds), into, drop_beat["number"], drop_beat["name"]),
            "action": "Cut about %ss from beats 1-%d so the material after %s arrives sooner."
                      % (budget, drop_beat["number"] - 1, timestamp(drop_seconds))
                      if before else
                      "The drop is inside the opening beat. Rewrite the first %ss, not the rest."
                      % drop_beat["seconds"],
        })
        for b in sorted(before, key=lambda x: -x["seconds"])[:3]:
            share = b["seconds"] / float(sum(x["seconds"] for x in before)) if before else 0
            fixes.append({
                "kind": "beat cut",
                "detail": "Beat %d (%s) runs %ss from %s — %.0f%% of everything before the drop."
                          % (b["number"], b["name"], b["seconds"], b["timestamp"], share * 100),
                "action": "Take %ss out of it." % max(1, int(round(budget * share))),
            })
    if canon_pace and actual_pace:
        delta = actual_pace - canon_pace
        if abs(delta) >= 1.0:
            fixes.append({
                "kind": "pacing",
                "detail": "This episode runs %.2fs per scene against the channel's verified "
                          "%.2fs — %.2fs %s." % (actual_pace, canon_pace, abs(delta),
                                                 "slower" if delta > 0 else "faster"),
                "action": ("Add roughly %d more scene changes to reach canon pace."
                           % max(1, int(round(abs(delta) / canon_pace * 10))) if delta > 0 else
                           "Hold shots longer; the channel's verified pace is slower than this."),
            })
    return fixes


def recurring_feedback(comments, minimum):
    counts = {}
    for comment in comments or []:
        for word in {w for w in re.findall(r"[a-z']+", comment.lower())
                     if len(w) > 3 and w not in STOPWORDS}:
            counts[word] = counts.get(word, 0) + 1
    recurring = sorted(((w, c) for w, c in counts.items() if c >= minimum),
                       key=lambda x: (-x[1], x[0]))
    return [{"term": w, "mentions": c} for w, c in recurring[:12]]


def analyze(root, channel, episode_id, metrics, comments=None):
    canon = load_canon(channel, root)
    cfg = load_thresholds(root)
    state = EpisodeState.load(root, channel, episode_id)
    script = state.data.get("script") or {}
    beats = script.get("beats") or []
    runtime = script.get("runtime_target_s") or state.data.get("runtime_target_s")

    avd = metrics.get("average_view_duration_s")
    avd_ratio = round(avd / float(runtime), 3) if (avd and runtime) else None
    drop = metrics.get("drop_off_s", avd)

    actual_pace = (round(runtime / float(script["scene_total"]), 2)
                   if runtime and script.get("scene_total") else None)
    canon_pace = canon.seconds_per_scene
    configured_pace = cfg.get("pacing", {}).get(channel)
    pace_drift = (configured_pace is not None and canon_pace is not None
                  and abs(configured_pace - canon_pace) > 0.01)

    t = cfg["thresholds"]
    checks = [
        check("CTR %", metrics.get("ctr_percent"), t["ctr_percent"]),
        check("30s retention %", metrics.get("retention_30s_percent"), t["retention_30s_percent"]),
        check("AVD / runtime", avd_ratio, t["avd_ratio"]),
    ]
    supplied = [c for c in checks if c["value"] is not None]

    return {
        "channel": channel,
        "episode_id": episode_id,
        "title": state.gate("1")["payload"].get("chosen_title"),
        "state": state.state,
        "generated_utc": utcnow(),
        "runtime_target_s": runtime,
        "runtime_target": timestamp(runtime) if runtime else None,
        "metrics_supplied": sorted(metrics),
        "metrics_missing": [c["metric"] for c in checks if c["value"] is None],
        "average_view_duration_s": avd,
        "average_view_duration": timestamp(avd) if avd else None,
        "avd_ratio": avd_ratio,
        "drop_off_s": drop,
        "checks": checks,
        "below_floor": [c["metric"] for c in supplied if c["verdict"] == "below floor"],
        "canon_pace": canon_pace,
        "actual_pace": actual_pace,
        "configured_pace": configured_pace,
        "pace_config_drift": pace_drift,
        "fixes": pacing_fixes(beats, drop, canon_pace, actual_pace),
        "recurring_feedback": recurring_feedback(comments, cfg["feedback"]["min_mentions_to_flag"]),
        "comment_count": len(comments or []),
        "thresholds_path": cfg["_path"],
        "existing_learnings": memory.learnings_for(root, channel),
    }


def render_markdown(p):
    L = []
    A = L.append
    A("# 06 — Performance audit")
    A("")
    A("| Field | Value |")
    A("|---|---|")
    A("| Channel | `%s` |" % p["channel"])
    A("| Episode | `%s` |" % p["episode_id"])
    A("| Title | %s |" % (p["title"] or "_not selected_"))
    A("| Runtime | %s |" % (p["runtime_target"] or "unknown"))
    A("| Average view duration | %s |" % (p["average_view_duration"] or "not supplied"))
    A("| Generated | %s |" % p["generated_utc"])
    A("")
    if p["metrics_missing"]:
        A("> **Not supplied:** %s. Those checks were skipped rather than estimated."
          % ", ".join(p["metrics_missing"]))
        A("")
    A("## Metrics")
    A("")
    A("| Metric | Value | Floor | Target | Verdict | Threshold basis |")
    A("|---|---|---|---|---|---|")
    for c in p["checks"]:
        A("| %s | %s | %s | %s | %s | %s |" % (
            c["metric"], "—" if c["value"] is None else c["value"],
            c["floor"] if c["floor"] is not None else "—",
            c["target"] if c["target"] is not None else "—",
            c["verdict"], c["threshold_basis"]))
    A("")
    A("_Thresholds live in `%s`._" % p["thresholds_path"])
    A("")
    A("## Pacing")
    A("")
    A("| Source | Seconds per scene |")
    A("|---|---|")
    A("| Canon (verified episodes) | %s |" % (p["canon_pace"] or "unmeasured"))
    A("| This episode as written | %s |" % (p["actual_pace"] or "unknown"))
    A("")
    if p["pace_config_drift"]:
        A("> **Config drift:** `analytics.json` says %s s/scene, the canon parses to %s. "
          "The canon wins; fix the config." % (p["configured_pace"], p["canon_pace"]))
        A("")
    A("## Fixes")
    A("")
    if not p["fixes"]:
        A("No pacing fix could be computed — that needs an average view duration or a "
          "drop-off timecode, plus a beat sheet in `state.json`.")
    for f in p["fixes"]:
        A("### %s" % f["kind"])
        A("")
        A("%s" % f["detail"])
        A("")
        A("**Do:** %s" % f["action"])
        A("")
    A("## Recurring audience feedback")
    A("")
    if not p["recurring_feedback"]:
        A("Nothing recurred across %d comment(s) at the configured minimum."
          % p["comment_count"])
    else:
        A("| Term | Mentions |")
        A("|---|---|")
        for f in p["recurring_feedback"]:
            A("| %s | %d |" % (f["term"], f["mentions"]))
    A("")
    A("## Learnings already applied to this channel")
    A("")
    if not p["existing_learnings"]:
        A("None recorded yet. Approve a fix above with "
          "`python scripts/run.py analyze ... --record-learning <n>`.")
    else:
        A("| ID | Finding | Fix | Applied |")
        A("|---|---|---|---|")
        for e in p["existing_learnings"]:
            A("| %s | %s | %s | %d |" % (e["id"], e["finding"], e["fix"],
                                         e.get("applied_count", 0)))
    A("")
    return "\n".join(L).rstrip() + "\n"


def write_audit(root, payload):
    path = os.path.join(paths.episode_dir(root, payload["channel"],
                                          payload["episode_id"]),
                        "06_performance_audit.md")
    write_atomic(path, render_markdown(payload))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Retention audit and pacing fixes for one episode.")
    ap.add_argument("--channel", required=True, choices=CHANNELS)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--metrics", required=True,
                    help="path to a metrics JSON file, or inline JSON")
    ap.add_argument("--comments", help="path to a JSON list of comment strings")
    ap.add_argument("--record-learning", type=int, metavar="N",
                    help="record fix N from the audit into memory/learnings.json")
    ap.add_argument("--by", default=os.environ.get("USER", "operator"))
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = args.root or repo_root()
    comments = None
    if args.comments:
        if not os.path.isfile(args.comments):
            raise SystemExit(f"error: no comments file at {args.comments}")
        with open(args.comments, "r", encoding="utf-8") as fh:
            comments = json.load(fh)

    payload = analyze(root, args.channel, args.episode, load_metrics(args.metrics), comments)
    path = write_audit(root, payload)

    if args.record_learning:
        fixes = payload["fixes"]
        if not 1 <= args.record_learning <= len(fixes):
            raise SystemExit("error: --record-learning %d is out of range 1..%d"
                             % (args.record_learning, len(fixes)))
        fix = fixes[args.record_learning - 1]
        entry = memory.record_learning(
            root, args.channel, fix["detail"], fix["action"],
            source="%s/%s 06_performance_audit.md" % (args.channel, args.episode),
            metric=payload["below_floor"] or None, approved_by=args.by)
        print("recorded %s: %s" % (entry["id"], entry["fix"]))

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("wrote %s" % os.path.relpath(path, root))
        for c in payload["checks"]:
            print("  %-18s %-8s %s" % (c["metric"],
                                       "—" if c["value"] is None else c["value"], c["verdict"]))
        for f in payload["fixes"]:
            print("  fix: %s" % f["action"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
