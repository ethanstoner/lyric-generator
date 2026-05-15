from backend.jobs import update_job
from backend.services.spotify import extract_track_id, fetch_metadata
from backend.services.library import scan_library, match_track, save_index
from backend.services.lyrics import get_lyrics
from backend.services.layout import generate_layout
from backend.services.render import render_video
from backend.services.downloader import download_track
from backend.config import LIBRARY_DIR


def run_pipeline(job_id: str, spotify_url: str):
    """Run the full generation pipeline. Called in a background thread."""
    try:
        # Step 1: Spotify metadata
        update_job(job_id, status="fetching_metadata", progress=5, step="Fetching Spotify metadata...")
        track_id = extract_track_id(spotify_url)
        metadata = fetch_metadata(track_id)

        # Step 2: Library match
        update_job(job_id, status="matching_library", progress=10, step="Matching local audio file...")
        index = scan_library(LIBRARY_DIR)
        save_index(index, LIBRARY_DIR)
        match = match_track(metadata, index)

        if match is None:
            # Auto-download via yt-dlp
            update_job(job_id, status="downloading", progress=15, step="Downloading audio...")
            artist = metadata.artists[0] if metadata.artists else "Unknown"
            downloaded = download_track(spotify_url, artist, metadata.title)
            if downloaded is None:
                update_job(job_id, status="error", progress=0, step="Download failed",
                           error=f"Could not download '{metadata.title}' by {', '.join(metadata.artists)}. "
                                 "Try adding the audio file manually to data/library/.")
                return
            # Re-scan library to pick up the new file
            index = scan_library(LIBRARY_DIR)
            save_index(index, LIBRARY_DIR)
            match = match_track(metadata, index)
            if match is None:
                # Match by most recent file as fallback
                from pathlib import Path
                audio_path = str(downloaded)
            else:
                audio_path = match.audio_path
        else:
            audio_path = match.audio_path

        # Step 3: Lyrics
        update_job(job_id, status="fetching_lyrics", progress=25, step="Fetching lyrics and timing...")
        lines = get_lyrics(
            title=metadata.title,
            artist=metadata.artists[0] if metadata.artists else "",
            duration_ms=metadata.duration_ms,
            audio_path=audio_path,
        )

        # Step 4: Layout
        update_job(job_id, status="generating_layout", progress=50, step="Generating lyric layout...")
        total_duration = metadata.duration_ms / 1000.0
        frames = generate_layout(lines, total_duration)

        # Step 5: Render
        update_job(job_id, status="rendering", progress=55, step="Rendering video...")

        def on_progress(pct):
            overall = 55 + int(pct * 0.45)
            update_job(job_id, progress=overall, step=f"Rendering video... {pct}%")

        render_video(frames, audio_path, job_id, on_progress=on_progress)

        update_job(job_id, status="complete", progress=100, step="Done!")

    except Exception as e:
        update_job(job_id, status="error", progress=0, step="Error", error=str(e))
