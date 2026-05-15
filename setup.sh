#!/bin/bash
set -e
PYTHON="<home>/AppData/Local/Programs/Python/Python312/python.exe"

# Create venv
$PYTHON -m venv venv
source venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt

# Download Inter font if not present
if [ ! -f "fonts/Inter-Regular.ttf" ]; then
    mkdir -p fonts
    curl -L -o /tmp/inter.zip \
        "https://github.com/rsms/inter/releases/download/v4.1/Inter-4.1.zip"
    unzip -j /tmp/inter.zip "*/Inter-Regular.ttf" -d fonts/ 2>/dev/null || \
    unzip -j /tmp/inter.zip "Inter-Regular.ttf" -d fonts/ 2>/dev/null
    rm -f /tmp/inter.zip
    if ! python -c "from PIL import ImageFont; ImageFont.truetype('fonts/Inter-Regular.ttf', 48)" 2>/dev/null; then
        echo "WARNING: Font extraction failed. Download Inter manually from https://rsms.me/inter/ and place Inter-Regular.ttf in fonts/"
    else
        echo "Downloaded Inter-Regular.ttf"
    fi
fi

# Verify ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "WARNING: ffmpeg not found on PATH. Install it before rendering."
fi

echo "Setup complete. Activate venv with: source venv/Scripts/activate"
echo "Run server with: uvicorn backend.main:app --reload --port 8000"
