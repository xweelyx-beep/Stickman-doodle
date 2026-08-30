#!/usr/bin/env python3
"""Episode state machine and approval-gate enforcement.

    DRAFT -> SCRIPT_APPROVED -> PROMPTS_STAGED -> RENDERED -> PUBLISHED

Every edge is explicit and every edge that follows a human decision names the
gate that unlocks it. There is no force flag and no multi-step jump: the only
way from DRAFT to PROMPTS_STAGED is through gate 2 and then gate 3, each
recorded with who approved it and when. That is the whole 5% of this pipeline
that is not automated, so it is the part that refuses to be convenient.
"""

import argparse
import datetime
import json
import os
import tempfile

try:
    from canon import CHANNELS, repo_root
    import paths
except ImportError:  # imported as a package from run.py
    from .canon import CHANNELS, repo_root
    from . import paths

STATES = ("DRAFT", "SCRIPT_APPROVED", "PROMPTS_STAGED", "RENDERED", "PUBLISHED")

GATES = {
    "1": {
        "key": "gate_1_title_hook",
        "label": "Title & hook",
        "opened_by": "init",
        "unlocks": "script",
        "requires_prior": None,
        "transition": None,
    },
    "2": {
        "key": "gate_2_script",
        "label": "Narration script",
        "opened_by": "script",
        "unlocks": "prompts",
        "requires_prior": "1",
        "transition": ("DRAFT", "SCRIPT_APPROVED"),
    },
    "3": {
        "key": "gate_3_credits",
        "label": "KIE credit spend",
        "opened_by": "prompts",
        "unlocks": "package",
        "requires_prior": "2",
        "transition": ("SCRIPT_APPROVED", "PROMPTS_STAGED"),
    },
}

# to_state -> (from_state, gate key that must be approved or None)
TRANSITIONS = {
    "SCRIPT_APPROVED": ("DRAFT", "gate_2_script"),
    "PROMPTS_STAGED": ("SCRIPT_APPROVED", "gate_3_credits"),
    "RENDERED": ("PROMPTS_STAGED", None),
    "PUBLISHED": ("RENDERED", None),
}

EPISODE_FILES = {
    "seo": "01_ideation_and_seo.md",
    "script": "02_narration_script.md",
    "video_prompts": "03_kie_video_prompts.json",
    "thumbnail_prompts": "04_kie_thumbnail_prompts.md",
    "metadata": "05_metadata.md",
    "state": "state.json",
}


def utcnow():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def channel_dir(root, channel):
    return paths.channel_dir(root, channel)


def episode_dir(root, channel, episode_id):
    return paths.episode_dir(root, channel, episode_id)


def write_atomic(path, text):
    """Write through a temp file in the same directory so a crash never leaves
    a half-written state.json behind."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)  # mkstemp makes 0600; these are repo files, not secrets
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


class EpisodeState(object):
    def __init__(self, path, data):
        self.path = path
        self.data = data

    # ---------- construction ----------

    @classmethod
    def create(cls, root, channel, episode_id, topic, **extra):
        path = os.path.join(episode_dir(root, channel, episode_id), EPISODE_FILES["state"])
        if os.path.exists(path):
            raise SystemExit(
                f"error: {path} already exists; pick a different --episode-id or "
                "delete the episode directory to start over"
            )
        now = utcnow()
        data = {
            "schema": 1,
            "episode_id": episode_id,
            "channel": channel,
            "topic": topic,
            "state": "DRAFT",
            "created_utc": now,
            "updated_utc": now,
            "gates": {g["key"]: {
                "gate": key,
                "label": g["label"],
                "status": "not_opened",
                "opened_utc": None,
                "approved_utc": None,
                "approved_by": None,
                "note": None,
                "payload": {},
            } for key, g in sorted(GATES.items())},
            "artifacts": {},
            "approval_log": [{
                "utc": now, "actor": "pipeline", "action": "created",
                "from_state": None, "to_state": "DRAFT", "note": f"topic: {topic}",
            }],
            "seo": {}, "script": {}, "prompts": {}, "metadata": {},
        }
        data.update(extra)
        state = cls(path, data)
        state.save()
        return state

    @classmethod
    def load(cls, root, channel, episode_id):
        path = os.path.join(episode_dir(root, channel, episode_id), EPISODE_FILES["state"])
        if not os.path.isfile(path):
            raise SystemExit(
                f"error: no episode at {path}; run "
                f"`python scripts/run.py init --channel {channel} --topic \"...\"` first"
            )
        with open(path, "r", encoding="utf-8") as fh:
            return cls(path, json.load(fh))

    def save(self):
        self.data["updated_utc"] = utcnow()
        write_atomic(self.path, json.dumps(self.data, indent=2, sort_keys=False) + "\n")

    # ---------- accessors ----------

    @property
    def state(self):
        return self.data["state"]

    @property
    def dir(self):
        return os.path.dirname(self.path)

    def gate(self, key):
        if key not in GATES:
            raise SystemExit(f"error: unknown gate {key!r}; gates are 1, 2 and 3")
        return self.data["gates"][GATES[key]["key"]]

    def is_approved(self, key):
        return self.gate(key)["status"] == "approved"

    def log(self, actor, action, note=None, from_state=None, to_state=None):
        self.data["approval_log"].append({
            "utc": utcnow(), "actor": actor, "action": action,
            "from_state": from_state, "to_state": to_state, "note": note,
        })

    # ---------- gate mechanics ----------

    def require_command(self, command):
        """Refuse to run a stage whose unlocking gate is not approved."""
        needed = [k for k, g in sorted(GATES.items()) if g["unlocks"] == command]
        for key in needed:
            if not self.is_approved(key):
                g = self.gate(key)
                raise SystemExit(
                    f"error: gate {key} ({g['label']}) is {g['status']}, so `{command}` is locked. "
                    f"Review {EPISODE_FILES['seo'] if key == '1' else EPISODE_FILES['script'] if key == '2' else EPISODE_FILES['video_prompts']} "
                    f"in {self.dir}, then run `python scripts/run.py approve "
                    f"--channel {self.data['channel']} --episode {self.data['episode_id']} --gate {key} ...`"
                )

    def open_gate(self, key, payload=None, actor="pipeline"):
        gate = self.gate(key)
        gate["status"] = "pending"
        gate["opened_utc"] = utcnow()
        gate["payload"] = payload or {}
        gate["approved_utc"] = None
        gate["approved_by"] = None
        self.log(actor, f"gate_{key}_opened", note=GATES[key]["label"])
        self.save()
        return gate

    def check_gate_ready(self, key):
        """Order and openness, checked before any gate-specific validation so the
        error a person sees is the first thing actually wrong."""
        spec = GATES[key]
        gate = self.gate(key)
        prior = spec["requires_prior"]
        if prior and not self.is_approved(prior):
            raise SystemExit(
                f"error: gate {prior} ({GATES[prior]['label']}) is not approved, "
                f"so gate {key} cannot be. Approval gates run in order 1 -> 2 -> 3."
            )
        if gate["status"] == "not_opened":
            raise SystemExit(
                f"error: gate {key} ({spec['label']}) has not been opened; run "
                f"`python scripts/run.py {spec['opened_by']} ...` first so there is "
                "something to approve"
            )
        if gate["status"] == "approved":
            raise SystemExit(
                f"error: gate {key} ({spec['label']}) was already approved by "
                f"{gate['approved_by']} at {gate['approved_utc']}"
            )
        return gate

    def approve_gate(self, key, approved_by, note=None, payload=None):
        """Record a human approval and take the transition that gate unlocks.

        A gate can only be approved once it has been opened by its generating
        command, and never before the gate ahead of it. Approval is always a
        separate invocation from generation; there is no --approve flag on the
        generate commands, which is what makes these gates real."""
        spec = GATES[key]
        gate = self.check_gate_ready(key)
        gate["status"] = "approved"
        gate["approved_utc"] = utcnow()
        gate["approved_by"] = approved_by
        gate["note"] = note
        gate["payload"].update(payload or {})
        self.log(approved_by, f"gate_{key}_approved", note=note)
        if spec["transition"]:
            self.transition(spec["transition"][1], actor=approved_by,
                            note=f"gate {key} approved")
        else:
            self.save()
        return gate

    def transition(self, to_state, actor="pipeline", note=None):
        if to_state not in TRANSITIONS:
            raise SystemExit(
                f"error: {to_state!r} is not a reachable state; "
                f"states are {' -> '.join(STATES)}"
            )
        expected_from, gate_key = TRANSITIONS[to_state]
        if self.state != expected_from:
            raise SystemExit(
                f"error: cannot go {self.state} -> {to_state}; that edge starts at "
                f"{expected_from}. The only path is {' -> '.join(STATES)} and no step "
                "can be skipped."
            )
        if gate_key:
            gate = self.data["gates"][gate_key]
            if gate["status"] != "approved":
                raise SystemExit(
                    f"error: {self.state} -> {to_state} is gated on {gate['label']} "
                    f"(gate {gate['gate']}), currently {gate['status']}. Approve it first."
                )
        previous = self.state
        self.data["state"] = to_state
        self.log(actor, "transition", note=note, from_state=previous, to_state=to_state)
        self.save()
        return to_state

    def record_artifact(self, name, relative_path, **facts):
        self.data["artifacts"][name] = dict(
            {"path": relative_path, "written_utc": utcnow()}, **facts)
        self.save()

    def summary(self):
        gates = []
        for key, spec in sorted(GATES.items()):
            g = self.gate(key)
            gates.append({
                "gate": key, "label": spec["label"], "status": g["status"],
                "approved_by": g["approved_by"], "approved_utc": g["approved_utc"],
                "unlocks": spec["unlocks"],
            })
        return {
            "episode_id": self.data["episode_id"],
            "channel": self.data["channel"],
            "topic": self.data["topic"],
            "state": self.state,
            "gates": gates,
            "artifacts": sorted(self.data["artifacts"]),
            "next": self.next_action(),
        }

    def next_action(self):
        for key, spec in sorted(GATES.items()):
            g = self.gate(key)
            if g["status"] == "pending":
                return f"approve gate {key} ({spec['label']})"
            if g["status"] == "not_opened":
                return f"run `{spec['opened_by']}` to open gate {key} ({spec['label']})"
        if self.state == "PROMPTS_STAGED":
            return "run `package` to build metadata and mark RENDERED"
        if self.state == "RENDERED":
            return "run `package --publish` once the video is live"
        return "done"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Inspect or drive one episode's state machine.")
    ap.add_argument("action", choices=("show", "approve", "transition"))
    ap.add_argument("--channel", required=True, choices=CHANNELS)
    ap.add_argument("--episode", required=True)
    ap.add_argument("--gate", choices=sorted(GATES))
    ap.add_argument("--to", choices=[s for s in STATES if s != "DRAFT"])
    ap.add_argument("--by", default=os.environ.get("USER", "operator"))
    ap.add_argument("--note")
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = args.root or repo_root()
    state = EpisodeState.load(root, args.channel, args.episode)

    if args.action == "approve":
        if not args.gate:
            raise SystemExit("error: --gate is required for approve (1, 2 or 3)")
        state.approve_gate(args.gate, args.by, note=args.note)
    elif args.action == "transition":
        if not args.to:
            raise SystemExit("error: --to is required for transition")
        state.transition(args.to, actor=args.by, note=args.note)

    summary = state.summary()
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"{summary['channel']} / {summary['episode_id']}  [{summary['state']}]")
        print(f"  topic : {summary['topic']}")
        for g in summary["gates"]:
            mark = {"approved": "x", "pending": "!", "not_opened": " "}[g["status"]]
            who = f" by {g['approved_by']} {g['approved_utc']}" if g["approved_by"] else ""
            print(f"  [{mark}] gate {g['gate']}  {g['label']:<18} {g['status']}{who}")
        print(f"  next  : {summary['next']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
