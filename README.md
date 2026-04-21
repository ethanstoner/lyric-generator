# Lyric Generator

Generate brat-style lyric videos from a Spotify track link.

This project runs a local FastAPI app with a small frontend. You paste a Spotify track URL, the backend fetches track metadata, finds or downloads audio, gets lyrics, records a white brat-style video in Chromium with Playwright, and exports an `.mp4`.

## What It Does

- Accepts a Spotify track URL
- Fetches song metadata with the Spotify API
- Reuses local audio from `data/library/` when available
- Falls back to `yt-dlp` to download audio if no local match is found
- Fetches synced lyrics from LRCLIB when possible
- Optionally uses WhisperX for better lyric timing if installed
- Records the lyric animation in a browser and muxes it with the song using `ffmpeg`

## Stack

- Python 3.10+
- FastAPI + Uvicorn
- Static frontend in `frontend/`
- Playwright for browser recording
- `ffmpeg` for final video encoding
- `yt-dlp` for download fallback

## Prerequisites

Install these before running the app:

- Python 3.10 or newer
- `ffmpeg` available on your `PATH`
- `yt-dlp` available on your `PATH` if you want automatic audio downloads
- Chromium browser binaries for Playwright via `python -m playwright install chromium`

You also need Spotify API credentials:

1. Create an app at the Spotify Developer Dashboard.
2. Copy the client ID and client secret.
3. Put them in your local `.env`.

## Spotify API Tutorial

This project does not use a Spotify "bot token". It uses standard Spotify API app credentials: a `client_id` and `client_secret`.

1. Go to `https://developer.spotify.com/dashboard`.
2. Log in with your Spotify account.
3. Click `Create app`.
4. Enter any app name and description you want.
5. Accept Spotify's terms and create the app.
6. Open the app you just created.
7. Copy the `Client ID`.
8. Click `View client secret` and copy the `Client Secret`.
9. Create a local `.env` from `.env.example`.
10. Paste both values into `.env`.

Example:

```env
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

These values stay local on the machine running the app. Do not commit them to GitHub.

## Setup

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
Copy-Item .env.example .env
```

### macOS / Linux / Git Bash

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env
```

Then edit `.env`:

```env
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
WHISPER_MODEL=auto
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
WHISPER_ALIGN=true
WHISPER_GPU_MEMORY_GB=0
```

### Recommended `.env` values by hardware

Lower-end machines can use more conservative settings to avoid memory errors:

```env
WHISPER_MODEL=tiny
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_ALIGN=false
```

Balanced default:

```env
WHISPER_MODEL=auto
WHISPER_DEVICE=auto
WHISPER_COMPUTE_TYPE=auto
WHISPER_ALIGN=true
WHISPER_GPU_MEMORY_GB=0
```

Notes:

- `WHISPER_DEVICE=auto` picks `cuda` when available, otherwise `cpu`.
- `WHISPER_MODEL=auto` now chooses `tiny`, `base`, or `small` based on detected GPU VRAM and system RAM.
- `WHISPER_COMPUTE_TYPE=auto` picks a lighter `int8` mode on smaller GPUs and `float16` on roomier GPUs.
- `WHISPER_GPU_MEMORY_GB=0` means auto-detect VRAM. You can set a number manually if detection is wrong on a specific machine.
- On very small GPUs, auto mode will prefer CPU over unstable CUDA runs.
- If CUDA still runs out of memory, the app now retries WhisperX work on CPU automatically.
- `WHISPER_ALIGN=false` disables the WhisperX alignment pass and uses LRCLIB line timing only, which is slower to degrade in quality but much easier on weak hardware.

## Running The App

Start the API and frontend together with Uvicorn:

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000`.

On Windows, you can also use [`start.bat`](./start.bat) after creating the virtual environment and installing dependencies.

## How The Pipeline Works

1. `backend/services/spotify.py` validates the Spotify URL and fetches track metadata.
2. `backend/services/library.py` scans `data/library/` for a matching local audio file.
3. `backend/services/downloader.py` uses `yt-dlp` if no local match is found.
4. `backend/services/lyrics.py` fetches LRCLIB lyrics and optionally aligns them with WhisperX.
5. [`generate_brat.py`](./generate_brat.py) records the animated text in Playwright.
6. `ffmpeg` combines the recorded video with the audio into `data/outputs/`.

## Project Layout

```text
backend/         FastAPI app, pipeline, models, services
frontend/        Static UI served by FastAPI
data/library/    Local source audio files
data/outputs/    Generated mp4 files
data/temp/       Temporary recording artifacts
tests/           Basic test coverage
generate_brat.py Browser recording script
```

## Notes On Dependencies

- `ffmpeg` is required for final `.mp4` output.
- `yt-dlp` is optional but strongly recommended. Without it, users must place audio files in `data/library/` manually.
- WhisperX is not installed by `requirements.txt`. The app will still run without it, but lyric timing may be less accurate and fallback behavior is more limited when LRCLIB has no lyrics.
- The included `openai-whisper` package is separate from WhisperX.
- Whisper runtime settings can now be controlled through `.env` for safer low-memory setups.

## Running Tests

```bash
pytest
```

Some tests hit live external services, so they may fail without network access or valid Spotify credentials.

## Publishing To GitHub

Before pushing:

- Keep your real `.env` out of git
- Do not commit `credentials.json`
- Do not commit generated media from `data/outputs/` or source audio in `data/library/`
- Make sure your repository contains `.env.example`, `README.md`, and the updated `.gitignore`

Recommended first push:

```bash
git init
git add README.md .gitignore .env.example backend frontend tests requirements.txt setup.sh start.bat generate.py generate_brat.py zotify_login.py data docs fonts
git commit -m "Prepare lyric generator for GitHub"
```

## Known Limitations

- This is designed to run locally, not as a stateless cloud deployment.
- Background jobs are in-memory only, so restarting the server loses job status.
- The video recorder depends on the current bratgenerator.com page structure.
- Output filenames are generated from song metadata and may be long.
