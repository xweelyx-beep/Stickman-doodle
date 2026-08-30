# Music bed cues — Why You Check Your Phone

**Runtime:** 11:22 (682s) · 7 movements
**Status:** mood progression is the operator's spec, given 2026-08-29. The
direction notes under each movement are production suggestions, not canon.

> **The channel bible has no music section.** Tempo, genre, key, licence source
> and stinger vocabulary are all undecided for this channel. This sheet is a
> per-episode cue map, not a channel lock. If a choice here should hold for
> every future episode, it belongs in `docs/channel-bible.md` first.

---

## The seven movements

| # | Range | Movement | Length | Mood |
|---|---|---|---|---|
| 1 | `[00:00]`–`[01:00]` | **Hook & Initial Slump** | 1:00 | Sparse, ambient, subtle curiosity. |
| 2 | `[01:01]`–`[03:45]` | **Skinner & Schultz Lab** | 2:44 | Colder, clinical, minimal rhythmic pulse. |
| 3 | `[03:46]`–`[05:37]` | **The Prediction Gap** | 1:51 | Rising tension, mid-tempo syncopation. |
| 4 | `[05:38]`–`[06:44]` | **Casino & Machine Zone** | 1:06 | Darkest, hypnotic low-bass drone, repetitive mechanical cadence. |
| 5 | `[06:45]`–`[09:48]` | **Friction & Gloria Mark Data** | 3:03 | Fragmented, uneasy percussive ticks. |
| 6 | `[09:49]`–`[10:39]` | **Savannah Evolution** | 0:50 | Warm, organic, spacious percussion, opening up. |
| 7 | `[10:40]`–`[11:22]` | **Synthesis & Resolution** | 0:42 | Warm, clear, grounded resolution chords. |

**Coverage.** 11:22 is 682 s. Summing each movement as `end − start` gives
676 s; the missing 6 s are the six internal boundaries, where one movement's end
mark and the next one's start mark are one second apart (`[01:00]` → `[01:01]`).
Counted inclusively the movements total 683 s, one over, for the same reason.
Nothing is missing from the map — the boundary second belongs to both sides and
is where the crossfade goes. Budget 1–2 s of bleed at each of the six and
resolve it in the edit.

---

## Movement detail

### 1. Hook & Initial Slump — `[00:00]`–`[01:00]`  ·  1:00

**Mood:** Sparse, ambient, subtle curiosity.

**Carries:** Couch slump, the pocket drift, DISCIPLINE PROBLEM, the boulder, the question mark.

**Direction:** Almost nothing. A held pad and a single soft mallet figure. The hook works because the room is quiet — the first sound the viewer notices should be the narration, not the bed.

### 2. Skinner & Schultz Lab — `[01:01]`–`[03:45]`  ·  2:44

**Mood:** Colder, clinical, minimal rhythmic pulse.

**Carries:** 1930s lab, the box, the pigeon, the variable-ratio diagrams, dopamine, the monkey, the oscilloscope.

**Direction:** Drop the warmth: thin the low end and move the pad up an octave. A quiet metronomic pulse, one note per bar, sitting under the lever presses. It should feel like measurement.

### 3. The Prediction Gap — `[03:46]`–`[05:37]`  ·  1:51

**Mood:** Rising tension, mid-tempo syncopation.

**Carries:** 100% vs 0% vs 50%, the coin flip, Sapolsky, chasing the question mark.

**Direction:** The pulse from movement 2 stays but goes off-grid — accents land between beats. Tension comes from displacement, not from adding layers.

### 4. Casino & Machine Zone — `[05:38]`–`[06:44]`  ·  1:06

**Mood:** Darkest, hypnotic low-bass drone, repetitive mechanical cadence.

**Carries:** The kitchen reach, notifications, Schüll, slot reels, near-misses, the trance.

**Direction:** The floor of the episode. A sustained low drone with a short mechanical figure looping every two bars, unchanged, for the whole movement. The loop must not develop — the point is that it does not.

### 5. Friction & Gloria Mark Data — `[06:45]`–`[09:48]`  ·  3:03

**Mood:** Fragmented, uneasy percussive ticks.

**Carries:** Pull-to-refresh against the slot pull, Tristan Harris, the 47-second decline, the heart-rate spike.

**Direction:** Break the drone into ticks. Irregular spacing, dry and close, no reverb tail. The longest movement at 3:04 — it needs one internal shift or it will fatigue; put it at the 47-second data point.

### 6. Savannah Evolution — `[09:49]`–`[10:39]`  ·  0:50

**Mood:** Warm, organic, spacious percussion, opening up.

**Carries:** Empty box, prehistoric foraging, ancient against modern, the blazing sun.

**Direction:** The first real relief. Bring the low end back, swap processed percussion for hand percussion, widen the reverb. This is the only movement allowed to breathe.

### 7. Synthesis & Resolution — `[10:40]`–`[11:22]`  ·  0:42

**Mood:** Warm, clear, grounded resolution chords.

**Carries:** Catching his own wrist, OLD CIRCUIT NEW LEVER, the cloud breaking, the couch with a knowing smile, the wave.

**Direction:** Resolve the harmony the bed has avoided since movement 1. Land the final chord under the sign-off and let it ring past the last frame.

---

## Shape of the whole

The bed runs cold from `[01:01]` and does not warm again until `[09:49]` — a
**8:48 stretch, 77% of the runtime**, spent below the emotional temperature of
the opening. That is deliberate: the savannah movement is the release, and it
only reads as release if movement 6 has been uncomfortable for long enough.

Two watch-outs:

- **Movement 5 is the risk.** At 3:04 it is the longest and the least musical.
  Fragmented ticks over three minutes will read as an error rather than a
  choice unless something shifts inside it.
- **Movement 4 must not build.** Every instinct in scoring is to develop a loop.
  The Machine Zone beat is about a loop that never resolves, so the bed has to
  do the same thing to the listener that the slot machine does to the player.

## Against the picture

The prompt file's palette turns cold at `[01:01]` — the Skinner lab is warm tan,
then `[02:30]` splits the frame warm-left / cool-blue-right and everything after
sits in cool blue-grey. Movement 2 starts at exactly the same second the
laboratory does. Movement 6's warmth returns with the savannah's blazing sun.

The bed and the palette move together. Worth preserving if either is re-cut.

## Production constraints

| | |
|---|---|
| Narration | ElevenLabs, voice **Eva** — `locked: false`, an operator preference. See `docs/toolchain.md`. |
| Duck under VO | Yes. The bed is never the top layer; this is an explainer. |
| Lyrics | None. Words compete with narration. |
| Licence | **Undecided.** Record track, source and licence per movement here before the cut is published. |
| Renders | Gitignored. Commit the cue sheet and the settings, not the audio. See `audio/README.md`. |

## Not decided here

Tempo in BPM, key, instrumentation beyond the textures named, stinger and
transition vocabulary, and where the track actually comes from. All of it is
open, and none of it is guessed in this file.
