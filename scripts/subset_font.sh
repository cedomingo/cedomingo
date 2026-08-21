#!/usr/bin/env bash
# Subsets JetBrains Mono into tiny per-role woff2 files, then base64s them
# into fonts/*.b64 so generate_stats.py / make_ascii_svg.py can inline a
# <style> @font-face data URI directly into each SVG.
#
# JetBrains Mono is SIL OFL and uses 600/1000 units per em — exactly the
# CHAR_W=7.74 / FONT_SIZE=12.9 the portrait grid in make_ascii_svg.py
# assumes, so no geometry changes are needed.
#
# Run this once locally (not in CI — it needs the source TTF, which this
# repo does not vendor to keep it small):
#
#   1. Download JetBrainsMono-Regular.ttf from
#      https://github.com/JetBrains/JetBrainsMono/releases  (OFL-1.1)
#   2. Drop it next to this script as fonts/JetBrainsMono-Regular.ttf
#   3. Run: bash scripts/subset_font.sh
#
# Output: fonts/ramp.woff2 (13 ramp chars, ~1.3KB), fonts/headings.woff2
# (letters used in heading SVGs), fonts/basic-latin.woff2 (data graphics).
# Ship fonts/OFL.txt alongside — the license must travel with the font.

set -euo pipefail
cd "$(dirname "$0")/.."

SRC="fonts/JetBrainsMono-Regular.ttf"
if [ ! -f "$SRC" ]; then
  echo "missing $SRC — see comments at the top of this script" >&2
  exit 1
fi

pip install --quiet fonttools brotli

RAMP_CHARS=' .`:-=+*cs#%@'
HEADING_TEXT="$(cat <<'EOF2'
abcdefghijklmnopqrstuvwxyz0123456789 &-.:'
EOF2
)"

pyftsubset "$SRC" --text="${RAMP_CHARS}" \
  --flavor=woff2 --layout-features='' --no-hinting -o fonts/ramp.woff2

pyftsubset "$SRC" --text="${HEADING_TEXT}" \
  --flavor=woff2 --layout-features='' --no-hinting -o fonts/headings.woff2

pyftsubset "$SRC" --unicodes="U+0020-007E" \
  --flavor=woff2 --layout-features='' --no-hinting -o fonts/basic-latin.woff2

for f in ramp headings basic-latin; do
  base64 -w0 "fonts/$f.woff2" > "fonts/$f.b64"
  echo "fonts/$f.woff2 -> fonts/$f.b64 ($(du -h fonts/$f.woff2 | cut -f1))"
done

echo "done. inline fonts/*.b64 into each SVG's <style> as:"
echo '  @font-face{font-family:"JBMono";src:url(data:font/woff2;base64,<contents>) format("woff2")}'
