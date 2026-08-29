#!/usr/bin/env python3
"""Narration script for one episode, formatted for ElevenLabs.

What this writes is a fully structured script: every beat allocated in seconds,
every scene given a visual cue, every line carrying its SSML pauses, and the
channel's own voice lock and signature moves attached to the beat they govern.

What it does not write is a sentence of prose that asserts a fact. Anything that
needs a checked quantity, a named journal or a real study comes out as a
«FILL:» or «CITE:» marker with the instruction attached. Known Unknowns' canon
says it in one line — "Verify every citation before it is written. No
exceptions, no placeholder facts" — and a generator that invented a plausible
journal name would break that rule silently. Gate 2 refuses an approval while
markers are still unresolved, which is how the placeholder stays honest.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import memory  # noqa: E402
from canon import CHANNELS, load_canon, repo_root  # noqa: E402
from seo_engine import build_chapters, build_keywords, parse_duration, timestamp  # noqa: E402

DEFAULT_WPM = 150  # narration rate assumption; override with --wpm after measuring a real read
MARKER = re.compile(r"«(FILL|CITE|CHECK):[^»]*»")

HOOK_SECONDS = 5  # the curiosity hook owns the first five seconds, before beat 1

# The retention spine, laid over whatever beat architecture the channel canon
# already locks. It re-labels beats by position; it never replaces them. Canon
# decides what the beats are, this decides what each one has to do to hold a
# viewer.
RETENTION_PHASES = (
    (0.00, "curiosity hook", "Open a loop the viewer needs closed. No preamble, no throat-clearing."),
    (0.01, "paradox / problem", "Name the thing that should not be true, or the cost the viewer "
                                "is already paying. This is why they stay past 30 seconds."),
    (0.45, "concrete examples", "Specifics only — a number, a name, an object, a case. Abstraction "
                                "is where retention dies."),
    (0.99, "high-tempo resolution", "Shorter sentences, faster cuts, close the loop opened at the "
                                    "top. Do not introduce anything new here."),
)

EXAMPLES_FRACTION = 0.45  # where the middle turns from stating the problem to evidencing it


def retention_phase(index, total, position):
    """Which retention phase a beat sits in.

    The first beat always carries the hook and the last always carries the
    resolution, whatever the runtime — anchoring the ends by position instead
    would leave a nine-beat episode with no resolution phase at all."""
    if index == 0:
        phase = RETENTION_PHASES[0]
    elif index == total - 1:
        phase = RETENTION_PHASES[3]
    elif position >= EXAMPLES_FRACTION:
        phase = RETENTION_PHASES[2]
    else:
        phase = RETENTION_PHASES[1]
    return {"phase": phase[1], "direction": phase[2]}


def resolve_signoff(canon, requested=None, force=False):
    """Which line closes the episode, and whether canon allows it.

    Known Unknowns closes on "You're welcome." by default. Lilweid's canon
    forbids that exact line in as many words, and stickman's says the channel
    needs its own and must borrow neither. So a requested sign-off is checked
    against the channel's forbidden list and refused by name unless the operator
    overrides it deliberately."""
    forbidden = canon.signoff_forbidden or []
    if requested:
        if requested in forbidden and not force:
            raise SystemExit(
                "error: %s canon forbids closing on %r — %s\n"
                "  Pass --force-signoff to override this lock deliberately; it will be "
                "recorded in the script header as an override of canon."
                % (canon.channel, requested,
                   (canon.signoff_note or "see the Sign-off section of the canon")[:200])
            )
        return {"line": requested, "source": "operator" + (" (canon override)" if force else ""),
                "overrides_canon": bool(requested in forbidden)}
    if canon.signoff_default:
        return {"line": canon.signoff_default, "source": "canon default",
                "overrides_canon": False}
    return {
        "line": None,
        "source": "none — this channel has no canon sign-off",
        "overrides_canon": False,
        "note": (canon.signoff_note or
                 "The canon gives this channel no sign-off and forbids borrowing another "
                 "channel's. Write one, or pass --signoff."),
    }


def load_voice_config(root, channel):
    path = os.path.join(root, "automation", "config", "elevenlabs.json")
    if not os.path.isfile(path):
        raise SystemExit(f"error: missing {path}; the ElevenLabs config is part of the pipeline")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    channel_cfg = dict(cfg.get("defaults", {}))
    channel_cfg.pop("_note", None)
    channel_cfg.update({k: v for k, v in cfg.get("channels", {}).get(channel, {}).items()
                        if not k.startswith("_")})
    return {
        "path": os.path.relpath(path, root),
        "api_key_env": cfg.get("api_key_env"),
        "api_key_present": bool(os.environ.get(cfg.get("api_key_env", ""))),
        "model_id": cfg.get("model_id"),
        "output_format": cfg.get("output_format"),
        "ssml": {k: v for k, v in cfg.get("ssml", {}).items() if not k.startswith("_")},
        "voice_settings": {k: v for k, v in channel_cfg.items() if k != "voice_id" and k != "voice_name"},
        "voice_id": channel_cfg.get("voice_id"),
        "voice_name": channel_cfg.get("voice_name"),
        "rationale": cfg.get("channels", {}).get(channel, {}).get("_rationale"),
    }


def visual_direction(canon, index, total):
    """The visual register for one beat, read off the channel's canon."""
    if canon.mascot_prompt:
        return {
            "register": "flat vector 2D, recurring mascot",
            "grade": None,
            "note": "Mascot traits are restated in full on every prompt; see canon prompt block.",
        }
    if canon.visual_registers:
        # Known Unknowns: "abstract 3D carries the mechanism, photoreal carries
        # the evidence" — so the photoreal register belongs to the beats that
        # cite a study.
        evidence_beat = bool(re.search(r"discovery|result|study|evidence|complication",
                                       canon.beats[index]["name"], re.I)) if canon.beats else False
        register = canon.visual_registers[1] if (evidence_beat and len(canon.visual_registers) > 1) \
            else canon.visual_registers[0]
        return {
            "register": register,
            "grade": canon.palette,
            "note": ("Frame goes to the real world here because the narration names a study."
                     if evidence_beat else
                     "Mechanism register. Say 'in a dark void' in the prompt; it is the "
                     "channel's default ground and the first thing to drift."),
        }
    if canon.grade:
        # Lilweid: the frame moves from cool to warm as the episode resolves.
        cool = canon.grade[0] if canon.grade else None
        warm = canon.grade[1] if len(canon.grade) > 1 else None
        pick = cool if index < total / 2.0 else warm
        return {
            "register": canon.visual_register,
            "grade": pick,
            "note": "Grade travels cool to warm across the episode; this beat sits %s." % (
                "in the cool half" if index < total / 2.0 else "in the warm half"),
        }
    return {"register": canon.visual_register, "grade": canon.palette, "note": None}


def beat_lines(canon, beat, index, keywords, word_budget, ssml, retention=None):
    """Three narration slots per beat: the turn into it, the body, the hand-off.

    Each slot is a marker carrying the instruction that governs it, so whoever
    fills it can see the canon rule without opening the canon."""
    kw = keywords[index % len(keywords)]
    moves = canon.signature_moves
    move = moves[index % len(moves)] if moves else None
    lines = []
    lines.append({
        "slot": "turn",
        "text": "«FILL: turn into '%s' — %s. Land the query term '%s' in the first sentence.»" % (
            beat["name"], beat.get("description") or "no canon description", kw),
        "words": max(12, int(word_budget * 0.2)),
        "break_after": ssml.get("clause_break", "0.6s"),
    })
    lines.append({
        "slot": "body",
        "text": "«FILL: the body of '%s', roughly %d words. Retention phase: %s — %s%s»" % (
            beat["name"], max(20, int(word_budget * 0.6)),
            (retention or {}).get("phase", "unset"), (retention or {}).get("direction", ""),
            (" Signature move to use here: " + re.sub(r"\s+", " ", move)) if move else ""),
        "words": max(20, int(word_budget * 0.6)),
        "break_after": ssml.get("sentence_break", "0.35s"),
    })
    if canon.evidence_rules:
        lines.append({
            "slot": "evidence",
            "text": "«CITE: journal, year, institution, researcher, species, sample size — "
                    "verified before it is written. Leave this beat without a citation rather "
                    "than approximating one.»",
            "words": 0,
            "break_after": ssml.get("sentence_break", "0.35s"),
        })
    lines.append({
        "slot": "handoff",
        "text": "«FILL: close '%s' and hand off to the next beat, roughly %d words.»" % (
            beat["name"], max(10, int(word_budget * 0.2))),
        "words": max(10, int(word_budget * 0.2)),
        "break_after": ssml.get("beat_break", "1.0s"),
    })
    return lines


def generate(channel, topic, keywords=None, runtime_s=None, root=None, wpm=DEFAULT_WPM,
             allow_provisional=False, seconds_per_scene=None, variant=None, title=None,
             signoff=None, force_signoff=False, voice_lock=None):
    root = root or repo_root()
    canon = load_canon(channel, root)
    if voice_lock:
        canon.voice_lock = voice_lock  # operator-supplied, for a channel whose canon is blocked
    canon.voice_lock_or_die()
    pace = canon.pace_or_die(seconds_per_scene)

    if runtime_s is None:
        if not canon.runtime_range_s:
            raise SystemExit(
                f"error: {channel} has no measured runtime range in {canon.path}; "
                "pass --runtime for this episode"
            )
        runtime_s = int(round(sum(canon.runtime_range_s) / 2.0))
    if canon.runtime_range_s and not (canon.runtime_range_s[0] * 0.8 <= runtime_s
                                      <= canon.runtime_range_s[1] * 1.2):
        sys.stderr.write(
            "warning: %ss is outside this channel's verified runtime range %s-%ss\n"
            % (runtime_s, canon.runtime_range_s[0], canon.runtime_range_s[1]))

    kws = build_keywords(topic, keywords)
    chapters = build_chapters(canon, kws, runtime_s, allow_provisional)
    cfg = load_voice_config(root, channel)
    ssml = cfg["ssml"]

    learnings = memory.learnings_for(root, channel)
    signoff_spec = resolve_signoff(canon, signoff, force_signoff)

    entries = chapters["chapters"]
    beats = []
    for i, ch in enumerate(entries):
        end = entries[i + 1]["start_s"] if i + 1 < len(entries) else runtime_s
        seconds = max(1, end - ch["start_s"])
        word_budget = int(round(seconds * wpm / 60.0))
        beat = {
            "number": i + 1,
            "name": ch["beat"],
            "description": ch["beat_description"],
            "start_s": ch["start_s"],
            "end_s": end,
            "timestamp": ch["timestamp"],
            "seconds": seconds,
            "word_budget": word_budget,
            "scenes": max(1, int(round(seconds / pace))),
            "query_term": ch["query_term"],
            "retention": retention_phase(i, len(entries), ch["start_s"] / float(runtime_s)),
            "visual": visual_direction(canon, i, len(entries)),
        }
        beat["lines"] = beat_lines(canon, {"name": ch["beat"], "description": ch["beat_description"]},
                                   i, kws, word_budget, ssml, beat["retention"])
        beat["visual_cues"] = [
            {
                "scene": n + 1,
                "cue": "«FILL: scene %d of %d for '%s' — %s%s»" % (
                    n + 1, beat["scenes"], beat["name"], beat["visual"]["register"] or "register BLOCKED",
                    (", " + beat["visual"]["grade"]) if beat["visual"]["grade"] else ""),
                "seconds": round(seconds / float(beat["scenes"]), 1),
            }
            for n in range(beat["scenes"])
        ]
        beats.append(beat)

    hook_words = int(round(HOOK_SECONDS * wpm / 60.0))
    hook_block = {
        "seconds": HOOK_SECONDS,
        "word_budget": hook_words,
        "phase": RETENTION_PHASES[0][1],
        "direction": RETENTION_PHASES[0][2],
        "line": "«FILL: the first %d seconds — about %d words. Open a loop about '%s' that the "
                "viewer needs closed. No greeting, no channel name, no 'in this video'.»"
                % (HOOK_SECONDS, hook_words, kws[0]),
        "break_after": ssml.get("clause_break", "0.6s"),
    }

    body_words = hook_words + sum(l["words"] for b in beats for l in b["lines"])
    payload = {
        "channel": channel,
        "canon_path": os.path.relpath(canon.path, root),
        "topic": topic,
        "title": title,
        "variant": variant,
        "keywords": kws,
        "voice_lock": canon.voice_lock,
        "voice_lock_source": "operator-supplied" if voice_lock else "canon",
        "banned_in_narration": canon.banned_in_narration,
        "signature_moves": canon.signature_moves,
        "evidence_rules": canon.evidence_rules,
        "signoff": signoff_spec,
        "signoff_default": signoff_spec["line"],
        "signoff_forbidden": canon.signoff_forbidden,
        "signoff_note": canon.signoff_note,
        "hook": hook_block,
        "retention_phases": [{"from_fraction": f, "phase": n, "direction": d}
                             for f, n, d in RETENTION_PHASES],
        "learnings_applied": learnings,
        "runtime_target_s": runtime_s,
        "runtime_target": timestamp(runtime_s),
        "wpm_assumption": wpm,
        "seconds_per_scene": pace,
        "scene_total": sum(b["scenes"] for b in beats),
        "word_budget_total": body_words,
        "estimated_runtime_s": int(round(body_words / float(wpm) * 60)),
        "estimated_runtime": timestamp(int(round(body_words / float(wpm) * 60))),
        "duration_basis": "word budget at %d wpm; an estimate until a real read is timed" % wpm,
        "beat_method": chapters["method"],
        "beats_provisional": chapters["provisional"],
        "beats": beats,
        "elevenlabs": cfg,
        "variants_available": canon.variants,
    }
    payload["ssml"] = build_ssml(payload)
    payload["placeholders"] = count_markers(payload["ssml"])
    return payload


def build_ssml(payload):
    """One continuous ElevenLabs-ready block: narration text plus break tags,
    with the beat names as comments so a human can navigate it."""
    out = []
    hook = payload.get("hook")
    if hook:
        out.append("<!-- 00:00  curiosity hook (%ss) -->" % hook["seconds"])
        out.append(hook["line"])
        out.append('<break time="%s" />' % hook["break_after"])
    for beat in payload["beats"]:
        out.append("<!-- %s  beat %d: %s (%ss) — %s -->" % (
            beat["timestamp"], beat["number"], beat["name"], beat["seconds"],
            beat["retention"]["phase"]))
        for line in beat["lines"]:
            out.append(line["text"])
            out.append('<break time="%s" />' % line["break_after"])
    if payload["signoff_default"]:
        out.append('<break time="%s" />' % payload["elevenlabs"]["ssml"].get("beat_break", "1.0s"))
        out.append(payload["signoff_default"])
    return "\n".join(out)


def count_markers(text):
    found = MARKER.findall(text)
    return {"total": len(found), "fill": found.count("FILL"),
            "cite": found.count("CITE"), "check": found.count("CHECK")}


def unresolved_markers(text):
    return MARKER.findall(text)


def render_markdown(p):
    L = []
    A = L.append
    A("# 02 — Narration script")
    A("")
    A("| Field | Value |")
    A("|---|---|")
    A("| Channel | `%s` |" % p["channel"])
    A("| Title | %s |" % (p["title"] or "_not selected — gate 1_"))
    A("| Variant | %s |" % (p["variant"] or "n/a"))
    A("| Target runtime | %s |" % p["runtime_target"])
    A("| Estimated runtime | %s (%s) |" % (p["estimated_runtime"], p["duration_basis"]))
    A("| Word budget | %d |" % p["word_budget_total"])
    A("| Scenes | %d at %ss each |" % (p["scene_total"], p["seconds_per_scene"]))
    A("| Beat method | %s |" % p["beat_method"])
    A("| Sign-off | %s (%s) |" % (
        ('`"%s"`' % p["signoff"]["line"]) if p["signoff"]["line"] else "none",
        p["signoff"]["source"]))
    A("| Learnings applied | %d |" % len(p["learnings_applied"]))
    A("| Unresolved markers | %d (%d FILL, %d CITE) |" % (
        p["placeholders"]["total"], p["placeholders"]["fill"], p["placeholders"]["cite"]))
    A("")
    if p["beats_provisional"]:
        A("> **These beats are provisional.** The channel canon marks its architecture "
          "[BLOCKED]; nothing here is a lock.")
        A("")
    A("## Voice lock")
    A("")
    A("> %s" % p["voice_lock"])
    A("")
    if p["banned_in_narration"]:
        A("**Banned in narration**")
        A("")
        for b in p["banned_in_narration"]:
            A("- %s" % b)
        A("")
    if p["signoff_forbidden"]:
        A("**Never close on:** %s" % ", ".join('`"%s"`' % s for s in p["signoff_forbidden"]))
        A("")
    sign = p["signoff"]
    A("**Sign-off:** %s — %s" % (
        ('`"%s"`' % sign["line"]) if sign["line"] else "none set",
        sign["source"]))
    if sign.get("overrides_canon"):
        A("")
        A("> **This sign-off overrides the channel canon.** It was forced with "
          "`--force-signoff`. The canon says: %s" % (p.get("signoff_note") or "see the canon."))
    if sign.get("note"):
        A("")
        A("> %s" % sign["note"])
    A("")
    if p["learnings_applied"]:
        A("## Learnings carried in from past episodes")
        A("")
        A("| ID | Finding | Fix |")
        A("|---|---|---|")
        for e in p["learnings_applied"]:
            A("| %s | %s | %s |" % (e["id"], e["finding"], e["fix"]))
        A("")
    A("## Retention spine")
    A("")
    A("The first %ss is a curiosity hook, then the canon beats carry the phases below."
      % p["hook"]["seconds"])
    A("")
    A("| Position | Phase | What it has to do |")
    A("|---|---|---|")
    A("| first beat | %s | %s |" % (p["retention_phases"][0]["phase"],
                                    p["retention_phases"][0]["direction"]))
    A("| middle, before %d%% | %s | %s |" % (round(EXAMPLES_FRACTION * 100),
                                             p["retention_phases"][1]["phase"],
                                             p["retention_phases"][1]["direction"]))
    A("| middle, from %d%% | %s | %s |" % (round(EXAMPLES_FRACTION * 100),
                                           p["retention_phases"][2]["phase"],
                                           p["retention_phases"][2]["direction"]))
    A("| last beat | %s | %s |" % (p["retention_phases"][3]["phase"],
                                   p["retention_phases"][3]["direction"]))
    A("")
    if p["evidence_rules"]:
        A("## Evidence discipline")
        A("")
        for r in p["evidence_rules"]:
            A("- %s" % r)
        A("")
    A("## Beat sheet")
    A("")
    A("| # | Beat | In | Secs | Words | Scenes | Retention phase | Register |")
    A("|---|---|---|---|---|---|---|---|")
    for b in p["beats"]:
        A("| %d | %s | %s | %d | %d | %d | %s | %s |" % (
            b["number"], b["name"], b["timestamp"], b["seconds"], b["word_budget"],
            b["scenes"], b["retention"]["phase"], b["visual"]["register"] or "BLOCKED"))
    A("")
    A("## Script")
    A("")
    A("### 00:00 — curiosity hook (%ss, ~%d words)" % (p["hook"]["seconds"],
                                                       p["hook"]["word_budget"]))
    A("")
    A("_%s_" % p["hook"]["direction"])
    A("")
    A(p["hook"]["line"])
    A("")
    for b in p["beats"]:
        A("### %s — beat %d: %s" % (b["timestamp"], b["number"], b["name"]))
        A("")
        if b["description"]:
            A("_%s._" % b["description"])
            A("")
        A("**Retention phase:** %s — %s" % (b["retention"]["phase"], b["retention"]["direction"]))
        A("")
        A("**Visual:** %s%s%s" % (
            b["visual"]["register"] or "BLOCKED",
            (" · " + b["visual"]["grade"]) if b["visual"]["grade"] else "",
            (" · " + b["visual"]["note"]) if b["visual"]["note"] else ""))
        A("")
        for line in b["lines"]:
            A("%s" % line["text"])
            A("")
        A("**Visual cues (%d scenes)**" % b["scenes"])
        A("")
        for cue in b["visual_cues"]:
            A("- `%ss` %s" % (cue["seconds"], cue["cue"]))
        A("")
    A("## ElevenLabs block")
    A("")
    cfg = p["elevenlabs"]
    A("| Setting | Value |")
    A("|---|---|")
    A("| voice_id | %s |" % (cfg["voice_id"] or "**NOT SET** — supply the operator's voice id in `%s`" % cfg["path"]))
    A("| model_id | %s |" % cfg["model_id"])
    A("| output_format | %s |" % cfg["output_format"])
    for k, v in sorted(cfg["voice_settings"].items()):
        A("| %s | %s |" % (k, v))
    A("| API key | `$%s` %s |" % (cfg["api_key_env"],
                                  "present in env" if cfg["api_key_present"] else "not set in this shell"))
    A("")
    if cfg["rationale"]:
        A("_%s_" % cfg["rationale"])
        A("")
    A("Paste-ready narration with SSML pauses:")
    A("")
    A("```xml")
    A(p["ssml"])
    A("```")
    A("")
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="ElevenLabs-ready narration script for one episode.")
    ap.add_argument("--channel", required=True, choices=CHANNELS)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--keyword", action="append", dest="keywords")
    ap.add_argument("--runtime")
    ap.add_argument("--wpm", type=int, default=DEFAULT_WPM)
    ap.add_argument("--seconds-per-scene", type=float)
    ap.add_argument("--variant")
    ap.add_argument("--title")
    ap.add_argument("--voice-lock",
                    help="narration direction for a channel whose canon marks its voice BLOCKED")
    ap.add_argument("--signoff", help="closing line; checked against the channel's canon")
    ap.add_argument("--force-signoff", action="store_true",
                    help="use --signoff even when the channel canon forbids that line")
    ap.add_argument("--allow-provisional-architecture", action="store_true")
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    payload = generate(
        args.channel, args.topic, args.keywords,
        parse_duration(args.runtime) if args.runtime else None,
        args.root, args.wpm, args.allow_provisional_architecture,
        args.seconds_per_scene, args.variant, args.title,
        args.signoff, args.force_signoff, args.voice_lock,
    )
    print(json.dumps(payload, indent=2) if args.json else render_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
