# scripts/ — the standalone pipeline

Forked from `automation/` in xweelyx-beep/Business @ `06de1d8` and decoupled on
2026-08-29. Stdlib-only Python 3, no third-party dependencies, no network calls.

**This is now a fork, deliberately.** It was a read-only snapshot for one
commit; the decoupling made it independent. The two copies will diverge, and
that is the intent — Business keeps the three-channel tree, this keeps
Stickman. A fix that matters to both has to be applied twice. `core/paths.py`
is the whole of the divergence in layout terms, so a port is usually a matter
of leaving that file alone.

Behaviour is otherwise unchanged: `core/canon.py --json` returns byte-identical
output to the Business copy for this channel, checked against it.

## Standalone as of 2026-08-29

It no longer needs the Business checkout. The layout is declared in
`channel.json` at the repository root and resolved by `core/paths.py`, which is
the only module that builds a repository path:

| Was, in Business | Is, here | Declared as |
|---|---|---|
| `.claude/rules/stickman.md` | `docs/channel-bible.md` | `layout.canon` |
| `automation/config/*.json` | `scripts/config/*.json` | `layout.config` |
| `automation/memory/` | `memory/` | `layout.memory` |
| `channels/stickman/episodes/` | `episodes/` | `layout.episodes` |
| `channels/stickman/brand.json` | `references/brand.json` | `layout.brand` |

Root resolution, in order: an explicit `--root`, then `$STICKMAN_REPO_ROOT`,
then a walk up from the module for `channel.json`. No hard-coded fallback — a
missing marker fails loudly rather than reading the wrong tree:

```
$ cd / && python3 -c "import sys; sys.path.insert(0,'scripts/core'); import paths; paths.find_root('/etc')"
error: no channel.json found at or above /etc; this is not a Stickman-doodle checkout. Run from inside one, pass --root, or set $STICKMAN_REPO_ROOT.
```

Moving a directory means editing `channel.json`, not the Python. There is a test
that proves it (`tests/test_standalone.py::test_moving_a_directory_needs_no_python_change`).

## Running it

```bash
python3 scripts/run.py init    --channel stickman --topic "..." --keyword "..." --runtime 8:30
python3 scripts/run.py approve --channel stickman --episode <id> --gate 1 --title 1 --by you
python3 scripts/run.py script  --channel stickman --episode <id>
python3 scripts/run.py approve --channel stickman --episode <id> --gate 2 --by you
python3 scripts/run.py prompts --channel stickman --episode <id>
python3 scripts/run.py approve --channel stickman --episode <id> --gate 3 --credits <n> --by you
python3 scripts/run.py package --channel stickman --episode <id> --by you
```

Works from any working directory, and from a checkout moved anywhere on disk.

## Tests

```bash
python3 scripts/tests/test_standalone.py       # 17 tests — the decoupling
python3 scripts/tests/test_seo_generator.py   # 41 tests — metadata character budgets
python3 scripts/tests/test_generate_frames.py  # 20 tests — the manual queue driver
python3 scripts/tests/test_auto_generate.py    # 67 tests — the automated driver
python3 scripts/tests/test_video_pipeline.py   # 28 tests — timeline, assembly, audio
```

Stdlib `unittest`, 173 tests total. They assert the layout is declared rather than
hard-coded, that root resolution works from any cwd and fails loudly outside a
checkout, that no module builds a Business path, that the brand gate reads a
file that is really on disk, and that the blocked canon still refuses to
generate. The Business suite (`automation/tests/test_pipeline.py`, 648 lines)
was not portable: it asserts the three-channel tree.

## Three things to know before running it for Stickman

1. **`init` and `script` will refuse by default.** The canon marks the beat
   architecture, the voice lock and the pace `[BLOCKED]`, so the engines stop
   rather than guess. `--allow-provisional-architecture`, `--voice-lock` and
   `--seconds-per-scene` override each one explicitly, and what they produce is
   a working draft, not canon.
2. **`schedule` will refuse.** `config/schedule.json` sets
   `requires_brand_ready: true`, and 6 of 7 items in `references/brand.json` are
   still `false`. That is the gate working, not a bug.
3. **`analyze` has no pace baseline.** `config/analytics.json` carries
   `pacing.stickman: null` because no episode has been analysed.

## Contents

| Path | Lines | What it does |
|---|---|---|
| `run.py` | 747 | the four commands, three gates, the state machine |
| `core/script_engine.py` | 536 | narration script from topic + canon |
| `core/kie_prompt_builder.py` | 474 | Seedance scene prompts + the manual Nano Banana Pro handoff sheet |
| `core/scheduler.py` | 464 | Tue/Fri slots, the brand gate, publish plan |
| `core/seo_engine.py` | 417 | titles, hooks, keywords |
| `core/seo_generator.py` | 687 | **new** — publish metadata: title variants, description, tags, `metadata.json` |
| `core/canon.py` | 402 | parses the channel bible into structured locks |
| `core/state_manager.py` | 362 | episode state, gate enforcement |
| `core/analyzer.py` | 344 | metrics → pacing fixes |
| `core/memory.py` | 277 | session checkpoints, topic dedup |
| `core/wizard.py` | 261 | the guided numbered flow |
| `core/paths.py` | 187 | **new** — the layout authority; the only module that builds a repo path |
| `generate_frames.py` | 394 | the manual 157-frame queue driver; submits nothing |
| `auto_generate.py` | 290 | **new** — automated end-to-end rendering; submits |
| `core/backends.py` | 410 | generation backends: mock, HTTP providers, Playwright |
| `assemble_video.py` | 319 | **new** — 157 shots to one 4K master, with camera motion |
| `build_full_video.py` | 288 | **new** — the single command: generate, validate, mix, assemble |
| `core/timeline.py` | 224 | **new** — shot durations, camera moves, dynamic-clip selection |
| `tests/test_standalone.py` | 177 | **new** — 17 tests guarding the decoupling |
| `tests/test_seo_generator.py` | 388 | **new** — 41 tests guarding the metadata character budgets |
| `tests/test_generate_frames.py` | 240 | 20 tests guarding the manual queue driver |
| `tests/test_auto_generate.py` | 658 | 67 tests guarding the automated driver |
| `tests/test_video_pipeline.py` | 258 | **new** — 28 tests guarding timeline, assembly and audio |
| `config/*.json` | — | the toolchain locks — see `docs/toolchain.md` |

`automation/tests/test_pipeline.py` (648 lines) was not copied: it asserts
against the three-channel Business layout. `tests/test_standalone.py` replaces
it for the layout concerns that actually apply here.
