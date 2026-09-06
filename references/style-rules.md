# Style rules

Two kinds of rule live here. The **house production method** is verified and
applies today. The **channel visual system** was locked 2026-09-06 from an
operator-directed Zenn+Rico benchmark session — see `docs/channel-bible.md`
section 6 for the pivot note. The two pre-existing unanalyzed episodes (still
on an unreachable Windows drive) are now legacy assets, not the blocking
condition for this section.

Source: `docs/channel-bible.md` sections 6, 9 and 10.

---

## 1. House production method — verified, applies now

Written by the operator on an earlier project, recovered from the KIE pipeline
branch. Channel-agnostic. These exist to stop credit burn.

| Rule | Value |
|---|---|
| Block structure | 15-second blocks, three 5-second clips per block |
| Mandatory halt | Stop and wait for approval after **every** block. No exceptions. |
| Concurrency cap | Never output more than **three** generation prompts at once |
| Bulk generation | Forbidden. Prompting a whole script at once is a failure. |
| Camera motion | Required on every clip, exactly one of `slow push-in` · `slow pull-back` · `slow tilt-up` · `gentle drift`. A static shot is a failure. |
| Motion variety | No block repeats the same motion in all three scenes |
| Style key | Appended to every scene prompt, identically |
| Runtime | Agreed before writing; credit cost projected per block before any submission |
| Negative prompt | On every clip, listing what must not appear |

## 2. Channel production rules — partial

From bible section 10. Extend once footage is analysed.

- **Never invent the mascot.** Reference the existing episodes.
- **Every prompt stands alone.** Restate the locked traits in full.
- **No character names in image or video prompts.** Describe visually.
- **Actionable means actionable.** If an episode explains a mechanism but hands
  the viewer nothing to do, it has drifted toward Lilweid.
- **9:16 for Shorts, 16:9 for long-form.**

## 3. The Lilweid boundary test

Both channels explain why people do things that hurt them. Three separations
hold at once:

| | Stickman | Lilweid |
|---|---|---|
| **Question** | Mechanism — the biological and behavioural machinery | Meaning — the emotional weight |
| **Tone** | Light, quick, a little funny | Slow and literary |
| **Payload** | Actionable; gives the viewer something to do | Reflective; deliberately does not |

**The test.** "Can't stop eating sugar" belongs here when it explains dopamine,
habit loops and what to change. The same title belongs on Lilweid when it asks
what the eating is protecting. If a script cannot say which of the two it is
doing, it is not ready.

## 4. Visual system — locked 2026-09-06

Full lock lives in `docs/channel-bible.md` section 6 — palette hex table,
7px/1080p outline weight, flat 2-tone cel shading, the two-background split
(light-grey for reference sheets, Deep Slate/Charcoal for scenes), the
push-in=tension/pull-back=release camera convention, and the 3-pivot
Extreme-Close-Up signature shot. Not repeated here in full to avoid the two
copies drifting — read the bible section for the authoritative version.

Pacing: 3.5–4.0s average editorial beat-change rate inside the house
method's 5s/clip ceiling. For comparison, the sibling channels sit at **4.7s
per scene** (Lilweid) and **8.3s per scene** (Known Unknowns); Rico
Animations measured at **3.0s** average via real scene analysis.

`scripts/config/analytics.json` still records `pacing.stickman: null` —
that's real production data (from actual published episodes), not the same
thing as this locked pre-production target, and should stay null until real
footage exists to measure.

## 5. Voice `[BLOCKED]`

Register, pace, sentence length, how the narrator addresses the viewer, and
whether it uses humour — all to be read off the finished episodes.

**Sign-off.** Known Unknowns ends on `"You're welcome."` Lilweid ends on an
aphorism. This channel needs its own and must not borrow either. Note that the
`scriptwriting` skill appends `"You're welcome."` by default, so using it
unmodified here produces the wrong sign-off.

**Narrator.** `Eva` (`Xn6GqAFT1vo7SexgOVmn`) is recorded in
`scripts/config/elevenlabs.json` as `locked: false`, `"operator preference, not
final"`. Picking a voice id does not unblock this section.

## 6. Episode architecture — locked 2026-09-06

~450–550 words, ~45–55 beats, 2.5–3 min runtime: cold open → 3–4 escalating
independent mechanism reveals (each with a named researcher + concrete study)
→ exactly 3 false-summit retention pivots interleaved between them →
actionable circuit-level resolution → closing callback bookend. Full detail
and the 8-episode topic roadmap: `docs/channel-bible.md` section 8.

## 7. What unblocks sections 4–6

**One reachable link to either episode.** Unlisted YouTube, or any host serving
a public or direct URL. On arrival: run the scene analysis, extract the
sections, and replace every `[BLOCKED]` marker with a verified lock.
