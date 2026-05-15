import logging

from backend.jobs import update_job
from backend.services.spotify import extract_track_id, fetch_metadata
from backend.services.library import scan_library, match_track, save_index
from backend.services.lyrics import get_lyrics
from backend.services.layout import generate_layout
from backend.services.render import render_video
from backend.services.downloader import download_track
from backend.config import LIBRARY_DIR

logger = logging.getLogger(__name__)


def run_pipeline(job_id: str, spotify_url: str):
    """Run the full generation pipeline. Called in a background thread.

    Every failure path sets the job to status='error' with a user-readable
    message — it never raises out of this function or produces a blank video.
    """
    try:
        # Step 1: Spotify metadata
        update_job(job_id, status="fetching_metadata", progress=5, step="Fetching Spotify metadata...")
        track_id = extract_track_id(spotify_url)
        metadata = fetch_metadata(track_id)
        logger.info("[%s] %s by %s", job_id, metadata.title, ", ".join(metadata.artists))

        # Step 2: Library match (scan once, reuse after download)
        update_job(job_id, status="matching_library", progress=10, step="Matching local audio file...")
        index = scan_library(LIBRARY_DIR)
        save_index(index, LIBRARY_DIR)
        match = match_track(metadata, index)

        if match is None:
            update_job(job_id, status="downloading", progress=15, step="Downloading audio...")
            artist = metadata.artists[0] if metadata.artists else "Unknown"
            downloaded = download_track(spotify_url, artist, metadata.title)
            if downloaded is None:
                update_job(
                    job_id, status="error", progress=0, step="Download failed",
                    error=f"Could not download '{metadata.title}' by "
                          f"{', '.join(metadata.artists)}. See server logs for "
                          "details, or add the audio file manually to data/library/.",
                )
                return
            index = scan_library(LIBRARY_DIR)
            save_index(index, LIBRARY_DIR)
            match = match_track(metadata, index)
            audio_path = match.audio_path if match else str(downloaded)
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
        if not lines:
            update_job(
                job_id, status="error", progress=0, step="No lyrics",
                error=f"No lyrics could be found or transcribed for "
                      f"'{metadata.title}' by {', '.join(metadata.artists)}.",
            )
            return

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
        logger.info("[%s] complete", job_id)

    except Exception as e:
        logger.exception("[%s] pipeline failed", job_id)
        update_job(job_id, status="error", progress=0, step="Error", error=str(e))
