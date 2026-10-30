from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="VISIONLAB_", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_console_enabled: bool = True
    log_file_enabled: bool = True
    log_format: Literal["pretty", "json"] = "pretty"
    log_directory: Path = Path("data/logs")
    log_file_max_mb: int = Field(default=10, ge=1, le=100)
    log_file_backup_count: int = Field(default=5, ge=1, le=20)
    log_request_id_enabled: bool = True
    log_slow_request_ms: int = Field(default=1000, ge=1, le=600_000)
    log_health_requests: bool = False
    log_inference_details: bool = True
    log_colors: Literal["auto", "always", "never"] = "auto"
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
    model_root: Path = Path("data/models")
    detection_model: Literal["yolo26n.pt"] = "yolo26n.pt"
    detection_device: Literal["auto", "cpu", "cuda"] = "auto"
    detection_confidence: float = Field(default=0.25, gt=0, le=1)
    detection_iou: float = Field(default=0.45, ge=0, le=1)
    detection_image_size: int = Field(default=640, ge=160, le=1280)
    detection_max_detections: int = Field(default=100, ge=1, le=300)
    detection_concurrency: int = Field(default=1, ge=1, le=4)
    detection_max_source_side: int = Field(default=2048, ge=640, le=8192)
    florence_checkpoint: str = "florence-community/Florence-2-base-ft"
    florence_revision: str = "0b03b6f15a4a211370fb204aee4e7dd48887ea37"
    florence_device: Literal["auto", "cpu", "cuda"] = "cpu"
    florence_max_new_tokens: int = Field(default=512, ge=32, le=1024)
    florence_num_beams: int = Field(default=1, ge=1, le=4)
    florence_max_regions: int = Field(default=30, ge=1, le=100)
    florence_max_source_side: int = Field(default=2048, ge=640, le=4096)

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
