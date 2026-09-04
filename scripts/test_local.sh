#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_DIR="$(dirname "$DIR")"

echo "========================================================"
echo "    /g/ - thatfrozenfrog Profile Generator & Tester     "
echo "========================================================"
echo ""

# 1. Avatar ASCII Generation
IMAGE_INPUT="${1:-$DIR/avatar.png}"
echo "--> [1/4] Generating ascii.svg from $IMAGE_INPUT ..."
uv run "$DIR/make_portrait.py" "$IMAGE_INPUT" "$REPO_DIR/ascii.svg"

# 2. Styled Text SVGs Generation
echo ""
echo "--> [2/4] Generating banned notice SVG (banned.svg) ..."
uv run "$DIR/compile_text.py" --out-dir "$REPO_DIR"

# 3. Stats SVGs Generation
echo ""
echo "--> [3/4] Generating stats SVGs (Yotsuba B palette) ..."
uv run "$DIR/generate_stats.py" --out-dir "$REPO_DIR"

# 4. Summary & Preview
echo ""
echo "--> [4/4] Generated SVGs in $REPO_DIR:"
ls -lh "$REPO_DIR"/*.svg

echo ""
echo "✓ All graphics refreshed successfully!"
echo "To preview the 4chan thread layout in your browser:"
echo "  xdg-open \"$DIR/preview.html\""
