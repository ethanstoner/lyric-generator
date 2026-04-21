import pytest
from backend.services.spotify import extract_track_id, fetch_metadata

def test_extract_track_id_standard_url():
    url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
    assert extract_track_id(url) == "4cOdK2wGLETKBW3PvgPWqT"

def test_extract_track_id_with_query():
    url = "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=abc123"
    assert extract_track_id(url) == "4cOdK2wGLETKBW3PvgPWqT"

def test_extract_track_id_uri():
    url = "spotify:track:4cOdK2wGLETKBW3PvgPWqT"
    assert extract_track_id(url) == "4cOdK2wGLETKBW3PvgPWqT"

def test_extract_track_id_invalid():
    with pytest.raises(ValueError):
        extract_track_id("https://open.spotify.com/album/abc123")

def test_extract_track_id_garbage():
    with pytest.raises(ValueError):
        extract_track_id("not a url")

def test_fetch_metadata_real():
    meta = fetch_metadata("0VjIjW4GlUZAMYd2vXMi3b")
    assert meta.track_id == "0VjIjW4GlUZAMYd2vXMi3b"
    assert "Blinding Lights" in meta.title or "blinding" in meta.title.lower()
    assert meta.duration_ms > 0
    assert len(meta.artists) > 0
