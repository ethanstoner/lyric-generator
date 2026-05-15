import logging
import os
import subprocess
from pathlib import Path
from backend.config import LIBRARY_DIR

logger = logging.getLogger(__name__)


def download_track(spotify_url: str, artist: str, title: str) -> Path | None:
    """Download audio via yt-dlp (YouTube search from Spotify metadata).
    Returns path to downloaded MP3 file."""
    # Add deno to PATH for yt-dlp JS runtime
    deno_path = Path.home() / ".deno" / "bin"
    env = os.environ.copy()
    if deno_path.exists():
        env["PATH"] = str(deno_path) + os.pathsep + env.get("PATH", "")

    search_query = f"ytsearch1:{artist} {title}"
    output_template = str(LIBRARY_DIR / f"{artist} - {title}.%(ext)s")

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-x", "--audio-format", "mp3", "--audio-quality", "0",
                "--remote-components", "ejs:github",
                "-o", output_template,
                search_query,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )

        expected_path = LIBRARY_DIR / f"{artist} - {title}.mp3"
        if expected_path.exists():
            return expected_path

        # Fallback: find most recent mp3
        mp3s = sorted(LIBRARY_DIR.glob("*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
        if mp3s:
            return mp3s[0]

        logger.error(
            "yt-dlp produced no mp3 for '%s - %s'. exit=%s stderr=%s",
            artist, title, result.returncode, (result.stderr or "")[-800:],
        )
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found on PATH — cannot download audio.")
        return None
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp timed out downloading '%s - %s'.", artist, title)
        return None
    except Exception as e:
        logger.error("Unexpected download error for '%s - %s': %s", artist, title, e)
        return None
