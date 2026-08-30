# audio/

Music cues and voiceover assets, per episode.

Holds `music_bed_cues.md` — the 7-movement mood map for *Why You Check Your
Phone*, from the operator's spec. No audio **files** yet: none has ever been
committed to xweelyx-beep/Business either, verified across all 355 unique paths
in every commit on all 4 branches.

| File | What it is |
|---|---|
| `music_bed_cues.md` | 7 movements across the 11:22 timeline, contiguous, mood + direction per movement |

## Layout when files arrive

```
audio/
  voiceover/<episode_slug>/     ElevenLabs renders, one file per block or one per episode
  music/<episode_slug>.md       cue sheet: track, timestamp, licence, source
  sfx/<episode_slug>/           stingers, whooshes, UI blips
```

## Voiceover — how it is produced

Not by anything in this repository. `scripts/` contains no code that calls a
paid endpoint (`models.json` → `credit_safeguard.pipeline_submits: false`).
Rendering is a separate, human-approved step.

| Field | Value |
|---|---|
| Engine | ElevenLabs, locked |
| Voice | **Eva** — `Xn6GqAFT1vo7SexgOVmn` — `locked: false` |
| Model | `eleven_multilingual_v2` |
| Format | `mp3_44100_128` |
| API key | `$ELEVENLABS_API_KEY`, read from the environment, never stored |

Eva is an operator *preference*, not a lock. See `docs/toolchain.md`.

SSML break tags emitted by the pipeline: sentence `0.35s`, clause `0.6s`, beat
`1.0s`. The config notes these need confirming against the chosen `model_id`
before a full render.

## Music — nothing decided

The channel bible has no music section at all. Tempo, genre, cue placement and
licence source are undecided, and inventing them here would be a guess written
into canon. Decide, then record the decision in `docs/channel-bible.md` first
and mirror it here.

## Do not commit large renders

`.gitignore` excludes `*.mp3`, `*.wav`, `*.m4a`, `*.aac` and `*.mp4`. Commit the
**cue sheets and the settings** — the things that let a render be reproduced —
and keep the renders themselves out of git. Lift the ignore deliberately if a
specific short reference clip needs to live here.
