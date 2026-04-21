#!/bin/bash
set -e

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "Python was not found on PATH."
    exit 1
fi

"$PYTHON_BIN" -m venv venv

if [ -f "venv/Scripts/activate" ]; then
    # Git Bash / Windows venv layout
    source venv/Scripts/activate
else
    source venv/bin/activate
fi

python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "WARNING: ffmpeg not found on PATH. Install it before rendering videos."
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
    echo "WARNING: yt-dlp not found on PATH. Auto-download fallback will not work."
fi

echo "Setup complete."
echo "Copy .env.example to .env and add your Spotify API credentials."
echo "Run the app with: python -m uvicorn backend.main:app --reload --port 8000"
