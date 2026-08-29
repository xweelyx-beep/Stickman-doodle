# Style rules

Two kinds of rule live here. The **house production method** is verified and
applies today. The **channel visual system** is `[BLOCKED]` — two finished
episodes define it and neither has been analysed, because they sit on a local
Windows drive this environment cannot reach.

**Do not fill a blocked section from imagination.** A lock invented here would
contradict footage that already exists, which is worse than no lock at all.

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

## 4. Visual system `[BLOCKED]`

Not known. To be extracted from the finished footage, not invented:

- Palette and background treatment
- Line weight
- Text-on-screen style and typography
- Transition vocabulary
- How diagrams and numbers are drawn
- Camera behaviour, if any
- Pacing in seconds per beat

For comparison once measured, the sibling channels sit at **4.7 s per scene**
(Lilweid) and **8.3 s per scene** (Known Unknowns). A modern explainer channel
would be *expected* to run faster than both — that is an expectation, not a
measurement, and must not be written in as a lock.

`scripts/config/analytics.json` records `pacing.stickman: null` for the same
reason.

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

## 6. Episode architecture `[BLOCKED]`

To be read off the finished episode. Lilweid and Known Unknowns each turned out
to have a strict repeatable beat structure — six and nine beats respectively.
Assume this one does too and read it off the footage rather than imposing a
generic explainer template.

## 7. What unblocks sections 4–6

**One reachable link to either episode.** Unlisted YouTube, or any host serving
a public or direct URL. On arrival: run the scene analysis, extract the
sections, and replace every `[BLOCKED]` marker with a verified lock.
