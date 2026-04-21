from pydantic import BaseModel

class SpotifyMetadata(BaseModel):
    track_id: str
    title: str
    artists: list[str]
    duration_ms: int
    album_name: str
    album_art_url: str | None = None
    isrc: str | None = None

class TimedWord(BaseModel):
    word: str
    start: float
    end: float

class TimedLine(BaseModel):
    text: str
    start: float
    end: float
    words: list[TimedWord] | None = None

class TextBlock(BaseModel):
    text: str
    x: int
    y: int
    font_size: int
    opacity: int  # 0-255

class FrameInstruction(BaseModel):
    time: float
    duration: float
    blocks: list[TextBlock]
    transition: str  # "fade_in" | "cut" | "fade_out"

class LibraryEntry(BaseModel):
    title: str
    artist: str
    audio_path: str
    duration_s: float
    isrc: str | None = None

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: int  # 0-100
    step: str
    error: str | None = None
    filename: str | None = None
