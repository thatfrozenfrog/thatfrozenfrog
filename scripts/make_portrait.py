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
import base64
import math
import os
import random
import sys

import cv2
import numpy as np
from PIL import Image, ImageFont

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


def font_embedded():
    font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "jbmono-400.woff2")
    if not os.path.exists(font_path):
        return ""
    with open(font_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return (f"@font-face{{font-family:JBMono;font-style:normal;"
            f"font-weight:400;font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


def build_3d_frames(path, cols=56, rows=32, total_frames=24):
    """Generate 3D rotated ASCII frames of the avatar with dynamic depth and lighting."""
    img = Image.open(path).convert("L")
    arr = np.array(img)
    arr = cv2.bilateralFilter(arr, 7, 50, 50)
    arr = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(arr)

    # Normalize ink
    ink_map = (255.0 - arr.astype(float)) / 255.0
    ink_map = np.clip((ink_map - 0.08) / 0.88, 0.0, 1.0)
    ink_map = ink_map ** 1.25

    H_img, W_img = ink_map.shape
    gx = cv2.Sobel(ink_map, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(ink_map, cv2.CV_64F, 0, 1, ksize=3)

    CHAR_ASPECT = 0.50
    frames = []

    for fi in range(total_frames):
        phase = 2 * math.pi * (fi / total_frames)
        yaw_deg = 24.0 * math.sin(phase)
        pitch_deg = 6.0 * math.cos(phase)
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)

        # 3D orbiting directional light
        light_angle = phase + math.pi / 4
        lx = math.sin(light_angle) * 0.5
        ly = -0.3
        lz = math.cos(light_angle) * 0.5 + 0.6
        l_norm = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / l_norm, ly / l_norm, lz / l_norm

        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)

        char_buf = [[" "] * cols for _ in range(rows)]
        R = 1.05
        scan_row = 2 + int((fi / total_frames) * (rows - 5))

        for r in range(2, rows - 2):
            sy_norm = (r - rows / 2) / (rows / 2)
            for c in range(2, cols - 2):
                sx_norm = (c - cols / 2) / (cols / 2) * (cols / rows * CHAR_ASPECT)

                if abs(sx_norm) <= R:
                    z_cyl = math.sqrt(max(0, R * R - sx_norm * sx_norm))

                    # Inverse pitch
                    x0 = sx_norm
                    y0 = sy_norm * cp + z_cyl * sp
                    z0 = -sy_norm * sp + z_cyl * cp

                    # Inverse yaw
                    x_world = x0 * cy - z0 * sy
                    z_world = x0 * sy + z0 * cy
                    y_world = y0

                    phi = math.atan2(x_world, z_world)
                    u = 0.50 + phi / (math.pi * 0.78)
                    v = 0.42 + y_world * 0.54

                    if 0.0 <= u < 1.0 and 0.0 <= v < 1.0:
                        px_x = int(u * (W_img - 1))
                        px_y = int(v * (H_img - 1))
                        ink = ink_map[px_y, px_x]

                        # 3D Normal with surface relief
                        nx = (x_world / R) - gx[px_y, px_x] * 0.8
                        ny = -gy[px_y, px_x] * 0.8
                        nz = z_world / R
                        n_len = math.sqrt(nx * nx + ny * ny + nz * nz)
                        nx, ny, nz = nx / n_len, ny / n_len, nz / n_len

                        # Rotate normal to camera space
                        nx_c = nx * cy + nz * sy
                        nz_c = -nx * sy + nz * cy
                        ny_c = ny * cp - nz_c * sp
                        nz_c = ny * sp + nz_c * cp

                        dot = max(0.0, nx_c * lx + ny_c * ly + nz_c * lz)
                        val = ink * (0.65 + 0.35 * dot)

                        # Subtle sci-fi scanline beam
                        if r == scan_row:
                            val = min(1.0, val + 0.15)

                        if val > 0.05:
                            idx = min(len(RAMP) - 1, int(val * len(RAMP)))
                            char_buf[r][c] = RAMP[idx]

        # Top & Bottom 3D emitter arch
        arch_w = min(40, cols - 16)
        arch_start = (cols - arch_w) // 2
        for i in range(arch_w):
            c_pos = arch_start + i
            if i == 0 or i == arch_w - 1:
                char_buf[1][c_pos] = "."
                char_buf[rows - 2][c_pos] = "'"
            else:
                char_buf[1][c_pos] = "-"
                char_buf[rows - 2][c_pos] = "."

        # Live telemetry header and footer
        rot_str = f"{yaw_deg:+05.1f}*"
        header = f"+--[ 3D YOTSUBA // YAW: {rot_str} ]"
        header = header + "-" * (cols - len(header) - 1) + "+"
        for c in range(min(cols, len(header))):
            char_buf[0][c] = header[c]

        footer = "+--[ 3D HOLOGRAM // 4CHAN TECH LAB // 12FPS ]"
        footer = footer + "-" * (cols - len(footer) - 1) + "+"
        for c in range(min(cols, len(footer))):
            char_buf[rows - 1][c] = footer[c]

        for r in range(1, rows - 1):
            char_buf[r][0] = "|"
            char_buf[r][cols - 1] = "|"

        lines = ["".join(row) for row in char_buf]
        frames.append(lines)

    return frames


def build_3d_svg(frames, cols=56, fps=12):
    """Assemble frames into an infinite-looping SMIL + CSS step-animated SVG."""
    rows = len(frames[0])
    char_w = 7.74
    line_h = 15.0
    font_size = 12.9
    pad = 12

    width = int(cols * char_w + pad * 2)
    frame_h = int(rows * line_h + pad * 2)
    total_h = frame_h * len(frames)
    duration = len(frames) / fps
    smil_values = "; ".join(f"0 {-i * frame_h}" for i in range(len(frames)))

    font_css = font_embedded()

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{frame_h}" '
        f'viewBox="0 0 {width} {frame_h}" fill="none" font-family="JBMono,{FAMILY}">',
        f'<style>',
        font_css,
        f'@keyframes spin3d {{',
        f'  0% {{ transform: translateY(0); }}',
        f'  100% {{ transform: translateY(-{total_h}px); }}',
        f'}}',
        f'.filmstrip {{ animation: spin3d {duration:.2f}s steps({len(frames)}) infinite; }}',
        f'.holo {{ fill: {FG_LIGHT}; font-size: {font_size}px; }}',
        f'.hud {{ fill: {CURSOR_LIGHT}; font-weight: 700; font-size: {font_size}px; }}',
        f'@media(prefers-color-scheme: dark) {{',
        f'  .holo {{ fill: {FG_DARK}; }}',
        f'  .hud {{ fill: {CURSOR_DARK}; }}',
        f'}}',
        f'</style>',
        f'<clipPath id="vp"><rect x="0" y="0" width="{width}" height="{frame_h}" /></clipPath>',
        f'<g clip-path="url(#vp)">',
        f'<g class="filmstrip">',
        f'<animateTransform attributeName="transform" type="translate" values="{smil_values}" calcMode="discrete" dur="{duration:.2f}s" repeatCount="indefinite" />',
    ]

    for fi, frame in enumerate(frames):
        fy = fi * frame_h
        for li, line in enumerate(frame):
            y = fy + pad + (li + 1) * line_h - 3.2
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            cls = "hud" if (li == 0 or li == len(frame) - 1) else "holo"
            svg.append(f'<text x="{pad}" y="{y:.1f}" class="{cls}" xml:space="preserve">{safe}</text>')

    svg.append('</g></g></svg>')
    return "".join(svg)


def generate_cyber_sjis_svg(art_path, out_path, font_path=None):
    """Generate borderless cyberpunk Matrix rain + ASCII scanlines + ASCII glitch SVG from Shift-JIS art."""
    with open(art_path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("cp932")
    except Exception:
        text = raw.decode("shift_jis", errors="replace")

    # Map double vertical line to U+2225 present in IPAMona font
    text = text.replace("\u2016", "\u2225")
    lines = text.splitlines()

    if font_path is None:
        saitamaar = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Saitamaar.woff2")
        ipamona = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "ipamona-subset.woff2")
        font_path = saitamaar if os.path.exists(saitamaar) else ipamona

    font_name = "Saitamaar" if "saitamaar" in os.path.basename(font_path).lower() else "IPAMona"

    font_b64 = ""
    if os.path.exists(font_path):
        with open(font_path, "rb") as f:
            font_b64 = base64.b64encode(f.read()).decode("ascii")

    # Measure exact visual dimensions dynamically from art content
    try:
        font_measurer = ImageFont.truetype(font_path, 16)
        max_line_w = max((font_measurer.getbbox(l.rstrip())[2] for l in lines if l.strip()), default=400)
    except Exception:
        import unicodedata
        max_line_w = max(
            (sum(2 if unicodedata.east_asian_width(c) in ('F', 'W') else 0.5 for c in l.rstrip()) * 8.5 for l in lines if l.strip()),
            default=400
        )

    line_h = 18.2
    pad_x = 8
    pad_y = 10
    width = max(int(max_line_w + pad_x * 2), 200)
    height = max(int(len(lines) * line_h + pad_y * 2), 100)
    art_top = pad_y
    art_left = pad_x

    # 1. Matrix digital rain: columns dynamically scaled to artwork width
    cols_count = max(int(width / 23), 12)
    col_spacing = width / cols_count

    matrix_glyphs = [
        "ｦ", "ｧ", "ｨ", "ｩ", "ｪ", "ｫ", "ｬ", "ｭ", "ｮ", "ｯ", "ｰ",
        "ｱ", "ｲ", "ｳ", "ｴ", "ｵ", "ｶ", "ｷ", "ｸ", "ｹ", "ｺ",
        "ｻ", "ｼ", "ｽ", "ｾ", "ｿ", "ﾀ", "ﾁ", "ﾂ", "ﾃ", "ﾄ",
        "ﾅ", "ﾆ", "ﾇ", "ﾈ", "ﾉ", "ﾊ", "ﾋ", "ﾌ", "ﾍ", "ﾎ",
        "ﾏ", "ﾐ", "ﾑ", "ﾒ", "ﾓ", "ﾔ", "ﾕ", "ﾖ", "ﾗ", "ﾘ", "ﾙ", "ﾚ", "ﾛ", "ﾜ", "ﾝ",
        "0", "1", "2", "3", "4", "5", "7", "8", "9", "A", "B", "E", "F", "X", "Z"
    ]

    random.seed(42)
    matrix_streams = []

    for c in range(cols_count):
        x = int(c * col_spacing + col_spacing / 2)
        stream_len = random.randint(14, 24)
        dur = round(random.uniform(3.4, 6.2), 2)
        delay = round(random.uniform(-6.5, 0.0), 2)

        chars = [random.choice(matrix_glyphs) for _ in range(stream_len)]
        tspans = []
        for i, ch in enumerate(chars):
            dist = (stream_len - 1) - i
            cls = "th" if dist == 0 else ("t1" if dist < 3 else ("t2" if dist < 6 else ("t3" if dist < 12 else "t4")))
            y_offset = i * 16
            tspans.append(f'<tspan class="{cls}" x="{x}" y="{y_offset}">{ch}</tspan>')

        col_content = "".join(tspans)
        matrix_streams.append(
            f'<g class="mcol" style="animation-duration:{dur}s;animation-delay:{delay}s;">'
            f'<text class="mtxt" xml:space="preserve">{col_content}</text></g>'
        )

    matrix_svg_group = "\n        ".join(matrix_streams)

    # 2. ASCII static scanlines (subtle horizontal dashes)
    ascii_scanlines = []
    scan_step = 9.0
    total_scan_lines = int(height / scan_step)
    dash_count = int(width / 6.0) + 1
    dash_str = "- " * dash_count
    for i in range(total_scan_lines):
        y = int(i * scan_step)
        ascii_scanlines.append(f'<tspan x="0" y="{y}">{dash_str}</tspan>')
    ascii_scanlines_content = "".join(ascii_scanlines)

    # 3. Sweeping ASCII scan beam (fine terminal hairline + subtle phosphor dots)
    beam_dot = "· " * (int(width / 6.0) + 1)
    beam_line = "─" * (int(width / 7.5) + 2)
    ascii_beam = f'''
    <g class="scan-beam">
        <text class="beam-1" x="0" y="4" xml:space="preserve">{beam_dot}</text>
        <text class="beam-3" x="0" y="14" xml:space="preserve">{beam_line}</text>
        <text class="beam-1" x="0" y="24" xml:space="preserve">{beam_dot}</text>
    </g>'''

    # 4. Master text lines directly from art file
    text_lines_xml = []
    for i, line in enumerate(lines):
        y = art_top + i * line_h + 13.0
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text_lines_xml.append(f'<tspan x="{art_left}" y="{y:.1f}">{safe}</tspan>')
    lain_text_content = "".join(text_lines_xml)

    # 5. ASCII Glitch corruption bursts
    slice1_y = int(height * 0.35)
    slice2_y = int(height * 0.65)
    glitch_corrupt_lines = [
        f'<tspan x="{int(width*0.05)}" y="{slice1_y}">░▒▓_#!%?=/*[]~#0x7F!~+=-;*!&amp;^$@░▒▓</tspan>',
        f'<tspan x="{int(width*0.05)}" y="{slice1_y + 16}">/QA/ WIN SWEDISH WIN::7F4C//&gt;&gt;KKKQLYMV SQQN.&lt;&lt;</tspan>',
        f'<tspan x="{int(width*0.1)}" y="{slice2_y}">░░░%%$$###!!!??///===++~--___</tspan>',
        f'<tspan x="{int(width*0.05)}" y="{slice2_y + 16}">&gt;&gt;&gt;&gt;&gt;&gt;ADMIN THREMBO WILL TAKE OVER THE WORLD&lt;&lt;&lt;&lt;&lt;&lt;</tspan>'
    ]
    ascii_glitch_content = "".join(glitch_corrupt_lines)

    font_face_css = ""
    if font_b64:
        font_face_css = f"""
            @font-face {{
                font-family: '{font_name}';
                font-style: normal;
                font-weight: 400;
                font-display: block;
                src: url('data:font/woff2;base64,{font_b64}') format('woff2');
            }}"""

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" style="overflow:hidden;">
    <defs>
        <style><![CDATA[{font_face_css}

            /* Matrix Rain Falling */
            @keyframes mfall {{
                0%   {{ transform: translateY(-380px); }}
                100% {{ transform: translateY({height + 40}px); }}
            }}
            .mcol {{
                animation-name: mfall;
                animation-iteration-count: infinite;
                animation-timing-function: linear;
            }}
            .mtxt {{
                font-family: '{font_name}', 'IPAMona', monospace;
                font-size: 13px;
            }}
            .th {{ fill: #b8ffce; opacity: 0.95; font-weight: bold; }}
            .t1 {{ fill: #00ff66; opacity: 0.75; }}
            .t2 {{ fill: #00cc55; opacity: 0.45; }}
            .t3 {{ fill: #008833; opacity: 0.25; }}
            .t4 {{ fill: #004d1c; opacity: 0.12; }}

            /* Sweeping ASCII Scan Beam */
            .scan-beam {{
                font-family: '{font_name}', 'IPAMona', monospace;
                font-size: 10px;
                letter-spacing: 1px;
            }}
            .beam-1 {{ fill: #00ff66; opacity: 0.20; font-size: 8px; letter-spacing: 1px; }}
            .beam-3 {{ fill: #a6ffc9; opacity: 0.80; font-size: 11px; filter: drop-shadow(0 0 3px #00ff66); }}

            /* 1-char Horizontal Displacement under Scanline */
            .scan-displaced-slice {{
                fill: #39ff14;
                filter: drop-shadow(0 0 3px #00ff66);
            }}

            /* Static ASCII Background Scanlines */
            .ascii-scanlines {{
                font-family: '{font_name}', 'IPAMona', monospace;
                font-size: 7px;
                fill: #00aa44;
                opacity: 0.12;
                letter-spacing: 0.5px;
            }}

            /* Glitch Keyframes */
            @keyframes glitch-main {{
                0%, 14.8%, 17.2%, 70.8%, 72.8%, 100% {{
                    transform: translate(0, 0);
                    filter: drop-shadow(0 0 1px #00ff66) drop-shadow(0 0 5px rgba(0,255,102,0.45));
                }}
                15% {{
                    transform: translate(-3px, 1px);
                }}
                15.8% {{
                    transform: translate(2px, -1px);
                    filter: drop-shadow(0 0 4px #00ff66) drop-shadow(0 0 8px #39ff14);
                }}
                16.6% {{
                    transform: translate(-1px, 2px);
                }}
                17% {{
                    transform: translate(0, 0);
                }}
                71% {{
                    transform: translate(3px, 1px);
                }}
                71.8% {{
                    transform: translate(-3px, -1px);
                }}
                72.4% {{
                    transform: translate(1px, 1px);
                }}
            }}

            @keyframes glitch-cyan {{
                0%, 14.8%, 17.2%, 70.8%, 72.8%, 100% {{
                    opacity: 0;
                    transform: translate(0, 0);
                }}
                15% {{
                    opacity: 0.75;
                    transform: translate(-5px, -1px);
                }}
                15.8% {{
                    opacity: 0.9;
                    transform: translate(-7px, 1px);
                }}
                16.6% {{
                    opacity: 0.4;
                    transform: translate(-2px, 0);
                }}
                71% {{
                    opacity: 0.8;
                    transform: translate(-5px, 2px);
                }}
                71.8% {{
                    opacity: 0.6;
                    transform: translate(-3px, -1px);
                }}
            }}

            @keyframes glitch-red {{
                0%, 14.8%, 17.2%, 70.8%, 72.8%, 100% {{
                    opacity: 0;
                    transform: translate(0, 0);
                }}
                15% {{
                    opacity: 0.75;
                    transform: translate(5px, 1px);
                }}
                15.8% {{
                    opacity: 0.85;
                    transform: translate(7px, -1px);
                }}
                16.6% {{
                    opacity: 0.35;
                    transform: translate(2px, 0);
                }}
                71% {{
                    opacity: 0.8;
                    transform: translate(5px, -1px);
                }}
                71.8% {{
                    opacity: 0.5;
                    transform: translate(3px, 1px);
                }}
            }}

            @keyframes slice-shift-1 {{
                0%, 14.8%, 16.8%, 100% {{
                    transform: translate(0, 0);
                }}
                15% {{
                    transform: translate(6px, 0);
                }}
                15.8% {{
                    transform: translate(-5px, 0);
                }}
                16.4% {{
                    transform: translate(3px, 0);
                }}
            }}

            @keyframes slice-shift-2 {{
                0%, 70.8%, 72.6%, 100% {{
                    transform: translate(0, 0);
                }}
                71% {{
                    transform: translate(-7px, 0);
                }}
                71.8% {{
                    transform: translate(6px, 0);
                }}
                72.3% {{
                    transform: translate(-3px, 0);
                }}
            }}

            @keyframes ascii-corrupt {{
                0%, 14.8%, 16.8%, 70.8%, 72.6%, 100% {{
                    opacity: 0;
                    display: none;
                }}
                15%, 16.4% {{
                    opacity: 0.9;
                    display: block;
                    transform: translate(4px, 0);
                }}
                71%, 72.2% {{
                    opacity: 0.85;
                    display: block;
                    transform: translate(-4px, 0);
                }}
            }}

            .g-main {{
                animation: glitch-main 4.8s infinite;
                fill: #14ff70;
            }}
            .g-cyan {{
                animation: glitch-cyan 4.8s infinite;
                fill: #00f3ff;
            }}
            .g-red {{
                animation: glitch-red 4.8s infinite;
                fill: #ff0055;
            }}
            .slice-1 {{
                animation: slice-shift-1 4.8s infinite;
                fill: #14ff70;
            }}
            .slice-2 {{
                animation: slice-shift-2 4.8s infinite;
                fill: #14ff70;
            }}
            .ascii-glitch-overlay {{
                animation: ascii-corrupt 4.8s infinite;
                font-family: '{font_name}', 'IPAMona', monospace;
                font-size: 15px;
                font-weight: bold;
                fill: #ff2a6d;
                filter: drop-shadow(0 0 3px #00f3ff);
            }}

            .aa-text {{
                font-family: '{font_name}', 'IPAMona', 'Mona', 'MS PGothic', 'IPAMonaGothic', monospace, sans-serif;
                font-size: 16px;
                line-height: 18.2px;
                letter-spacing: 0px;
                white-space: pre;
            }}

            /* Light mode adaptation */
            @media (prefers-color-scheme: light) {{
                .g-main {{ fill: #0e6328; filter: none; }}
                .scan-displaced-slice {{ fill: #083c17; filter: none; }}
                .slice-1, .slice-2 {{ fill: #0e6328; }}
                .th {{ fill: #083c17; opacity: 0.95; }}
                .t1 {{ fill: #0e6328; opacity: 0.75; }}
                .t2 {{ fill: #1a7f37; opacity: 0.45; }}
                .t3 {{ fill: #2da44e; opacity: 0.25; }}
                .t4 {{ fill: #57ab5a; opacity: 0.15; }}
                .ascii-scanlines {{ fill: #1a7f37; opacity: 0.12; }}
                .beam-1 {{ fill: #1a7f37; opacity: 0.20; }}
                .beam-3 {{ fill: #083c17; opacity: 0.75; filter: none; }}
            }}
        ]]></style>

        <!-- Scanline Displacement Masks: masks main art and shifts slice by 1 char -->
        <mask id="mask-main">
            <rect x="0" y="0" width="100%" height="100%" fill="#fff" />
            <rect x="0" y="-50" width="100%" height="24" fill="#000">
                <animate attributeName="y" from="-50" to="{height + 40}" dur="4.8s" repeatCount="indefinite" />
            </rect>
        </mask>
        <mask id="mask-slice">
            <rect x="0" y="-50" width="100%" height="24" fill="#fff">
                <animate attributeName="y" from="-50" to="{height + 40}" dur="4.8s" repeatCount="indefinite" />
            </rect>
        </mask>

        <clipPath id="clip-slice-1">
            <rect x="0" y="{slice1_y - 20}" width="{width}" height="60" />
        </clipPath>
        <clipPath id="clip-slice-2">
            <rect x="0" y="{slice2_y - 20}" width="{width}" height="60" />
        </clipPath>

        <g id="art-master">
            <text class="aa-text" xml:space="preserve">{lain_text_content}</text>
        </g>
    </defs>

    <!-- 1. Static ASCII Background Scanlines -->
    <text class="ascii-scanlines" xml:space="preserve">{ascii_scanlines_content}</text>

    <!-- 2. Animated Matrix Digital Rain -->
    <g id="matrix-rain" opacity="0.60">
        {matrix_svg_group}
    </g>

    <!-- 3. Glitch Chromatic Aberration Layers -->
    <use href="#art-master" class="g-cyan" opacity="0" />
    <use href="#art-master" class="g-red" opacity="0" />

    <!-- 4. Main Foreground Art (masked where scan beam passes) -->
    <g mask="url(#mask-main)">
        <use href="#art-master" class="g-main" />
    </g>

    <!-- 5. Scanline Displaced Slice (shifted 1 char as beam sweeps) -->
    <g mask="url(#mask-slice)" transform="translate(30, 0)">
        <use href="#art-master" class="scan-displaced-slice" />
    </g>

    <!-- 6. Horizontal Slice Glitches -->
    <g clip-path="url(#clip-slice-1)" class="slice-1">
        <use href="#art-master" />
    </g>
    <g clip-path="url(#clip-slice-2)" class="slice-2">
        <use href="#art-master" />
    </g>

    <!-- 7. ASCII Glitch Corrupt Text Bursts -->
    <g class="ascii-glitch-overlay" opacity="0">
        <text xml:space="preserve">{ascii_glitch_content}</text>
    </g>

    <!-- 8. Sweeping ASCII Scan Beam -->
    <g class="scan-beam">
        <animateTransform attributeName="transform" type="translate" from="0 -50" to="0 {height + 40}" dur="4.8s" repeatCount="indefinite" />
        {ascii_beam}
    </g>
</svg>'''

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg)
    return out_path


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_dir = os.path.dirname(script_dir)
    default_art = os.path.join(script_dir, "art.txt")
    default_photo = os.path.join(script_dir, "avatar.png")
    default_out = os.path.join(repo_dir, "ascii.svg")

    if os.path.exists(default_art):
        default_input = default_art
        default_mode = "cyber"
    else:
        default_input = default_photo
        default_mode = "3d"

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("photo", nargs="?", default=default_input,
                    help="Path to art text or avatar image (default: scripts/art.txt)")
    ap.add_argument("out", nargs="?", default=default_out,
                    help="Output SVG path (default: ascii.svg in repo root)")
    ap.add_argument("--mode", choices=["cyber", "3d", "2d"], default=default_mode,
                    help="Render mode: cyber (Shift-JIS Matrix glitch terminal, default), 3d, or 2d")
    ap.add_argument("--fps", type=int, default=12, help="Animation framerate for 3D mode (default: 12)")
    ap.add_argument("--frames", type=int, default=24, help="Total frames for 3D loop (default: 24)")
    ap.add_argument("--crop", help="left,top,right,bottom (e.g. 0,0,388,388)")
    ap.add_argument("--cols", type=int, default=56)
    ap.add_argument("--curve", type=float, default=CURVE, help="Darkening exponent")
    ap.add_argument("--rembg", action="store_true", help="Enable neural background removal with rembg")
    ap.add_argument("--no-embed", action="store_true", help="Skip inlining the font")
    ap.add_argument("--preview", action="store_true", help="Print ASCII to terminal as well")
    args = ap.parse_args()

    # Automatically detect Shift-JIS / text file inputs
    if args.photo.endswith(".txt") or (args.mode == "cyber" and os.path.exists(args.photo)):
        out_file = generate_cyber_sjis_svg(args.photo, args.out)
        print(f"wrote {out_file} — Cyberpunk Shift-JIS Matrix Glitch terminal ({os.path.getsize(out_file)} bytes)")
        return

    crop = None
    if args.crop:
        parts = [int(v) for v in args.crop.split(",")]
        if len(parts) != 4:
            sys.exit("--crop needs four numbers: left,top,right,bottom")
        crop = tuple(parts)

    if args.mode == "3d":
        cols = args.cols
        frames = build_3d_frames(args.photo, cols=cols, rows=32, total_frames=args.frames)
        if args.preview:
            print("\n".join(frames[0]))

        svg_data = build_3d_svg(frames, cols=cols, fps=args.fps)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(svg_data)
        print(f"wrote {args.out} — {len(frames)} frames of 3D ASCII animation ({cols} cols, {args.fps} FPS)")
    else:
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

