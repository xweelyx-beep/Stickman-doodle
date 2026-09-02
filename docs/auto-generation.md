# Automated generation

`scripts/auto_generate.py` renders all 157 frames end to end — submit, download,
verify, record, resume — without stopping for a human between frames.

It sits beside `scripts/generate_frames.py`, which does not submit and hands
batches to a person instead. Both remain supported; see
[`docs/generating-frames.md`](generating-frames.md) for the manual route.

## What changed, and what did not

This script contradicts what `scripts/config/models.json` used to say. That file
put Stickman art on `route: "manual"`, called Google Flow and Meta AI *"browser
surfaces with no API this pipeline can reach"*, and set
`credit_safeguard.pipeline_submits: false` with the note *"This repository
contains no code that calls a paid endpoint."*

The operator authorised automated submission on 2026-08-29. **Both entries in
`models.json` were rewritten to say so**, naming the change and its date, rather
than leaving a config that quietly disagrees with the code next to it.

Two things that config was protecting are kept, because they were the point of
it rather than incidental:

| Safeguard | How it survives |
|---|---|
| The tool is never the pipeline's choice | `--backend` is required. `default_backend` in `generation.json` is deliberately `null`. |
| Nothing paid runs unwatched | Every run is a dry run unless `--execute`. A paid backend *also* needs `--approve-spend N` matching the exact image count. |

The concurrency cap in `references/style-rules.md` §1 governs batches a human
reviews, not machine submission. Its spirit survives as `--delay`: requests are
paced serially, so a misconfigured run costs a few frames rather than 157.

## Quick start — free, no account, no spend

```bash
python3 scripts/auto_generate.py --list-backends
python3 scripts/auto_generate.py --backend mock --start 0 --end 9            # dry run
python3 scripts/auto_generate.py --backend mock --start 0 --end 9 --execute  # renders
python3 scripts/generate_frames.py verify                                    # cross-check
```

`mock` is local and free. It writes structurally valid PNGs derived from each
prompt, so the whole harness — resume, retry, backoff, verification, the
manifest — can be exercised before any provider is involved. **Run it first.**

## Real generation

```bash
# 1. Pick a backend and configure its model in scripts/config/generation.json.
# 2. Export that backend's key.
export FAL_KEY=...

# 3. Dry run. Shows the window, the count, and the cost line.
python3 scripts/auto_generate.py --backend fal --start 0 --end 156

# 4. Execute, acknowledging the exact number of images.
python3 scripts/auto_generate.py --backend fal --start 0 --end 156 \
        --delay 3 --execute --approve-spend 157
```

If `--approve-spend` does not match what the run would submit, it refuses:

```
error: --approve-spend 5 does not match the 10 image(s) this run would submit.
Re-check the window and approve the real number.
```

Keys are read from the environment and never written to disk.

## Arguments

| Flag | Default | What it does |
|---|---|---|
| `--backend` | **required** | `mock`, `gemini`, `fal`, `replicate`, `flow` |
| `--start` | `0` | first frame |
| `--end` | `156` | last frame, inclusive |
| `--delay` | `3.0` paid, `0` free | seconds between requests |
| `--max-retries` | `5` | retries per frame |
| `--execute` | off | actually submit; otherwise dry run |
| `--approve-spend N` | — | required for paid backends; must equal the real count |
| `--regenerate` | off | re-render frames that already verify |
| `--no-reference` | off | run without the mascot — invites drift |
| `--abort-after N` | `3` | stop after N consecutive failures; `0` disables |
| `--list-backends` | — | show what is configured |

## Resume

Automatic and requires no state file. Before each run every frame in the window
is checked on disk; one that exists **and passes verification** is skipped. So:

- Interrupt with Ctrl-C and re-run — it picks up where it stopped.
- A corrupted or truncated frame is re-rendered; its neighbours are not.
- `--regenerate` forces the whole window.

Verified live: after rendering frames 0–9, corrupting `004.png`, and re-running,
the driver reported `to render : 1 of 10 (9 already done)` and touched only
`004.png`.

## Retry and rate limiting

- **Delay** between every request, not just after a failure. It defaults to
  3 s for a paid backend and **0 for a free one** — pacing exists to stay inside
  a provider's rate limit, and `mock` has none, so the default would otherwise
  spend about eight minutes asleep across 157 frames for no reason. An explicit
  `--delay` wins either way.
- **Exponential backoff with full jitter** on retryable failures, capped at 60 s.
  Full jitter rather than fixed doubling so parallel runs do not resonate.
- **`Retry-After` is honoured** when the provider sends one on a 429 or 503.
- **4xx is not retried.** A malformed request fails the same way five times; the
  driver reports it and moves on rather than burning the window.
- **Transport faults are classified, not blanket-retried.** A proxy answering
  4xx to CONNECT, a TLS verification failure, and a hostname that does not
  resolve all mean the request never left the machine and never will. Those fail
  immediately. Timeouts, resets, and proxy 429/502/503 still retry, and anything
  unrecognised defaults to retryable — a blip is likelier than a permanent
  condition.
- **A systemic fault stops the run.** `--abort-after N` (default 3) halts after N
  consecutive failures. A blocked host, a bad key or a wrong model id fails
  identically on every frame, and discovering that 157 times is just waiting.
  `--abort-after 0` disables it.

Measured on a container whose egress policy blocks `fal.run`: **2.7 minutes down
to 7.4 seconds**, stopping at 3 frames instead of 157. The old path would have
spent about 2.4 hours reaching the same answer.

## Validation

Bytes are checked **before** anything reaches disk, against the same contract
`generate_frames.py verify` applies afterwards:

- PNG magic bytes and a readable `IHDR`
- a 4 KB floor, which catches truncated and error-page renders
- writes go to `NNN.png.part` and are renamed only once valid, so an interrupted
  download never leaves a half file that later looks done

A backend returning junk therefore produces a `FAILED` line, a non-zero exit, and
no file at all.

**A wrong format is never retried.** On a paid backend every retry is another
billed generation, and a provider that returns JPEG returns JPEG every time —
six retries buys nothing and costs six images per frame. Only a plausibly
truncated download is retried.

**The failure names the format and the fix.** A live run on 2026-08-30 returned
JPEG and reported only `not a PNG (bad magic bytes)`. It now reads:

```
expected PNG, got JPEG (server sent Content-Type: image/jpeg).
    FLUX and several other models default to JPEG. Set request.static.output_format
    to "png" for this backend in scripts/config/generation.json.
    JPEG, 6010 bytes, first 200 hex: ffd8ffe000104a464946...
```

and an error body arrives decoded rather than as hex:

```
the response is not an image — JSON, 49 bytes, first 49:
'{"detail":"Unauthorized: invalid or expired key"}'
```

Both `fal` and `gemini` now request PNG explicitly in `generation.json`
(`output_format` and `outputOptions.mimeType` respectively).

## The reference image

Every frame is conditioned on `references/character_ref_body.png`. The driver
refuses to start if it is missing, and refuses a backend whose config declares no
`reference_path` — generating 157 frames without the mascot is how character
drift enters a set. `--no-reference` overrides deliberately and prints
`DRIFT RISK` in the header.

## Backends

Request and response shapes live in `scripts/config/generation.json` rather than
in code, because provider APIs and model ids move. Each ships the provider's
documented shape with `model_verified: false` until a human checks it.

| Backend | Kind | Needs |
|---|---|---|
| `mock` | local | nothing |
| `gemini` | HTTP | `$GEMINI_API_KEY`; Imagen predict endpoint |
| `fal` | HTTP | `$FAL_KEY`; synchronous |
| `replicate` | HTTP | `$REPLICATE_API_TOKEN`; a **version id**, not a model name; polls |
| `flow` | Playwright | a signed-in Chromium profile and DOM selectors |

Preflight fails with the fix named — which variable is unset, which field is
`null` — before a single request goes out.

### Two things I could not verify from here

**Model ids.** `gemini` ships `imagen-3.0-generate-002` and `fal` ships
`fal-ai/flux/dev/image-to-image`. Both carry `model_verified: false`. These
change as providers ship new versions; check them against current docs before a
157-frame run. `replicate.model` is `null` — Replicate needs a version hash,
which only you can supply.

**Prices.** `rates.usd_per_image` is `null` for every backend, so the driver
prints an image count and says it has no sourced rate. It will not estimate from
memory. Fill `rates` with a source URL and a date and it starts printing real
totals.

### The `flow` backend, and a risk worth naming

Google Flow has no public API. This backend drives the live page in Chromium:
types the prompt, attaches the reference, submits, reads the result image back.

It needs a `profile_dir` pointing at a Chromium user-data directory **you have
signed into once by hand**, and DOM selectors filled from the live page —
shipped as `null` because Flow's markup is not a stable contract.

**Automating a Google product may breach its terms of service, and the account
carrying that risk is yours.** It is implemented because you asked for it. Prefer
an API backend where one exists, and treat `flow` as the route of last resort.

## Cost before you run

At 157 frames a mistake is expensive. Before any paid run:

1. `--backend mock --execute` on the full range — free, proves the harness.
2. Dry run against the real backend and read the count.
3. Real run on a **small window** first: `--start 0 --end 2 --approve-spend 3`.
   Look at the three PNGs against `references/character-sheet.md`.
4. Only then open the window. `--delay 3` on 157 frames is about 8 minutes of
   pacing plus provider time.

## Tests

```bash
python3 scripts/tests/test_auto_generate.py
```

67 tests, no network. HTTP backends are exercised through stubs; end-to-end runs
use `mock`. They cover the spend gate, resume, retry and backoff behaviour,
validation, the reference requirement, request shaping per provider, and that no
default backend is configured.
