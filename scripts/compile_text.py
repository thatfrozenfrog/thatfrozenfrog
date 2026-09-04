#!/usr/bin/env python3
"""Generate 4chan-style SVGs for big bold red text and greentext.

GitHub strips inline style="", <font>, and custom tags like <greentext> and <bigred>.
Pre-rendering text into standalone SVGs guarantees authentic 4chan styling with
full dark/light mode responsiveness and inlined monospace fonts.

Generators:
  bigtext_generator(text, font_size=17.0) -> str (SVG)
  greentext_generator(text, font_size=13.0, line_height=20.0) -> str (SVG)
"""
import argparse
import base64
import functools
import os
import sys

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
MONO_FALLBACK = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"


@functools.lru_cache(maxsize=None)
def font_face(filename: str, weight: int) -> str:
    path = os.path.join(FONT_DIR, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return (f"@font-face{{font-family:JBMono;font-style:normal;"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


def font_regular() -> str:
    return font_face("jbmono-400.woff2", 400)


def font_bold() -> str:
    return font_face("jbmono-600.woff2", 600)


def bigtext_generator(text: str, font_size: float = 17.0) -> str:
    """Generate a responsive SVG with classic 4chan big bold red text."""
    FS = font_size
    w = int(len(text) * FS * 0.60 + 16)
    h = 26 if font_size == 17.0 else int(FS * 1.5 + 1)
    y = 19 if font_size == 17.0 else int(FS * 1.12)
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" font-family="JBMono,{MONO_FALLBACK}">',
        f'<style>{font_bold()}',
        '.bf{fill:#AF0A0F;font-weight:700;letter-spacing:0.3px;}',
        '@media(prefers-color-scheme:dark){.bf{fill:#f85149;}}',
        '</style>',
        f'<text x="0" y="{y}" class="bf" font-size="{FS}" font-weight="700">{safe}</text>',
        '</svg>'
    ]
    return "".join(svg)


def greentext_generator(
    text: str | list[str],
    font_size: float = 13.0,
    line_height: float = 20.0
) -> str:
    """Generate a responsive SVG with authentic 4chan monospace greentext.

    Supports single-line string, multi-line string (separated by newline), or list of strings.
    """
    if isinstance(text, str):
        lines = text.splitlines()
    else:
        lines = list(text)

    if not lines:
        lines = [""]

    FS = font_size
    LH = line_height
    max_len = max(len(l) for l in lines)
    w = int(max_len * FS * 0.60 + 16)

    if len(lines) <= 1:
        h = 18
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" font-family="JBMono,{MONO_FALLBACK}">',
            f'<style>{font_regular()}',
            '.gt{fill:#789922;font-weight:400;}',
            '@media(prefers-color-scheme:dark){.gt{fill:#3fb950;}}',
            '</style>'
        ]
        safe = lines[0].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        svg.append(f'<text x="0" y="14" class="gt" font-size="{FS}">{safe}</text>')
    else:
        h = int(len(lines) * LH + 6)
        svg = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" font-family="JBMono,{MONO_FALLBACK}">',
            f'<style>{font_regular()}',
            '.gt{fill:#789922;font-weight:400;}',
            '@media(prefers-color-scheme:dark){.gt{fill:#3fb950;}}',
            '</style>'
        ]
        for i, line in enumerate(lines):
            y = 15 + i * LH
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            svg.append(f'<text x="0" y="{y:.1f}" class="gt" font-size="{FS}">{safe}</text>')

    svg.append('</svg>')
    return "".join(svg)


# Backward-compatible convenience functions
def draw_banned() -> str:
    return bigtext_generator("(USER WAS BANNED FOR THIS POST)")


def draw_itt() -> str:
    return bigtext_generator("ITT we dox thatfrozenfrog o algo assim")


def write_if_changed(path: str, content: str) -> bool:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == content:
                return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def compile_all(out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    targets = {
        "banned.svg": draw_banned(),
        "itt.svg": draw_itt(),
        "ronald.svg": bigtext_generator("RQNVVVVVVVVVVVVLD"),
        "inb4.svg": greentext_generator(">inb4 banned for posting nu-frog and AI giga"),
    }
    changed = []
    for name, svg_data in targets.items():
        dst = os.path.join(out_dir, name)
        if write_if_changed(dst, svg_data):
            changed.append(name)
    return targets, changed


def main():
    default_out = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Generate 4chan-style SVGs for big bold text and greentext.")
    ap.add_argument("--out-dir", default=default_out, help="Output directory for generated SVGs")
    ap.add_argument("--bigtext", help="Generate a big bold red text SVG with the given string")
    ap.add_argument("--greentext", help="Generate a greentext SVG with the given string (use \\n for multiple lines)")
    ap.add_argument("-o", "--output", help="Specific output filename/path when using --bigtext or --greentext")
    args = ap.parse_args()

    if args.bigtext:
        svg_data = bigtext_generator(args.bigtext)
        out_path = args.output or os.path.join(args.out_dir, "bigtext.svg")
        write_if_changed(out_path, svg_data)
        print(f"Generated bigtext SVG: {out_path}")
        return

    if args.greentext:
        raw_text = args.greentext.replace("\\n", "\n")
        svg_data = greentext_generator(raw_text)
        out_path = args.output or os.path.join(args.out_dir, "greentext.svg")
        write_if_changed(out_path, svg_data)
        print(f"Generated greentext SVG: {out_path}")
        return

    targets, changed = compile_all(args.out_dir)
    print(f"Compiled {len(targets)} SVG(s) to: {args.out_dir}")
    if changed:
        print("Updated: " + ", ".join(sorted(changed)))
    else:
        print("Everything up to date.")


if __name__ == "__main__":
    main()


