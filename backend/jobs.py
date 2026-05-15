import threading
import time
import uuid
from backend.models import JobStatus
from backend.config import settings

_lock = threading.Lock()
_jobs: dict[str, JobStatus] = {}
_created: dict[str, float] = {}

_TTL_SECONDS = max(settings.job_ttl_hours, 1) * 3600


def _prune_locked() -> None:
    """Drop jobs older than the TTL. Caller must hold _lock."""
    cutoff = time.monotonic() - _TTL_SECONDS
    stale = [jid for jid, ts in _created.items() if ts < cutoff]
    for jid in stale:
        _jobs.pop(jid, None)
        _created.pop(jid, None)


def create_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _prune_locked()
        _jobs[job_id] = JobStatus(
            job_id=job_id, status="pending", progress=0, step="Queued", error=None
        )
        _created[job_id] = time.monotonic()
    return job_id


def update_job(job_id: str, status: str = None, progress: int = None, step: str = None, error: str = None):
    with _lock:
        if job_id not in _jobs:
            return
        job = _jobs[job_id]
        if status is not None:
            job.status = status
        if progress is not None:
            job.progress = progress
        if step is not None:
            job.step = step
        if error is not None:
            job.error = error


def get_job(job_id: str) -> JobStatus | None:
    with _lock:
        return _jobs.get(job_id)
