#!/usr/bin/env python3
"""Publish-time metadata for one episode: title variants, a structured
description, a clean tag set, and the `metadata.json` the package stage exports.

This sits downstream of `seo_engine`. That module answers the ideation question —
what is this episode about, what does the viewer type, where do the chapters
fall. This one answers the publish question: what goes in the three fields
YouTube actually shows, under the character budgets that decide whether they are
read or truncated.

Two rules carry over from the rest of the pipeline and shape the code.

Nothing here invents a number. The number-driven title variant is only emitted
when a real count is supplied — the script's beat count — and the payload records
where that number came from. With no count, the variant falls back to a
numberless curiosity shape rather than picking a plausible "7".

Nothing here claims search volume. The queries in the description and the tags
are ranked by intent shape. No traffic was measured, and the payload says so.

Titles are candidates, not decisions. Gate 1 selects one.
"""

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from seo_engine import STOPWORDS, head_term, subject_phrase, title_case
    from state_manager import GATES, write_atomic
except ImportError:  # imported as a package from run.py
    from .seo_engine import STOPWORDS, head_term, subject_phrase, title_case
    from .state_manager import GATES, write_atomic

SCHEMA = 1

# Title budgets. YouTube stores 100 characters, shows about 60 in search, and
# truncates a Suggested Videos card well before that — the 40-50 core band is
# where a title survives both surfaces intact.
TITLE_CORE_MIN = 40
TITLE_CORE_MAX = 50
TITLE_HARD_MAX = 60
TITLE_FIELD_MAX = 100
TITLE_BAND_CENTRE = (TITLE_CORE_MIN + TITLE_CORE_MAX) // 2

# Description architecture.
HOOK_LINES = 2
SUMMARY_SENTENCES_MIN = 2
SUMMARY_SENTENCES_MAX = 3
QUERIES_MIN = 5
QUERIES_MAX = 8
QUERIES_HEADER = "Search Queries / Topics Covered"

# Tag budgets.
TAGS_MIN = 8
TAGS_MAX = 12
TAG_CHARS_MAX = 30
TAGS_FIELD_MAX = 500

VARIANTS = ("curiosity", "emotional", "direct")
VARIANT_LABELS = {
    "curiosity": "Curiosity / number-driven",
    "emotional": "Emotional / FOMO hook",
    "direct": "Direct query",
}

# Numbered shapes are used only when a counted number is available.
TITLE_TEMPLATES_NUMBERED = [
    "{S}, In {n} Steps",
    "The {n} Steps Behind {S}",
    "{n} Things Nobody Explains About {S}",
    "{n} Things About {S} Nobody Explains",
    "The {n} Steps Behind {S}, In Order",
    "{n} Reasons {S} Works The Way It Does",
    "The {n} Parts Of {S} That Actually Matter",
]

TITLE_TEMPLATES = {
    "curiosity": [
        "{S}: The Missing Part",
        "The Part Of {S} Nobody Explains",
        "What Nobody Explains About {S}",
        "What Nobody Tells You About {S}",
        "The Thing About {S} That Never Adds Up",
        "{S}: The Part That Never Gets Explained",
    ],
    "emotional": [
        "The Truth About {S}",
        "Nobody Warned You About {S}",
        "What {S} Is Quietly Doing To You",
        "The Truth About {S}, Finally",
        "You Have Been Getting {S} Wrong",
        "{S} Is Not What You Were Told",
    ],
    "direct": [
        "What Is {S}?",
        "{S}, Explained",
        "How {S} Actually Works",
        "Why {S} Happens, Explained",
        "How {S} Works, Step By Step",
        "What {S} Is And Why It Matters",
        "{S}: How It Works And Why It Matters",
    ],
}

# Query frames, ordered by how directly each maps to a typed search.
QUERY_FRAMES = [
    "how {kw} works",
    "what is {kw}",
    "why {kw} happens",
    "{kw} explained",
    "what {kw} actually does",
    "the real reason {kw}",
    "{kw} step by step",
    "is {kw} real",
]

# Core frames run against every keyword. The backfill frames only run when the
# core set lands under the eight-tag minimum — a topic with several keywords
# fills the field on its own, and padding it further is what makes a tag field
# read as spam.
TAG_FRAMES = [
    "{kw} explained",
    "how {kw} works",
    "what is {kw}",
    "why {kw} happens",
]

TAG_BACKFILL_FRAMES = [
    "{kw} science",
    "{kw} explained simply",
    "{kw} basics",
    "{kw} facts",
    "{kw} guide",
]


def utcnow():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def channel_display(channel):
    """`known-unknowns` -> `Known Unknowns`. The channel name is a tag and a
    description line, so it is rendered once, here."""
    return " ".join(w.capitalize() for w in str(channel or "").split("-") if w)


def _clean_phrase(text):
    """Lowercase, single-spaced, punctuation stripped. A tag that reads as a
    sentence fragment is spam; a tag that reads as a typed query is not."""
    text = re.sub(r"[^a-z0-9' ]+", " ", str(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def _sentence_case(text):
    """First letter up, everything else left alone — an operator's `ISS` stays
    `ISS`, which title-casing would flatten to `Iss`."""
    text = str(text).strip()
    return text[:1].upper() + text[1:] if text else text


def _topic_tag(topic):
    """The topic as a tag, or nothing. Leading stop words come off; interior
    ones stay, because `keep eating sugar even full` is a mangled phrase, not a
    search term. A topic that will not fit the per-tag budget is dropped rather
    than trimmed into nonsense."""
    words = _clean_phrase(topic).split()
    while words and words[0] in STOPWORDS:
        words.pop(0)
    phrase = " ".join(words)
    return phrase if phrase and len(phrase) <= TAG_CHARS_MAX else None


def _keyword_ngrams(keyword):
    """Contiguous multi-word runs of the operator's own keyword, longest first.
    A 24-character keyword leaves no room for a frame, so the fallback is the
    keyword itself, cut at word boundaries — never a word the operator did not
    write."""
    words = _clean_phrase(keyword).split()
    grams = []
    for size in range(len(words) - 1, 1, -1):
        for start in range(0, len(words) - size + 1):
            gram = " ".join(words[start:start + size])
            if len(gram) <= TAG_CHARS_MAX and gram not in grams:
                grams.append(gram)
    return grams


def _has_repeated_word(phrase):
    words = phrase.split()
    return len(set(words)) != len(words)


def _frame_fits(kw, phrase):
    """Reject a frame the keyword already carries, so `anaesthesia works` does
    not become `how anaesthesia works works`."""
    tail = phrase.replace(kw, "").strip()
    if tail and tail.split()[-1] in kw.split():
        return False
    return not _has_repeated_word(phrase)


def _dedupe(items):
    out = []
    for item in items:
        if item and item not in out:
            out.append(item)
    return out


# ------------------------------------------------------------------- titles

def _subject_forms(topic, primary_keyword):
    """Subjects to try, shortest-usable first. The keyword form is what the
    viewer types; the topic form is what the operator wrote."""
    forms = []
    if primary_keyword:
        forms.append(title_case(subject_phrase(primary_keyword)))
    forms.append(title_case(subject_phrase(topic)))
    forms.append(title_case(topic))
    return _dedupe(forms)


def _score(text):
    """Sort key: hard limit first, then the 40-50 core band, then distance from
    the band centre. A title over 60 characters is never preferred to one under
    it, however well it reads."""
    n = len(text)
    return (0 if n <= TITLE_HARD_MAX else 1,
            0 if TITLE_CORE_MIN <= n <= TITLE_CORE_MAX else 1,
            abs(n - TITLE_BAND_CENTRE),
            text)


def _render(templates, subjects, n=None):
    out = []
    for subject in subjects:
        for template in templates:
            if "{n}" in template:
                if n is None:
                    continue
                out.append(template.format(S=subject, n=n))
            else:
                out.append(template.format(S=subject))
    return out


def _title_record(variant, text, alternates, number, number_source):
    n = len(text)
    return {
        "variant": variant,
        "label": VARIANT_LABELS[variant],
        "text": text,
        "chars": n,
        "in_core_band": TITLE_CORE_MIN <= n <= TITLE_CORE_MAX,
        "over_hard_max": n > TITLE_HARD_MAX,
        "over_field_max": n > TITLE_FIELD_MAX,
        "number": number,
        "number_source": number_source,
        "alternates": alternates[:3],
    }


def build_titles(topic, primary_keyword=None, item_count=None,
                 item_count_source=None):
    """One candidate per variant, each the best fit to the character band.

    `item_count` is a counted quantity — the script's beat count — not a guess.
    Without one the curiosity variant is numberless and `number_source` is null.
    """
    subjects = _subject_forms(topic, primary_keyword)
    titles = []
    for variant in VARIANTS:
        templates = list(TITLE_TEMPLATES[variant])
        number = int(item_count) if (variant == "curiosity" and item_count) else None
        number_source = (item_count_source or "counted") if number else None

        plain = sorted(_dedupe(_render(templates, subjects)), key=_score)
        candidates = plain
        if number:
            # The variant is number-driven, so a numbered shape wins even when a
            # numberless one sits closer to the middle of the band. It only
            # yields when no numbered shape fits inside the hard limit.
            numbered = sorted(_dedupe(_render(TITLE_TEMPLATES_NUMBERED, subjects,
                                              n=number)), key=_score)
            if numbered and len(numbered[0]) <= TITLE_HARD_MAX:
                candidates = numbered + plain
            else:
                number, number_source = None, None
        chosen = candidates[0]
        if number and not re.search(r"\b%d\b" % number, chosen):
            number, number_source = None, None
        titles.append(_title_record(variant, chosen, candidates[1:],
                                    number, number_source))
    return titles


# -------------------------------------------------------------- description

def build_queries(keywords, limit=QUERIES_MAX):
    """High-intent search phrases, primary keyword first, ranked by how directly
    the frame maps to a typed query. No volume is measured or claimed."""
    queries = []
    for frame in QUERY_FRAMES:
        for kw in keywords:
            phrase = frame.format(kw=kw)
            if _frame_fits(kw, phrase) and phrase not in queries:
                queries.append(phrase)
            if len(queries) >= limit:
                return queries
    return queries


def build_hook(topic, keywords):
    """Two lines. The first carries the primary keyword verbatim, because it is
    the line that shows above the fold and the line search reads."""
    return [
        "%s: what is actually happening, and why it matters."
        % _sentence_case(keywords[0]),
        "%s — the short version, in the order it happens."
        % _sentence_case(str(topic).strip().rstrip(".?")),
    ][:HOOK_LINES]


def build_summary(topic, keywords, beats=None, channel=None):
    """Two or three sentences describing the premise. Every sentence is built
    from something on record — the operator's topic, the keywords, the beat
    names already in state — so nothing here asserts a fact the script does not
    carry."""
    sentences = [
        "This episode is about %s, taken from the first observation through to "
        "the mechanism itself." % str(topic).strip().rstrip(".?"),
    ]
    named = [str(b.get("name")).lower() for b in (beats or []) if b.get("name")]
    if len(named) >= 3:
        # First, middle and last, not the whole beat sheet. A nine-beat episode
        # listed in full runs past 300 characters and reads as a table of
        # contents; naming three of nine and calling it the order would be
        # inaccurate, so the sentence says where it opens, turns and closes.
        sentences.append("It opens on %s, works through %s, and closes on %s."
                         % (named[0], named[len(named) // 2], named[-1]))
    elif len(named) == 2:
        sentences.append("It opens on %s and closes on %s." % (named[0], named[1]))
    else:
        sentences.append("It works through the mechanism step by step rather "
                         "than summarising the conclusion.")
    if channel:
        sentences.append("%s covers one question per episode, in plain terms."
                         % channel_display(channel))
    return sentences[:SUMMARY_SENTENCES_MAX]


def build_description(topic, keywords, beats=None, channel=None, chapters=None):
    """Hook, then premise, then the query block — in that order, because that is
    the order the description is read: two lines above the fold, the rest after
    the viewer has already clicked."""
    hook = build_hook(topic, keywords)
    summary = build_summary(topic, keywords, beats, channel)
    queries = build_queries(keywords)

    blocks = [
        {"name": "hook", "lines": list(hook)},
        {"name": "summary", "lines": [" ".join(summary)]},
        {"name": "queries",
         "lines": [QUERIES_HEADER] + ["- %s" % q for q in queries]},
    ]
    if chapters:
        blocks.append({
            "name": "chapters",
            "lines": ["Chapters"] + ["%s %s" % (c["timestamp"], c["label"])
                                     for c in chapters],
        })

    parts = []
    for block in blocks:
        parts.append("\n".join(block["lines"]))
    text = "\n\n".join(parts)
    return {
        "text": text,
        "blocks": blocks,
        "hook_lines": hook,
        "summary_sentences": summary,
        "queries": queries,
        "queries_header": QUERIES_HEADER,
        "chars": len(text),
        "volume_measured": False,
        "ranking_basis": "query-intent shape; no search-volume data was measured",
    }


# --------------------------------------------------------------------- tags

def build_tags(topic, keywords, channel=None, extra=None):
    """Eight to twelve tags: the keywords, their highest-intent query forms, the
    channel name, and the topic's head term. Cleaned, deduped, and capped — a
    keyword-stuffed field is the failure this function exists to avoid."""
    def framed(frames):
        out = []
        for frame in frames:
            for kw in keywords:
                phrase = _clean_phrase(frame.format(kw=kw))
                if _frame_fits(_clean_phrase(kw), phrase):
                    out.append(phrase)
        return out

    candidates = [_clean_phrase(t) for t in (extra or [])]
    candidates += [_clean_phrase(kw) for kw in keywords]
    candidates.append(_topic_tag(topic))
    if channel:
        candidates.append(_clean_phrase(channel_display(channel)))
    candidates += framed(TAG_FRAMES)

    tags, rejected = [], []

    def take(pool, cap):
        for tag in pool:
            if not tag or tag in tags:
                continue
            if len(tag) > TAG_CHARS_MAX:
                rejected.append({"tag": tag,
                                 "reason": "over %d characters" % TAG_CHARS_MAX})
                continue
            if _has_repeated_word(tag):
                rejected.append({"tag": tag, "reason": "repeated word"})
                continue
            if len(tags) >= cap:
                rejected.append({"tag": tag,
                                 "reason": "over the %d-tag cap" % TAGS_MAX})
                continue
            tags.append(tag)

    take(_dedupe(candidates), TAGS_MAX)
    if len(tags) < TAGS_MIN:
        take(_dedupe(framed(TAG_BACKFILL_FRAMES)), TAGS_MIN)
    if len(tags) < TAGS_MIN:
        grams = []
        for kw in keywords:
            grams += _keyword_ngrams(kw)
        take(_dedupe(grams), TAGS_MIN)

    field, used, dropped = [], 0, []
    for tag in tags:
        cost = len(tag) + (1 if field else 0)
        if used + cost > TAGS_FIELD_MAX:
            dropped.append(tag)
            continue
        field.append(tag)
        used += cost

    channel_tag = _clean_phrase(channel_display(channel)) if channel else None
    return {
        "tags": field,
        "count": len(field),
        "field_string": ",".join(field),
        "field_chars": used,
        "field_limit": TAGS_FIELD_MAX,
        "tag_char_limit": TAG_CHARS_MAX,
        "min_tags": TAGS_MIN,
        "max_tags": TAGS_MAX,
        "channel_tag": channel_tag,
        "channel_tag_present": bool(channel_tag and channel_tag in field),
        "rejected": rejected,
        "dropped_over_field_limit": dropped,
        "volume_measured": False,
    }


# --------------------------------------------------------------- validation

def validate(payload):
    """Every rule this module claims to enforce, checked against its own output.
    Returns a list of issues; an empty list is the passing case."""
    issues = []

    def fail(code, message, severity="error"):
        issues.append({"code": code, "severity": severity, "message": message})

    titles = payload.get("titles") or []
    if [t["variant"] for t in titles] != list(VARIANTS):
        fail("titles.variants",
             "expected one title per variant %s" % ", ".join(VARIANTS))
    for t in titles:
        if t["over_field_max"]:
            fail("titles.field_max",
                 "%s title is %d characters and will not fit YouTube's %d-character "
                 "title field; pass a shorter --keyword for this episode"
                 % (t["variant"], t["chars"], TITLE_FIELD_MAX))
        elif t["over_hard_max"]:
            fail("titles.hard_max",
                 "%s title is %d characters, over the %d-character maximum"
                 % (t["variant"], t["chars"], TITLE_HARD_MAX))
        elif not t["in_core_band"]:
            fail("titles.core_band",
                 "%s title is %d characters, outside the %d-%d core band"
                 % (t["variant"], t["chars"], TITLE_CORE_MIN, TITLE_CORE_MAX),
                 severity="warning")
        if t["number"] and not t["number_source"]:
            fail("titles.number_source",
                 "%s title carries a number with no recorded source" % t["variant"])

    desc = payload.get("description") or {}
    names = [b["name"] for b in desc.get("blocks", [])]
    for required in ("hook", "summary", "queries"):
        if required not in names:
            fail("description.blocks", "description is missing the %s block" % required)
    if len(desc.get("hook_lines") or []) > HOOK_LINES:
        fail("description.hook", "hook is longer than %d lines" % HOOK_LINES)
    sentences = desc.get("summary_sentences") or []
    if not SUMMARY_SENTENCES_MIN <= len(sentences) <= SUMMARY_SENTENCES_MAX:
        fail("description.summary",
             "summary is %d sentences; expected %d-%d"
             % (len(sentences), SUMMARY_SENTENCES_MIN, SUMMARY_SENTENCES_MAX))
    queries = desc.get("queries") or []
    if not QUERIES_MIN <= len(queries) <= QUERIES_MAX:
        fail("description.queries",
             "%d search queries; expected %d-%d"
             % (len(queries), QUERIES_MIN, QUERIES_MAX))
    if QUERIES_HEADER not in desc.get("text", ""):
        fail("description.header", "description is missing the %r header" % QUERIES_HEADER)

    tags = payload.get("tags") or {}
    if not TAGS_MIN <= tags.get("count", 0) <= TAGS_MAX:
        fail("tags.count", "%d tags; expected %d-%d"
             % (tags.get("count", 0), TAGS_MIN, TAGS_MAX))
    if tags.get("channel_tag") and not tags.get("channel_tag_present"):
        fail("tags.channel", "the channel tag %r is not in the field"
             % tags.get("channel_tag"))
    if tags.get("field_chars", 0) > TAGS_FIELD_MAX:
        fail("tags.field", "tags field is %d characters, over %d"
             % (tags.get("field_chars", 0), TAGS_FIELD_MAX))
    for tag in tags.get("tags", []):
        if len(tag) > TAG_CHARS_MAX:
            fail("tags.length", "tag %r is over %d characters" % (tag, TAG_CHARS_MAX))
        if _has_repeated_word(tag):
            fail("tags.spam", "tag %r repeats a word" % tag)
    return issues


# ---------------------------------------------------------------- generate

def generate(topic, keywords=None, channel=None, episode_id=None, beats=None,
             chapters=None, selected_title=None, extra_tags=None,
             item_count=None, item_count_source=None, publish_date=None):
    """The whole metadata payload. Pure: it reads no canon and touches no disk,
    so the same inputs always give the same output and the tests can hold it to
    its own character rules."""
    # Queries and tags are lowercase; the titles use the operator's own casing,
    # so an acronym they typed in caps survives into the title.
    supplied = [k.strip() for k in (keywords or []) if k and k.strip()]
    if not supplied:
        supplied = [head_term(topic)]
    keywords = _dedupe([k.lower() for k in supplied])
    if beats and item_count is None:
        item_count = len(beats)
        item_count_source = item_count_source or "script beat count"

    titles = build_titles(topic, supplied[0], item_count, item_count_source)
    description = build_description(topic, keywords, beats, channel, chapters)
    tags = build_tags(topic, keywords, channel, extra_tags)

    chosen = selected_title or titles[0]["text"]
    payload = {
        "schema": SCHEMA,
        "generated_utc": utcnow(),
        "channel": channel,
        "episode_id": episode_id,
        "topic": topic,
        "publish_date": publish_date,
        "primary_keyword": keywords[0],
        "keywords": keywords,
        "title": chosen,
        "title_chars": len(chosen),
        "title_source": ("gate 1 selection" if selected_title
                         else "top candidate — gate 1 has not selected"),
        "titles": titles,
        "description": description,
        "tags": tags,
        "constraints": {
            "title_core_min": TITLE_CORE_MIN,
            "title_core_max": TITLE_CORE_MAX,
            "title_hard_max": TITLE_HARD_MAX,
            "title_field_max": TITLE_FIELD_MAX,
            "description_queries": [QUERIES_MIN, QUERIES_MAX],
            "tags": [TAGS_MIN, TAGS_MAX],
            "tag_chars_max": TAG_CHARS_MAX,
            "tags_field_max": TAGS_FIELD_MAX,
        },
        "notes": [
            "Titles are candidates. Gate 1 selects one.",
            "No search volume was measured; query order is intent shape only.",
        ],
    }
    payload["validation"] = validate(payload)
    payload["valid"] = not [i for i in payload["validation"] if i["severity"] == "error"]
    return payload


def from_state(state_data, selected_title=None, publish_date=None):
    """Build the payload from an episode's `state.json`, which already carries
    the topic, the keywords, the approved title and the script's beats."""
    seo = state_data.get("seo") or {}
    script = state_data.get("script") or {}
    gates = state_data.get("gates") or {}
    gate1 = gates.get(GATES["1"]["key"]) or {}
    chosen = selected_title or (gate1.get("payload") or {}).get("chosen_title")
    return generate(
        topic=state_data.get("topic") or seo.get("topic") or "",
        keywords=state_data.get("keywords") or seo.get("keywords"),
        channel=state_data.get("channel"),
        episode_id=state_data.get("episode_id"),
        beats=script.get("beats"),
        chapters=(seo.get("chapters") or {}).get("chapters"),
        selected_title=chosen,
        publish_date=publish_date or state_data.get("publish_date"),
    )


def export(payload, path):
    """Write `metadata.json` next to the episode's other assets."""
    write_atomic(path, json.dumps(payload, indent=2) + "\n")
    return path


def render_terse(payload):
    """One screen. The character counts are the point — everything else is in
    metadata.json."""
    L = []
    A = L.append
    A("topic: %s" % payload["topic"])
    A("primary keyword: %s" % payload["primary_keyword"])
    A("")
    for t in payload["titles"]:
        A("%-28s %2d  %-6s %s"
          % (t["label"], t["chars"],
             "band" if t["in_core_band"] else ("OVER" if t["over_hard_max"] else "wide"),
             t["text"]))
    A("")
    A("description: %d chars, %d queries" % (payload["description"]["chars"],
                                             len(payload["description"]["queries"])))
    A("tags: %d (%d/%d chars)" % (payload["tags"]["count"],
                                  payload["tags"]["field_chars"],
                                  payload["tags"]["field_limit"]))
    A(payload["tags"]["field_string"])
    if payload["validation"]:
        A("")
        for issue in payload["validation"]:
            A("%-8s %s: %s" % (issue["severity"], issue["code"], issue["message"]))
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Title variants, description and tags for one episode.")
    ap.add_argument("--topic", required=True)
    ap.add_argument("--keyword", action="append", dest="keywords",
                    help="search query term, used verbatim; repeatable")
    ap.add_argument("--channel")
    ap.add_argument("--episode")
    ap.add_argument("--title", help="the title approved at gate 1")
    ap.add_argument("--tag", action="append", dest="extra_tags")
    ap.add_argument("--count", type=int,
                    help="a counted quantity for the number-driven title; "
                         "omit it and no number is invented")
    ap.add_argument("--count-source", help="where --count was counted from")
    ap.add_argument("--out", help="write metadata.json to this path")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    payload = generate(
        args.topic, args.keywords, args.channel, args.episode,
        selected_title=args.title, extra_tags=args.extra_tags,
        item_count=args.count,
        item_count_source=args.count_source or ("operator-supplied" if args.count else None),
    )
    if args.out:
        export(payload, args.out)
    print(json.dumps(payload, indent=2) if args.json else render_terse(payload))
    return 0 if payload["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
