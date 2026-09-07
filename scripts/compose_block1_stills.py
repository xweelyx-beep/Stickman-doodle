#!/usr/bin/env python3
"""Crop-and-frame Block 1 stills from the locked canon reference image.

This is NOT AI generation. It takes the single locked reference image
(references/character_ref_body.png), isolates the character from its
light-grey reference-sheet background by color-distance thresholding
(the source has no alpha channel), and composites three crops of that
same pose onto the locked #0F172A scene background:

  clip_01.jpg  Medium shot  (waist-up)
  clip_02.jpg  Close-up     (head + collar)
  clip_03.jpg  Wide shot    (grounded full body)

Because all three crops come from one static reference pose, they are
identity-locked by construction, but do NOT show the beat-specific
actions in 02_scene_prompts.md (questioning shrug / head-shake denial /
arms-crossed). This is a placeholder for pipeline/timing QA, not final
per-beat art -- said plainly here so it isn't mistaken for one later.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

BG_COLOR = (15, 23, 42)  # #0F172A
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
SOURCE = os.path.join("references", "character_ref_body.png")
OUT_DIR = os.path.join("episodes", "ep001-nail-biting-dermatophagia", "assets", "stills")


def isolate_character(img_path):
    img = Image.open(img_path).convert("RGB")
    arr = np.array(img).astype(np.int16)

    h, w, _ = arr.shape
    corners = np.array([arr[0, 0], arr[0, w - 1], arr[h - 1, 0], arr[h - 1, w - 1]])
    bg_color = corners.mean(axis=0)
    print(f"[*] Sampled background color from corners: {bg_color.round(1).tolist()}")

    dist = np.sqrt(((arr - bg_color) ** 2).sum(axis=2))
    # The source has a soft radial highlight behind the figure, so a single
    # global threshold either lets the halo through (low) or eats light-toned
    # character details like the white gloves/shoes (high). Flood-fill from
    # the border instead: only mark background-close pixels that are actually
    # *connected* to the image edge through the gradient as background --
    # isolated same-colored regions inside the figure stay foreground.
    bg_candidate = dist < 55
    labels, _ = ndimage.label(bg_candidate)
    border_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
    border_labels.discard(0)
    bg_mask = np.isin(labels, list(border_labels))

    fg_mask = (~bg_mask).astype(np.uint8) * 255
    mask_img = Image.fromarray(fg_mask, mode="L")
    mask_img = mask_img.filter(ImageFilter.MinFilter(3))  # erode: drop 1-2px edge noise
    mask_img = mask_img.filter(ImageFilter.MaxFilter(3))  # dilate: restore true edges
    mask_img = mask_img.filter(ImageFilter.GaussianBlur(1.0))  # soften the cut edge
    fg_mask = np.array(mask_img) > 0

    ys, xs = np.where(fg_mask)
    if len(xs) == 0:
        print("[!] Could not isolate a foreground subject -- aborting.")
        sys.exit(1)

    x_min, x_max, y_min, y_max = xs.min(), xs.max(), ys.min(), ys.max()
    print(f"[*] Character bounding box: x[{x_min}:{x_max}] y[{y_min}:{y_max}]")

    rgba = np.dstack([arr.astype(np.uint8), np.array(mask_img)])
    return Image.fromarray(rgba, mode="RGBA").crop((x_min, y_min, x_max + 1, y_max + 1))


def frame(char, scale_ratio, y_anchor):
    scale = (CANVAS_HEIGHT * scale_ratio) / char.height
    new_size = (int(char.width * scale), int(char.height * scale))
    resized = char.resize(new_size, Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR)
    pos_x = (CANVAS_WIDTH - new_size[0]) // 2
    if y_anchor == "bottom":
        pos_y = CANVAS_HEIGHT - new_size[1]
    elif y_anchor == "grounded":
        pos_y = int(CANVAS_HEIGHT * 0.90) - new_size[1]
    else:
        pos_y = (CANVAS_HEIGHT - new_size[1]) // 2
    canvas.paste(resized, (pos_x, pos_y), resized)
    return canvas


def main():
    if not os.path.exists(SOURCE):
        print(f"[!] Source not found: {SOURCE}")
        sys.exit(1)

    print(f"[*] Loading locked reference: {SOURCE}")
    char = isolate_character(SOURCE)
    print(f"[*] Isolated character size: {char.size}")

    print("[*] Composing clip_01 (Medium Shot, waist-up)...")
    waist_up = char.crop((0, 0, char.width, int(char.height * 0.62)))
    clip_01 = frame(waist_up, scale_ratio=0.85, y_anchor="bottom")

    print("[*] Composing clip_02 (Close-Up, head + collar)...")
    head_close = char.crop((0, 0, char.width, int(char.height * 0.42)))
    clip_02 = frame(head_close, scale_ratio=0.90, y_anchor="bottom")

    print("[*] Composing clip_03 (Wide Shot, grounded full body)...")
    clip_03 = frame(char, scale_ratio=0.72, y_anchor="grounded")

    os.makedirs(OUT_DIR, exist_ok=True)
    for name, frame_img in [("clip_01.jpg", clip_01), ("clip_02.jpg", clip_02), ("clip_03.jpg", clip_03)]:
        path = os.path.join(OUT_DIR, name)
        frame_img.save(path, "JPEG", quality=95)
        print(f"    saved {path}  ({frame_img.size[0]}x{frame_img.size[1]})")

    print("\nDone. These are crops of one static reference pose, not per-beat art -- see module docstring.")


if __name__ == "__main__":
    main()
