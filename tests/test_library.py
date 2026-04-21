import json
import pytest
from pathlib import Path
from backend.services.library import normalize_text, scan_library, match_track, LibraryIndex
from backend.models import SpotifyMetadata

def test_normalize_text():
    assert normalize_text("Hello, World!") == "hello world"
    assert normalize_text("  The   Weeknd  ") == "the weeknd"
    assert normalize_text("Don't") == "dont"

def test_scan_empty_library(tmp_path):
    index = scan_library(tmp_path)
    assert len(index.entries) == 0

def test_scan_library_with_mp3(tmp_path):
    fake_mp3 = tmp_path / "Artist Name - Song Title.mp3"
    fake_mp3.write_bytes(b"\x00" * 100)
    index = scan_library(tmp_path)
    assert len(index.entries) == 1
    entry = index.entries[0]
    assert "song title" in entry.title.lower()
    assert "artist name" in entry.artist.lower()

def test_match_track_by_title_artist(tmp_path):
    fake_mp3 = tmp_path / "The Weeknd - Blinding Lights.mp3"
    fake_mp3.write_bytes(b"\x00" * 100)
    index = scan_library(tmp_path)
    meta = SpotifyMetadata(
        track_id="abc", title="Blinding Lights", artists=["The Weeknd"],
        duration_ms=200000, album_name="After Hours",
        album_art_url=None, isrc=None,
    )
    result = match_track(meta, index)
    assert result is not None
    assert "blinding" in result.title.lower()

def test_match_track_no_match(tmp_path):
    index = scan_library(tmp_path)
    meta = SpotifyMetadata(
        track_id="abc", title="Nonexistent Song", artists=["Nobody"],
        duration_ms=200000, album_name="Nothing",
        album_art_url=None, isrc=None,
    )
    result = match_track(meta, index)
    assert result is None
