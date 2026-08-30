# prompts/

Per-episode image and video prompt files.

Holds one partially-supplied episode. See "What is here" below for counts and
"What is still missing" for what has not arrived.

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

## What is here

| File | Frames | Range | Character presence |
|---|---|---|---|
| `image_prompts_why_you_check_your_phone.txt` | 54 | `[00:00]`–`[03:19]` | 20.4% (11/54) |
| `image_prompts_why_you_check_your_phone_v2.txt` | 54 | `[00:00]`–`[03:19]` | **46.3% (25/54)** |
| `revision_changelog.md` | — | — | the pass between them |

**v2 is the one to generate from.** The base file is kept unmodified so the
revision stays diffable — 14 frames changed, 40 byte-identical.

## What is still missing

The supplied file is **partial**. The source paste ends mid-sentence inside
`[03:22]`:

```
[03:22] 2D cartoon animation in modern YouTube explainer style, bold clean
black outlines, cel-shaded flat colors with soft ambient shading and gentle
```

That truncated entry was not saved. Everything from `[03:22]` to `[11:22]` is
absent — roughly 100 frames of the stated 157, covering:

| Segment | Range |
|---|---|
| Fiorillo, Tobler & 50% uncertainty | `[03:22]`–`[05:37]` |
| Smartphone mechanism & the casino floor | `[05:38]`–`[06:44]` |
| Friction, Harris & Gloria Mark's attention data | `[06:45]`–`[09:48]` |
| Reward gap & savannah evolution | `[09:49]`–`[10:39]` |
| Awareness, resolution & close | `[10:40]`–`[11:22]` |

**None of it was generated.** A beat summary is not a prompt, and inventing ~100
frames for an episode that is already cut would contradict the footage — the
failure the channel bible names explicitly. Paste the rest and the same revision
pass runs on it; the method and the measured baseline are in
`revision_changelog.md`.

