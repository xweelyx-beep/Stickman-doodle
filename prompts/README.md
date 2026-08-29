# prompts/

Per-episode image and video prompt files.

**This folder is empty of episode prompts right now.** That is not an oversight
in the migration — see below.

## Naming

```
image_prompts_<episode_slug>.txt      manual Nano Banana Pro queue, one prompt per shot
video_prompts_<episode_slug>.json     Seedance 1.5 Pro scene prompts
```

The slug is the episode title, lowercased, spaces to underscores — e.g. an
episode titled *Why you check your phone* becomes
`image_prompts_why_you_check_your_phone.txt`.

## What the pipeline emits

`scripts/run.py prompts` writes into an episode directory, not here, using the
names fixed in `scripts/core/state_manager.py`:

| Key | File |
|---|---|
| `seo` | `01_ideation_and_seo.md` |
| `script` | `02_narration_script.md` |
| `video_prompts` | `03_kie_video_prompts.json` |
| `thumbnail_prompts` | `04_kie_thumbnail_prompts.md` |
| `metadata` | `05_metadata.md` |
| `state` | `state.json` |

Copy the ones worth keeping into this folder under the naming above, or leave
them in the episode directory — either is fine, but pick one and stay with it.

## Why there are no prompt files here yet

Searched exhaustively before writing this: **355 unique file paths across every
commit on all 4 branches of xweelyx-beep/Business.** Zero `.txt` files have ever
existed in that repository, and no file matching `image_prompts_*` or
`*_prompts_*` has ever been committed to it. `git grep` over every reachable
commit for the phrase "check your phone" returns nothing.

The two episodes named in the canon —

| # | Title | State |
|---|---|---|
| 1 | Can't stop eating Sugar | Finished, unpublished |
| 2 | Can't stop checking your phone | Nearly done |

— were produced before this repository existed. The canon states plainly that
they "live on a local Windows drive this environment cannot reach." Their prompt
files are almost certainly on that drive.

**To fill this folder:** copy the episode prompt files off the Windows drive and
commit them here. Nothing is reconstructed or regenerated in the meantime —
inventing prompts for footage that already exists would contradict the real
episodes, which is the specific failure the canon warns against.
