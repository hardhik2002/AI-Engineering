from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VISIONLAB_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:5180,http://127.0.0.1:5180"
    database_url: str = "sqlite:///./visionlab.db"
    inference_device: Literal["cpu", "cuda"] = "cpu"
    media_root: Path = Path("data/media")
    thumbnail_root: Path = Path("data/thumbnails")
    max_image_bytes: int = Field(default=20 * 1024 * 1024, gt=0)
    max_video_bytes: int = Field(default=250 * 1024 * 1024, gt=0)
    max_video_duration_ms: int = Field(default=10 * 60 * 1000, gt=0)
    max_image_pixels: int = Field(default=40_000_000, gt=0)
    ffprobe_binary: str = "ffprobe"
    ffmpeg_binary: str = "ffmpeg"
    probe_timeout_seconds: int = Field(default=15, gt=0, le=120)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Phase 2 requires a sqlite:/// database URL")
        return Path(self.database_url.removeprefix(prefix))


@lru_cache
def get_settings() -> Settings:
    return Settings()

