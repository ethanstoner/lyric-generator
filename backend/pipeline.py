import re
import asyncio
from backend.jobs import update_job
from backend.services.spotify import extract_track_id, fetch_metadata
from backend.services.library import scan_library, match_track, save_index
from backend.services.lyrics import get_lyrics
from backend.services.downloader import download_track
from backend.config import LIBRARY_DIR, OUTPUTS_DIR


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

        # Step 4: Record brat video via bratgenerator.com
        update_job(job_id, status="recording", progress=40, step="Recording brat-style video...")

        total_duration = metadata.duration_ms / 1000.0

        # Build proper filename: "Title - Artist #hashtags.mp4"
        artist = metadata.artists[0] if metadata.artists else "Unknown"
        artist_tag = re.sub(r'[^a-zA-Z0-9]', '', artist).lower()
        safe_title = metadata.title.replace("/", "-").replace("\\", "-")
        safe_artist = " & ".join(metadata.artists).replace("/", "-").replace("\\", "-")
        filename = f"{safe_title} - {safe_artist} #musicvibes #lyricssong #slowedaudios #audios #{artist_tag}"
        output_path = OUTPUTS_DIR / f"{filename}.mp4"

        def on_progress(pct):
            overall = 40 + int(pct * 0.60)
            update_job(job_id, progress=overall, step=f"Recording video... {pct}%")

        # Import and run the brat recorder (bratgenerator.com via Playwright)
        from generate_brat import record_brat_video
        asyncio.run(record_brat_video(lines, audio_path, output_path, total_duration, on_progress=on_progress))

        # Store the filename so download endpoint can find it
        update_job(job_id, status="complete", progress=100, step="Done!", filename=filename)

    except Exception as e:
        update_job(job_id, status="error", progress=0, step="Error", error=str(e))
