from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

class Settings(BaseSettings):
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    whisper_model: str = "auto"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"
    whisper_align: bool = True
    whisper_gpu_memory_gb: float = Field(default=0.0)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LIBRARY_DIR = DATA_DIR / "library"
OUTPUTS_DIR = DATA_DIR / "outputs"
TEMP_DIR = DATA_DIR / "temp"
FONT_PATH = PROJECT_ROOT / "fonts" / "Inter-Regular.ttf"

settings = Settings()
