import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.config import OUTPUTS_DIR, LIBRARY_DIR, PROJECT_ROOT
from backend.jobs import create_job, get_job
from backend.pipeline import run_pipeline
from backend.services.library import scan_library

_queue: asyncio.Queue = asyncio.Queue()


async def _job_worker():
    while True:
        job_id, spotify_url = await _queue.get()
        try:
            await asyncio.to_thread(run_pipeline, job_id, spotify_url)
        except Exception:
            pass
        _queue.task_done()


@asynccontextmanager
async def lifespan(app: FastAPI):
    worker = asyncio.create_task(_job_worker())
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    yield
    worker.cancel()


app = FastAPI(title="Lyric Video Generator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = PROJECT_ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


class GenerateRequest(BaseModel):
    spotify_url: str


class GenerateResponse(BaseModel):
    job_id: str


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    job_id = create_job()
    await _queue.put((job_id, req.spotify_url))
    return GenerateResponse(job_id=job_id)


@app.get("/api/status/{job_id}")
async def status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/download/{job_id}")
async def download(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "complete":
        raise HTTPException(status_code=400, detail=f"Job not complete: {job.status}")
    output_path = OUTPUTS_DIR / f"{job_id}.mp4"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    return FileResponse(
        str(output_path), media_type="video/mp4",
        filename=f"lyric-video-{job_id}.mp4",
    )


@app.get("/api/library")
async def library():
    index = scan_library(LIBRARY_DIR)
    return {"songs": [e.model_dump() for e in index.entries]}


@app.post("/api/library/rescan")
async def rescan():
    from backend.services.library import save_index
    index = scan_library(LIBRARY_DIR)
    save_index(index, LIBRARY_DIR)
    return {"songs": len(index.entries)}


@app.get("/")
async def root():
    index_path = frontend_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Lyric Video Generator API"}
