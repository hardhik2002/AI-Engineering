from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MediaAsset(BaseModel):
    media_id: str
    original_filename: str
    media_type: Literal["image", "video"]
    detected_mime_type: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    file_size_bytes: int = Field(gt=0)
    duration_ms: int | None = None
    frame_rate: float | None = None
    video_codec: str | None = None
    playback_compatibility: Literal["likely", "uncertain"] | None = None
    created_at: datetime
    sha256: str
    thumbnail_available: bool


class MediaLimits(BaseModel):
    max_image_bytes: int
    max_video_bytes: int
    max_video_duration_ms: int
    max_image_pixels: int


class ApiErrorDetail(BaseModel):
    code: str
    message: str


class ApiError(BaseModel):
    error: ApiErrorDetail
