from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.vision import BoundingBox

CaptionMode = Literal["short", "detailed", "extended"]
CaptionTask = Literal["short", "detailed", "extended", "dense", "selected_object"]


class CaptionRequest(BaseModel):
    mode: CaptionMode = "short"


class DescribeObjectRequest(BaseModel):
    detection_analysis_id: str
    detection_id: str


class CaptionModelInfo(BaseModel):
    provider: Literal["transformers"] = "transformers"
    checkpoint: str
    revision: str
    device: str
    package_version: str


class CaptionRegion(BaseModel):
    id: str
    description: str = Field(min_length=1)
    bounding_box: BoundingBox
    model: CaptionModelInfo


class CaptionRecord(BaseModel):
    analysis_id: str
    media_id: str
    task: CaptionTask
    status: Literal["completed"] = "completed"
    created_at: datetime
    completed_at: datetime
    model: CaptionModelInfo
    duration_ms: float = Field(ge=0)
    model_load_ms: float = Field(ge=0)
    inference_ms: float = Field(ge=0)
    text: str | None = None
    regions: list[CaptionRegion] = Field(default_factory=list)
    detection_analysis_id: str | None = None
    detection_id: str | None = None
