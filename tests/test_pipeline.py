"""Integration tests for the job pipeline and worker resilience.

These mock all external I/O (Spotify, lyrics, render) and assert that
failure paths produce a clear job error instead of a crash, a wedged
queue, or a silently-blank video.
"""
import asyncio
import types

import pytest

import backend.pipeline as pipeline
import backend.main as main
from backend.jobs import create_job, get_job
from backend.models import SpotifyMetadata


def _fake_meta():
    return SpotifyMetadata(
        track_id="x" * 22, title="Test Song", artists=["Tester"],
        duration_ms=180000, album_name="Album", album_art_url=None, isrc=None,
    )


@pytest.fixture
def stub_pipeline(monkeypatch):
    """Stub everything up to (but not including) get_lyrics/render."""
    monkeypatch.setattr(pipeline, "extract_track_id", lambda url: "x" * 22)
    monkeypatch.setattr(pipeline, "fetch_metadata", lambda tid: _fake_meta())
    monkeypatch.setattr(pipeline, "scan_library", lambda d: types.SimpleNamespace(entries=[]))
    monkeypatch.setattr(pipeline, "save_index", lambda idx, d: None)
    monkeypatch.setattr(
        pipeline, "match_track",
        lambda meta, idx: types.SimpleNamespace(audio_path="fake.mp3"),
    )


def test_empty_lyrics_sets_error_and_skips_render(stub_pipeline, monkeypatch):
    """No lyrics must fail the job with a clear message, not render a blank video."""
    monkeypatch.setattr(pipeline, "get_lyrics", lambda **kw: [])

    render_called = False

    def fake_render(*a, **k):
        nonlocal render_called
        render_called = True

    monkeypatch.setattr(pipeline, "render_video", fake_render)

    job_id = create_job()
    pipeline.run_pipeline(job_id, "spotify:track:" + "x" * 22)

    job = get_job(job_id)
    assert job.status == "error"
    assert "lyrics" in job.error.lower()
    assert render_called is False


def test_pipeline_exception_becomes_job_error(stub_pipeline, monkeypatch):
    """An unexpected failure mid-pipeline is caught and reported, not raised."""
    def boom(**kw):
        raise RuntimeError("whisper exploded")

    monkeypatch.setattr(pipeline, "get_lyrics", boom)

    job_id = create_job()
    pipeline.run_pipeline(job_id, "spotify:track:" + "x" * 22)  # must not raise

    job = get_job(job_id)
    assert job.status == "error"
    assert "whisper exploded" in job.error


def test_worker_continues_after_a_crashing_job(monkeypatch):
    """One job crashing must not kill the worker or wedge the queue."""
    processed = []

    def fake_run(job_id, url):
        processed.append(job_id)
        if url == "crash":
            raise RuntimeError("dispatch failure")

    monkeypatch.setattr(main, "run_pipeline", fake_run)

    async def scenario():
        q = asyncio.Queue()
        monkeypatch.setattr(main, "_queue", q)
        worker = asyncio.create_task(main._job_worker())

        bad = create_job()
        good = create_job()
        await q.put((bad, "crash"))
        await q.put((good, "ok"))
        await asyncio.wait_for(q.join(), timeout=5)

        worker.cancel()
        return bad, good

    bad, good = asyncio.run(scenario())

    # Both jobs were processed despite the first one crashing.
    assert bad in processed and good in processed
    assert get_job(bad).status == "error"
    assert "dispatch failure" in get_job(bad).error
