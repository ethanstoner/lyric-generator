from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    spotify_client_id: str = ""
    spotify_client_secret: str = ""
    whisper_model: str = "base"

    class Config:
        env_file = ".env"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LIBRARY_DIR = DATA_DIR / "library"
OUTPUTS_DIR = DATA_DIR / "outputs"
TEMP_DIR = DATA_DIR / "temp"
FONT_PATH = PROJECT_ROOT / "fonts" / "Inter-Regular.ttf"

settings = Settings()
