# Episode 001 — Nail Biting / Dermatophagia

**Title (Package B / brand thesis):** Your Brain Is Wired Wrong (Not Broken)
**Title (Package A / broad appeal):** Why 1 in 3 Adults Still Bite Their Nails

**Status:** Script, scene prompts, motion prompts, thumbnails, SEO metadata and
A/B framework locked 2026-09-06. **Not yet rendered or published** — no paid
generation call has been made for this episode.

## How this episode was built

This episode was **not** produced through `scripts/run.py init/script/prompts/
package` — the standard four-command pipeline documented in
`docs/pipeline-commands.md`. It was built conversationally, beat by beat, in a
single session using a 22-state guided flow with a simulated 5-member council
(Growth Hacker, Brand/Art Director, Behavioral Psychologist, Red Team
Skeptic, Operations Lead) gating every major decision. `run.py status` will
not find a `state.json` for this episode — the files in this directory are
the actual state, hand-numbered to match the convention `state.json` would
otherwise use.

A future episode should go through the real pipeline; this one is the
canon-defining first pass.

## File index

| File | Content |
|---|---|
| `01_script.md` | Locked voiceover script — 49 beats, 479 words, 153.5s |
| `02_scene_prompts.md` | 49 standalone scene image prompts, one per beat |
| `03_motion_prompts.md` | 42 clip motion prompts across 14 gated blocks |
| `04_thumbnails.md` | 5 thumbnail concepts + council verdict + locked A/B pair |
| `05_seo_metadata.md` | Titles, description, tags, pinned comment, fact-check clearance |
| `06_ab_testing_and_calendar.md` | A/B decision rules + this episode's place in the 60-day calendar |

## Shorts cutdown map (6 archetypes, directly repurposed from this episode's assets — zero redundant rendering)

| Archetype | Source range | Real runtime |
|---|---|---|
| Cold-Open Hook | Beats 1–7 / Clips 1–6 | 0:00–0:20 (~20s) |
| Mechanism Deep-Dive | Beats 8–18 / Clips 7–17 | 0:20–0:56 (~36s) |
| Dual-Trigger Contrast | Beats 19–27 / Clips 18–24 | 0:56–1:26 (~30s) |
| Cortical-Lag Demonstration | Beats 28–33 / Clips 25–30 | 1:26–1:51 (~25s) |
| Actionable Competing-Response Tutorial | Beats 34–49 / Clips 31–42 | 1:51–2:34 (~43s) |
| Existential/Callback Reframe | Beats 1–7 + 45–49 (recut) | Hook + closing bookend only |

Aspect-ratio rule (16:9→9:16): center-crop by default (most shots are
mascot-centered); for Wide Shots, extend the existing background gradient
vertically rather than stretching the character. Short-specific on-screen
text: center-weighted, bottom-third safe-zone, clear of platform UI overlays.

## Open items carried forward (not blockers, but not resolved)

1. **Citation verification** — run at STATE 19, confirmed accurate (Graybiel,
   Mansueto, Azrin & Nunn 1973, and the 60-second competing-response duration
   all checked against real sources — see `05_seo_metadata.md`).
2. **Clip 35's VO** runs 5.12s against a 5.0s clip nominal (0.12s over) —
   accepted as within normal tolerance; flag if the actual render tool
   enforces a strict 5.00s cap with zero tolerance.
3. **Week 7 scheduling** (a *different* episode, Overeating/Sugar Craving)
   needs a cross-check against Lilweid's actual publish calendar
   (`automation/config/schedule.json` in the Business repo) before that
   week is hard-locked — this repo doesn't have that file.
4. **Render tool choice** — not made. Per the standing rule, the paid tool
   (Seedance for clips, Flux/GPT-Image for thumbnails, ElevenLabs for voice)
   is the operator's pick, asked for before any spend.
