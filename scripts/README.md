# scripts/ — pinned snapshot, not a fork

A byte-identical copy of `automation/` from xweelyx-beep/Business @ `06de1d8`:
`run.py`, `core/*.py`, `config/*.json`. 4,284 lines of stdlib-only Python 3.

**Business is the source of truth.** This snapshot exists so the generation code
that produced this channel's prompts travels with the assets. Fix bugs in
Business and re-copy; edits made here will drift and be lost.

## Why it is a snapshot rather than a working copy

The pipeline is shared across three channels. `core/canon.py` hard-codes
`CHANNELS = ("lilweid", "known-unknowns", "stickman")`, and `repo_root()` walks
up looking for a `.claude/rules/` directory, then expects
`channels/<channel>/brand.json` beside it. Run from this repository it exits
with:

```
$ python3 scripts/core/canon.py --channel stickman
error: no repository root found above /home/user/Stickman-doodle/scripts/core/canon.py; run this from inside the Business repo
```

Making it run here means recreating the Business layout — at which point there
are two copies of a three-channel pipeline drifting apart. Run it from Business
instead; this copy is the record.

## Running it, from the Business checkout

```bash
python automation/run.py init    --channel stickman --topic "..." --keyword "..." --runtime 8:30
python automation/run.py approve --channel stickman --episode <id> --gate 1 --title 1 --by you
python automation/run.py script  --channel stickman --episode <id>
python automation/run.py approve --channel stickman --episode <id> --gate 2 --by you
python automation/run.py prompts --channel stickman --episode <id>
python automation/run.py approve --channel stickman --episode <id> --gate 3 --credits <n> --by you
python automation/run.py package --channel stickman --episode <id> --by you
```

Full command reference: `docs/pipeline-commands.md`. The reasoning behind the
gates: `docs/pipeline-conventions.md`.

## Two things to know before running it for Stickman

1. **`schedule` will refuse.** `config/schedule.json` sets
   `requires_brand_ready: true`, and 6 of 7 items in `references/brand.json` are
   still `false`. That is the gate working, not a bug.
2. **`analyze` has no pace baseline.** `config/analytics.json` carries
   `pacing.stickman: null` because no episode has been analysed.

## Contents

| Path | Lines | What it does |
|---|---|---|
| `run.py` | 747 | the four commands, three gates, the state machine |
| `core/script_engine.py` | 536 | narration script from topic + canon |
| `core/kie_prompt_builder.py` | 474 | Seedance scene prompts + the manual Nano Banana Pro handoff sheet |
| `core/scheduler.py` | 464 | Tue/Fri slots, the brand gate, publish plan |
| `core/seo_engine.py` | 417 | titles, hooks, keywords |
| `core/canon.py` | 402 | parses the channel bible into structured locks |
| `core/state_manager.py` | 362 | episode state, gate enforcement |
| `core/analyzer.py` | 344 | metrics → pacing fixes |
| `core/memory.py` | 277 | session checkpoints, topic dedup |
| `core/wizard.py` | 261 | the guided numbered flow |
| `config/*.json` | — | the toolchain locks — see `docs/toolchain.md` |

`automation/tests/test_pipeline.py` (648 lines) was **not** copied: it asserts
against the three-channel Business layout and cannot pass here.
