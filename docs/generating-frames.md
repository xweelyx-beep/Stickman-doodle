# Generating the frames

`scripts/generate_frames.py` drives the 157-frame Nano Banana Pro queue for
*Why You Check Your Phone*.

## What it does, and what it cannot

**It generates nothing, and it makes no network call of any kind.** That is not
a limitation to work around — it is what this repository's own locked config
requires. `scripts/config/models.json`:

```json
"stickman_art": {
  "engine": "nano-banana-pro",
  "route": "manual",
  "route_options": ["google-flow", "meta-ai"],
  "_route_note": "Google Flow ... and Meta AI are browser surfaces with no API
                  this pipeline can reach ... Nothing here submits automatically."
}
```

and:

```json
"credit_safeguard": {
  "pipeline_submits": false,
  "_note": "This repository contains no code that calls a paid endpoint."
}
```

Nano Banana Pro reaches this channel through Google Flow or Meta AI, both
browser surfaces. There is no API to call. A script that claimed otherwise
would be lying about what it does.

What it automates is the part that actually costs time across 157 frames:
**owning the queue.** It parses and validates the prompt file, hands out work in
canon-sized batches, watches the output directory, verifies what lands there is
a real image under the right name, records progress durably, and resumes exactly
where it stopped.

## Why it batches instead of looping

`references/style-rules.md` §1 — the house production method, written to stop
credit burn:

| Rule | Value |
|---|---|
| Concurrency cap | Never output more than **three** generation prompts at once |
| Bulk generation | **Forbidden.** Prompting a whole script at once is a failure. |
| Mandatory halt | Stop and wait for approval after every block. No exceptions. |

A loop that fired all 157 prompts would break all three. `next` hands out three,
marks them issued, and halts. `--batch-size` above 3 is refused, with the rule
quoted.

## Running it

```bash
# See the plan. Read-only, submits nothing, changes nothing.
python3 scripts/generate_frames.py plan

# Hand out the next three prompts as a work sheet.
python3 scripts/generate_frames.py next

# ... run those three in Google Flow or Meta AI, with
# references/character_ref_body.png attached as the reference image on every
# one, and save the results as output/frames/000.png, 001.png, 002.png ...

# Record the arrivals. Exits non-zero if anything is wrong.
python3 scripts/generate_frames.py verify

# Then repeat `next` / `verify` until done.
python3 scripts/generate_frames.py status
```

Progress at any point:

```
$ python3 scripts/generate_frames.py status
[###.....................................] 12/157  7.6%
pending 145 · issued 0 · done 12
next up: 012.png, 013.png, 014.png
```

`status -v` lists every frame with its state and recorded dimensions.

## Commands

| Command | What it does | Writes? |
|---|---|---|
| `plan` | parse, validate, show the batch plan | no |
| `next` | emit the next batch as a work sheet | marks issued |
| `verify` | scan the output directory, record arrivals | manifest only |
| `status` | progress, overall and per frame with `-v` | manifest only |
| `reset --yes` | clear queue state, keeping the rendered PNGs | deletes manifest |

Options: `--root` to point at a checkout explicitly, `--batch-size` (max 3),
`--force` on `next` to hand out a batch while frames are still outstanding.

## Output

```
output/frames/000.png  ..  156.png     one per frame, 0-indexed
output/frames/manifest.json            queue state
```

`output/` is gitignored — renders are not committed. The manifest is queue
state, not a source file; `reset --yes` followed by `status` rebuilds progress
from whatever PNGs are on disk, so losing it costs nothing.

**Numbering.** Filenames are 0-indexed (`000.png` = frame 1 = `[00:00]`;
`156.png` = frame 157 = `[11:22]`). The changelog numbers frames from 1 and the
prompt file addresses them by timestamp. The manifest carries all three for
every frame, so nothing is ambiguous.

This diverges from `models.json` → `filename_convention`
(`{episode_id}_{NN}_{YYYYMMDD-HHMM}_nbpro.png`), which was written for the
episode-directory handoff sheet the four-command pipeline emits. These prompts
were authored by hand rather than by that pipeline, and the flat `NNN.png` form
is what this queue uses. Worth reconciling if the two ever need to meet.

## What `verify` actually checks

Not just that a file exists:

- **PNG magic bytes and a readable IHDR** — a renamed JPEG or an error page
  saved as `.png` is rejected.
- **A size floor of 4 KB** — catches truncated or failed renders that still
  carry a valid header.
- **Dimensions**, recorded per frame in the manifest so drift is visible.
- **Regressions** — a frame previously marked done whose file has vanished is
  demoted back to issued rather than silently left green.

Any problem exits non-zero, so it composes into a shell loop.

## The reference image

Every frame is generated against `references/character_ref_body.png`
(1348 × 752, the lossless PNG `brand.json` records as the locked character).
The queue refuses to start if it is missing — the canon's rule is that the
mascot is never invented, and a batch run without the reference attached is how
character drift enters a 157-frame set.

`next` restates the reference path on every batch header for that reason.

## Tests

```bash
python3 scripts/tests/test_generate_frames.py
```

20 tests. The first class, `NeverSubmits`, is the one that matters: it greps the
source for any network surface and asserts the concurrency cap is enforced. The
rest cover parsing, the halt, resume, verification, and reset.
