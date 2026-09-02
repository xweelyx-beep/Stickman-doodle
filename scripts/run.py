#!/usr/bin/env python3
"""The four-command production workflow, with the three approval gates between.

    init     -> writes 01_ideation_and_seo.md,  opens GATE 1 (title & hook)
    script   -> writes 02_narration_script.md,  opens GATE 2 (script)
    prompts  -> writes 03/04 KIE prompts,       opens GATE 3 (credit spend)
    package  -> writes 05_metadata.md and metadata.json, updates publish-plan.csv,
                RENDERED/PUBLISHED

Each generate command stops at its gate and does nothing further. There is no
--approve flag on any of them: approval is always a separate invocation of
`approve`, by a person, recorded with their name and the time. That separation
is the 5%.
"""

import argparse
import csv
import datetime
import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "core"))

from canon import CHANNELS, load_canon, repo_root            # noqa: E402
import kie_prompt_builder                                     # noqa: E402
import analyzer                                               # noqa: E402
import memory                                                 # noqa: E402
import scheduler                                              # noqa: E402
import wizard                                                 # noqa: E402
import script_engine                                          # noqa: E402
import seo_engine                                             # noqa: E402
import seo_generator                                          # noqa: E402
from state_manager import (EPISODE_FILES, EpisodeState, channel_dir,  # noqa: E402
                           episode_dir, utcnow, write_atomic)

PUBLISH_PLAN = scheduler.PLAN
PLAN_COLUMNS = scheduler.PLAN_COLUMNS

# Token-overflow protection. state.json carries the full script and SEO payloads,
# so a long-form episode's state grows past what is comfortable to hold in a
# session. Past this size the pipeline checkpoints and says to start fresh
# rather than letting a session quietly run out of room mid-gate.
STATE_WARN_KB = 96


def rel(root, path):
    return os.path.relpath(path, root)


def write_episode_file(state, root, key, text):
    path = os.path.join(state.dir, EPISODE_FILES[key])
    write_atomic(path, text)
    state.record_artifact(key, rel(root, path), bytes=len(text.encode("utf-8")))
    return path


def checkpoint_and_warn(root, state, stage):
    """Record the position, then say plainly when the session should be restarted."""
    memory.checkpoint(root, state.data["channel"], state.data["episode_id"], stage)
    size_kb = os.path.getsize(state.path) / 1024.0
    if size_kb < STATE_WARN_KB:
        return None
    message = (
        "state.json is %.0f KB. Everything needed to continue is on disk and the position "
        "is checkpointed, so finish this session and open a fresh one, then run:\n"
        "    python scripts/run.py status --channel %s --episode %s"
        % (size_kb, state.data["channel"], state.data["episode_id"]))
    print("")
    banner(["TOKEN OVERFLOW PROTECTION"] + message.split("\n"))
    return message


def banner(lines):
    width = max(len(l) for l in lines) + 2
    print("+" + "-" * width + "+")
    for l in lines:
        print("| " + l.ljust(width - 1) + "|")
    print("+" + "-" * width + "+")


# --------------------------------------------------------------------------- init

def cmd_init(args, root):
    dup = memory.check_topic(root, args.topic, args.channel)
    if dup["duplicate"] and not args.allow_duplicate:
        prior = dup["exact_matches"][0]
        raise SystemExit(
            "error: this topic is already in the memory store (memory/topic_history.json) — "
            "%s on %s (%s). Pick a different angle, or pass --allow-duplicate to make it "
            "anyway." % (prior.get("episode_id") or "recorded", prior.get("channel"),
                         prior.get("recorded_utc")))

    payload = seo_engine.generate(
        args.channel, args.topic, args.keywords,
        seo_engine.parse_duration(args.runtime) if args.runtime else None,
        root, args.allow_provisional_architecture,
    )
    episode_id = args.episode_id or "%s-%s" % (
        datetime.date.today().strftime("%Y%m%d"), seo_engine.slugify(args.topic, 48))

    state = EpisodeState.create(root, args.channel, episode_id, args.topic)
    state.data["seo"] = payload
    state.data["runtime_target_s"] = payload["runtime_target_s"]
    state.data["keywords"] = payload["keywords"]
    state.save()

    state.data["topic_check"] = dup
    memory.record_topic(root, args.topic, args.channel, episode_id,
                        titles=[t["text"] for t in payload["titles"]],
                        search_terms=payload["keywords"])

    write_episode_file(state, root, "seo", seo_engine.render_markdown(payload))
    state.open_gate("1", payload={
        "titles": [t["text"] for t in payload["titles"]],
        "hook_beat": payload["hook"]["beat"],
    })

    if args.json:
        print(json.dumps({"episode_id": episode_id, "state": state.state,
                          "dir": rel(root, state.dir), "seo": payload}, indent=2))
        return 0
    print("wrote %s" % rel(root, os.path.join(state.dir, EPISODE_FILES["seo"])))
    print("state: DRAFT  ·  runtime target %s  ·  %s scenes at %ss"
          % (payload["runtime_target"], payload["scene_estimate"], payload["seconds_per_scene"]))
    print()
    for i, t in enumerate(payload["titles"], 1):
        print("  %d. [%s] %s" % (i, t["label"], t["text"]))
    print()
    print("  hook: %s" % payload["hook"]["draft"])
    if dup["near_matches"]:
        print()
        print("  near matches in topic history:")
        for m in dup["near_matches"]:
            print("    %.0f%%  %s (%s)" % (m["similarity"] * 100, m["topic"], m["channel"]))
    print()
    checkpoint_and_warn(root, state, "gate-1-open")
    banner([
        "GATE 1 — TITLE & HOOK. Nothing else runs until a person approves.",
        "Read %s, then:" % EPISODE_FILES["seo"],
        "  python scripts/run.py approve --channel %s \\" % args.channel,
        "      --episode %s --gate 1 --title <1|2|3> --by <you>" % episode_id,
    ])
    return 0


# ------------------------------------------------------------------------- script

def cmd_script(args, root):
    state = EpisodeState.load(root, args.channel, args.episode)
    state.require_command("script")
    seo = state.data.get("seo") or {}
    title = state.gate("1")["payload"].get("chosen_title")

    payload = script_engine.generate(
        args.channel, state.data["topic"], seo.get("keywords"),
        state.data.get("runtime_target_s"), root, args.wpm,
        args.allow_provisional_architecture, args.seconds_per_scene,
        args.variant, title, args.signoff, args.force_signoff, args.voice_lock,
    )
    payload["titles"] = seo.get("titles", [])
    state.data["script"] = payload
    state.save()

    rendered = script_engine.render_markdown(payload)
    write_episode_file(state, root, "script", rendered)
    # Count markers in the file the operator will actually edit, so the number
    # here is the same number gate 2 enforces against.
    markers = script_engine.unresolved_markers(rendered)
    state.open_gate("2", payload={
        "word_budget": payload["word_budget_total"],
        "estimated_runtime": payload["estimated_runtime"],
        "unresolved_markers": len(markers),
    })

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("wrote %s" % rel(root, os.path.join(state.dir, EPISODE_FILES["script"])))
    print("beats %d  ·  scenes %d  ·  words %d  ·  estimated %s (target %s)" % (
        len(payload["beats"]), payload["scene_total"], payload["word_budget_total"],
        payload["estimated_runtime"], payload["runtime_target"]))
    print("unresolved markers in the file: %d (%d FILL, %d CITE)" % (
        len(markers), markers.count("FILL"), markers.count("CITE")))
    if payload["learnings_applied"]:
        print("learnings carried in: %s" % ", ".join(
            e["id"] for e in payload["learnings_applied"]))
        memory.mark_applied(root, [e["id"] for e in payload["learnings_applied"]])
    print("sign-off: %s (%s)" % (payload["signoff"]["line"] or "none",
                                 payload["signoff"]["source"]))
    print()
    checkpoint_and_warn(root, state, "gate-2-open")
    banner([
        "GATE 2 — SCRIPT. Fill every «FILL» and «CITE» marker by hand,",
        "then approve. Gate 2 refuses while markers remain.",
        "  python scripts/run.py approve --channel %s \\" % args.channel,
        "      --episode %s --gate 2 --by <you>" % args.episode,
    ])
    return 0


# ------------------------------------------------------------------------ prompts

def cmd_prompts(args, root):
    state = EpisodeState.load(root, args.channel, args.episode)
    state.require_command("prompts")
    script_payload = state.data.get("script")
    if not script_payload:
        raise SystemExit("error: no script payload in state.json; run `script` first")

    payload = kie_prompt_builder.generate(
        args.channel, script_payload, root, args.style_key, args.video_model,
        args.image_model, script_payload.get("titles"), args.shorts, args.episode,
    )
    state.data["prompts"] = {
        "video_model": payload["video_model"],
        "video_model_display": payload["video_model_display"],
        "resolution": payload["resolution"],
        "prompt_standard": payload["prompt_standard"],
        "manual_image_handoff": bool(payload.get("manual_image_handoff")),
        "scene_count": payload["scene_count"],
        "blocks": payload["blocks"],
        "aspect_ratio": payload["aspect_ratio"],
        "image_model": payload["image_model"],
        "cost_estimate": payload["cost_estimate"],
        "style_key": payload["style_key"],
        "production_constraints": payload["production_constraints"],
    }
    state.save()

    write_episode_file(state, root, "video_prompts", json.dumps(payload, indent=2) + "\n")
    write_episode_file(state, root, "thumbnail_prompts",
                       kie_prompt_builder.render_thumbnail_markdown(payload))
    cost = payload["cost_estimate"]
    state.open_gate("3", payload={"cost_estimate": cost})

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("wrote %s" % rel(root, os.path.join(state.dir, EPISODE_FILES["video_prompts"])))
    print("wrote %s" % rel(root, os.path.join(state.dir, EPISODE_FILES["thumbnail_prompts"])))
    print()
    print("BATCH: %d clips of %ss in %d blocks = %ss of video, plus %d thumbnail images"
          % (cost["video_clips"], cost["clip_seconds"], cost["blocks"],
             cost["video_seconds"], cost["thumbnail_images"]))
    print("CREDITS: %s" % (cost["total_credits"] if cost["total_credits"] is not None
                           else "not computed — %s" % cost["note"]))
    print("MODEL: %s, %s %s, locked in %s" % (
        payload["video_model_display"], payload["prompt_standard"], payload["aspect_ratio"],
        payload["models_path"]))
    if payload.get("manual_image_handoff"):
        h = payload["manual_image_handoff"]
        print("MANUAL: %d %s images to run by hand via %s — not automated"
              % (len(h["queue"]), h["model"], " or ".join(h["route_options"])))
    print()
    checkpoint_and_warn(root, state, "gate-3-open")
    banner([
        "GATE 3 — CREDIT SPEND. Nothing is submitted to KIE by this pipeline.",
        "State the spend you are approving; it is written to the approval log.",
        "  python scripts/run.py approve --channel %s \\" % args.channel,
        "      --episode %s --gate 3 --credits <n> --by <you>" % args.episode,
    ])
    return 0


# ------------------------------------------------------------------------ package

def build_metadata(state, root, publish_date):
    seo = state.data.get("seo") or {}
    script = state.data.get("script") or {}
    prompts = state.data.get("prompts") or {}
    title = state.gate("1")["payload"].get("chosen_title") or "«FILL: title not selected»"
    chapters = seo.get("chapters", {}).get("chapters", [])
    tags = seo.get("tags", {})

    description = []
    description.append("«FILL: two-sentence description opening on the query term "
                       "'%s'. No claim that is not in the script.»" % (seo.get("keywords", [""])[0]))
    description.append("")
    description.append("Chapters")
    for c in chapters:
        description.append("%s %s" % (c["timestamp"], c["label"]))
    description.append("")
    if script.get("evidence_rules"):
        description.append("Sources")
        description.append("«CITE: every source named in the script, one per line, "
                           "with journal, year and link. Verified before publish.»")
        description.append("")
    description.append("#" + " #".join(t.replace(" ", "") for t in tags.get("head_terms", [])[:3]))
    description_text = "\n".join(description)

    L = []
    A = L.append
    A("# 05 — Metadata")
    A("")
    A("| Field | Value |")
    A("|---|---|")
    A("| Channel | `%s` |" % state.data["channel"])
    A("| Episode | `%s` |" % state.data["episode_id"])
    A("| Title | %s |" % title)
    A("| Runtime target | %s |" % seo.get("runtime_target", "unknown"))
    A("| Scenes / blocks | %s / %s |" % (prompts.get("scene_count", "-"), prompts.get("blocks", "-")))
    A("| Aspect | %s |" % prompts.get("aspect_ratio", "-"))
    A("| Publish date | %s |" % (publish_date or "unscheduled"))
    A("| Credits approved | %s |" % state.gate("3")["payload"].get("credits_approved", "-"))
    A("")
    A("## Description")
    A("")
    A("```")
    A(description_text)
    A("```")
    A("")
    A("## Chapters")
    A("")
    A("```")
    for c in chapters:
        A("%s %s" % (c["timestamp"], c["label"]))
    A("```")
    A("")
    A("## Tags (%d/%d chars)" % (tags.get("field_chars", 0), tags.get("field_limit", 500)))
    A("")
    A("```")
    A(tags.get("field_string", ""))
    A("```")
    A("")
    A("## Publishing")
    A("")
    A("| Item | Value |")
    A("|---|---|")
    A("| Scheduled | %s |" % (publish_date or "unscheduled — pass --publish-date YYYY-MM-DD"))
    A("| Visibility | «FILL: public / unlisted / scheduled»")
    A("| Thumbnail | %s |" % ("see 04_kie_thumbnail_prompts.md"))
    for c in (prompts.get("production_constraints") or []):
        A("| Canon constraint | %s |" % c)
    A("")
    A("## Approval log")
    A("")
    A("| When | Who | Action | State |")
    A("|---|---|---|---|")
    for entry in state.data["approval_log"]:
        A("| %s | %s | %s | %s |" % (
            entry["utc"], entry["actor"], entry["action"],
            entry.get("to_state") or state.state))
    A("")
    return "\n".join(L).rstrip() + "\n", title


def update_publish_plan(root, state, title, publish_date):
    path = os.path.join(channel_dir(root, state.data["channel"]), PUBLISH_PLAN)
    rows, seen = [], False
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh)]
    prompts = state.data.get("prompts") or {}
    seo = state.data.get("seo") or {}
    row = {
        "episode_id": state.data["episode_id"],
        "channel": state.data["channel"],
        "state": state.state,
        "title": title,
        "topic": state.data["topic"],
        "runtime_target": seo.get("runtime_target", ""),
        "scenes": prompts.get("scene_count", ""),
        "blocks": prompts.get("blocks", ""),
        "credits_approved": state.gate("3")["payload"].get("credits_approved", ""),
        "publish_date": publish_date or "",
        "episode_dir": rel(root, state.dir),
        "updated_utc": utcnow(),
    }
    for i, existing in enumerate(rows):
        if existing.get("episode_id") == row["episode_id"]:
            rows[i] = row
            seen = True
    if not seen:
        rows.append(row)
    rows.sort(key=lambda r: r.get("publish_date") or "9999", reverse=False)

    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=PLAN_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in PLAN_COLUMNS})
    write_atomic(path, out.getvalue())
    return path


def export_metadata_json(state, root, publish_date):
    """The machine-readable half of the package stage: title variants under
    their character budgets, the structured description, and the tag field, as
    `metadata.json` beside the episode's other assets. 05_metadata.md is what a
    person reads; this is what an upload tool reads."""
    payload = seo_generator.from_state(state.data, publish_date=publish_date)
    state.data["metadata"] = payload
    write_episode_file(state, root, "metadata_json",
                       json.dumps(payload, indent=2) + "\n")
    return payload


def cmd_package(args, root):
    state = EpisodeState.load(root, args.channel, args.episode)
    state.require_command("package")

    if args.publish:
        if state.state != "RENDERED":
            raise SystemExit(
                "error: --publish moves RENDERED -> PUBLISHED, and this episode is %s. "
                "Run `package` without --publish first." % state.state)
        publish_date = args.publish_date or state.data.get("publish_date")
        text, title = build_metadata(state, root, publish_date)
        write_episode_file(state, root, "metadata", text)
        state.data["publish_date"] = publish_date
        export_metadata_json(state, root, publish_date)
        state.transition("PUBLISHED", actor=args.by, note="published")
        path = update_publish_plan(root, state, title, state.data.get("publish_date"))
        print("wrote %s" % rel(root, os.path.join(state.dir, EPISODE_FILES["metadata_json"])))
        print("state: PUBLISHED  ·  plan updated %s" % rel(root, path))
        return 0

    text, title = build_metadata(state, root, args.publish_date)
    write_episode_file(state, root, "metadata", text)
    state.data["publish_date"] = args.publish_date
    meta = export_metadata_json(state, root, args.publish_date)
    if state.state == "PROMPTS_STAGED":
        state.transition("RENDERED", actor=args.by, note="metadata packaged")
    else:
        state.save()
    path = update_publish_plan(root, state, title, args.publish_date)

    if args.json:
        print(json.dumps(state.summary(), indent=2))
        return 0
    print("wrote %s" % rel(root, os.path.join(state.dir, EPISODE_FILES["metadata"])))
    print("wrote %s" % rel(root, os.path.join(state.dir, EPISODE_FILES["metadata_json"])))
    print("wrote %s" % rel(root, path))
    print("state: %s" % state.state)
    print("title: %d chars  ·  description: %d chars  ·  tags: %d (%d/%d chars)"
          % (meta["title_chars"], meta["description"]["chars"], meta["tags"]["count"],
             meta["tags"]["field_chars"], meta["tags"]["field_limit"]))
    for issue in meta["validation"]:
        print("  %-8s %s: %s" % (issue["severity"], issue["code"], issue["message"]))
    print()
    banner([
        "Render the clips in KIE, cut the episode, upload it, then:",
        "  python scripts/run.py package --channel %s \\" % args.channel,
        "      --episode %s --publish --publish-date YYYY-MM-DD --by <you>" % args.episode,
    ])
    return 0


# ------------------------------------------------------------------------ approve

def cmd_approve(args, root):
    state = EpisodeState.load(root, args.channel, args.episode)
    state.check_gate_ready(args.gate)
    payload, note = {}, args.note

    if args.gate == "1":
        titles = state.gate("1")["payload"].get("titles") or []
        if not args.title:
            raise SystemExit(
                "error: gate 1 approves a specific title; pass --title <1..%d>. "
                "Candidates:\n  %s" % (len(titles),
                                       "\n  ".join("%d. %s" % (i, t) for i, t in enumerate(titles, 1))))
        if not 1 <= args.title <= len(titles):
            raise SystemExit("error: --title %d is out of range 1..%d" % (args.title, len(titles)))
        payload["chosen_title"] = titles[args.title - 1]
        payload["chosen_title_index"] = args.title
        note = note or "title: %s" % payload["chosen_title"]

    if args.gate == "2":
        path = os.path.join(state.dir, EPISODE_FILES["script"])
        if not os.path.isfile(path):
            raise SystemExit("error: %s is missing; run `script` first" % path)
        with open(path, "r", encoding="utf-8") as fh:
            markers = script_engine.unresolved_markers(fh.read())
        if markers and not args.allow_placeholders:
            raise SystemExit(
                "error: %d unresolved marker(s) still in %s (%d FILL, %d CITE). "
                "The canon rule is 'no placeholder facts', so gate 2 will not approve a "
                "script that still has them. Fill them in, or pass --allow-placeholders "
                "to approve a deliberately unfinished draft."
                % (len(markers), rel(root, path), markers.count("FILL"), markers.count("CITE")))
        payload["unresolved_markers_at_approval"] = len(markers)

    if args.gate == "3":
        cost = state.gate("3")["payload"].get("cost_estimate", {})
        if args.credits is None:
            raise SystemExit(
                "error: gate 3 approves a spend, so --credits is required. The batch is "
                "%s clips / %ss of video plus %s images. %s"
                % (cost.get("video_clips"), cost.get("video_seconds"),
                   cost.get("thumbnail_images"), cost.get("note", "")))
        estimated = cost.get("total_credits")
        if estimated is not None and args.credits + 1e-9 < estimated:
            raise SystemExit(
                "error: --credits %s is below the estimate of %s for this batch. "
                "Approve at least the estimate, or regenerate a smaller batch."
                % (args.credits, estimated))
        payload["credits_approved"] = args.credits
        payload["credits_estimated"] = estimated
        note = note or "approved spend: %s credits" % args.credits

    state.approve_gate(args.gate, args.by, note=note, payload=payload)
    print("gate %s approved by %s  ·  state: %s" % (args.gate, args.by, state.state))
    print("next: %s" % state.next_action())
    return 0


# ------------------------------------------------------------------------- status

def cmd_status(args, root):
    if args.episode:
        state = EpisodeState.load(root, args.channel, args.episode)
        summary = state.summary()
        if args.json:
            print(json.dumps(summary, indent=2))
            return 0
        print("%s / %s  [%s]" % (summary["channel"], summary["episode_id"], summary["state"]))
        print("  topic: %s" % summary["topic"])
        for g in summary["gates"]:
            mark = {"approved": "x", "pending": "!", "not_opened": " "}[g["status"]]
            who = " by %s" % g["approved_by"] if g["approved_by"] else ""
            print("  [%s] gate %s  %-16s %s%s" % (mark, g["gate"], g["label"], g["status"], who))
        print("  next: %s" % summary["next"])
        return 0

    base = os.path.join(channel_dir(root, args.channel), "episodes")
    if not os.path.isdir(base):
        print("no episodes yet for %s" % args.channel)
        return 0
    rows = []
    for ep in sorted(os.listdir(base)):
        if os.path.isfile(os.path.join(base, ep, EPISODE_FILES["state"])):
            s = EpisodeState.load(root, args.channel, ep)
            rows.append((ep, s.state, s.next_action()))
    if args.json:
        print(json.dumps([{"episode_id": e, "state": st, "next": n} for e, st, n in rows], indent=2))
        return 0
    for ep, st, nxt in rows:
        print("%-46s %-16s %s" % (ep, st, nxt))
    return 0


def cmd_remind(args, root):
    if args.install:
        for e in scheduler.install_entries(root):
            print("%s reminder at %s" % (e["kind"], e["time"]))
            print("  Windows: %s" % e["windows"])
            print("  cron   : %s\n" % e["cron"])
        return 0
    payload = scheduler.remind(root, args.kind, args.date)
    print(json.dumps(payload, indent=2) if args.json else scheduler.render_reminder(payload))
    return 0 if payload["count"] == payload["ready"] else 1


def cmd_schedule(args, root):
    payload = scheduler.slots(root, args.channel, 
                              scheduler.parse_date(args.start) if args.start else None,
                              args.weeks)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("%s — %s" % (payload["channel"], payload["cadence"]))
    if payload["blocked"]:
        gate = payload["brand_gate"]
        print("  BLOCKED by %s: %d of %d brand items still missing"
              % (gate["path"], len(gate["missing"]), gate["total"]))
        for m in gate["missing"]:
            print("    - %s (%s)" % (m, gate["reasons"][m]))
        return 1
    if not payload["scheduled"]:
        print("  %s" % (payload["note"] or "no cadence set"))
        return 0
    for slot in payload["slots"]:
        print("  %s  %s" % (slot["date"], slot["weekday"]))
    return 0


def cmd_analyze(args, root):
    state = EpisodeState.load(root, args.channel, args.episode)
    if state.state not in ("RENDERED", "PUBLISHED"):
        raise SystemExit(
            "error: %s is %s; there are no real metrics for an episode that has not shipped. "
            "Run `package` first." % (args.episode, state.state))
    comments = None
    if args.comments:
        if not os.path.isfile(args.comments):
            raise SystemExit("error: no comments file at %s" % args.comments)
        with open(args.comments, "r", encoding="utf-8") as fh:
            comments = json.load(fh)
    payload = analyzer.analyze(root, args.channel, args.episode,
                               analyzer.load_metrics(args.metrics), comments)
    path = analyzer.write_audit(root, payload)
    state.record_artifact("performance_audit", rel(root, path))

    if args.record_learning:
        fixes = payload["fixes"]
        if not 1 <= args.record_learning <= len(fixes):
            raise SystemExit("error: --record-learning %d is out of range 1..%d"
                             % (args.record_learning, len(fixes)))
        fix = fixes[args.record_learning - 1]
        entry = memory.record_learning(root, args.channel, fix["detail"], fix["action"],
                                       source=rel(root, path),
                                       metric=payload["below_floor"] or None,
                                       approved_by=args.by)
        print("recorded %s — future %s scripts carry this fix" % (entry["id"], args.channel))

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0
    print("wrote %s" % rel(root, path))
    for c in payload["checks"]:
        print("  %-18s %-8s %s" % (c["metric"], "—" if c["value"] is None else c["value"],
                                   c["verdict"]))
    for i, f in enumerate(payload["fixes"], 1):
        print("  %d. %s" % (i, f["action"]))
    if payload["fixes"] and not args.record_learning:
        print("\n  keep one: --record-learning <n>")
    return 0


def cmd_wizard(args, root):
    """Forward only the flags that were actually given.

    Pairs are dropped whole: filtering a flat list of flags and values would
    drop a None value and leave its flag behind to swallow the next one."""
    argv = ["--root", root]
    for flag, value in (("--channel", args.channel), ("--action", args.action),
                        ("--episode", args.episode), ("--topic", args.topic)):
        if value:
            argv += [flag, value]
    if args.json:
        argv.append("--json")
    return wizard.main(argv)


def cmd_checkpoint(args, root):
    if args.clear:
        memory.clear_session(root)
        print("session cleared")
        return 0
    active = memory.resume(root) if not (args.channel or args.episode or args.stage) \
        else memory.checkpoint(root, args.channel, args.episode, args.stage, args.note)
    if args.json:
        print(json.dumps(active, indent=2))
        return 0
    if not active:
        print("no active episode")
        return 0
    print("%s / %s  stage=%s  (%s)" % (active.get("channel"), active.get("episode_id"),
                                       active.get("stage"), active.get("updated_utc")))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(
        prog="scripts/run.py",
        description="Faceless channel pipeline: init -> script -> prompts -> package, "
                    "with three human approval gates.")
    sub = ap.add_subparsers(dest="command", required=True)

    def common(p, episode=True):
        p.add_argument("--channel", required=True, choices=CHANNELS)
        if episode:
            p.add_argument("--episode", required=True)
        p.add_argument("--json", action="store_true")
        p.add_argument("--root")
        return p

    p = common(sub.add_parser("init", help="SEO, titles and hook; opens gate 1"), episode=False)
    p.add_argument("--topic", required=True)
    p.add_argument("--keyword", action="append", dest="keywords",
                   help="explicit search query term; repeatable")
    p.add_argument("--runtime", help="target runtime: seconds, mm:ss or 8m30s")
    p.add_argument("--episode-id")
    p.add_argument("--allow-duplicate", action="store_true",
                   help="make an episode whose topic is already in topic_history.json")
    p.add_argument("--allow-provisional-architecture", action="store_true")

    p = common(sub.add_parser("script", help="ElevenLabs narration script; opens gate 2"))
    p.add_argument("--wpm", type=int, default=script_engine.DEFAULT_WPM)
    p.add_argument("--seconds-per-scene", type=float)
    p.add_argument("--variant")
    p.add_argument("--voice-lock",
                   help="narration direction for a channel whose canon marks its voice BLOCKED")
    p.add_argument("--signoff", help="closing line; checked against the channel's canon")
    p.add_argument("--force-signoff", action="store_true",
                   help="use --signoff even when the channel canon forbids that line")
    p.add_argument("--allow-provisional-architecture", action="store_true")

    p = common(sub.add_parser("prompts", help="KIE video and thumbnail prompts; opens gate 3"))
    p.add_argument("--video-model")
    p.add_argument("--image-model")
    p.add_argument("--style-key")
    p.add_argument("--shorts", action="store_true")

    p = common(sub.add_parser("package", help="metadata, publish plan, RENDERED/PUBLISHED"))
    p.add_argument("--publish-date")
    p.add_argument("--publish", action="store_true")
    p.add_argument("--by", default=os.environ.get("USER", "operator"))

    p = common(sub.add_parser("approve", help="record a human approval at gate 1, 2 or 3"))
    p.add_argument("--gate", required=True, choices=("1", "2", "3"))
    p.add_argument("--title", type=int, help="gate 1: which title variant to lock")
    p.add_argument("--credits", type=float, help="gate 3: the spend being approved")
    p.add_argument("--allow-placeholders", action="store_true",
                   help="gate 2: approve a script that still has «FILL»/«CITE» markers")
    p.add_argument("--by", default=os.environ.get("USER", "operator"))
    p.add_argument("--note")

    p = sub.add_parser("remind", help="the 17:30 / 18:30 publishing reminder")
    p.add_argument("--kind", choices=("shorts", "longform"))
    p.add_argument("--date")
    p.add_argument("--install", action="store_true", help="print the scheduler entries")
    p.add_argument("--json", action="store_true")
    p.add_argument("--root")

    p = sub.add_parser("schedule", help="upcoming publish slots for a channel")
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--from", dest="start")
    p.add_argument("--weeks", type=int, default=4)
    p.add_argument("--json", action="store_true")
    p.add_argument("--root")

    p = common(sub.add_parser("analyze", help="ingest metrics, write 06_performance_audit.md"))
    p.add_argument("--metrics", required=True, help="metrics JSON file, or inline JSON")
    p.add_argument("--comments", help="JSON list of comment strings")
    p.add_argument("--record-learning", type=int, metavar="N")
    p.add_argument("--by", default=os.environ.get("USER", "operator"))

    p = sub.add_parser("wizard", help="the guided /faceless-studio flow")
    p.add_argument("--channel", choices=CHANNELS)
    p.add_argument("--action", choices=("new", "resume", "metrics", "schedule"))
    p.add_argument("--episode")
    p.add_argument("--topic")
    p.add_argument("--json", action="store_true")
    p.add_argument("--root")

    p = sub.add_parser("checkpoint", help="read or write the cross-session position")
    p.add_argument("--channel", choices=CHANNELS)
    p.add_argument("--episode")
    p.add_argument("--stage")
    p.add_argument("--note")
    p.add_argument("--clear", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--root")

    p = sub.add_parser("status", help="where an episode or a channel stands")
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--episode")
    p.add_argument("--json", action="store_true")
    p.add_argument("--root")

    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.root or repo_root()
    return {
        "init": cmd_init, "script": cmd_script, "prompts": cmd_prompts,
        "package": cmd_package, "approve": cmd_approve, "status": cmd_status,
        "remind": cmd_remind, "schedule": cmd_schedule, "analyze": cmd_analyze,
        "wizard": cmd_wizard, "checkpoint": cmd_checkpoint,
    }[args.command](args, root)


if __name__ == "__main__":
    raise SystemExit(main())
