#!/usr/bin/env python3
"""The single authority on where things live on disk.

Migrated out of the Business repo, where the pipeline served three channels and
resolved everything relative to a multi-channel tree:

    <root>/.claude/rules/<channel>.md      canon
    <root>/automation/config/*.json        toolchain locks
    <root>/automation/memory/              cross-session state
    <root>/channels/<channel>/episodes/    episodes

This repository holds one channel, so the layout is flat and declared in
`channel.json` at the repository root rather than hard-coded here. Nothing else
in this package constructs a repository path: every module asks this one. That
is what makes the tree movable — change `channel.json`, not the Python.

Root resolution, in order:

    1. an explicit `root` argument, wherever a caller passes --root
    2. $STICKMAN_REPO_ROOT
    3. the marker walk: up from this file until a directory holds channel.json

The walk means the pipeline runs from any working directory, and a checkout can
sit anywhere on disk. There is no fallback to a hard-coded path, so a missing
marker fails loudly instead of silently reading the wrong tree.
"""

import json
import os

MARKER = "channel.json"
ROOT_ENV = "STICKMAN_REPO_ROOT"

_DEFAULT_LAYOUT = {
    "canon": "docs/channel-bible.md",
    "config": "scripts/config",
    "memory": "memory",
    "episodes": "episodes",
    "brand": "references/brand.json",
}

_cache = {}


def find_root(start=None):
    """Walk up from `start` until a directory holding channel.json is found."""
    env = os.environ.get(ROOT_ENV)
    if env and not start:
        root = os.path.abspath(os.path.expanduser(env))
        if not os.path.isfile(os.path.join(root, MARKER)):
            raise SystemExit(
                f"error: ${ROOT_ENV} is set to {root!r} but there is no {MARKER} "
                "there; unset it or point it at the repository root"
            )
        return root

    here = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    if os.path.isfile(here):
        here = os.path.dirname(here)
    while True:
        if os.path.isfile(os.path.join(here, MARKER)):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            raise SystemExit(
                f"error: no {MARKER} found at or above {start or __file__}; "
                "this is not a Stickman-doodle checkout. Run from inside one, "
                f"pass --root, or set ${ROOT_ENV}."
            )
        here = parent


def repo_root(start=None):
    """Alias kept so the name reads the same as it did in the Business tree."""
    return find_root(start)


def manifest(root=None):
    """channel.json, parsed and cached per root."""
    root = root or find_root()
    if root not in _cache:
        path = os.path.join(root, MARKER)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"error: cannot read {path}: {exc}")
        if not data.get("channel"):
            raise SystemExit(f"error: {path} declares no 'channel'")
        layout = dict(_DEFAULT_LAYOUT)
        layout.update(data.get("layout") or {})
        data["layout"] = layout
        _cache[root] = data
    return _cache[root]


def channel_name(root=None):
    return manifest(root)["channel"]


def channels(root=None):
    """The tuple the argument parsers offer. One channel, in this repository."""
    try:
        return (channel_name(root),)
    except SystemExit:
        # argparse builds its choices at import time, before --root is parsed.
        # Outside a checkout, offer the default rather than refusing to start;
        # the real resolution happens when a command actually runs.
        return ("stickman",)


def _under(root, key):
    root = root or find_root()
    return os.path.join(root, manifest(root)["layout"][key])


def canon_path(channel=None, root=None):
    root = root or find_root()
    check_channel(channel, root)
    return _under(root, "canon")


def config_path(name, root=None):
    """A file in the config directory, e.g. config_path('models.json')."""
    return os.path.join(_under(root, "config"), name)


def brand_path(root=None, channel=None):
    """The brand gate. Its own layout key: it is a reference asset here, not a
    file sitting beside the episodes as it was in the multi-channel tree."""
    root = root or find_root()
    check_channel(channel, root)
    return _under(root, "brand")


def memory_dir(root=None, create=True):
    path = _under(root, "memory")
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def channel_dir(root=None, channel=None):
    """The channel's own directory. Flat here: the repository root itself."""
    root = root or find_root()
    check_channel(channel, root)
    return root


def episodes_dir(root=None, channel=None):
    root = root or find_root()
    check_channel(channel, root)
    return _under(root, "episodes")


def episode_dir(root=None, channel=None, episode_id=None):
    return os.path.join(episodes_dir(root, channel), episode_id)


def check_channel(channel, root=None):
    """Accept the repository's own channel, or None. Refuse anything else."""
    if channel is None:
        return
    try:
        expected = channel_name(root)
    except SystemExit:
        return
    if channel != expected:
        raise SystemExit(
            f"error: unknown channel {channel!r}; this repository holds "
            f"{expected!r} only. The other channels live in xweelyx-beep/Business."
        )


def describe(root=None):
    root = root or find_root()
    m = manifest(root)
    lines = [f"root     : {root}", f"channel  : {m['channel']}"]
    for key in sorted(m["layout"]):
        path = os.path.join(root, m["layout"][key])
        mark = "" if os.path.exists(path) else "   (missing)"
        lines.append(f"{key:9}: {m['layout'][key]}{mark}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe())
