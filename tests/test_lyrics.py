import pytest
from backend.services.lyrics import parse_lrc, fetch_lrclib

def test_parse_lrc_basic():
    lrc = "[00:12.40]so emotional\n[00:14.05]you know i'm\n[00:15.50]not able"
    lines = parse_lrc(lrc)
    assert len(lines) == 3
    assert lines[0].text == "so emotional"
    assert abs(lines[0].start - 12.4) < 0.01
    assert lines[1].text == "you know i'm"

def test_parse_lrc_empty():
    lines = parse_lrc("")
    assert lines == []

def test_parse_lrc_skips_non_lyric():
    lrc = "[ti:Song Title]\n[ar:Artist]\n[00:05.00]actual lyric"
    lines = parse_lrc(lrc)
    assert len(lines) == 1
    assert lines[0].text == "actual lyric"

def test_parse_lrc_end_times():
    lrc = "[00:10.00]line one\n[00:13.00]line two\n[00:16.00]line three"
    lines = parse_lrc(lrc)
    assert abs(lines[0].end - 13.0) < 0.01
    assert abs(lines[1].end - 16.0) < 0.01
    assert lines[2].end > lines[2].start

@pytest.mark.live
def test_fetch_lrclib_real():
    result = fetch_lrclib("Blinding Lights", "The Weeknd", 200)
    if result is not None:
        synced, plain = result
        assert synced is not None or plain is not None
