from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    whisper_model: str = "base"
    # "" lets whisper auto-select (CUDA if available, else CPU). Set to
    # "cpu" or "cuda" to force.
    whisper_device: str = ""
    # Hours before a finished/failed job is pruned from memory.
    job_ttl_hours: int = 24

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LIBRARY_DIR = DATA_DIR / "library"
OUTPUTS_DIR = DATA_DIR / "outputs"
TEMP_DIR = DATA_DIR / "temp"
FONT_PATH = PROJECT_ROOT / "fonts" / "Inter-Regular.ttf"

settings = Settings()
