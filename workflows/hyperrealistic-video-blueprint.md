> **Ported from [xweelyx-beep/Business](https://github.com/xweelyx-beep/Business)
> on 2026-09-02, as reference only. This blueprint does not apply to Stickman.**
>
> Its own Scope table says so: Stickman is 2D stickman art locked to
> nano-banana-pro, with "no real person, name or likeness, ever". Nothing in
> here is a Stickman lock, a Stickman default, or an input to
> `docs/channel-bible.md` — the blocked sections of that canon stay blocked.
>
> The body below is unchanged from the Business copy, so every path it names
> (`automation/config/models.json`, `.claude/rules/<channel>.md`) refers to that
> repository, not this one. Here those are `scripts/config/models.json` and
> `docs/channel-bible.md`.

# Hyperrealistic AI Shorts — Production Blueprint

**Status: Draft 1. Not canon. Not verified against a shipped episode.**

Drafted 2026-09-02 from an operator brief. Every parameter below is a starting
default, not a measured result — nothing here has been run through a published
Short and checked against retention. Treat it as a hypothesis to test, and move
what survives into the channel canon (`.claude/rules/<channel>.md`), which is
what the engines actually read.

Four decisions are the operator's, not this document's. They are listed under
[Open decisions](#open-decisions) and two of them **block production today**.

---

## Scope

| Channel | Applies | Why |
|---|---|---|
| Lilweid | yes | Canon already calls for photoreal cinematic footage, real-looking humans and places |
| Known Unknowns | yes | Faceless long-form and Shorts, photoreal register |
| Stickman | **no** | 2D stickman art, locked to nano-banana-pro. "No real person, name or likeness, ever" |

"Faceless" here means what the canons mean by it: **one narrator, no name, no
face, no personal biography**. Synthetic humans on screen are allowed and
expected on Lilweid and Known Unknowns. The rule bites on identity, not on
whether a human appears in frame. Nothing in this blueprint may put the
operator's likeness, name or voice into a published asset.

---

## Pipeline

Three generation stages, mapped onto the four commands and three gates that
already exist. This blueprint adds no new stage and no new gate.

```
run.py init      → topic, SEO, dedup check          → gate 1 (human approves brief)
run.py script    → narration + beats + pacing marks → gate 2 (human approves script)
run.py prompts   → base-plate prompts + motion pairs → gate 3 (human approves SPEND)
run.py package   → publish plan
                   ↓ (all generation happens here, by hand, after gate 3)
   Stage A  base visual generation   → photoreal stills
   Stage B  image-to-video           → 5s clips
   Stage C  ElevenLabs voiceover     → narration track, cut to pacing marks
```

`paid_stages` in `automation/config/models.json` is `["voice", "video",
"image"]` — **all three stages of this blueprint are paid.** The credit
safeguard is explicit: *"No paid generation fires without a human approving the
exact credit estimate at gate 3."* The repository contains no code that calls a
paid endpoint; gate 3 records what a human approved and the human submits.

### Runtime math is fixed by the video lock

`clip_seconds: 5`, `clips_per_block: 3`, `block_seconds: 15`, `aspect_shorts: 9:16`.

| Target | Blocks | Clips | Note |
|---|---|---|---|
| 30s | 2 | 6 | clean |
| 45s | 3 | 9 | clean |
| 50s | — | 10 | **not a whole number of blocks** — either accept a 5s partial block or retarget to 45s |

The 30–50s band in the brief is only cleanly expressible as 30s or 45s under
the current lock. Draft 1 recommends **45s / 3 blocks / 9 clips** as the default
Short and 30s as the short variant.

---

## Stage A — Base visual generation (photorealism guardrails)

Purpose: kill the plastic AI look at the still stage, before motion multiplies it.

**Operator-specified parameter stack** (use verbatim unless testing a variant):

```
natural ambient lighting
raw photography style
visible skin texture and subtle pores
candid angle
cinematic depth of field (f/1.8)
```

Read these as five separate jobs:

| Parameter | What it is fighting |
|---|---|
| `natural ambient lighting` | The three-point studio glow that reads as render, not room |
| `raw photography style` | Post-processed HDR gloss; asks for the unretouched frame |
| `visible skin texture and subtle pores` | Wax skin. The single highest-value token in the stack |
| `candid angle` | Centred, symmetrical, posed-for-camera framing |
| `cinematic depth of field (f/1.8)` | Flat all-in-focus depth. f/1.8 is shallow — expect the background to go soft |

**Negative direction** (append per the target tool's syntax): plastic skin,
airbrushed, waxy, symmetrical face, studio glamour lighting, oversaturated,
HDR, smooth gradient skin, perfect teeth, dead eyes, extra fingers.

**Draft-1 caution.** `f/1.8` on a vertical Short with a moving subject will
throw focus often. If subjects drift soft in testing, try f/2.8 before blaming
the motion stage.

## Stage B — Motion directives (image-to-video)

Every clip is a **pair**: the still from Stage A, plus a motion prompt that
describes only what changes. Do not restate the scene — restating it invites
the motion model to redraw and lose the face.

Four directive slots per clip:

1. **Natural physics** — weight, momentum, what gravity does. Cloth settles,
   hair lags behind the head turn, liquid has surface tension.
2. **Micro-expressions** — a blink, a breath, a swallow, the eyes finding
   something off-frame. Small. This is the tell that separates a live frame
   from a puppet.
3. **Camera movement** — name one move and its speed. Slow push in. Handheld
   drift. Static with breathing-room sway. One move per clip, never two.
4. **Environmental continuity** — what carries across the cut: light direction,
   time of day, weather, wardrobe, the same room. State it every clip; the
   model has no memory of the last one.

**Template**

```
MOTION: <one camera move, with speed>
SUBJECT: <physics + one micro-expression>
CONTINUITY: <light direction, time of day, wardrobe, location — repeated verbatim across the block>
HOLD: <what must not change>
```

**Worked example (Lilweid register)**

```
MOTION: slow push in, ~10% over 5 seconds, handheld micro-drift
SUBJECT: shoulders rise and fall once with a breath; a single slow blink; weight shifts to the left foot
CONTINUITY: hard morning light from frame left, overcast, grey wool coat, same stone doorway
HOLD: face, wardrobe, light direction
```

## Stage C — Voiceover and pacing (ElevenLabs)

Voice is locked to ElevenLabs. The script engine writes narration; this stage
adds the marks that make speech land on cuts.

- **Write pacing into the script at gate 2**, not after the voice is rendered.
  Re-rendering a take to fix a pause is a second paid call.
- **One sentence per clip.** A 5s clip carries roughly 12–16 words of measured
  narration. Sentences that span a cut blur the edit.
- **Mark the beats inline**: `[beat]` for a short breath between sentences,
  `[hold]` for a full stop against a visual, `[lift]` where the reading rises
  into the turn.
- **Silence is a tool.** Leave the last 0.5–1s of the final clip unnarrated so
  the closing frame lands.
- **Never speed-correct in post** to fit a block. Cut a word instead — the
  canon's register survives trimming better than it survives time-stretching.

---

## Script and retention structure — 45s Short

Nine clips, three blocks. Beat table is the default shape, not a rule.

| Clip | Time | Beat | Job |
|---|---|---|---|
| 1 | 0:00–0:05 | **Hook** | Curiosity gap, stated as fact. Visual must contradict the expectation |
| 2 | 0:05–0:10 | Turn | Name the thing the viewer got wrong |
| 3 | 0:10–0:15 | Stakes | Why it costs them something |
| 4–6 | 0:15–0:30 | Body | One idea per clip. No lists, no recaps |
| 7 | 0:30–0:35 | Pivot | The reframe the whole Short exists to deliver |
| 8 | 0:35–0:40 | Instruction | The one thing to actually do |
| 9 | 0:40–0:45 | Close | Land it. Last second silent |

### Hooks

The brief's example is the `"0% of this is real..."` curiosity-gap form. Draft 1
adds one hard constraint, taken from the repo's existing standard for
thumbnails and marketing claims:

> **A hook must be literally true.** "0% of this is real" is a strong hook and
> an honest one for AI-generated footage. The same sentence over live-shot
> footage is a lie, and the channel's whole proposition is that it does not
> lie. Information gap, never false claim.

Forms that work with this pipeline:

- **The disclosure gap** — "none of this footage exists." True here, and the
  photorealism is the payoff.
- **The cost gap** — "this took four minutes and cost less than a coffee."
  Only if the gate-3 credit estimate actually says so.
- **The mechanism gap** — "you have seen this a hundred times and never noticed
  what it is doing."
- **The refusal gap** — "everyone tells you X. X is the reason it stopped working."

Avoid: engagement-bait questions, "wait for it", and any number that has not
come from a real run.

---

## Open decisions

Four calls that are the operator's. **The first two block production.**

1. **Motion engine conflict — blocking.** The brief names Kling AI, Seedance and
   Veo. `models.json` locks video to **`seedance-1.5-pro` via kie**, `locked:
   true`, set by the operator 2026-08-28, and the pipeline "refuses a paid stage
   against anything else." Kling and Veo cannot be used without the operator
   changing that lock. Draft 1 assumes **Seedance 1.5 Pro only** and treats the
   others as unavailable.
2. **No base-plate image lock — blocking.** The brief names Midjourney and
   Higgsfield Soul for Stage A. `models.json` has image locks for
   `thumbnails` (kie/flux) and `stickman_art` (nano-banana-pro) only. **There is
   no entry for photoreal base plates.** One must be added before Stage A can
   run through the pipeline's own checks.
3. **50s target.** Not a whole number of 15s blocks. Retarget to 45s, or accept
   a partial block.
4. **f/1.8.** Kept because the brief specifies it. Flagged as the parameter
   most likely to need revision after the first test.

## What Draft 2 needs

Nothing here is measured. Draft 2 should be written after one Short has shipped,
and should carry: the actual credit cost from gate 3, retention at 3s and at the
pivot, which photorealism parameters survived removal, and whether 45s or 30s
held better. Record the findings with `python automation/core/memory.py` so the
learnings reach future episodes.
