# Revision changelog — character density pass

**File:** `prompts/image_prompts_why_you_check_your_phone_v2.txt`
**Base:** `prompts/image_prompts_why_you_check_your_phone.txt` (unmodified, kept for diffing)
**Date:** 2026-08-29

---

## Result

| | Base | v2 |
|---|---|---|
| Frames | 54 | 54 |
| Protagonist present | 11 | **25** |
| Presence | **20.4%** | **46.3%** |
| Frames modified | — | 14 |
| Frames byte-identical | — | 40 |
| Longest dry run | **27 frames** (`[01:01]`–`[02:22]`) | **5 frames** (`[02:06]`–`[02:20]`) |

Target was 45–50%. 46.3% lands in band.

## About the numbers

The brief quoted a 29% baseline and a 25–30 frame injection. Those are figures
for the **full 157-frame file**. This pass ran on the 54 frames that were
actually supplied — the source paste ends mid-sentence inside `[03:22]`, so
everything from there to `[11:22]` is absent.

Measured, not assumed: 11 of 54 frames carry the character lock in the base, so
the real baseline for this slice is **20.4%**. Scaling the brief's target to 54
frames gives 14 injections, which is what was applied. The same pass re-run on
the complete file will need roughly 25 more.

## Dry runs found in the base

Measured as runs of 3+ consecutive frames with no protagonist:

| Run | Frames | Segment |
|---|---|---|
| `[00:32]`–`[00:44]` | 4 | phone / app icons / hourglass / brain machinery |
| `[01:01]`–`[02:22]` | **27** | Skinner lab, box, pigeon, variable-ratio diagrams |
| `[02:27]`–`[03:19]` | 12 | Schultz lab, dopamine molecule, monkey, oscilloscope |

The brief named Skinner `[01:11]`–`[02:22]` and Schultz `[02:27]`–`[03:42]`. The
measured Skinner run starts 10 seconds earlier, at `[01:01]`, and the Schultz run
is cut short at `[03:19]` by the truncation. Casino `[05:38]`–`[06:44]` and
Gloria Mark `[07:46]`–`[08:26]` are past the end of the supplied material and
were not touched.

## Frames modified

Distribution: 1 in the early object run, 9 across the Skinner run, 4 across the
Schultz run.

| Frame | Why the character was placed here | Contradiction removed | Chars |
|---|---|---|---|
| `[00:44]` | Turns the abstract 'MACHINERY' reveal into his realisation; carries the hook's question into the thesis. | dropped `no characters in the scene` | 669 → 1261 |
| `[01:11]` | Opens the 27-frame Skinner run with the viewer's surrogate; the box is introduced to him, not just shown. | dropped `no characters in the scene` | 591 → 1194 |
| `[01:17]` | 'SIMPLE' lands as his ease; sets the baseline his later confusion is measured against. | dropped `no human characters in the scene` | 614 → 1184 |
| `[01:25]` | He owns the cause-and-effect beat rather than the diagram explaining itself. | dropped `no characters in the scene` | 571 → 1145 |
| `[01:30]` | First crack in his understanding — the pigeon stops and he does not yet know why. | dropped `no human characters in the scene` | 597 → 1165 |
| `[01:42]` | 'UNPREDICTABLE' becomes a felt reversal; his objection is the viewer's. | dropped `no characters in the scene` | 614 → 1192 |
| `[01:44]` | Pulls him physically into the experiment at the moment the reward stops arriving. | dropped `no human characters in the scene` | 577 → 1150 |
| `[01:51]` | The 'SOMETIMES' beat is the episode's hinge; his recognition marks it. | dropped `no characters in the scene` | 548 → 1131 |
| `[02:02]` | Scale is legible against his height — the bar means something because he is dwarfed by it. | dropped `no characters in the scene` | 607 → 1179 |
| `[02:22]` | Closes the Skinner run by rhyming the pocket drift from [00:00]; the lever and the phone become one gesture. | dropped `no characters in the scene` | 646 → 1269 |
| `[02:47]` | Opens the 12-frame Schultz run with a reacting observer instead of a floating diagram. | dropped `no characters in the scene` | 600 → 1184 |
| `[02:52]` | 'WRONG' is the segment's reversal; he registers it so the correction has a face. | dropped `no characters in the scene` | 634 → 1201 |
| `[03:15]` | The flat line means nothing without someone expecting a spike; he supplies the expectation. | dropped `no characters in the scene` | 613 → 1199 |
| `[03:19]` | The payoff of the whole Schultz segment lands on him, matching his realisation beats elsewhere. | dropped `no characters in the scene` | 657 → 1244 |

## Method

Each modified frame received the **full character lock block verbatim** — no
shorthand — inserted directly after the front style anchor, followed by a
placement-and-reaction clause written for that beat, then the original scene
description unchanged.

Every injected frame previously carried `no characters in the scene` or `no
human characters in the scene`. That clause was removed wherever the character
was added; leaving it would put a direct contradiction in the prompt. The
removal is recorded per frame above and is the only deletion the pass made.

Constraints held:

- Front style anchor: unchanged in all 54 frames.
- End style lock: unchanged in all 54 frames.
- One frame per line, blank line between entries: verified, 0 multi-line entries.
- The 40 unmodified frames: **byte-identical**, verified by per-frame comparison
  against the base — 0 unintended differences.
- Supporting characters (Skinner, Schultz) keep their own distinct lock blocks
  and were not altered.

## Placement rationale

The protagonist is a **reacting observer**, never a second explainer. He is
placed at a frame edge or in the lower foreground, scaled small against the
subject, and given one readable expression drawn from the vocabulary already in
the base file — the same raised-brow tilt, uneasy frown and wide-eyed
realisation the hook frames use. No new expression vocabulary was invented.

Two placements do structural work rather than just filling a gap:

- **`[02:02]`** — he stands at the base of the bar chart, so the tall
  "SOMETIMES" bar is scaled against a known height instead of floating.
- **`[02:22]`** — his far glove drifts toward his pocket without him looking,
  the exact gesture from `[00:00]`. It closes the Skinner run by rhyming the
  lever with the phone, which is the episode's argument in one image.

## Not done

The pass covers `[00:00]`–`[03:19]` only. The remaining segments named in the
brief — Fiorillo/Tobler uncertainty, the smartphone mechanism, Schüll and the
casino floor, Harris, Gloria Mark's attention data, the savannah, and the close
— are not in the repository. Nothing was generated to fill them.
