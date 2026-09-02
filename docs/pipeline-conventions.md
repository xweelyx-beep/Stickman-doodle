---
paths:
  - "automation/**"
---

# Automation pipeline

The 95/5 pipeline: four commands, three human gates, one state machine. The
tools are stdlib-only Python and they run the same way from a shell, from an
agent, or from CI. Nothing here calls a paid API.

## The four commands

```bash
python automation/run.py init    --channel <name> --topic "<topic>" [--keyword "<query term>"] [--runtime 8:30]
python automation/run.py script  --channel <name> --episode <id>
python automation/run.py prompts --channel <name> --episode <id>
python automation/run.py package --channel <name> --episode <id> [--publish --publish-date YYYY-MM-DD]
```

Between them: `approve --gate 1|2|3`, and `status` to see where anything stands.
Around them: `wizard` (the guided flow), `schedule` and `remind` (publishing),
`analyze` (retention audit), `checkpoint` (cross-session position).

```
init ──▶ GATE 1 title & hook ──▶ script ──▶ GATE 2 script ──▶ prompts ──▶ GATE 3 credits ──▶ package
DRAFT ─────────────────────────────────────▶ SCRIPT_APPROVED ─────────▶ PROMPTS_STAGED ──▶ RENDERED ──▶ PUBLISHED
```

## Gate discipline

- **A generate command never approves its own output.** There is no `--approve`
  flag on `init`, `script`, `prompts` or `package`. Approval is a separate
  invocation of `approve`, by a person, logged with their name and the time.
  Adding a convenience flag that collapses the two would delete the 5%.
- **Gates run 1 → 2 → 3.** No skipping, no re-approving, no force flag.
- **Gate 1 selects a title.** `--title <n>` is required; the choice is written
  into `state.json` and carried through to the metadata.
- **Gate 2 refuses a script that still has `«FILL»` or `«CITE»` markers.**
  `--allow-placeholders` exists for a deliberately unfinished draft and says so
  in the log. It is not the normal path.
- **Gate 3 requires a stated spend.** `--credits <n>` is what the operator is
  approving, recorded verbatim. Nothing in this repo submits to KIE.

## Toolchain locks

Set by the operator in `automation/config/models.json`. The pipeline reads them
and refuses to run a paid stage against anything else.

| Stage | Lock |
|---|---|
| Voice | ElevenLabs direct API, key from `$ELEVENLABS_API_KEY`. Known Unknowns: **Johnny Kid** (`8JVbfL6oEdmuxKn5DK2C`), locked. Stickman: **Eva** (`Xn6GqAFT1vo7SexgOVmn`), a preference, not final. Lilweid: unassigned. |
| Video | Seedance 1.5 Pro via KIE, 4K, 16:9 long-form / 9:16 Shorts |
| Thumbnails | Flux, GPT-Image fallback |
| Stickman art | Nano Banana Pro, **manual** via Google Flow or Meta AI |

- **A different video model is an error, not a warning.** `--video-model kling`
  exits non-zero and names the lock file. Changing the decision means editing
  that file, deliberately.
- **The Nano Banana Pro route is not automated and does not pretend to be.**
  Google Flow and Meta AI are browser surfaces with no API reachable from here,
  so the builder emits a numbered, timestamped work order and a human runs it.
- **The cost claim is unverified.** `models.json` records "lowest cost-per-second"
  as something the operator asserted, with `verified: false` and no source. Do
  not repeat it as fact anywhere until someone checks it against live pricing
  and fills in the source and date.
- **Nothing here calls a paid endpoint.** Gate 3 records what a human approved;
  the human runs the generation. `credit_safeguard.pipeline_submits` is `false`
  and there is no code path that makes it true.

## Publishing and reminders

Cadence lives in `automation/config/schedule.json`. Known Unknowns long-form
runs Tuesday and Friday; Stickman Friday; shorts daily. **Lilweid has no
operator-set cadence and therefore has none here** — it reports as unscheduled
rather than being given an invented slot.

- **Stickman long-form is gated on `channels/stickman/brand.json`.** Until the
  logo, avatar, name, handle, locked character, links and description are marked
  done, `schedule --channel stickman` returns no slots and names what is missing.
- **A brand item that names an asset must have that file on disk.** Marking
  `locked_character` done while its reference image is absent reports as
  "marked done but no file at ...", not as satisfied. A gate that clears on a
  promise is not a gate.
- **No two channels may share a voice id.** The stickman canon requires each
  channel to have its own narrator; a test enforces it.
- **Uploads are hardlinks, not copies.** `scheduler link` puts
  `YYYY-MM-DD_PLATFORM_VIDEO-SHORT.mp4` (or `-LONG`) in `_upload/` pointing at
  the same bytes as the render. A cross-volume link fails loudly and prints the
  Windows `mklink /H` equivalent rather than silently copying.
- **The reminders are not installed by this repo.** `remind --install` prints the
  `schtasks` and `cron` lines; a human installs them. 17:30 long-form, 18:30
  shorts. Each reminder reads the day's plan row, verifies the file is really in
  `_upload/`, and prints platform, filename, canon safety notes and caption
  metadata.

## Memory

`automation/memory/` holds three plain-JSON stores a human can read and correct.

- `session_state.json` — active channel, episode and stage. Written at every
  gate boundary so a session that ends can be resumed cold.
- `topic_history.json` — every topic and title already made. `init` refuses an
  exact repeat and prints near matches for a person to judge. Near matches are
  never auto-resolved; `--allow-duplicate` is the operator's call, not the
  pipeline's.
- `learnings.json` — approved retention fixes. `script` reads them, prints which
  ones it carried, and stamps them into the script header.

**Loaders return a fresh object every time.** The stores are built by factories,
not module-level literals — a shared literal once let one run's appends leak into
every later load in the same process.

## Token safety, continued

Past **96 KB** of `state.json` the pipeline prints a token-overflow banner. The
position is already checkpointed, so end the session and resume with `status`.
Do not try to carry a long-form episode's full state in conversation.

## What the tools may not do

- **Never invent a number.** Pace, runtime and beat timings are parsed from the
  verified-episode table in the channel canon. Where the canon has no
  measurement, the value is `None` and the tool exits with a message naming the
  flag that supplies it. A plausible default here becomes a fake figure in a
  report two steps later.
- **Never fill a `[BLOCKED]` canon section.** Stickman's architecture, voice and
  visual system are blocked because two finished episodes define them and this
  environment cannot reach the footage. `--allow-provisional-architecture`
  produces a working draft that is labelled provisional in every file it
  touches, and is still not canon.
- **Never write a citation.** The script engine emits `«CITE:»` slots with the
  fields a real citation needs. Known Unknowns' canon: *"Verify every citation
  before it is written. No exceptions, no placeholder facts."*
- **Never borrow a sign-off across channels.** Known Unknowns closes on
  `"You're welcome."`; Lilweid's canon forbids that exact line; Stickman needs
  its own and must borrow neither. `--signoff` is checked against the channel's
  forbidden list and refused by name. `--force-signoff` overrides deliberately
  and stamps "overrides canon" into the script header — it is not a shortcut.
- **Never invent a metric.** `analyze` reports a figure the operator did not
  supply as not supplied and skips its check. Thresholds in
  `automation/config/analytics.json` print their own provenance, so a house
  default never reads as evidence about these channels.
- **Never pick the paid model.** `automation/config/kie.json` ships with
  `model: null` and a candidate list. The operator chooses; the pipeline prints
  the options and the cost basis.
- **Never print a credit figure without a sourced rate.** Billable units are
  always exact and always shown. Credits appear only when the rate card carries
  a `source` and a `checked_utc`.

## Token safety

**API tokens.** `ELEVENLABS_API_KEY` and `KIE_API_KEY` are read from the
environment, by name, and never written anywhere. No key belongs in a config
file, an episode file, `state.json`, a commit, or terminal output. The config
files carry the *name* of the variable, never its value. If a key ever lands in
a tracked file, treat it as leaked: rotate it first, then remove it.

**Context tokens.** Episode files are large by design — a long-form
`03_kie_video_prompts.json` runs past 100 KB — and reading one whole into a
session wastes the budget that the actual work needs.

- Use `--json` and pipe it, or read the specific fields. Do not `cat` an episode
  file to find one value.
- `status` is the cheap way to ask where an episode stands; `state.json` is the
  expensive way.
- Call the engines as subprocesses. Do not re-implement what
  `automation/core/` already does inline in a session.
- `canon.py --channel <name>` prints the parsed canon in about twenty lines.
  Prefer it to reading a 300-line rule file when all you need is the pace or the
  voice lock.

## Layout

```
automation/run.py                     the four commands, the gates, publish-plan.csv
automation/core/canon.py              parses .claude/rules/<channel>.md
automation/core/seo_engine.py         titles, chapters, tags
automation/core/script_engine.py      ElevenLabs narration script
automation/core/kie_prompt_builder.py KIE video and thumbnail prompts, cost
automation/core/state_manager.py      state machine and approval gates
automation/core/scheduler.py          cadence, upload queue, 17:30/18:30 reminders
automation/core/analyzer.py           metrics -> 06_performance_audit.md
automation/core/memory.py             session state, topic dedup, learnings
automation/core/wizard.py             the guided /faceless-studio flow
automation/config/elevenlabs.json     voices and SSML pacing (voice ids are the operator's)
automation/config/kie.json            rate card (starts null)
automation/config/models.json         the toolchain locks
automation/config/schedule.json       publishing cadence and reminder times
automation/config/analytics.json      review thresholds (house defaults)
automation/memory/*.json              session state, topic history, learnings
automation/tests/test_pipeline.py     python3 automation/tests/test_pipeline.py

channels/<channel>/episodes/<episode_id>/
    01_ideation_and_seo.md  02_narration_script.md  03_kie_video_prompts.json
    04_kie_thumbnail_prompts.md  05_metadata.md  metadata.json
    06_performance_audit.md  state.json
channels/<channel>/publish-plan.csv
channels/stickman/brand.json          the Stickman longform gate
_upload/                              dated hardlinks for the upload queue
```

## Before changing anything here

Run the tests. They exist to catch the two failures that matter: a gate that
lets a stage through, and a tool that answers with a number it did not measure.

```bash
python3 automation/tests/test_pipeline.py
```
