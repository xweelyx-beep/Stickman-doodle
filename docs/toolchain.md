# Toolchain — what is locked, what is a preference, what is blocked

Every value below is read out of `scripts/config/*.json`, which is a pinned
snapshot of `automation/config/` in xweelyx-beep/Business @ `06de1d8`. Nothing
here is estimated. Business is the source of truth; change it there.

---

## Video — locked

| Field | Value |
|---|---|
| Engine | `kie` |
| Model | `seedance-1.5-pro` (Seedance 1.5 Pro) |
| Locked | `true`, by operator, 2026-08-28 |
| Clip length | 5 s |
| Clips per block | 3 |
| Block length | 15 s |
| Aspect — long-form | 16:9 (`3840x2160`) |
| Aspect — Shorts | 9:16 (`2160x3840`) |
| Prompt standard | 4K |

The config records an operator claim that this is "the lowest cost-per-second
of the KIE video models" with `verified: false` and no source. **Do not repeat
it as fact** until someone fills in `verified_utc` and `source`.

## Image

| Use | Engine / model | Route |
|---|---|---|
| Thumbnails | `kie` · `flux`, fallback `gpt-image` · 3 variants · 1280×720 | automated prompt build |
| Stickman art | `nano-banana-pro` | **manual** — `google-flow` or `meta-ai` |

Overlay text on thumbnails is **burned in post, never rendered by the model.**

Stickman art is a manual handoff by design: Google Flow and Meta AI are browser
surfaces with no API this pipeline can reach. The prompt builder emits a
numbered, timestamped queue sheet; a human runs it and drops the returned files
into the episode's assets directory. Filename convention:

```
{episode_id}_{NN}_{YYYYMMDD-HHMM}_nbpro.png
```

## Voice — a preference, not a lock

| Field | Value |
|---|---|
| Engine | `elevenlabs` (locked) |
| Model | `eleven_multilingual_v2` |
| Output | `mp3_44100_128` |
| Voice | **Eva** — `Xn6GqAFT1vo7SexgOVmn` |
| `locked` | **`false`** |
| Status | `"operator preference, not final"` |
| stability / similarity / style | 0.45 / 0.75 / 0.30 — placeholders, untuned |

Eva is described in the config as "naturally rich female voice, slightly deep —
confident, soothing, effortlessly engaging." She is distinct from Known
Unknowns' Johnny Kid, which satisfies the canon rule that each channel has its
own narrator and they must not converge. **Picking a voice id does not unblock
canon section 7**, which still needs register, pace and sentence length read off
the finished episodes.

The API key is read from `$ELEVENLABS_API_KEY` and is never written to a config
file, an episode file, or git.

## Credit safeguard

> No paid generation fires without a human approving the exact credit estimate
> at gate 3.

Enforced by `scripts/core/state_manager.py`. `pipeline_submits: false` — this
code contains nothing that calls a paid endpoint. Paid stages are `voice`,
`video`, `image`.

## Schedule — blocked

| Field | Value |
|---|---|
| Long-form | Friday (weekday `4`) |
| `requires_brand_ready` | **`true`** |
| Shorts | daily — youtube, tiktok, instagram |
| Reminders | 17:30 long-form · 18:30 shorts |

Stickman long-form **stays unschedulable** until every item in
`references/brand.json` is marked done. The canon calls this channel's identity
blocked and the scheduler respects that rather than routing around it.

Current gate state — 1 of 7 items done:

| Item | Done | Note |
|---|---|---|
| `logo` | ❌ | |
| `avatar` | ❌ | |
| `name` | ❌ | canon section 4 (Naming) is still `[TBD]` |
| `identifier_name` | ❌ | the @handle |
| `locked_character` | ✅ | `references/character_ref_body.png` |
| `links` | ❌ | |
| `description` | ❌ | |

## Analytics — no measured pace

`analytics.json` records `pacing.stickman: null`. Known Unknowns is 9.33 s and
Lilweid 6.17 s per scene, both derived from analysed footage. Stickman has none
because no episode has been analysed. Every CTR / retention threshold in that
file carries `source: null` — they are house defaults to start a conversation,
not benchmarks for this channel.
