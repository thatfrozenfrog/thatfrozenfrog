#!/usr/bin/env python3
"""Pre-render the 4chan admin notice into a responsive SVG.

GitHub strips inline style="", <font>, and custom tags like <bigred>.
Pre-rendering (USER WAS BANNED FOR THIS POST) into an SVG guarantees
authentic 4chan bold red styling with full dark/light mode responsiveness.

Outputs:
  banned.svg          Admin stamp: (USER WAS BANNED FOR THIS POST)
"""
import argparse
import base64
import functools
import os
import sys

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
MONO_FALLBACK = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"


@functools.lru_cache(maxsize=None)
def font_bold():
    path = os.path.join(FONT_DIR, "jbmono-600.woff2")
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return (f"@font-face{{font-family:JBMono;font-style:normal;"
            f"font-weight:600;font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


def draw_banned():
    """Big bold red text: (USER WAS BANNED FOR THIS POST)."""
    text = "(USER WAS BANNED FOR THIS POST)"
    FS = 17
    w, h = int(len(text) * FS * 0.60 + 16), 26
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" font-family="JBMono,{MONO_FALLBACK}">',
        f'<style>{font_bold()}',
        '.bf{fill:#AF0A0F;font-weight:700;letter-spacing:0.3px;}',
        '@media(prefers-color-scheme:dark){.bf{fill:#f85149;}}',
        '</style>',
        f'<text x="0" y="19" class="bf" font-size="{FS}" font-weight="700">{text}</text>',
        '</svg>'
    ]
    return "".join(svg)

def draw_itt():
    """Big bold red text: (USER WAS BANNED FOR THIS POST)."""
    text = "ITT we dox thatfrozenfrog o algo assim"
    FS = 17
    w, h = int(len(text) * FS * 0.60 + 16), 26
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none" font-family="JBMono,{MONO_FALLBACK}">',
        f'<style>{font_bold()}',
        '.bf{fill:#AF0A0F;font-weight:700;letter-spacing:0.3px;}',
        '@media(prefers-color-scheme:dark){.bf{fill:#f85149;}}',
        '</style>',
        f'<text x="0" y="19" class="bf" font-size="{FS}" font-weight="700">{text}</text>',
        '</svg>'
    ]
    return "".join(svg)

def write_if_changed(path, content):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == content:
                return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def compile_all(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    targets = {
        "banned.svg": draw_banned(),
        "itt.svg": draw_itt(),
    }
    changed = []
    for name, svg_data in targets.items():
        dst = os.path.join(out_dir, name)
        if write_if_changed(dst, svg_data):
            changed.append(name)
    return targets, changed


def main():
    default_out = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Compile banned notice into responsive SVG.")
    ap.add_argument("--out-dir", default=default_out, help="Output directory for generated SVG")
    args = ap.parse_args()

    targets, changed = compile_all(args.out_dir)
    print(f"Compiled {len(targets)} SVG(s) to: {args.out_dir}")
    if changed:
        print("Updated: " + ", ".join(sorted(changed)))
    else:
        print("Everything up to date.")


if __name__ == "__main__":
    main()

