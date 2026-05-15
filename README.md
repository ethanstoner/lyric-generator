# Lyric Generator

Generate brat-style lyric videos from a Spotify track link.

This project runs a local FastAPI app with a small frontend. You paste a
Spotify track URL; the backend fetches track metadata, finds or downloads
audio, transcribes word-level lyric timing with Whisper (LRCLIB as fallback),
renders the animated text to frames with Pillow, and muxes them with the song
using `ffmpeg` into an `.mp4`.

## What It Does

- Accepts a Spotify track URL
- Fetches song metadata with the Spotify API
- Reuses local audio from `data/library/` when available
- Falls back to `yt-dlp` to download audio if no local match is found
- Transcribes word-level lyric timing with `openai-whisper`
- Falls back to LRCLIB synced/plain lyrics if Whisper fails
- Renders lyric frames with Pillow and encodes the video with `ffmpeg`

## Stack

- Python 3.10+
- FastAPI + Uvicorn
- Static frontend in `frontend/`
- `openai-whisper` for word-level lyric timing
- Pillow for frame rendering
- `ffmpeg` for final video encoding
- `yt-dlp` for download fallback

## Prerequisites

- Python 3.10 or newer
- `ffmpeg` available on your `PATH`
- `yt-dlp` available on your `PATH` if you want automatic audio downloads
- Spotify API credentials (client ID + secret)

## Spotify API Tutorial

This project uses standard Spotify API app credentials: a `client_id` and
`client_secret` (not a "bot token").

1. Go to `https://developer.spotify.com/dashboard`.
2. Log in with your Spotify account.
3. Click `Create app`.
4. Enter any app name and description.
5. Accept Spotify's terms and create the app.
6. Open the app and copy the `Client ID`.
7. Click `View client secret` and copy the `Client Secret`.
8. Create a local `.env` from `.env.example` and paste both values.

```env
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

These values stay local. Do not commit them to GitHub.

## Setup

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

### macOS / Linux / Git Bash

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env`:

```env
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
# tiny | base | small | medium | large-v3
WHISPER_MODEL=base
# blank = auto-select (CUDA if available, else CPU); or force cpu / cuda
WHISPER_DEVICE=
# prune finished/failed jobs from memory after this many hours
JOB_TTL_HOURS=24
```

Smaller `WHISPER_MODEL` values (`tiny`, `base`) are faster and lighter on
memory; larger ones are more accurate but need more RAM/VRAM. Whisper
downloads the chosen model on first run.

## Running The App

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Open `http://localhost:8000`. On Windows you can also use
[`start.bat`](./start.bat) after creating the venv and installing deps.

### CLI

```bash
python generate.py <spotify_url>
```

## How The Pipeline Works

1. `backend/services/spotify.py` validates the Spotify URL and fetches metadata.
2. `backend/services/library.py` scans `data/library/` for a matching local file.
3. `backend/services/downloader.py` uses `yt-dlp` if no local match is found.
4. `backend/services/lyrics.py` transcribes word-level timing with Whisper,
   falling back to LRCLIB synced/plain lyrics if Whisper fails.
5. `backend/services/layout.py` lays out the lyric frames.
6. `backend/services/render.py` renders frames with Pillow and `ffmpeg`
   combines them with the audio into `data/outputs/`.

The web app (`backend/main.py`) wraps this in an in-memory job queue;
`generate.py` runs the same pipeline from the CLI.

## Project Layout

```text
backend/         FastAPI app, pipeline, models, services
frontend/        Static UI served by FastAPI
data/library/    Local source audio files
data/outputs/    Generated mp4 files
data/temp/       Temporary render artifacts
tests/           Test coverage
generate.py      CLI entry point (same pipeline as the web app)
```

## Notes On Dependencies

- `ffmpeg` is required for final `.mp4` output. The job fails with a clear
  message if it is missing from `PATH`.
- `yt-dlp` is optional but strongly recommended. Without it, place audio files
  in `data/library/` manually.
- Whisper (`openai-whisper`) provides word-level timing. If it fails, the app
  falls back to LRCLIB synced lyrics, then LRCLIB plain lyrics.

## Running Tests

```bash
pytest
```

Some tests hit live external services and may fail without network access or
valid Spotify credentials.

## Publishing To GitHub

- Keep your real `.env` out of git
- Do not commit `credentials.json` or `.cache` (auth tokens)
- Do not commit generated media from `data/outputs/` or audio in `data/library/`
- Ensure the repo contains `.env.example`, `README.md`, and `.gitignore`

## Known Limitations

- Designed to run locally, not as a stateless cloud deployment.
- Background jobs are in-memory only; restarting the server loses job status.
  Jobs are pruned after `JOB_TTL_HOURS`.
- Output filenames are generated from song metadata and may be long.
