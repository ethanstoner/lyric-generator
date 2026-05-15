#!/usr/bin/env bash
# Bootstrap a local dev environment.
#   bash setup.sh                # core + Whisper (full functionality)
#   bash setup.sh --no-whisper   # skip the heavy torch/Whisper stack
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python

EXTRAS=".[whisper,test]"
if [ "${1:-}" = "--no-whisper" ]; then
    EXTRAS=".[test]"
fi

echo "Creating virtual environment (venv/) ..."
"$PYTHON" -m venv venv

# Resolve the venv python cross-platform (POSIX: bin, Windows: Scripts).
if [ -x "venv/bin/python" ]; then
    VENV_PY="venv/bin/python"
else
    VENV_PY="venv/Scripts/python.exe"
fi

echo "Installing dependencies ($EXTRAS) ..."
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -e "$EXTRAS"

# The bundled font (fonts/Inter-Regular.ttf) ships with the repo — no download.
if ! "$VENV_PY" -c "from PIL import ImageFont; ImageFont.truetype('fonts/Inter-Regular.ttf', 48)" 2>/dev/null; then
    echo "WARNING: fonts/Inter-Regular.ttf missing or unreadable."
fi

command -v ffmpeg >/dev/null 2>&1 || echo "WARNING: ffmpeg not found on PATH — required for rendering."

cat <<'EOF'

Setup complete.
  Activate:  source venv/bin/activate   (Windows: venv\Scripts\activate)
  Run web:   uvicorn backend.main:app --reload --port 8000
  Run CLI:   python generate.py <spotify_url>
  Test:      pytest -m "not live"
EOF
