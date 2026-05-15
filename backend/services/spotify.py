import logging
import re
from urllib.parse import urlparse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from backend.config import settings
from backend.models import SpotifyMetadata

logger = logging.getLogger(__name__)

_sp: spotipy.Spotify | None = None

def _get_client() -> spotipy.Spotify:
    global _sp
    if _sp is None:
        if not settings.spotify_client_id or not settings.spotify_client_secret:
            raise RuntimeError(
                "Spotify credentials missing. Set SPOTIFY_CLIENT_ID and "
                "SPOTIFY_CLIENT_SECRET in your .env file."
            )
        auth_manager = SpotifyClientCredentials(
            client_id=settings.spotify_client_id,
            client_secret=settings.spotify_client_secret,
        )
        _sp = spotipy.Spotify(auth_manager=auth_manager)
    return _sp

def extract_track_id(url: str) -> str:
    uri_match = re.match(r"spotify:track:([a-zA-Z0-9]{22})", url.strip())
    if uri_match:
        return uri_match.group(1)
    parsed = urlparse(url.strip())
    if parsed.netloc == "open.spotify.com" and parsed.path.startswith("/track/"):
        track_id = parsed.path.split("/track/")[1].split("/")[0]
        if re.match(r"^[a-zA-Z0-9]{22}$", track_id):
            return track_id
    raise ValueError(f"Invalid Spotify track URL: {url}")

def fetch_metadata(track_id: str) -> SpotifyMetadata:
    sp = _get_client()
    try:
        track = sp.track(track_id)
    except spotipy.SpotifyException as e:
        logger.error("Spotify API error for track %s: %s", track_id, e)
        if e.http_status == 401:
            raise RuntimeError("Spotify authentication failed — check your credentials.") from e
        if e.http_status == 404:
            raise RuntimeError(f"Spotify track not found: {track_id}") from e
        if e.http_status == 429:
            raise RuntimeError("Spotify rate limit hit — try again shortly.") from e
        raise RuntimeError(f"Spotify API error: {e}") from e
    except Exception as e:
        logger.error("Could not reach Spotify: %s", e)
        raise RuntimeError(f"Could not reach Spotify: {e}") from e
    isrc = None
    external_ids = track.get("external_ids", {})
    if "isrc" in external_ids:
        isrc = external_ids["isrc"]
    album = track.get("album", {})
    images = album.get("images", [])
    album_art_url = images[0]["url"] if images else None
    return SpotifyMetadata(
        track_id=track_id,
        title=track["name"],
        artists=[a["name"] for a in track["artists"]],
        duration_ms=track["duration_ms"],
        album_name=album.get("name", ""),
        album_art_url=album_art_url,
        isrc=isrc,
    )
