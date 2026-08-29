# Migration record — Business → Stickman-doodle

**Date:** 2026-08-29
**Source:** xweelyx-beep/Business
**Source commits:** `06de1d8` (default branch head) and
`c4d23c1` (`claude/faceless-channel-automation-b13g75`, for the PNG mascot)

Every copied file was verified byte-identical against its source with `cmp` /
`diff -r`. The one exception is noted below.

---

## What moved

| Destination | Source | Bytes / lines | Change |
|---|---|---|---|
| `references/character_ref_body.png` | `c4d23c1:channels/stickman/assets/character_ref.png` | 1,246,362 B · PNG 1348×752 RGBA | renamed only |
| `references/character_ref_body.jpg` | `06de1d8:channels/stickman/character_ref_body.png.jpeg` | 425,087 B · JPEG 1376×768 | renamed only |
| `references/brand.json` | `06de1d8:channels/stickman/brand.json` | 1.2 KB | verbatim |
| `docs/channel-bible.md` | `06de1d8:.claude/rules/stickman.md` | 213 lines | **frontmatter replaced**, body verbatim |
| `docs/pipeline-commands.md` | `06de1d8:automation/README.md` | 67 lines | verbatim |
| `docs/pipeline-conventions.md` | `06de1d8:.claude/rules/automation.md` | 209 lines | verbatim |
| `scripts/run.py` + `scripts/core/*.py` | `06de1d8:automation/run.py`, `automation/core/` | 4,284 lines | verbatim |
| `scripts/config/*.json` | `06de1d8:automation/config/` | 5 files | verbatim |

The single edit: `docs/channel-bible.md` had a four-line YAML frontmatter
(`paths: channels/stickman/**`) that scopes the rule to a directory which does
not exist in this repository. It was replaced with a provenance comment. Body
diffed clean against the original.

## Written for this repository

Not copied from anywhere — derived from the sources above, with every claim
traceable to a quoted line:

| File | Derived from |
|---|---|
| `README.md` | this migration |
| `references/character-sheet.md` | channel bible §5 |
| `references/style-rules.md` | channel bible §6, §9, §10, §3 |
| `docs/toolchain.md` | `scripts/config/*.json` |
| `prompts/README.md`, `audio/README.md`, `scripts/README.md` | this migration |

## The two mascot images

Same artwork, two encodings. `brand.json` records
`channels/stickman/assets/character_ref.png` as the locked character, and that
PNG is lossless — **it is the canonical one.** The JPEG on the Business default
branch is a re-encode kept so nothing is dropped.

Worth knowing: on the Business default branch that `brand.json` reference is
**broken**. Commit `644bb18` deleted `channels/stickman/assets/`, so
`brand.json` points at a path that no longer exists there; the PNG survives only
on `claude/faceless-channel-automation-b13g75`, which is where it was recovered
from. Not fixed here — it is a Business-side issue.

## What was searched for and does not exist

Searched exhaustively, not assumed. Method: enumerated every unique path in
every commit reachable from all 4 branches of Business — **355 unique paths** —
and `git grep` across every reachable commit.

| Asked for | Result |
|---|---|
| `image_prompts_why_you_check_your_phone.txt` | **Never existed.** No `.txt` file of any kind has ever been committed to Business. No path matching `image_prompts*` or `*_prompts_*`. `git grep -i "check your phone"` over all commits: no match. |
| Episode prompt files, any episode | None. `channels/stickman/prompts/` and `episodes/` contain only `.gitkeep`. |
| Music cues | None. No cue sheet, and the channel bible has no music section. |
| Voiceover assets | None. No `.mp3`, `.wav`, `.m4a` or `.aac` in any commit. |
| Drawn character sheet / turnaround | None. Canon §5 marks it `[TBD]`. |
| Episode scripts | None in git. |

The likely explanation is in the canon itself: the two finished episodes
"live on a local Windows drive this environment cannot reach." They predate the
Business repository. Their prompts, audio and project files are on that drive.

Three near-miss files were checked and correctly excluded — `project_state.md`,
`current_script.md` and `current_block_prompts.md` on
`claude/kie-ai-production-pipeline-xue2d7`. They are a complete 1:45 production
package for *"Why You No Longer Feel Time"*: a Known Unknowns episode, Johnny
Kid narration, isometric flat-vector art direction. Not Stickman, so not
migrated. Its **house production method** was already lifted into the Stickman
canon §9 and is carried here in `references/style-rules.md` §1.

## Not copied, deliberately

| Item | Why |
|---|---|
| `automation/tests/test_pipeline.py` (648 lines) | Asserts against the three-channel Business layout; cannot pass here. |
| `.claude/rules/lilweid.md`, `known-unknowns.md` | Other channels. The bible's boundary test is summarised in `references/style-rules.md` §3 instead. |
| `.agents/skills/` (24 skills) | Agent configuration, not channel assets. Installed via `find-skills`, never copied by hand. |
| `automation/memory/*.json` | Cross-channel session state, not Stickman assets. |
| `channels/stickman/*/.gitkeep` | Placeholders for empty directories that this layout replaces. |

## How to keep the two repos honest

Business stays the source of truth for the bible and the pipeline. When
`.claude/rules/stickman.md` or `automation/` changes there, re-copy and bump the
commit SHA in this file. When an asset is produced *for this channel* — a
character sheet, an episode's prompts, a cue sheet — it belongs here first.
