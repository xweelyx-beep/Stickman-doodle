# The video pipeline

From 157 prompts to a 4K master, in one command.

```bash
python3 scripts/build_full_video.py --backend mock --execute
```

That renders the frames, validates them, builds the audio bed, and assembles
`output/final_video_4k.mp4`. Swap `mock` for a real backend to get real
pictures. Each stage is also runnable on its own.

## The single command

```bash
# Free end-to-end, proves the whole chain without spending anything
python3 scripts/build_full_video.py --backend mock --execute

# Real generation, paid, with the spend acknowledged
python3 scripts/build_full_video.py --backend fal --execute --approve-spend 157

# Assemble only, from frames already on disk
python3 scripts/build_full_video.py --skip-generate
```

Output: `output/final_video_4k.mp4` — 3840×2160, H.264 + AAC, 30 fps by default
(`--fps 60` for 60).

## What each stage does

| Stage | Tool | Skippable with |
|---|---|---|
| 1. generate | `scripts/auto_generate.py` | `--skip-generate`, or omit `--backend` |
| 2. validate | `scripts/generate_frames.py verify` | — |
| 3. audio | built here from the cue sheet | happens automatically when files exist |
| 4. assemble | `scripts/assemble_video.py` | `--skip-assemble` |

## Timing comes from the prompt file

Every frame carries an `[MM:SS]` marker. A shot runs until the next one starts:

```
duration[i] = timestamp[i+1] - timestamp[i]
```

Those 156 gaps sum to **exactly 682 s**, which is the stated 11:22 runtime. So
picture is locked to the VO timing by construction — there is no separate sync
pass to drift out of alignment, and a test asserts that sum.

**The last frame is the one exception.** Nothing follows `[11:22]`, so its
length is not derivable from the data. It takes `--tail-seconds` (default 3.0,
the median gap) and the tool reports the result as **11:25**, not 11:22. That is
three seconds the data does not contain; set it to whatever the cut actually
needs.

## Camera motion

Stills get continuous 2D motion. The vocabulary is not invented — it is the
four moves fixed in `references/style-rules.md` §1:

| Motion | What it does |
|---|---|
| `slow push-in` | zoom 1.00 → 1.12, centred |
| `slow pull-back` | zoom 1.12 → 1.00, centred |
| `slow tilt-up` | zoom held at 1.10, frame travels bottom → top |
| `gentle drift` | zoom held at 1.08, frame drifts left → right |

Assignment is deterministic and honours the canon's rule that **no three
consecutive shots share a motion** — enforced in code, and asserted by a test.
Across the film: gentle drift ×51, push-in ×37, tilt-up ×36, pull-back ×33.

Motion is expressed as a function of `on`, the output frame index, so a move
lands exactly on the shot boundary whatever the duration or frame rate.

### Why the moves are subtle

The zoom range is 1.00–1.12, not 1.0–1.5. Under a 2–3 second median shot length
a large move reads as a lurch. It also compounds the upscale problem below.

## Selective motion clips

18 of 157 shots are flagged as candidates for a generated video clip rather than
a panned still, classified from what the prompt actually describes:

| Shot | Timestamp | Why |
|---|---|---|
| 076, 077 | 04:52, 04:54 | the character is running |
| 136 | 09:30 | running toward the phone screen |
| 094, 108 | 06:04, 07:10 | slot reels spinning, refresh spinner |
| 065 | 04:07 | the coin spinning mid-air |
| 118, 119 | 08:14, 08:19 | the attention graph falling |
| 073 | 04:36 | the gauge needle slamming across |
| 101 | 06:31 | the melting clock |
| 153 | 11:11 | the storm cloud dispersing |

See the full list:

```bash
python3 scripts/core/timeline.py --dynamic
```

**Drop a clip at `output/clips/NNN.mp4` and the assembler uses it instead of the
still**, fitted to its slot: a short clip holds its last frame to fill, a long
one is cut. The timeline owns the duration, not the clip.

Two cues were deliberately *not* used, after a first pass produced false
positives: "eyebrows drooping" is an expression rather than movement, and
"radiating" describes a static glow as often as it does motion lines.

### Generating the clips is a separate, paid step

`auto_generate.py` renders stills. There is no video backend wired up —
`models.json` locks video to Seedance 1.5 Pro, and 18 clips is a spend decision
with its own approval. The assembler is ready for the files; producing them is
not automated here.

## Audio

Stage 3 reads `audio/music_bed_cues.md`, parses the seven movements, and builds
the bed: each movement trimmed to its own length, 1.0 s crossfades between them,
the whole bed ducked **15 dB** under the voiceover, then limited.

Verified against the real cue sheet — the seven movements parse contiguous, and
the built track came out **685.000 s**, matching the planned runtime exactly.

It needs files that are not in the repository:

```
audio/voiceover/why-you-check-your-phone.wav    (or .mp3/.m4a, or --vo PATH)
audio/music/01.wav .. 07.wav                    one per movement, in order
```

**The cue sheet is a plan, not audio.** Without these, stage 3 says so and the
build produces a silent 4K master — the correct intermediate, not a failure.
Partial music is refused outright: seven tracks or none, because a bed with
holes in it is worse than no bed.

## The 4K caveat, stated plainly

Output is always 3840×2160. If the rendered frames are smaller — the mascot
reference is 1348×752 — **the result is an upscale and will look soft.** The
assembler detects this and warns once:

```
! source frames are 1348x752, output is 3840x2160 — this is an upscale and will look soft.
  Generate at 4K in the backend if sharpness matters.
```

No filter fixes missing pixels. If sharpness matters, generate at 4K, or at
least 2K, in the backend. That is a generation setting, not an assembly one.

## How it renders

Shot by shot into `output/shots/NNN.mp4`, then a stream-copy concat. Slower to
start than one enormous `filter_complex`, and worth it:

- **Resumable.** A re-run skips shots already rendered at the right duration.
- **A bad shot fails alone**, instead of taking an 11-minute render with it.
- **Clips slot in** without a special case in the graph.

`zoompan` samples from a 4800×2700 working canvas so the maximum zoom still
downscales rather than upscaling — that is what stops the classic zoompan
shimmer.

## Requirements

**ffmpeg and ffprobe on PATH.** There is no pure-Python substitute for the
encoding.

```bash
brew install ffmpeg          # macOS
sudo apt-get install ffmpeg  # Debian/Ubuntu
```

Everything else is stdlib Python 3.

## Verified

On this machine, with ffmpeg 6.1.1:

```
$ python3 scripts/assemble_video.py --start 0 --end 5 --out output/test.mp4
wrote output/test_6shots.mp4  —  27.2 MB, 0:26, 0 clips used
timing     : 26.00s rendered vs 26.00s planned  (drift 0.00s)

$ ffprobe output/test_6shots.mp4
codec_name=h264  width=3840  height=2160  r_frame_rate=30/1  duration=26.000000
```

Also verified: a 1.0 s clip dropped in for a 2.0 s slot was padded to exactly
2.0 s; the audio stage built a 685.000 s mixed track from seven movements; and a
video+audio mux produced H.264 4K with an AAC stream at zero drift.

## Tests

```bash
python3 scripts/tests/test_video_pipeline.py
```

28 tests. Timing (durations are the marker gaps, the 682 s sum, tail handling),
camera motion (vocabulary, the no-three-in-a-row rule, determinism), dynamic
selection (the running and reel shots are caught, an expression is not),
filters, cue-sheet parsing including a deliberately broken sheet, audio gating,
and — where ffmpeg is present — real 4K renders, clip substitution and caching.
Tests needing ffmpeg skip cleanly without it.

## A note on "the Known Unknowns style"

Camera motion here comes from the **house production method** in
`references/style-rules.md` §1, which is channel-agnostic and applies to
Stickman by canon. It is not borrowed from another channel's look.

That matters because `docs/channel-bible.md` §3 draws an explicit boundary
between Stickman and its sibling channels, and §6 marks Stickman's own visual
system `[BLOCKED]` pending analysis of the two finished episodes. Copying a
sibling's aesthetic wholesale would contradict footage that already exists —
the specific failure the bible warns against. Pacing, palette and transition
vocabulary stay blocked until that footage is analysed.
