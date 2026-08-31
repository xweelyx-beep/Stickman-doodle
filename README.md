# Stickman-doodle

Asset repository for the **Stickman** channel — faceless 2D stickman animation
explaining life skills and how things work, in modern YouTube explainer style.
Long-form is the engine; Shorts are cut from it.

Migrated out of [xweelyx-beep/Business](https://github.com/xweelyx-beep/Business)
on 2026-08-29. What moved, what did not, and why: [`docs/MIGRATION.md`](docs/MIGRATION.md).

> **Read this first.** The channel canon is **provisional and deliberately
> incomplete.** Two episodes exist — one finished, one nearly done — and neither
> has been analysed, because they live on a local Windows drive this environment
> cannot reach. Everything visual below the mascot is `[BLOCKED]`, not guessed.
> **Do not fill a blocked section from imagination.** A lock invented here would
> contradict footage that already exists, which is worse than no lock at all.

---

## Structure

```
prompts/      per-episode image and video prompt files          — no assets yet
references/   mascot lock, style rules, brand gate              — 5 files
audio/        music cues and voiceover assets                   — no assets yet
docs/         channel bible, pipeline docs, toolchain locks     — 5 files
scripts/      pinned snapshot of the generation pipeline        — 16 files
```

| Folder | What belongs there |
|---|---|
| [`prompts/`](prompts/) | `image_prompts_<slug>.txt` and `video_prompts_<slug>.json`, one set per episode |
| [`references/`](references/) | The mascot reference image, the written character lock, the style rules, `brand.json` |
| [`audio/`](audio/) | Cue sheets and voiceover settings. Renders are gitignored — commit what reproduces them, not the files |
| [`docs/`](docs/) | The channel bible and everything about how the pipeline runs |
| [`scripts/`](scripts/) | Read-only snapshot. Business is the source of truth — see [`scripts/README.md`](scripts/README.md) |

## Start here

| Question | File |
|---|---|
| What is this channel, and what is still undecided? | [`docs/channel-bible.md`](docs/channel-bible.md) |
| What does the mascot look like, exactly? | [`references/character-sheet.md`](references/character-sheet.md) |
| What are the production rules? | [`references/style-rules.md`](references/style-rules.md) |
| Which models and voices are locked? | [`docs/toolchain.md`](docs/toolchain.md) |
| How do I run an episode? | [`docs/pipeline-commands.md`](docs/pipeline-commands.md) |
| Why are those gates there? | [`docs/pipeline-conventions.md`](docs/pipeline-conventions.md) |
| How do I generate the frames by hand? | [`docs/generating-frames.md`](docs/generating-frames.md) |
| How do I render all 157 automatically? | [`docs/auto-generation.md`](docs/auto-generation.md) |
| Where did all this come from? | [`docs/MIGRATION.md`](docs/MIGRATION.md) |

## Workflow

An episode runs in four commands with three human gates between them. The gates
are the point: nothing paid fires without a person approving the exact credit
estimate, and the state machine will not let a stage skip one.

```
init ──GATE 1── script ──GATE 2── prompts ──GATE 3── package
       title & hook          script            credit spend
```

| Stage | Writes | Then |
|---|---|---|
| `init` | `01_ideation_and_seo.md` | **halt** — a human picks the title |
| `script` | `02_narration_script.md` | **halt** — a human approves the script |
| `prompts` | `03_kie_video_prompts.json`, `04_kie_thumbnail_prompts.md` | **halt** — a human approves the credit estimate |
| `package` | `05_metadata.md`, publish plan row | done |

There is no `--approve` flag on any generate command. Approval is always a
separate invocation by a person, recorded with their name and the time.

Run it from the Business checkout, not this one — [`scripts/README.md`](scripts/README.md)
explains why.

### Inside the generation loop

From `references/style-rules.md` §1, and these are hard:

- **15-second blocks**, three 5-second clips each.
- **Stop and wait for approval after every block.** No exceptions.
- **Never more than three generation prompts at once.** Prompting a whole script
  is forbidden.
- **Camera motion on every clip** — exactly one of `slow push-in`,
  `slow pull-back`, `slow tilt-up`, `gentle drift`. A static shot is a failure.
- **No block repeats the same motion in all three scenes.**
- **A negative prompt on every clip.**

### Stickman art: two routes

**Manual (default).** `prompts` emits a numbered, timestamped queue sheet; a
human runs it through Google Flow or Meta AI and drops the returned files back
in. The four-command pipeline submits nothing.

**Automated.** `scripts/auto_generate.py` submits to a configured backend — see
below. Enabling it means this repository *does* now contain code that calls a
paid endpoint, which is why `models.json` was rewritten rather than left saying
otherwise.

## Current state

| | |
|---|---|
| **Mascot** | ✅ locked, from the operator's reference image |
| **3-panel character sheet** | ❌ `[TBD]` — generate from the reference before episode three |
| **Channel name / @handle** | ❌ `[TBD]` — the operator's decision, not a derived one |
| **Visual system** | 🚫 `[BLOCKED]` on footage |
| **Voice register** | 🚫 `[BLOCKED]` on footage. Eva is a preference, not a lock |
| **Episode architecture** | 🚫 `[BLOCKED]` on footage |
| **Long-form schedule** | ❌ Friday, but unschedulable — 6 of 7 brand items are `false` |
| **Sign-off line** | ❌ needed, and must not borrow the sibling channels' |

**One reachable link to either finished episode unblocks all three blocked
sections.** Unlisted YouTube or any host serving a direct URL. On arrival: run
the scene analysis and replace every `[BLOCKED]` marker with a verified lock.

## House rules that apply here

- **Faceless is absolute.** No face, no name, no personal identity in any
  published asset. Not tradeable for a better-performing thumbnail.
- **The paid tool is never the agent's choice.** Name the options with real
  costs and wait. Picking one and proceeding is the failure, even when the pick
  would have been correct.
- **Never invent the mascot.** Reference the locked image.
- **Every prompt stands alone.** Restate the locked traits in full.
- **Actionable means actionable.** An episode that explains a mechanism but
  hands the viewer nothing to do has drifted toward Lilweid.
- **Videos get analysed, not guessed.**

## Generating the frames

```bash
python3 scripts/generate_frames.py plan     # validate and show the batch plan
python3 scripts/generate_frames.py next     # hand out the next 3 prompts
python3 scripts/generate_frames.py verify   # record what landed in output/frames/
python3 scripts/generate_frames.py status   # progress
```

This driver **submits nothing and makes no network call.** It hands out three
frames at a time and halts, because
[`references/style-rules.md`](references/style-rules.md) §1 caps concurrency at
three and calls bulk generation a failure. What it automates is the queue:
validation, batching, verification, durable progress, and resume.

Full detail: [`docs/generating-frames.md`](docs/generating-frames.md).

### Or render all 157 automatically

```bash
python3 scripts/auto_generate.py --list-backends
python3 scripts/auto_generate.py --backend mock --start 0 --end 156 --execute   # free
python3 scripts/auto_generate.py --backend fal  --start 0 --end 156 \
        --delay 3 --execute --approve-spend 157                                 # paid
```

`scripts/auto_generate.py` submits, downloads, verifies and resumes on its own.
It supports HTTP providers (Gemini/Imagen, fal, Replicate) and Google Flow via
Playwright, with exponential backoff, `Retry-After` handling, and rate limiting.

Two guards are deliberate: **`--backend` is required** — `generation.json` names
no default, because picking a paid tool is yours to do — and every run is a
**dry run unless `--execute`**, with paid backends additionally needing
`--approve-spend N` matching the exact image count.

Enabling this changed `models.json`, which previously said the repository
contained no code calling a paid endpoint. That entry was rewritten rather than
left to contradict the code beside it.

Full detail, including the terms-of-service risk on the Flow backend:
[`docs/auto-generation.md`](docs/auto-generation.md).

## Episode assets

**Why You Check Your Phone** — 11:22, complete.

| | |
|---|---|
| Image prompts | **157 frames** — `prompts/` |
| Revision pass | 28.7% → **47.8%** character presence, 30 frames changed, 127 byte-identical |
| Music bed | 7 movements across the full 11:22 — `audio/music_bed_cues.md` |

All 157 frames carry real `[MM:SS]` timestamps, `[00:00]`–`[11:22]`, strictly
increasing and ending exactly on the runtime. Four of the five music-bed
movement boundaries land on a frame exactly.
