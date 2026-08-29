# automation

Four commands, three human gates, one state machine. Stdlib-only Python 3.

```bash
python automation/run.py init    --channel known-unknowns --topic "how anaesthesia works" \
                                 --keyword "anaesthesia" --runtime 8:30
python automation/run.py approve --channel known-unknowns --episode <id> --gate 1 --title 1 --by you
python automation/run.py script  --channel known-unknowns --episode <id>
python automation/run.py approve --channel known-unknowns --episode <id> --gate 2 --by you
python automation/run.py prompts --channel known-unknowns --episode <id>
python automation/run.py approve --channel known-unknowns --episode <id> --gate 3 --credits 900 --by you
python automation/run.py package --channel known-unknowns --episode <id> --by you
python automation/run.py package --channel known-unknowns --episode <id> --publish \
                                 --publish-date 2026-09-10 --by you
```

Or let the wizard pick the command:

```bash
python automation/run.py wizard                 # numbered: channel, then action
python automation/run.py wizard --channel known-unknowns --action resume
```

Publishing and retention:

```bash
python automation/run.py schedule --channel known-unknowns    # Tue/Fri slots
python automation/run.py remind --kind longform               # the 17:30 check
python automation/run.py remind --kind shorts                 # the 18:30 check
python automation/run.py remind --install                     # schtasks / cron lines
python automation/run.py analyze --channel known-unknowns --episode <id> \
    --metrics '{"ctr_percent": 4.1, "retention_30s_percent": 62, "average_view_duration_s": 214}'
```

`status` shows where one episode or a whole channel stands:

```bash
python automation/run.py status --channel known-unknowns
python automation/run.py status --channel known-unknowns --episode <id>
```

Each core tool also runs on its own:

```bash
python automation/core/canon.py --channel lilweid
python automation/core/seo_engine.py --channel lilweid --topic "..." --runtime 3:20
python automation/core/script_engine.py --channel lilweid --topic "..." --json > script.json
python automation/core/kie_prompt_builder.py --channel lilweid --script-json script.json
python automation/core/state_manager.py show --channel lilweid --episode <id>
```

## Before first use

- `automation/config/elevenlabs.json` — set `voice_id` per channel. The API key
  is read from `$ELEVENLABS_API_KEY` and is never stored.
- `automation/config/kie.json` — fill the rate card with a `source` and
  `checked_utc` if you want credit figures instead of billable units.
- `automation/config/models.json` — the toolchain locks (Seedance 1.5 Pro, Flux,
  Nano Banana Pro, ElevenLabs). Edit here to change a locked model; the tools
  will not accept an override on the command line.
- `channels/stickman/brand.json` — Stickman long-form stays unschedulable until
  every item is marked done.
- `python automation/run.py remind --install` — prints the two scheduled-task
  lines (17:30 long-form, 18:30 shorts). Installing them is yours to run.

Conventions and the reasoning behind the gates: `.claude/rules/automation.md`.
