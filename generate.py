"""
Lyric Video Generator
Paste a Spotify link → get an MP4 lyric video.

Usage: python generate.py <spotify_url>
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.services.spotify import extract_track_id, fetch_metadata
from backend.services.library import scan_library, match_track, save_index
from backend.services.downloader import download_track
from backend.services.lyrics import get_lyrics
from backend.services.layout import generate_layout
from backend.services.render import render_video
from backend.config import LIBRARY_DIR, OUTPUTS_DIR


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate.py <spotify_url>")
        sys.exit(1)

    spotify_url = sys.argv[1]

    # 1. Spotify metadata
    print("[1/5] Fetching Spotify metadata...")
    track_id = extract_track_id(spotify_url)
    meta = fetch_metadata(track_id)
    print(f"       {meta.title} by {', '.join(meta.artists)} ({meta.duration_ms // 1000}s)")

    # 2. Find or download audio
    print("[2/5] Looking for local audio...")
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    index = scan_library(LIBRARY_DIR)
    save_index(index, LIBRARY_DIR)
    match = match_track(meta, index)

    if match:
        audio_path = match.audio_path
        print(f"       Found: {audio_path}")
    else:
        print("       Not found locally. Downloading...")
        artist = meta.artists[0] if meta.artists else "Unknown"
        downloaded = download_track(spotify_url, artist, meta.title)
        if downloaded is None:
            print("ERROR: Download failed. Add the audio file manually to data/library/")
            sys.exit(1)
        audio_path = str(downloaded)
        print(f"       Downloaded: {audio_path}")

    # 3. Lyrics + timing
    print("[3/5] Getting lyrics and word timestamps (Whisper)...")
    lines = get_lyrics(
        title=meta.title,
        artist=meta.artists[0] if meta.artists else "",
        duration_ms=meta.duration_ms,
        audio_path=audio_path,
    )
    word_count = sum(len(l.words) for l in lines if l.words)
    print(f"       {len(lines)} lines, {word_count} words with timestamps")

    # 4. Layout
    print("[4/5] Generating lyric layout...")
    total_duration = meta.duration_ms / 1000.0
    frames = generate_layout(lines, total_duration)
    print(f"       {len(frames)} frame instructions")

    # 5. Render
    print("[5/5] Rendering video...")
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{meta.artists[0]} - {meta.title}".replace("/", "-").replace("\\", "-")
    job_id = safe_name

    def on_progress(pct):
        print(f"       {pct}%", end="\r")

    output = render_video(frames, audio_path, job_id, on_progress=on_progress)
    print(f"\nDone! -> {output}")


if __name__ == "__main__":
    main()
