#!/usr/bin/env python3
"""Publishing cadence, the upload queue, and the two daily reminders.

Cadence comes from scripts/config/schedule.json: Known Unknowns longform on
Tuesday and Friday, Stickman longform on Friday, shorts daily. Lilweid has no
operator-set cadence and therefore has none here — an unscheduled channel is
reported as unscheduled rather than given an invented slot.

Stickman longform is gated on references/brand.json. The operator's rule
is that Friday publishing starts once the logo, avatar, name, handle, locked
character, links and description exist, so the scheduler refuses a Stickman
longform slot until that file says they do.

The two reminders (17:30 longform, 18:30 shorts) each do the same three things:
read today's row from publish-plan.csv, check the file is really in _upload/,
and print the platform, the exact filename, the safety notes and the caption
metadata. This module does not install the scheduled task — `remind --install`
prints the schtasks and cron entries for a human to install.
"""

import argparse
import csv
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canon import CHANNELS, load_canon, repo_root  # noqa: E402
try:
    import paths
except ImportError:  # imported as a package from run.py
    from . import paths
from state_manager import EpisodeState, channel_dir, utcnow, write_atomic  # noqa: E402

WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
PLAN = "publish-plan.csv"

# The canonical publish-plan schema. run.py imports this so the two writers of
# this file can never disagree about its columns.
PLAN_COLUMNS = ("episode_id", "channel", "state", "title", "topic", "runtime_target",
                "format", "platform", "publish_date", "upload_filename", "upload_ready",
                "scenes", "blocks", "credits_approved", "episode_dir", "updated_utc")


def load_schedule(root):
    path = paths.config_path("schedule.json", root)
    if not os.path.isfile(path):
        raise SystemExit(f"error: missing {path}; the schedule config is part of the pipeline")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def parse_date(value):
    try:
        return datetime.date(*[int(x) for x in value.split("-")])
    except (ValueError, TypeError):
        raise SystemExit(f"error: cannot read date {value!r}; use YYYY-MM-DD")


def brand_status(root, channel):
    """None when the channel has no brand gate; otherwise what is still missing.

    An item that claims an asset is only satisfied once that file is really on
    disk. Marking `locked_character` done while its reference image is missing
    would let the gate report ready on a promise, which is the one thing a gate
    exists to stop."""
    path = paths.brand_path(root, channel)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    items = data.get("items", {})
    missing, reasons = [], {}
    for key, item in sorted(items.items()):
        if not item.get("done"):
            missing.append(key)
            reasons[key] = "not marked done"
            continue
        asset = item.get("asset")
        if asset and not os.path.isfile(os.path.join(root, asset)):
            missing.append(key)
            reasons[key] = "marked done but no file at %s" % asset
    return {"path": os.path.relpath(path, root), "missing": missing, "reasons": reasons,
            "ready": not missing, "total": len(items)}


def slots(root, channel, start=None, weeks=4):
    """Upcoming longform publish dates for one channel."""
    schedule = load_schedule(root)
    rule = schedule["longform"].get(channel, {})
    weekdays = rule.get("weekdays") or []
    start = start or datetime.date.today()

    gate = None
    if rule.get("requires_brand_ready"):
        gate = brand_status(root, channel)

    out = []
    if weekdays:
        for offset in range(weeks * 7):
            day = start + datetime.timedelta(days=offset)
            if day.weekday() in weekdays:
                out.append({"date": day.isoformat(), "weekday": WEEKDAY_NAMES[day.weekday()],
                            "format": "longform"})
    return {
        "channel": channel,
        "cadence": rule.get("_weekdays_human", "unscheduled"),
        "scheduled": bool(weekdays),
        "brand_gate": gate,
        "blocked": bool(gate and not gate["ready"]),
        "slots": [] if (gate and not gate["ready"]) else out,
        "note": rule.get("_note"),
    }


# ---------------------------------------------------------------- the publish plan

def plan_path(root, channel):
    return os.path.join(channel_dir(root, channel), PLAN)


def read_plan(root, channel):
    path = plan_path(root, channel)
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def write_plan(root, channel, rows, columns):
    import io
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in columns})
    path = plan_path(root, channel)
    write_atomic(path, out.getvalue())
    return path


def upload_dir(root, create=False):
    schedule = load_schedule(root)
    path = os.path.join(root, schedule["upload"]["dir"])
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def upload_filename(root, date, platform, video_format):
    schedule = load_schedule(root)["upload"]
    pattern = schedule["short_pattern"] if video_format == "short" else schedule["longform_pattern"]
    return pattern.format(date=date, PLATFORM=platform.upper())


def safety_notes(root, channel):
    """Publish-time checks, read off the channel canon rather than a generic list."""
    canon = load_canon(channel, root)
    notes = ["Faceless is absolute: no face, no name, no personal identity in the upload, "
             "the thumbnail, or the caption."]
    for rule in canon.production_rules + canon.production_constraints:
        low = rule.lower()
        if any(k in low for k in ("never", "verify", "cannot", "unavailable", "no ")):
            notes.append(rule)
    return notes


def caption_metadata(root, channel, episode_id):
    """Title, description opener, tags and hashtags for the upload form."""
    try:
        state = EpisodeState.load(root, channel, episode_id)
    except SystemExit:
        return {"available": False, "reason": "no state.json for %s" % episode_id}
    seo = state.data.get("seo") or {}
    tags = seo.get("tags", {})
    return {
        "available": True,
        "title": state.gate("1")["payload"].get("chosen_title"),
        "topic": state.data.get("topic"),
        "runtime_target": seo.get("runtime_target"),
        "chapters": [c["line"] for c in seo.get("chapters", {}).get("chapters", [])],
        "tags_field": tags.get("field_string", ""),
        "tags_chars": tags.get("field_chars"),
        "hashtags": ["#" + t.replace(" ", "") for t in tags.get("head_terms", [])[:3]],
        "state": state.state,
        "metadata_file": os.path.relpath(
            os.path.join(paths.episode_dir(root, channel, episode_id), "05_metadata.md"),
            root),
    }


def queue_for(root, date, kind=None):
    """Every plan row scheduled for one date, across all channels."""
    rows = []
    for channel in CHANNELS:
        for row in read_plan(root, channel):
            if row.get("publish_date") != date:
                continue
            fmt = (row.get("format") or "longform").lower()
            if kind and fmt != ("short" if kind == "shorts" else "longform"):
                continue
            rows.append(dict(row, channel=channel, format=fmt))
    return rows


def verify_upload(root, row):
    """Does the file actually exist in _upload/, and is it a plausible size?"""
    name = row.get("upload_filename")
    if not name:
        return {"ok": False, "filename": None, "reason": "no upload_filename on this plan row"}
    path = os.path.join(upload_dir(root), name)
    if not os.path.exists(path):
        return {"ok": False, "filename": name, "path": path,
                "reason": "not present in %s" % os.path.relpath(upload_dir(root), root)}
    size = os.path.getsize(path)
    return {
        "ok": size > 0, "filename": name, "path": path, "bytes": size,
        "reason": None if size > 0 else "file is empty",
        "links": getattr(os.stat(path), "st_nlink", 1),
    }


def link_upload(root, source, date, platform, video_format):
    """Hardlink a rendered file into _upload/ under the dated convention.

    A hardlink, not a copy: the upload queue and the episode directory point at
    the same bytes, so nothing is duplicated and nothing drifts."""
    if not os.path.isfile(source):
        raise SystemExit(f"error: no file at {source}; render it before queueing the upload")
    name = upload_filename(root, date, platform, video_format)
    target = os.path.join(upload_dir(root, create=True), name)
    if os.path.exists(target):
        raise SystemExit(f"error: {target} already exists; remove it or pick another date/platform")
    try:
        os.link(source, target)
        mode = "hardlink"
    except OSError as exc:
        raise SystemExit(
            "error: could not hardlink %s -> %s (%s). Source and destination must be on the "
            "same volume. On Windows the equivalent is: mklink /H \"%s\" \"%s\""
            % (source, target, exc, target, source))
    return {"filename": name, "path": target, "source": source, "mode": mode,
            "links": os.stat(target).st_nlink}


def assign(root, channel, episode_id, date, platform, video_format="longform"):
    """Put an episode in the plan for a date, with the upload filename it will need."""
    rows = read_plan(root, channel)
    match = [r for r in rows if r.get("episode_id") == episode_id]
    if not match:
        raise SystemExit(
            "error: %s has no row in %s; run `package` on it first so there is a plan row "
            "to schedule" % (episode_id, os.path.relpath(plan_path(root, channel), root)))
    row = match[0]
    row["publish_date"] = date
    row["platform"] = platform.lower()
    row["format"] = video_format
    row["upload_filename"] = upload_filename(root, date, platform, video_format)
    row["upload_ready"] = "no"
    row["updated_utc"] = utcnow()
    rows.sort(key=lambda r: r.get("publish_date") or "9999")
    write_plan(root, channel, rows, PLAN_COLUMNS)
    return row


def remind(root, kind, date=None):
    """The scheduled reminder: today's row, the file check, and what to upload."""
    date = date or datetime.date.today().isoformat()
    schedule = load_schedule(root)
    rows = queue_for(root, date, kind)
    items = []
    for row in rows:
        check = verify_upload(root, row)
        items.append({
            "channel": row["channel"],
            "episode_id": row.get("episode_id"),
            "format": row["format"],
            "platform": (row.get("platform") or "").upper() or "UNSET",
            "title": row.get("title"),
            "state": row.get("state"),
            "file": check,
            "safety_notes": safety_notes(root, row["channel"]),
            "caption": caption_metadata(root, row["channel"], row.get("episode_id")),
        })
    return {
        "date": date,
        "kind": kind,
        "reminder_time": schedule["reminders"].get(kind, {}).get("time"),
        "count": len(items),
        "ready": sum(1 for i in items if i["file"]["ok"]),
        "items": items,
    }


def render_reminder(payload):
    L = []
    A = L.append
    A("%s reminder — %s (%s)" % (payload["kind"].upper(), payload["date"],
                                 payload["reminder_time"] or "no time set"))
    if not payload["items"]:
        A("  nothing scheduled for this date")
        return "\n".join(L)
    A("  %d scheduled, %d with the file present" % (payload["count"], payload["ready"]))
    for item in payload["items"]:
        A("")
        A("  %s / %s  [%s]" % (item["channel"], item["episode_id"], item["state"]))
        A("    platform : %s" % item["platform"])
        f = item["file"]
        A("    file     : %s  %s" % (f["filename"] or "UNSET",
                                     "OK (%d bytes)" % f["bytes"] if f["ok"]
                                     else "MISSING — %s" % f["reason"]))
        A("    title    : %s" % (item["caption"].get("title") or "not selected"))
        cap = item["caption"]
        if cap.get("available"):
            A("    tags     : %s chars" % cap.get("tags_chars"))
            A("    hashtags : %s" % " ".join(cap.get("hashtags", [])))
            A("    metadata : %s" % cap.get("metadata_file"))
        A("    safety   :")
        for note in item["safety_notes"]:
            A("      - %s" % note)
    return "\n".join(L)


def install_entries(root, schedule=None):
    """Scheduler entries for a human to install. This does not install them."""
    schedule = schedule or load_schedule(root)
    out = []
    for kind, cfg in sorted(schedule["reminders"].items()):
        hh, mm = cfg["time"].split(":")
        cmd = ('python scripts/run.py remind --kind %s' % cfg["kind"])
        out.append({
            "kind": cfg["kind"],
            "time": cfg["time"],
            "command": cmd,
            "windows": ('schtasks /Create /SC DAILY /TN "faceless-%s-reminder" /ST %s '
                        '/TR "cmd /c cd /d %s && %s"' % (cfg["kind"], cfg["time"], root, cmd)),
            "cron": "%s %s * * * cd %s && %s" % (int(mm), int(hh), root, cmd),
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Publishing cadence, upload queue and reminders.")
    sub = ap.add_subparsers(dest="action", required=True)

    p = sub.add_parser("slots", help="upcoming longform publish dates")
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--from", dest="start")
    p.add_argument("--weeks", type=int, default=4)
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("queue", help="everything scheduled for a date")
    p.add_argument("--date")
    p.add_argument("--kind", choices=("shorts", "longform"))
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("assign", help="schedule an episode on a date")
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--episode", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--format", dest="video_format", default="longform",
                   choices=("short", "longform"))
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("remind", help="the daily reminder output")
    p.add_argument("--kind", choices=("shorts", "longform"),
                   help="required unless --install is given")
    p.add_argument("--date")
    p.add_argument("--install", action="store_true", help="print scheduler entries instead")
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("link", help="hardlink a rendered file into _upload/")
    p.add_argument("--source", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--platform", required=True)
    p.add_argument("--format", dest="video_format", default="short", choices=("short", "longform"))
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("brand", help="the Stickman brand-readiness gate")
    p.add_argument("--channel", required=True, choices=CHANNELS)
    p.add_argument("--root")
    p.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    root = args.root or repo_root()

    if args.action == "slots":
        payload = slots(root, args.channel, parse_date(args.start) if args.start else None,
                        args.weeks)
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("%s — %s" % (payload["channel"], payload["cadence"]))
            if payload["blocked"]:
                gate = payload["brand_gate"]
                print("  BLOCKED by %s: %d of %d brand items missing" % (
                    gate["path"], len(gate["missing"]), gate["total"]))
                for m in gate["missing"]:
                    print("    - %s (%s)" % (m, gate["reasons"][m]))
            elif not payload["scheduled"]:
                print("  %s" % (payload["note"] or "no cadence set"))
            else:
                for s in payload["slots"]:
                    print("  %s  %s" % (s["date"], s["weekday"]))
    elif args.action == "queue":
        date = args.date or datetime.date.today().isoformat()
        rows = queue_for(root, date, args.kind)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            print("%s — %d scheduled" % (date, len(rows)))
            for r in rows:
                print("  %-16s %-14s %-9s %s" % (r["channel"], r.get("episode_id"),
                                                 r["format"], r.get("upload_filename") or "-"))
    elif args.action == "assign":
        row = assign(root, args.channel, args.episode, args.date, args.platform,
                     args.video_format)
        print(json.dumps(row, indent=2) if args.json else
              "%s scheduled %s on %s as %s" % (args.episode, args.video_format,
                                               row["publish_date"], row["upload_filename"]))
    elif args.action == "remind":
        if args.install:
            entries = install_entries(root)
            if args.json:
                print(json.dumps(entries, indent=2))
            else:
                print("These are not installed. Run the line for your platform.\n")
                for e in entries:
                    print("%s reminder at %s" % (e["kind"], e["time"]))
                    print("  Windows: %s" % e["windows"])
                    print("  cron   : %s\n" % e["cron"])
            return 0
        if not args.kind:
            raise SystemExit("error: --kind is required (shorts or longform) unless --install")
        payload = remind(root, args.kind, args.date)
        print(json.dumps(payload, indent=2) if args.json else render_reminder(payload))
        return 0 if payload["count"] == payload["ready"] else 1
    elif args.action == "link":
        result = link_upload(root, args.source, args.date, args.platform, args.video_format)
        print(json.dumps(result, indent=2) if args.json else
              "linked %s -> %s (%d links)" % (result["source"], result["filename"],
                                              result["links"]))
    elif args.action == "brand":
        gate = brand_status(root, args.channel)
        if gate is None:
            print("%s has no brand gate" % args.channel)
            return 0
        if args.json:
            print(json.dumps(gate, indent=2))
        else:
            print("%s brand gate: %s (%d of %d done)" % (
                args.channel, "READY" if gate["ready"] else "BLOCKED",
                gate["total"] - len(gate["missing"]), gate["total"]))
            for m in gate["missing"]:
                print("  missing: %s — %s" % (m, gate["reasons"][m]))
        return 0 if gate["ready"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
