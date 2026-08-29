# Mascot — locked character sheet

**Status:** the written lock is canon. The *drawn* turnaround is not — see
"What is still missing" at the bottom.

Extracted verbatim from `docs/channel-bible.md` section 5, which was itself
locked from the operator's reference image. Nothing here is new. When the two
disagree, the bible wins and this file is the stale copy.

**Reference image:** [`character_ref_body.png`](character_ref_body.png)
(1348 × 752, PNG, lossless — the file `brand.json` records as the locked
character). [`character_ref_body.jpg`](character_ref_body.jpg) is the same
artwork re-encoded as JPEG; prefer the PNG for anything fed to a model.

---

## The figure

**Not a pure stick figure.** Stick-style limbs on a clothed, volumetric body.
Getting this wrong in either direction is the main drift risk: a true stick
figure is too crude, a full cartoon body loses the channel's look.

| Part | Lock |
|---|---|
| **Head** | Large white rounded head, roughly a third of total height. Thick black outline. Two big round eyes, white with solid black pupils, thin arched black brows. Small closed smiling mouth. **No nose, no ears.** |
| **Hair** | Short, spiky, dark chocolate brown with a lighter brown highlight, swept slightly forward, thick black outline. |
| **Limbs** | Thin solid black tubular arms and legs, constant width, no elbow or knee joints, rubber-hose style. **This is the stick element.** |
| **Hands** | White four-fingered rounded gloves with black outlines, always gloved, never bare. |
| **Wardrobe (default)** | Royal-blue hooded sweatshirt with a hood, front kangaroo pocket, drawstring, white inner collar V. Dark charcoal-grey trousers. White low-top sneakers with grey soles and laces. |
| **Rendering** | Flat vector cel style, uniform heavy black outlines, light cel shading, soft elliptical drop shadow under the feet, plain light-grey gradient background. |

## The never clause

Never a plain line-drawn stick figure with a circle head. Never bare hands.
Never five fingers. Never a nose or ears. Never visible elbow or knee joints.
Never photoreal, 3D-rendered, sketchy or hand-drawn-doodle. Never a different
hoodie colour without an explicit wardrobe change instruction.

## Prompt block, paste verbatim

> Flat vector cartoon character, thick uniform black outlines, cel shading.
> Large white rounded head about one third of body height, big round eyes with
> solid black pupils, thin arched brows, small closed smile, no nose, no ears.
> Short spiky dark-brown hair swept forward. Thin solid black tube arms and legs
> with no joints. White four-fingered rounded gloves. Royal-blue hoodie with
> hood, front pocket and drawstring over a white collar. Dark charcoal trousers.
> White low-top sneakers with grey soles. Soft elliptical drop shadow. Plain
> light-grey gradient background.

**Negative:** plain stick figure, circle head, bare hands, five fingers, nose,
ears, visible joints, photoreal, 3D render, sketch, doodle, outline-only.

## Prompting rules that apply to the mascot

From bible section 10:

- **Never invent the mascot.** Reference the existing episodes.
- **Every prompt stands alone.** Restate the locked traits in full.
- **No character names in image or video prompts.** Describe visually.
- Until the drawn turnaround exists, supply
  [`character_ref_body.png`](character_ref_body.png) as an **image reference**
  rather than relying on the written description alone (bible section 11.5).

## What is still missing

`[TBD]` in the canon, not filled here and not to be guessed:

- **3-panel character sheet** — headless front, full rear, tight chest-up face
  lock. The bible says generate it from the reference image before episode
  three, so later prompts have a real turnaround to reference rather than words.
- **Expression sheet.**
- **Side and rear views.**
- **Walk cycle.**

Generating any of these is a paid image call. Per the house rule, the tool is
the operator's choice and the spend is approved before the call, never after.
