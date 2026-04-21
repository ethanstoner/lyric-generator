from backend.models import (
    SpotifyMetadata, TimedWord, TimedLine,
    TextBlock, FrameInstruction, LibraryEntry, JobStatus
)

def test_spotify_metadata():
    m = SpotifyMetadata(
        track_id="abc123", title="test song", artists=["artist1"],
        duration_ms=180000, album_name="test album",
        album_art_url=None, isrc=None,
    )
    assert m.track_id == "abc123"
    assert m.duration_ms == 180000

def test_timed_line_with_words():
    words = [
        TimedWord(word="hello", start=0.0, end=0.5),
        TimedWord(word="world", start=0.6, end=1.0),
    ]
    line = TimedLine(text="hello world", start=0.0, end=1.0, words=words)
    assert len(line.words) == 2

def test_timed_line_without_words():
    line = TimedLine(text="hello world", start=0.0, end=1.0, words=None)
    assert line.words is None

def test_frame_instruction():
    blocks = [TextBlock(text="hello", x=120, y=640, font_size=48, opacity=255)]
    fi = FrameInstruction(time=1.0, duration=2.0, blocks=blocks, transition="fade_in")
    assert fi.transition == "fade_in"
    assert len(fi.blocks) == 1

def test_library_entry():
    entry = LibraryEntry(
        title="song", artist="artist", audio_path="data/library/song.mp3",
        duration_s=180.0, isrc=None,
    )
    assert entry.duration_s == 180.0

def test_job_status():
    job = JobStatus(job_id="j1", status="pending", progress=0, step="", error=None)
    assert job.status == "pending"
