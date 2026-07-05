#!/usr/bin/env bash
# Build GarminCoach.app for macOS (unsigned). Run from the repo root:
#   ./packaging/build_mac.sh
# Output: dist/GarminCoach.app  (zip it and send to a friend)
set -euo pipefail
cd "$(dirname "$0")/.."

PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"

echo "→ installing build + runtime deps…"
$PY -m pip install -q -r requirements.txt pyinstaller

echo "→ building GarminCoach.app…"
$PY -m PyInstaller packaging/GarminCoach.spec --noconfirm --clean

echo
echo "✓ Built dist/GarminCoach.app"
echo "  First launch on another Mac: right-click the app → Open (unsigned app)."
echo "  To share: zip it →  ditto -c -k --keepParent dist/GarminCoach.app GarminCoach.zip"
