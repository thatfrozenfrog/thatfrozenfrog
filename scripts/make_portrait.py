#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "opencv-python-headless",
#     "pillow",
#     "numpy",
# ]
# ///
"""Turn a photo or avatar into ascii.svg — a self-typing, monochrome ASCII portrait.

This is the generator that produces the portrait at the top of the README.
Run it once; it is not on a daily schedule, unlike scripts/generate_stats.py.

    uv run scripts/make_portrait.py scripts/avatar.png

Features:
  * Optional rembg: automatically skips neural background removal if rembg is not installed,
    making it fast and clean for manga scans, avatars, and drawings with clean backgrounds.
  * Embeds JetBrains Mono ramp font automatically after generation.
  * Animated SMIL typewriter clipPath wipe with a greentext cursor (#789922).
"""
import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image

try:
    from rembg import remove
    HAS_REMBG = True
except ImportError:
    HAS_REMBG = False

try:
    from embed_portrait_font import embed_font
except ImportError:
    try:
        from .embed_portrait_font import embed_font
    except Exception:
        embed_font = None

RAMP = " .`:-=+*cs#%@"     # bright/sparse -> dark/dense; leading space = blank
COLS = 68                  # 68-72 is optimal for avatar & profile layout
CLAHE_CLIP = 2.5           # contrast enhancement
GAMMA = 1.0                # ramp mapping exponent
CURVE = 1.35               # darkening curve
CROP_BOTTOM = 0.0          # fraction to trim off the bottom
ROW_RATIO = 0.48           # monospace cells are about twice as tall as wide

FG_LIGHT = "#1f2328"       # clean readable ink on GitHub light
FG_DARK = "#f0f6fc"        # GitHub dark-mode step
CURSOR_LIGHT = "#1f883d"   # GitHub contribution green cursor
CURSOR_DARK = "#3fb950"
CHAR_W = 7.74              # 0.600 em at FONT_SIZE
FONT_SIZE = 12.9
LINE_H = 15
ROW_DELAY = 0.08           # per-row stagger, seconds
FAMILY = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"


def prep(path, crop=None, use_rembg=False, curve=CURVE):
    """Cut out background or enhance contrast for line art/avatars."""
    src = Image.open(path).convert("RGBA")
    if crop:
        src = src.crop(crop)

    if use_rembg and HAS_REMBG:
        cut = remove(src)
        alpha = np.array(cut.split()[-1])
        white = Image.new("RGBA", cut.size, (255, 255, 255, 255))
        gray = np.array(Image.alpha_composite(white, cut).convert("L"))
        gray[alpha < 20] = 255
    else:
        # For line art / avatar without neural rembg:
        white = Image.new("RGBA", src.size, (255, 255, 255, 255))
        gray = np.array(Image.alpha_composite(white, src).convert("L"))

    gray = cv2.bilateralFilter(gray, 7, 50, 50)      # smooth noise, keep crisp edges
    gray = cv2.createCLAHE(clipLimit=CLAHE_CLIP,
                           tileGridSize=(8, 8)).apply(gray)
    gray = (255.0 * (gray / 255.0) ** curve).astype("uint8")
    return Image.fromarray(gray)


def to_lines(img, cols=COLS, gamma=GAMMA):
    w, h = img.size
    if CROP_BOTTOM:
        img = img.crop((0, 0, w, int(h * (1 - CROP_BOTTOM))))
        w, h = img.size

    rows = int(cols * (h / w) * ROW_RATIO)
    img = img.resize((cols, rows), Image.LANCZOS)
    if hasattr(img, "get_flattened_data"):
        px = list(img.get_flattened_data())
    else:
        px = list(img.getdata())
    n = len(RAMP)

    out = []
    for r in range(rows):
        out.append("".join(
            RAMP[min(n - 1, int((1 - px[r * cols + c] / 255.0) ** gamma * n))]
            for c in range(cols)
        ).rstrip())

    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def build_svg(lines, cols=COLS):
    pad = 14
    width = int(cols * CHAR_W + pad * 2)
    height = len(lines) * LINE_H + pad * 2

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
         f'height="{height}" viewBox="0 0 {width} {height}" '
         f'font-family="{FAMILY}">',
         f'<style>.a{{fill:{FG_LIGHT}}}.cur{{fill:{CURSOR_LIGHT}}}'
         f'@media(prefers-color-scheme:dark){{.a{{fill:{FG_DARK}}}.cur{{fill:{CURSOR_DARK}}}}}</style>']

    for i, line in enumerate(lines):
        y = pad + i * LINE_H
        begin = f"{i * ROW_DELAY:.2f}s"
        end = f"{(i + 1) * ROW_DELAY:.2f}s"
        w = max(len(line), 1) * CHAR_W
        safe = (line.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))

        p.append(f'<clipPath id="c{i}"><rect x="{pad}" y="{y}" '
                 f'height="{LINE_H}" width="0">'
                 f'<animate attributeName="width" from="0" to="{w:.1f}" '
                 f'begin="{begin}" dur="{ROW_DELAY}s" fill="freeze"/>'
                 f'</rect></clipPath>')
        p.append(f'<g clip-path="url(#c{i})"><text xml:space="preserve" '
                 f'x="{pad}" y="{y + 11.2:.1f}" class="a" '
                 f'font-size="{FONT_SIZE}">{safe}</text></g>')
        # the cursor: a small block riding the wipe edge, gone once the row lands
        p.append(f'<rect y="{y + 1}" width="6" height="12" class="cur" '
                 f'opacity="0">'
                 f'<animate attributeName="x" from="{pad}" to="{pad + w:.1f}" '
                 f'begin="{begin}" dur="{ROW_DELAY}s" fill="freeze"/>'
                 f'<set attributeName="opacity" to="0.85" begin="{begin}"/>'
                 f'<set attributeName="opacity" to="0" begin="{end}"/></rect>')

    p.append("</svg>")
    return "".join(p)


def main():
    default_photo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatar.png")
    default_out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ascii.svg")

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("photo", nargs="?", default=default_photo,
                    help="Path to photo or avatar image (default: scripts/avatar.png)")
    ap.add_argument("out", nargs="?", default=default_out,
                    help="Output SVG path (default: ascii.svg in repo root)")
    ap.add_argument("--crop", help="left,top,right,bottom (e.g. 0,0,388,388)")
    ap.add_argument("--cols", type=int, default=COLS)
    ap.add_argument("--curve", type=float, default=CURVE, help="Darkening exponent")
    ap.add_argument("--rembg", action="store_true", help="Enable neural background removal with rembg")
    ap.add_argument("--no-embed", action="store_true", help="Skip inlining the JetBrains Mono font")
    ap.add_argument("--preview", action="store_true", help="Print ASCII to terminal as well")
    args = ap.parse_args()

    crop = None
    if args.crop:
        parts = [int(v) for v in args.crop.split(",")]
        if len(parts) != 4:
            sys.exit("--crop needs four numbers: left,top,right,bottom")
        crop = tuple(parts)

    lines = to_lines(prep(args.photo, crop, use_rembg=args.rembg, curve=args.curve), cols=args.cols)
    if args.preview:
        print("\n".join(lines))

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_svg(lines, cols=args.cols))
    print(f"wrote {args.out} — {len(lines)} rows, {args.cols} columns")

    if not args.no_embed and embed_font:
        embed_font(args.out)


if __name__ == "__main__":
    main()
