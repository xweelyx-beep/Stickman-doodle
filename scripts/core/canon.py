#!/usr/bin/env python3
"""Read the channel's canon out of the path declared in channel.json.

The canon files are the single source of truth for voice, pace, architecture and
visual system. Nothing in this package hard-codes a channel fact: every value
below is parsed out of the rule file, and anything the canon marks `[BLOCKED]`
or `[TBD]` comes back as None with the block recorded, never as a plausible
default. A blocked lock that quietly becomes a number is the failure mode this
module exists to prevent.
"""

import argparse
import json
import os
import re

try:
    import paths
except ImportError:  # imported as a package from run.py
    from . import paths

# Resolved from channel.json rather than hard-coded, so this module carries no
# knowledge of which channel the repository holds.
CHANNELS = paths.channels()

# Reference-table columns the pace parser needs. Both verified canons carry a
# "| Ref | Subject | Runtime | Scenes | Pace |" table; stickman's episode table
# has neither runtime nor scene counts, which is why its pace comes back None.
_TABLE_HEAD = re.compile(r"^\|\s*Ref\s*\|", re.I)
_BLOCKED = re.compile(r"\[(BLOCKED|TBD)\]")
_MMSS = re.compile(r"^(\d+):(\d{2})$")


def repo_root(start=None):
    """Repository root. Delegates to paths.py, the layout authority."""
    return paths.find_root(start)


def _strip_frontmatter(text):
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[text.find("\n", end + 1) + 1:]
    return text


def _split_sections(body):
    """Return [(level, heading, text)] for every ## and ### heading, in order."""
    out = []
    current = None
    for line in body.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            if current:
                out.append(current)
            current = [len(m.group(1)), m.group(2).strip(), []]
        elif current:
            current[2].append(line)
    if current:
        out.append(current)
    return [(lvl, head, "\n".join(lines).strip()) for lvl, head, lines in out]


def _find(sections, *needles, **kw):
    """First section whose heading contains every needle (case-insensitive)."""
    level = kw.get("level")
    low = [n.lower() for n in needles]
    for lvl, head, text in sections:
        if level and lvl != level:
            continue
        h = head.lower()
        if all(n in h for n in low):
            return head, text
    return None, None


def _blockquote(text):
    """Join a markdown blockquote into one line, dropping bold markers."""
    if not text:
        return None
    lines = [l[1:].strip() for l in text.splitlines() if l.startswith(">")]
    if not lines:
        return None
    quote = " ".join(x for x in lines if x)
    return quote.replace("**", "").strip() or None


def _bullets(text):
    if not text:
        return []
    out = []
    for line in text.splitlines():
        m = re.match(r"^[-*]\s+(.*)$", line)
        if m:
            out.append(m.group(1).strip())
        elif out and line.startswith("  ") and line.strip():
            out[-1] += " " + line.strip()
    return [re.sub(r"\s+", " ", b).replace("**", "") for b in out]


def _mmss_to_seconds(value):
    m = _MMSS.match(value.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _parse_reference_table(body):
    """Pull the verified-episode table: runtime seconds, scene counts, pace."""
    rows = []
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if not _TABLE_HEAD.match(line.strip()):
            continue
        for row in lines[i + 2:]:
            row = row.strip()
            if not row.startswith("|"):
                break
            cells = [c.strip().strip("`") for c in row.strip("|").split("|")]
            if len(cells) < 5:
                break
            seconds = _mmss_to_seconds(cells[2])
            try:
                scenes = int(cells[3])
            except ValueError:
                scenes = None
            if seconds is None or not scenes:
                continue
            rows.append({
                "ref": cells[0],
                "subject": cells[1],
                "runtime_seconds": seconds,
                "scenes": scenes,
                "seconds_per_scene": round(seconds / scenes, 2),
            })
        break
    return rows


def _parse_beats(text):
    """Numbered `1. **Name** (0:00-0:16) - description` architecture lists."""
    if not text:
        return []
    joined = []
    for line in text.splitlines():
        if re.match(r"^\d+\.\s", line):
            joined.append(line.strip())
        elif joined and line.startswith(("   ", "\t")) and line.strip():
            joined[-1] += " " + line.strip()
        elif joined and not line.strip():
            continue
        elif joined and not line.startswith(" "):
            break
    beats = []
    for item in joined:
        m = re.match(
            r"^(\d+)\.\s+\*\*(.+?)\*\*\s*(?:\((\d+:\d{2})\s*[–—-]\s*(\d+:\d{2})\))?"
            r"\s*[—–-]?\s*(.*)$",
            item,
        )
        if not m:
            continue
        start = _mmss_to_seconds(m.group(3)) if m.group(3) else None
        end = _mmss_to_seconds(m.group(4)) if m.group(4) else None
        beats.append({
            "number": int(m.group(1)),
            "name": m.group(2).strip(),
            "verified_start_s": start,
            "verified_end_s": end,
            "verified_share": None if start is None or end is None else end - start,
            "description": re.sub(r"\s+", " ", m.group(5)).strip().rstrip("."),
        })
    return beats


def _parse_variants(text):
    if not text:
        return []
    out = []
    for m in re.finditer(r"\*\*Variant ([A-Z]) [—–-] (.+?)\*\*\s*\(([^)]*)\)", text):
        out.append({"id": m.group(1), "name": m.group(2).strip(), "note": m.group(3).strip()})
    return out


def _first_bold(text):
    if not text:
        return None
    m = re.search(r"\*\*(.+?)\*\*", text, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _bold_leads(text):
    """Every `**Lead sentence.**` in a section, in order. Used where the canon
    writes locks as bolded paragraph leads rather than bullets."""
    if not text:
        return []
    return [re.sub(r"\s+", " ", m).strip() for m in re.findall(r"\*\*(.+?)\*\*", text, re.S)]


def _quoted(text):
    """Backticked spoken lines, e.g. `"You're welcome."` — how the canon writes
    a sign-off. Bare backticks (file names, skill names) are deliberately not
    matched, so `scriptwriting` never reads as a spoken line."""
    if not text:
        return []
    out = re.findall(r"`\"(.+?)\"`", text)
    seen, uniq = set(), []
    for q in out:
        q = q.strip().strip('"')
        if q and q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


class Canon(object):
    """Parsed view of one channel's rule file. Unknown stays None."""

    def __init__(self, channel, path, body):
        self.channel = channel
        self.path = path
        self.body = body
        self.sections = _split_sections(body)

        head = re.search(r"^#\s+(.*)$", body, re.M)
        self.title = head.group(1).strip() if head else channel

        self.episodes = _parse_reference_table(body)
        paces = [e["seconds_per_scene"] for e in self.episodes]
        runtimes = [e["runtime_seconds"] for e in self.episodes]
        self.seconds_per_scene = round(sum(paces) / len(paces), 2) if paces else None
        self.runtime_range_s = (min(runtimes), max(runtimes)) if runtimes else None

        _, voice = _find(self.sections, "voice lock")
        self.voice_lock = _blockquote(voice)
        _, moves = _find(self.sections, "signature moves")
        self.signature_moves = _bullets(moves)
        _, evidence = _find(self.sections, "evidence discipline")
        self.evidence_rules = _bullets(evidence)
        _, banned = _find(self.sections, "banned")
        self.banned_in_narration = _bullets(banned)
        _, signoff = _find(self.sections, "sign-off")
        self.signoff_note = re.sub(r"\s+", " ", signoff).strip() if signoff else None
        # A sign-off is only canon when the section says to use it by default.
        # Lilweid's sign-off section exists purely to forbid borrowing Known
        # Unknowns' line, so it must come back as None, not as that line.
        self.signoff_forbidden = []
        flat = re.sub(r"\s+", " ", signoff or "")
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z*])", flat):
            if re.search(r"never|must not", sentence, re.I):
                self.signoff_forbidden.extend(_quoted(sentence))
        allowed = [q for q in _quoted(signoff) if q not in self.signoff_forbidden]
        self.signoff_default = None
        if signoff and re.search(r"by default|use it\b", signoff, re.I) and allowed:
            self.signoff_default = allowed[0]

        arch_head, arch = _find(self.sections, "episode architecture")
        self.architecture_heading = arch_head
        self.architecture_blocked = bool(arch_head and _BLOCKED.search(arch_head))
        self.beats = [] if self.architecture_blocked else _parse_beats(arch)
        self.variants = [] if self.architecture_blocked else _parse_variants(arch)

        vis_head, _ = _find(self.sections, "visual system", level=2)
        self.visual_blocked = bool(vis_head and _BLOCKED.search(vis_head))
        _, palette = _find(self.sections, "palette")
        self.palette = _first_bold(palette)
        register = None
        for lvl, head, text in self.sections:
            if re.match(r"^register\b", head.strip(), re.I):
                register = text
                break
        self.visual_register = _first_bold(register)
        _, grade = _find(self.sections, "grade")
        self.grade = _bullets(grade)
        _, registers = _find(self.sections, "registers")
        self.visual_registers = [b.split(".")[0].strip() for b in _bold_leads(registers)
                                 if not b.strip().endswith(":")]

        _, mascot = _find(self.sections, "prompt block")
        self.mascot_prompt = _blockquote(mascot)
        self.negative_prompt = None
        if mascot:
            neg = re.search(r"\*\*Negative:\*\*\s*([^\n]*(?:\n(?!\s*$)[^\n]*)*)", mascot)
            if neg:
                first = neg.group(1).split("\n\n")[0]
                self.negative_prompt = re.sub(r"\s+", " ", first).strip().rstrip(".")

        _, rules = _find(self.sections, "production rules")
        self.production_rules = _bullets(rules)
        _, constraints = _find(self.sections, "production constraints")
        self.production_constraints = _bullets(constraints) or _bold_leads(constraints)

        self.aspect_long = "16:9"
        self.aspect_short = "9:16"
        for bullet in self.production_rules + self.production_constraints:
            m = re.search(r"(\d+:\d+)\s+for Shorts,\s*(\d+:\d+)\s+for long-form", bullet)
            if m:
                self.aspect_short, self.aspect_long = m.group(1), m.group(2)

        self.blocked = sorted({
            head for _, head, text in self.sections
            if _BLOCKED.search(head) or _BLOCKED.search(text)
        })

    def voice_lock_or_die(self):
        if not self.voice_lock:
            raise SystemExit(
                f"error: {self.channel} has no verified voice lock in {self.path}; "
                "the canon marks it [BLOCKED]. Supply --voice-lock explicitly or "
                "unblock the canon before generating narration."
            )
        return self.voice_lock

    def pace_or_die(self, override=None):
        if override:
            return override
        if not self.seconds_per_scene:
            raise SystemExit(
                f"error: {self.channel} has no measured pace in {self.path} "
                "(no verified episode table). Pass --seconds-per-scene with a "
                "number you measured; this tool will not guess one."
            )
        return self.seconds_per_scene

    def to_dict(self):
        return {
            "channel": self.channel,
            "path": self.path,
            "title": self.title,
            "verified_episodes": self.episodes,
            "seconds_per_scene": self.seconds_per_scene,
            "runtime_range_s": list(self.runtime_range_s) if self.runtime_range_s else None,
            "voice_lock": self.voice_lock,
            "signature_moves": self.signature_moves,
            "evidence_rules": self.evidence_rules,
            "banned_in_narration": self.banned_in_narration,
            "signoff_default": self.signoff_default,
            "signoff_forbidden": self.signoff_forbidden,
            "signoff_note": self.signoff_note,
            "beats": self.beats,
            "variants": self.variants,
            "architecture_blocked": self.architecture_blocked,
            "visual_blocked": self.visual_blocked,
            "palette": self.palette,
            "visual_register": self.visual_register,
            "visual_registers": self.visual_registers,
            "grade": self.grade,
            "mascot_prompt": self.mascot_prompt,
            "negative_prompt": self.negative_prompt,
            "production_rules": self.production_rules,
            "production_constraints": self.production_constraints,
            "aspect_long": self.aspect_long,
            "aspect_short": self.aspect_short,
            "blocked_sections": self.blocked,
        }


def load_canon(channel, root=None):
    root = root or repo_root()
    paths.check_channel(channel, root)
    path = paths.canon_path(channel, root)
    if not os.path.isfile(path):
        raise SystemExit(f"error: canon not found at {path}; the channel bible is missing")
    with open(path, "r", encoding="utf-8") as fh:
        return Canon(channel, path, _strip_frontmatter(fh.read()))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Inspect a channel canon as parsed by the pipeline.")
    ap.add_argument("--channel", required=True, choices=CHANNELS)
    ap.add_argument("--root", help="repository root (defaults to auto-detect)")
    ap.add_argument("--json", action="store_true", help="emit the parsed canon as JSON")
    args = ap.parse_args(argv)

    canon = load_canon(args.channel, args.root)
    if args.json:
        print(json.dumps(canon.to_dict(), indent=2))
        return 0
    d = canon.to_dict()
    print(f"{d['title']}  ({d['path']})")
    print(f"  pace          : {d['seconds_per_scene'] or 'UNMEASURED'} s/scene "
          f"from {len(d['verified_episodes'])} verified episodes")
    rr = d["runtime_range_s"]
    print(f"  runtime range : {rr[0]}-{rr[1]}s" if rr else "  runtime range : UNMEASURED")
    print(f"  voice lock    : {d['voice_lock'] or 'BLOCKED'}")
    print(f"  beats         : {len(d['beats'])}"
          + (" (architecture BLOCKED)" if d["architecture_blocked"] else ""))
    print(f"  variants      : {', '.join(v['id'] + ' ' + v['name'] for v in d['variants']) or '-'}")
    print(f"  blocked       : {len(d['blocked_sections'])} sections")
    for head in d["blocked_sections"]:
        print(f"                  - {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
