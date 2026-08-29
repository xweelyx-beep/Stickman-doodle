#!/usr/bin/env python3
"""Titles, search-intent chapters and tags for one episode.

Three things this module deliberately does not do. It does not claim search
volume, because nothing here measures any: the tag lists are ranked by intent
shape, not by traffic, and say so in the output. It does not invent a title
formula for a channel whose canon lists one as an open question; it labels the
templates as house defaults instead. And it will not lay chapters over a channel
whose beat architecture the canon marks [BLOCKED] unless the operator explicitly
opts in, because a provisional beat sheet that reads like a lock is exactly the
failure the stickman canon warns about.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canon import CHANNELS, load_canon, repo_root  # noqa: E402
try:
    import paths
except ImportError:  # imported as a package from run.py
    from . import paths

YOUTUBE_TITLE_MAX = 100        # hard limit on the title field
YOUTUBE_TITLE_VISIBLE = 60     # about where search results truncate
YOUTUBE_TAGS_FIELD_MAX = 500   # hard limit on the whole tags field, commas included

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "do", "does",
    "for", "from", "how", "in", "is", "it", "its", "of", "on", "or", "so", "than",
    "that", "the", "their", "them", "they", "this", "to", "up", "was", "what",
    "when", "why", "will", "with", "you", "your",
}

# Title shapes are a house default, not a channel lock. Lilweid's canon lists
# "title formula" as an open question and the other two canons say nothing about
# titles at all, so nothing here is presented as verified.
TITLE_TEMPLATES = {
    "search_intent": [
        "How {Topic} Actually Works",
        "{Topic}, Explained",
        "Why {Topic} Happens",
    ],
    "curiosity": [
        "The Part of {Topic} Nobody Can Explain",
        "What {Topic} Is Really Doing To You",
        "{Topic}: The Thing Nobody Told You",
    ],
    "direct": [
        "{Topic}",
        "{Topic} — What The Evidence Says",
        "{Topic}, Start To Finish",
    ],
}

# Query frames used to build long-tail phrases and chapter labels.
QUERY_FRAMES = [
    "how {kw} works",
    "why {kw} happens",
    "what {kw} actually does",
    "{kw} explained",
    "the real reason {kw}",
    "what to do about {kw}",
    "is {kw} real",
    "{kw} step by step",
]


def slugify(text, maxlen=60):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:maxlen].rstrip("-") or "episode"


def parse_duration(value):
    """Accept 510, '510', '8:30' or '8m30s'."""
    value = str(value).strip()
    if re.match(r"^\d+$", value):
        return int(value)
    m = re.match(r"^(\d+):(\d{1,2})$", value)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.match(r"^(?:(\d+)m)?(?:(\d+)s)?$", value)
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    raise SystemExit(f"error: cannot read duration {value!r}; use seconds, mm:ss or 8m30s")


def timestamp(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return "%d:%02d:%02d" % (seconds // 3600, (seconds % 3600) // 60, seconds % 60)
    return "%02d:%02d" % (seconds // 60, seconds % 60)


def head_term(topic):
    words = [w for w in re.findall(r"[a-z0-9']+", topic.lower()) if w not in STOPWORDS]
    return " ".join(words) or topic.lower()


def title_case(text):
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on",
             "or", "the", "to", "vs", "with"}
    words = text.split()
    out = []
    for i, w in enumerate(words):
        out.append(w if (w.isupper() and len(w) > 1) else
                   (w.lower() if (i and w.lower() in small) else w[:1].upper() + w[1:]))
    return " ".join(out)


def subject_phrase(text):
    """Strip a leading interrogative so a topic phrased as a question does not
    produce "Why Why The Brain ... Happens" when a template adds its own."""
    return re.sub(r"^(?:why|how|what|when|where|who|is|are|does|do|can)\s+", "",
                  text.strip(), flags=re.I).strip() or text.strip()


def build_titles(topic, primary_keyword=None):
    """The templated variants key off the primary query term, so the title
    carries the phrase the viewer actually types. The direct variant keeps the
    operator's topic verbatim."""
    subject = title_case(subject_phrase(primary_keyword or topic))
    display = title_case(topic)
    titles = []
    for intent in ("search_intent", "curiosity", "direct"):
        word = display if intent == "direct" else subject
        options = [t.format(Topic=word) for t in TITLE_TEMPLATES[intent]]
        chosen = min(options, key=lambda s: (len(s) > YOUTUBE_TITLE_MAX, abs(len(s) - 52)))
        titles.append({
            "intent": intent,
            "label": {"search_intent": "Search-intent",
                      "curiosity": "High-CTR curiosity",
                      "direct": "Direct"}[intent],
            "text": chosen,
            "chars": len(chosen),
            "over_field_limit": len(chosen) > YOUTUBE_TITLE_MAX,
            "truncates_in_search": len(chosen) > YOUTUBE_TITLE_VISIBLE,
            "alternates": [o for o in options if o != chosen],
        })
    return titles


def build_keywords(topic, extra):
    """Explicit operator keywords come first and are used verbatim; the topic's
    head term backfills so there is always at least one query term."""
    keywords = []
    for k in list(extra or []) + [head_term(topic)]:
        k = k.strip().lower()
        if k and k not in keywords:
            keywords.append(k)
    return keywords


def build_chapters(canon, keywords, runtime_s, allow_provisional=False):
    """Chapter timestamps laid over the channel's verified beat architecture.

    Where the canon carries measured beat timings (Known Unknowns does, from an
    8:18 episode) the beats are scaled proportionally to the target runtime, so
    the shape of the episode survives a runtime change. Where it does not, the
    split is even and the output says so.
    """
    beats = canon.beats
    method = "scaled from canon beat timings"
    if not beats:
        if not allow_provisional:
            raise SystemExit(
                f"error: {canon.channel} has no beat architecture in {canon.path} "
                "(the canon marks it [BLOCKED]), so there is nothing to lay chapters "
                "over. Pass --allow-provisional-architecture to generate a generic "
                "explainer beat sheet, which is a working draft and NOT canon."
            )
        beats = [
            {"number": i + 1, "name": name, "verified_start_s": None,
             "verified_end_s": None, "description": desc}
            for i, (name, desc) in enumerate([
                ("The problem", "the behaviour the viewer recognises in themselves"),
                ("The mechanism", "what is actually happening, drawn out"),
                ("Why it persists", "the loop that keeps it running"),
                ("What to do", "the numbered, actionable part"),
                ("Close", "the return image and the sign-off"),
            ])
        ]
        method = "provisional generic explainer beats (channel architecture BLOCKED)"

    timed = [b for b in beats if b.get("verified_start_s") is not None]
    chapters = []
    if len(timed) == len(beats) and beats[-1].get("verified_end_s"):
        span = beats[-1]["verified_end_s"] - beats[0]["verified_start_s"]
        origin = beats[0]["verified_start_s"]
        for i, b in enumerate(beats):
            start = int(round((b["verified_start_s"] - origin) / float(span) * runtime_s))
            chapters.append((b, start))
    else:
        method = ("even split across canon beats" if canon.beats else method)
        step = runtime_s / float(len(beats))
        for i, b in enumerate(beats):
            chapters.append((b, int(round(i * step))))

    out = []
    for i, (beat, start) in enumerate(chapters):
        start = 0 if i == 0 else max(start, out[-1]["start_s"] + 1)
        kw = keywords[i % len(keywords)]
        frame = QUERY_FRAMES[i % len(QUERY_FRAMES)].format(kw=kw)
        label = "%s: %s" % (title_case(beat["name"]), frame)
        out.append({
            "index": i + 1,
            "start_s": start,
            "timestamp": timestamp(start),
            "beat": beat["name"],
            "beat_description": beat.get("description"),
            "query_term": kw,
            "label": label,
            "line": "%s %s" % (timestamp(start), label),
        })
    return {"method": method, "provisional": not canon.beats, "chapters": out}


def build_tags(topic, keywords, channel):
    """Head terms first, then long-tail query phrases, trimmed to YouTube's
    500-character tags field. Order is intent shape, not measured volume —
    nothing here counts searches."""
    head = []
    for kw in keywords:
        for candidate in (kw, "%s explained" % kw, "how %s works" % kw, "why %s" % kw):
            # Skip a frame the keyword already contains, so a topic phrased as
            # "anaesthesia works" does not become "how anaesthesia works works".
            tail = candidate.replace(kw, "").strip()
            if tail and tail.split()[-1] in kw.split():
                continue
            if candidate not in head:
                head.append(candidate)
    head.append(channel.replace("-", " "))

    long_tail = []
    for kw in keywords:
        for frame in QUERY_FRAMES:
            phrase = frame.format(kw=kw)
            tail = phrase.replace(kw, "").strip()
            if tail and tail.split()[-1] in kw.split():
                continue
            if phrase not in long_tail and phrase not in head:
                long_tail.append(phrase)

    field, used, dropped = [], 0, []
    for tag in head + long_tail:
        cost = len(tag) + (1 if field else 0)
        if used + cost > YOUTUBE_TAGS_FIELD_MAX:
            dropped.append(tag)
            continue
        field.append(tag)
        used += cost
    return {
        "head_terms": head,
        "long_tail_queries": long_tail,
        "field": field,
        "field_string": ",".join(field),
        "field_chars": used,
        "field_limit": YOUTUBE_TAGS_FIELD_MAX,
        "dropped_over_limit": dropped,
        "volume_measured": False,
        "ranking_basis": "query-intent shape; no search-volume data was measured",
    }


def build_hook(canon, topic, keywords):
    """The opening line, framed by the channel's first canon beat. Anything that
    needs a checked fact comes back as a marker, never as invented copy."""
    opener = canon.beats[0] if canon.beats else None
    return {
        "beat": opener["name"] if opener else None,
        "beat_intent": opener.get("description") if opener else None,
        "voice_lock": canon.voice_lock,
        "draft": ("«FILL: open on %s — %s. Query term to land in the first sentence: "
                  "%s»" % (opener["name"].lower(), opener.get("description", ""), keywords[0])
                  if opener else
                  "«FILL: opening line for %s; channel architecture is BLOCKED, so write "
                  "the hook by hand and do not borrow another channel's shape»" % topic),
    }


def generate(channel, topic, keywords=None, runtime_s=None, root=None,
             allow_provisional=False):
    canon = load_canon(channel, root)
    if runtime_s is None:
        if not canon.runtime_range_s:
            raise SystemExit(
                f"error: {channel} has no measured runtime range in {canon.path}; "
                "pass --runtime (seconds or mm:ss) for this episode"
            )
        runtime_s = int(round(sum(canon.runtime_range_s) / 2.0))
    kws = build_keywords(topic, keywords)
    chapters = build_chapters(canon, kws, runtime_s, allow_provisional)
    return {
        "channel": channel,
        "canon_path": os.path.relpath(canon.path, root or repo_root()),
        "topic": topic,
        "keywords": kws,
        "head_term": head_term(topic),
        "runtime_target_s": runtime_s,
        "runtime_target": timestamp(runtime_s),
        "runtime_source": ("operator-supplied" if runtime_s else "canon midpoint"),
        "canon_runtime_range_s": list(canon.runtime_range_s) if canon.runtime_range_s else None,
        "seconds_per_scene": canon.seconds_per_scene,
        "scene_estimate": (int(round(runtime_s / canon.seconds_per_scene))
                           if canon.seconds_per_scene else None),
        "titles": build_titles(topic, kws[0]),
        "title_formula_status": "house default; not a verified channel lock",
        "hook": build_hook(canon, topic, kws),
        "chapters": chapters,
        "tags": build_tags(topic, kws, channel),
        "blocked_canon_sections": canon.blocked,
    }


def render_markdown(payload):
    L = []
    A = L.append
    A("# 01 — Ideation & SEO")
    A("")
    A("| Field | Value |")
    A("|---|---|")
    A("| Channel | `%s` |" % payload["channel"])
    A("| Topic | %s |" % payload["topic"])
    A("| Canon | `%s` |" % payload["canon_path"])
    A("| Target runtime | %s (%ss) |" % (payload["runtime_target"], payload["runtime_target_s"]))
    A("| Canon pace | %s |" % (("%ss per scene" % payload["seconds_per_scene"])
                               if payload["seconds_per_scene"] else "UNMEASURED"))
    A("| Scene estimate | %s |" % (payload["scene_estimate"] or "unknown — pace unmeasured"))
    A("| Query terms | %s |" % ", ".join("`%s`" % k for k in payload["keywords"]))
    A("")
    A("## Titles — pick one at gate 1")
    A("")
    A("| # | Intent | Title | Chars | Search truncation |")
    A("|---|---|---|---|---|")
    for i, t in enumerate(payload["titles"], 1):
        A("| %d | %s | %s | %d | %s |" % (
            i, t["label"], t["text"], t["chars"],
            "truncates" if t["truncates_in_search"] else "fits"))
    A("")
    A("_Title shapes are a %s._" % payload["title_formula_status"])
    A("")
    for i, t in enumerate(payload["titles"], 1):
        if t["alternates"]:
            A("- **%d alternates:** %s" % (i, " · ".join(t["alternates"])))
    A("")
    A("## Hook")
    A("")
    if payload["hook"]["voice_lock"]:
        A("> **Voice lock:** %s" % payload["hook"]["voice_lock"])
        A("")
    A("**Opening beat:** %s" % (payload["hook"]["beat"] or "BLOCKED — no canon architecture"))
    A("")
    A(payload["hook"]["draft"])
    A("")
    A("## Chapters")
    A("")
    A("_Method: %s._%s" % (
        payload["chapters"]["method"],
        "  \n**These beats are provisional and are not canon.**"
        if payload["chapters"]["provisional"] else ""))
    A("")
    A("```")
    for c in payload["chapters"]["chapters"]:
        A(c["line"])
    A("```")
    A("")
    A("## Tags")
    A("")
    A("_%s._" % payload["tags"]["ranking_basis"])
    A("")
    A("**Tags field (%d/%d chars):**" % (payload["tags"]["field_chars"],
                                         payload["tags"]["field_limit"]))
    A("")
    A("```")
    A(payload["tags"]["field_string"])
    A("```")
    A("")
    if payload["tags"]["dropped_over_limit"]:
        A("**Dropped, field full:** %s" % ", ".join(payload["tags"]["dropped_over_limit"]))
        A("")
    A("**Long-tail queries**")
    A("")
    for q in payload["tags"]["long_tail_queries"]:
        A("- %s" % q)
    A("")
    if payload["blocked_canon_sections"]:
        A("## Canon sections still blocked")
        A("")
        for b in payload["blocked_canon_sections"]:
            A("- %s" % b)
        A("")
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Titles, chapters and tags for one episode.")
    ap.add_argument("--channel", required=True, choices=CHANNELS)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--keyword", action="append", dest="keywords",
                    help="explicit search query term; repeatable, used verbatim")
    ap.add_argument("--runtime", help="target runtime: seconds, mm:ss or 8m30s")
    ap.add_argument("--allow-provisional-architecture", action="store_true")
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    payload = generate(
        args.channel, args.topic, args.keywords,
        parse_duration(args.runtime) if args.runtime else None,
        args.root, args.allow_provisional_architecture,
    )
    print(json.dumps(payload, indent=2) if args.json else render_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
