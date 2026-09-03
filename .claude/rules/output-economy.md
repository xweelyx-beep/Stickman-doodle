# Output economy

The cheapest token is the one not spent; the second cheapest is the one that
carries a fact.

Ported from xweelyx-beep/Business on 2026-09-02 with the paths rewritten for
this repository.

## In replies

- Lead with the outcome. No preamble, no restating the request back.
- Show the **diff or the changed lines**, never a full file reprint. If a whole
  file must be shown, say why first.
- Quote the real terminal output, trimmed to the lines that carry the result —
  not the whole scrollback, not a description of it.
- One table beats three paragraphs. Cut adjectives, keep numbers.
- No progress narration ("Now I'll...", "Let me..."). Do it, then report.
- Do not re-explain a decision already recorded in `.claude/memory.md`,
  `docs/channel-bible.md` or `scripts/README.md`. Point to it.

## While working

- Read the part of the file you need — `sed -n`, `grep -n` — before reading all
  of it. Whole-file reads are for files under ~200 lines or genuine rewrites.
- Search before reading: `grep -rn` to find the anchor, then read around it.
- Batch independent commands into one call rather than a call each.
- Re-reading a file you just wrote is wasted context; the write already failed
  loudly if it failed.
- `scripts/core/canon.py --json` prints the parsed canon in about twenty lines.
  Prefer it to reading the whole channel bible when all you need is a lock.
- `run.py status` is the cheap way to ask where an episode stands; `state.json`
  is the expensive way. Episode files are large by design — a long-form
  `03_kie_video_prompts.json` runs past 100 KB. Use `--json` and pipe it.

## When the session gets long

- The status line shows context use (`.claude/statusline.py`). Past ~70% finish
  the step in hand rather than starting a new one.
- `.claude/hooks/context_watch.py` warns once when the transcript gets long, and
  `.claude/hooks/precompact_checkpoint.py` puts the position on disk before a
  compaction so `session_context.py` can hand it back afterwards. Checkpoint by
  hand before ending a session: `python3 scripts/core/memory.py checkpoint`.
- An episode's `state.json` past 96 KB triggers the pipeline's own overflow
  banner (`STATE_WARN_KB` in `scripts/run.py`). That is the signal to finish the
  session, not to push through it. The position is already checkpointed in
  `memory/`, so a fresh session resumes with `run.py status`.
