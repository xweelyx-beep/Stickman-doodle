#!/usr/bin/env python3
"""KIE AI video and thumbnail prompts, plus what the batch will cost.

The house production method is not this module's invention. It is the
operator's, recovered in `.claude/rules/stickman.md` section 9 and restated in
the `studio` skill, and it applies to every channel: 15-second blocks of three
5-second clips, one camera motion per clip from a closed set, no block running
the same motion three times, the style key appended identically to every scene,
a negative prompt on every clip, and a credit projection before anything is
submitted. All of it is enforced here rather than left to whoever is prompting.

On money: KIE is paid, so this module never picks the model and never invents a
rate. It counts billable units always, and converts them to credits only when
`automation/config/kie.json` carries a rate with a source. Unset means the
estimate comes back None, not a plausible number.
"""

import argparse
import datetime
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canon import CHANNELS, load_canon, repo_root  # noqa: E402

# Closed set, from the house method. A static shot is a failure.
CAMERA_MOTIONS = ("slow push-in", "slow pull-back", "slow tilt-up", "gentle drift")

HOUSE_NEGATIVE = (
    "identifiable real person, recognisable celebrity face, on-screen presenter, "
    "text artifacts, watermark, logo, subtitles, distorted hands, extra fingers, "
    "warped anatomy, flicker, morphing objects"
)

THUMBNAIL_CONCEPTS = (
    {
        "id": "A",
        "angle": "Information gap",
        "composition": "Single subject hard left on the thirds line, overlay text stacked right. "
                       "Subject occupies the left 45% of frame, text block the right 40%, 5% safe "
                       "margin all round.",
        "why": "The viewer can see what the video is about and cannot see the answer.",
    },
    {
        "id": "B",
        "angle": "Before / after split",
        "composition": "Vertical split down the centre, contrasting states either side, overlay "
                       "text as a two-word caption centred across the seam.",
        "why": "Reads as a comparison at 320x180 without any text being legible.",
    },
    {
        "id": "C",
        "angle": "Single object under hard light",
        "composition": "One object centred, negative space around it, overlay text lower third, "
                       "left aligned. No secondary subject.",
        "why": "Survives the smallest render; the object alone carries the click.",
    },
)


def load_models(root):
    """The operator's toolchain locks. The pipeline reads them; it never sets them."""
    path = os.path.join(root, "automation", "config", "models.json")
    if not os.path.isfile(path):
        raise SystemExit(f"error: missing {path}; the toolchain lock is part of the pipeline")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_path"] = os.path.relpath(path, root)
    return cfg


def enforce_video_lock(models, requested):
    """A locked engine means a locked engine. A different model is an error, not a warning."""
    lock = models["video"]
    if requested and lock.get("locked") and requested != lock["model"]:
        raise SystemExit(
            "error: video generation is locked to %s (%s) in %s. You asked for %r. "
            "Change the lock in that file if the decision has changed; this tool will not "
            "quietly render on a different paid model."
            % (lock["display_name"], lock["model"], models["_path"], requested))
    return lock["model"]


def load_kie_config(root):
    path = os.path.join(root, "automation", "config", "kie.json")
    if not os.path.isfile(path):
        raise SystemExit(f"error: missing {path}; the KIE config is part of the pipeline")
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_path"] = os.path.relpath(path, root)
    return cfg


def build_style_key(canon):
    """One string, appended identically to every scene prompt. Every fragment is
    lifted from the canon; the sources are reported alongside it."""
    parts, sources = [], []
    if canon.mascot_prompt:
        parts.append(canon.mascot_prompt)
        sources.append("mascot prompt block (verbatim)")
    if canon.palette:
        parts.append(canon.palette)
        sources.append("palette")
    if canon.visual_register:
        parts.append(canon.visual_register)
        sources.append("visual register")
    if canon.visual_registers:
        parts.append("registers: " + " / ".join(canon.visual_registers))
        sources.append("alternating registers")
    if not parts:
        raise SystemExit(
            f"error: {canon.channel} has no visual system in {canon.path} — the canon marks it "
            "[BLOCKED] and there is no mascot block to fall back on. Supply --style-key "
            "explicitly; this tool will not invent a look for a channel that already has one "
            "on screen."
        )
    return " ".join(p.rstrip(".") + "." for p in parts), sources


def build_negative(canon):
    if canon.negative_prompt:
        return canon.negative_prompt + ", " + HOUSE_NEGATIVE, "canon negative + house default"
    return HOUSE_NEGATIVE, "house default (canon states no negative for this channel)"


def clips_for(seconds, clip_seconds):
    return max(1, int(round(seconds / float(clip_seconds))))


def build_scenes(script_payload, style_key, negative, aspect, model, clip_seconds,
                 clips_per_block, resolution=None, prompt_standard=None):
    """Every beat becomes whole clips, then clips are chunked into blocks. Motion
    is assigned by absolute clip index, which guarantees the three clips inside
    one block never share a motion."""
    scenes = []
    index = 0
    for beat in script_payload["beats"]:
        for n in range(clips_for(beat["seconds"], clip_seconds)):
            block = index // clips_per_block + 1
            motion = CAMERA_MOTIONS[index % len(CAMERA_MOTIONS)]
            cue = beat["visual_cues"][min(n, len(beat["visual_cues"]) - 1)]
            scenes.append({
                "scene_id": "S%03d" % (index + 1),
                "block": block,
                "position_in_block": index % clips_per_block + 1,
                "beat": beat["name"],
                "beat_number": beat["number"],
                "timestamp": beat["timestamp"],
                "duration_s": clip_seconds,
                "aspect_ratio": aspect,
                "resolution": resolution,
                "prompt_standard": prompt_standard,
                "model": model,
                "camera_motion": motion,
                "register": beat["visual"]["register"],
                "grade": beat["visual"]["grade"],
                "prompt": "%s Camera: %s. %s" % (cue["cue"], motion, style_key),
                "negative_prompt": negative,
                "standalone": True,
            })
            index += 1
    return scenes


def check_house_rules(scenes, clips_per_block):
    """Assert the method held. A violation here is a bug, not a warning."""
    problems = []
    blocks = {}
    for s in scenes:
        blocks.setdefault(s["block"], []).append(s)
    for block, members in sorted(blocks.items()):
        motions = {m["camera_motion"] for m in members}
        if len(members) == clips_per_block and len(motions) == 1:
            problems.append("block %d uses one motion in all %d scenes" % (block, clips_per_block))
        for m in members:
            if m["camera_motion"] not in CAMERA_MOTIONS:
                problems.append("scene %s has motion %r outside the closed set"
                                % (m["scene_id"], m["camera_motion"]))
            if not m["negative_prompt"]:
                problems.append("scene %s has no negative prompt" % m["scene_id"])
    return problems


def build_thumbnails(titles, topic, keywords, canon, cfg):
    overlays = []
    for i, concept in enumerate(THUMBNAIL_CONCEPTS):
        title = titles[i % len(titles)] if titles else {"text": topic, "label": "Direct"}
        words = [w for w in title["text"].replace(",", " ").split() if len(w) > 2][:4]
        overlay = " ".join(w.upper() for w in words[:3]) or keywords[0].upper()
        overlays.append({
            "id": concept["id"],
            "angle": concept["angle"],
            "paired_title": title["text"],
            "title_intent": title.get("label"),
            "prompt": ("%s %s Extreme contrast between subject and background, single clear focal "
                       "point, no text rendered in the image. %s"
                       % (concept["composition"], concept["why"], build_style_key(canon)[0])),
            "overlay_text": {
                "text": overlay,
                "max_words": 3,
                "placement": concept["composition"].split(",")[0],
                "typeface": "heavy geometric sans, all caps",
                "min_cap_height_px": 90,
                "stroke": "4px outline plus drop shadow, so it holds on any background",
                "contrast_rule": "overlay never sits on a busy region; flatten or darken behind it",
                "added_in": "post, not by the image model",
            },
            "composition_guide": concept["composition"],
            "aspect_ratio": cfg["image"]["aspect_thumbnail"],
            "resolution": cfg["image"]["resolution"],
            "model": cfg["image"]["model"],
            "legibility_check": "renders readable at 320x180",
            "negative_prompt": build_negative(canon)[0],
        })
    return overlays


def estimate_cost(cfg, scene_count, clip_seconds, thumbnail_count, variants):
    """Billable units always; credits only when a sourced rate exists."""
    rates = cfg.get("rates", {})
    video_seconds = scene_count * clip_seconds
    images = thumbnail_count * variants
    per_second = rates.get("credits_per_video_second")
    per_clip = rates.get("credits_per_video_clip")
    per_image = rates.get("credits_per_image")

    video_credits = None
    if per_second is not None:
        video_credits = video_seconds * per_second
    elif per_clip is not None:
        video_credits = scene_count * per_clip
    image_credits = images * per_image if per_image is not None else None
    total = None
    if video_credits is not None and image_credits is not None:
        total = video_credits + image_credits

    usd = rates.get("usd_per_credit")
    return {
        "video_clips": scene_count,
        "clip_seconds": clip_seconds,
        "video_seconds": video_seconds,
        "thumbnail_images": images,
        "blocks": int(math.ceil(scene_count / float(cfg["video"]["clips_per_block"]))),
        "rates_source": rates.get("source"),
        "rates_checked_utc": rates.get("checked_utc"),
        "rates_configured": any(v is not None for v in (per_second, per_clip, per_image)),
        "video_credits": video_credits,
        "image_credits": image_credits,
        "total_credits": total,
        "total_usd": (total * usd) if (total is not None and usd is not None) else None,
        "note": ("Credits computed from the rate card in automation/config/kie.json."
                 if total is not None else
                 "No credit figure: automation/config/kie.json carries no sourced rate. "
                 "Billable units above are exact; fill the rate card in before gate 3 or "
                 "state the approved spend yourself with `approve --gate 3 --credits N`."),
    }


def build_manual_image_handoff(models, channel, episode_id, scenes):
    """Stickman art runs on Nano Banana Pro through Google Flow or Meta AI — browser
    surfaces with no API this pipeline can reach. So it emits a numbered, timestamped
    work order for a human to run, and nothing is submitted from here."""
    spec = models["image"]["stickman_art"]
    if channel != "stickman":
        return None
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M")
    return {
        "engine": spec["engine"],
        "model": spec["model"],
        "route": spec["route"],
        "route_options": spec["route_options"],
        "automated": False,
        "note": spec["_route_note"],
        "queue": [
            {
                "n": i + 1,
                "scene_id": s["scene_id"],
                "filename": spec["filename_convention"].format(
                    episode_id=episode_id or channel, NN="%02d" % (i + 1),
                    **{"YYYYMMDD-HHMM": stamp}).replace("{YYYYMMDD-HHMM}", stamp),
                "prompt": s["prompt"],
                "negative_prompt": s["negative_prompt"],
            }
            for i, s in enumerate(scenes)
        ],
    }


def generate(channel, script_payload, root=None, style_key=None, model=None,
             image_model=None, titles=None, shorts=False, episode_id=None):
    root = root or repo_root()
    canon = load_canon(channel, root)
    cfg = load_kie_config(root)
    models = load_models(root)

    # Toolchain locks win over the older kie.json fields.
    cfg["video"]["model"] = enforce_video_lock(models, model)
    cfg["video"]["clip_seconds"] = models["video"]["clip_seconds"]
    cfg["video"]["clips_per_block"] = models["video"]["clips_per_block"]
    cfg["video"]["aspect_long_form"] = models["video"]["aspect_long_form"]
    cfg["video"]["aspect_shorts"] = models["video"]["aspect_shorts"]
    cfg["image"]["model"] = image_model or models["image"]["thumbnails"]["model"]

    key, key_sources = (style_key, ["operator-supplied"]) if style_key else build_style_key(canon)
    negative, negative_source = build_negative(canon)
    aspect = cfg["video"]["aspect_shorts"] if shorts else cfg["video"]["aspect_long_form"]
    clip_seconds = cfg["video"]["clip_seconds"]
    clips_per_block = cfg["video"]["clips_per_block"]

    resolution = (models["video"]["resolution_shorts"] if shorts
                  else models["video"]["resolution_long_form"])
    scenes = build_scenes(script_payload, key, negative, aspect, cfg["video"]["model"],
                          clip_seconds, clips_per_block, resolution,
                          models["video"]["prompt_standard"])
    problems = check_house_rules(scenes, clips_per_block)
    if problems:
        raise SystemExit("error: house method violated by the generated scene list:\n  - "
                         + "\n  - ".join(problems))

    thumbnails = build_thumbnails(titles or [], script_payload["topic"],
                                  script_payload["keywords"], canon, cfg)
    cost = estimate_cost(cfg, len(scenes), clip_seconds, len(thumbnails),
                         cfg["image"]["variants"])

    payload = {
        "channel": channel,
        "topic": script_payload["topic"],
        "canon_path": os.path.relpath(canon.path, root),
        "config_path": cfg["_path"],
        "aspect_ratio": aspect,
        "video_engine": models["video"]["engine"],
        "video_model": cfg["video"]["model"],
        "video_model_display": models["video"]["display_name"],
        "video_model_locked": models["video"]["locked"],
        "video_cost_claim": models["video"]["cost_claim"],
        "resolution": resolution,
        "prompt_standard": models["video"]["prompt_standard"],
        "image_model": cfg["image"]["model"],
        "model_selection": "locked by the operator in %s" % models["_path"],
        "models_path": models["_path"],
        "manual_image_handoff": None,
        "style_key": key,
        "style_key_sources": key_sources,
        "negative_prompt": negative,
        "negative_prompt_source": negative_source,
        "house_method": {
            "block_seconds": cfg["video"]["block_seconds"],
            "clip_seconds": clip_seconds,
            "clips_per_block": clips_per_block,
            "camera_motions": list(CAMERA_MOTIONS),
            "halt_after_every_block": True,
            "max_concurrent_prompts": 3,
            "bulk_generation": "forbidden",
            "verified": "no house-rule violations in this scene list",
        },
        "blocks": cost["blocks"],
        "scene_count": len(scenes),
        "scenes": scenes,
        "thumbnails": thumbnails,
        "cost_estimate": cost,
        "credit_safeguard": models["credit_safeguard"],
        "production_constraints": canon.production_constraints,
    }
    payload["manual_image_handoff"] = build_manual_image_handoff(
        models, channel, episode_id, payload["scenes"])
    return payload


def render_thumbnail_markdown(p):
    L = []
    A = L.append
    A("# 04 — KIE thumbnail prompts")
    A("")
    A("| Field | Value |")
    A("|---|---|")
    A("| Channel | `%s` |" % p["channel"])
    A("| Image model | %s (locked in `%s`) |" % (p["image_model"], p["models_path"]))
    A("| Aspect | %s |" % p["thumbnails"][0]["aspect_ratio"])
    A("| Variants each | %d |" % (p["cost_estimate"]["thumbnail_images"] // len(p["thumbnails"])))
    A("")
    for c in p["production_constraints"]:
        A("> **Canon constraint:** %s" % c)
        A("")
    for t in p["thumbnails"]:
        A("## %s — %s" % (t["id"], t["angle"]))
        A("")
        A("**Paired title (%s):** %s" % (t["title_intent"], t["paired_title"]))
        A("")
        A("**Prompt**")
        A("")
        A("```")
        A(t["prompt"])
        A("```")
        A("")
        A("**Negative**")
        A("")
        A("```")
        A(t["negative_prompt"])
        A("```")
        A("")
        A("**Overlay text** — added in post, never rendered by the image model")
        A("")
        A("| Spec | Value |")
        A("|---|---|")
        for k in ("text", "max_words", "placement", "typeface", "min_cap_height_px",
                  "stroke", "contrast_rule"):
            A("| %s | %s |" % (k, t["overlay_text"][k]))
        A("")
        A("**Composition:** %s" % t["composition_guide"])
        A("")
        A("**Check:** %s" % t["legibility_check"])
        A("")
    handoff = p.get("manual_image_handoff")
    if handoff:
        A("## Manual image handoff — %s" % handoff["model"])
        A("")
        A("> **Not automated.** %s" % handoff["note"])
        A("")
        A("Route: %s (options: %s)" % (handoff["route"], ", ".join(handoff["route_options"])))
        A("")
        A("| # | Scene | Save as |")
        A("|---|---|---|")
        for item in handoff["queue"][:24]:
            A("| %d | %s | `%s` |" % (item["n"], item["scene_id"], item["filename"]))
        if len(handoff["queue"]) > 24:
            A("")
            A("_%d more in `03_kie_video_prompts.json` under `manual_image_handoff`._"
              % (len(handoff["queue"]) - 24))
        A("")
    return "\n".join(L).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="KIE video and thumbnail prompts from a script payload.")
    ap.add_argument("--channel", required=True, choices=CHANNELS)
    ap.add_argument("--script-json", required=True,
                    help="path to a script_engine --json payload, or - for stdin")
    ap.add_argument("--style-key")
    ap.add_argument("--video-model")
    ap.add_argument("--image-model")
    ap.add_argument("--shorts", action="store_true")
    ap.add_argument("--episode")
    ap.add_argument("--root")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.script_json == "-":
        script_payload = json.load(sys.stdin)
    else:
        if not os.path.isfile(args.script_json):
            raise SystemExit(f"error: no script payload at {args.script_json}; run "
                             "script_engine.py --json first")
        with open(args.script_json, "r", encoding="utf-8") as fh:
            try:
                script_payload = json.load(fh)
            except ValueError as exc:
                raise SystemExit(
                    "error: %s is not valid JSON (%s). It should be the output of "
                    "`script_engine.py --json`; check that command succeeded."
                    % (args.script_json, exc))

    payload = generate(args.channel, script_payload, args.root, args.style_key,
                       args.video_model, args.image_model,
                       script_payload.get("titles"), args.shorts, args.episode)
    print(json.dumps(payload, indent=2) if args.json else render_thumbnail_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
