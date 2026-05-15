import threading
import uuid
from backend.models import JobStatus

_lock = threading.Lock()
_jobs: dict[str, JobStatus] = {}

def create_job() -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = JobStatus(
            job_id=job_id, status="pending", progress=0, step="Queued", error=None
        )
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
