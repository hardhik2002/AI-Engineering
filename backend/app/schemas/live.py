"""Version 1 live-camera binary frame and result contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.vision import DetectedObject, ModelInfo


class LiveFrameMetadata(BaseModel):
    type: Literal["frame.submitted"]
    session_id: UUID
    frame_id: UUID
    captured_at_ms: float = Field(ge=0, le=1e15, allow_inf_nan=False)
    source_width: int = Field(ge=1)
    source_height: int = Field(ge=1)
    encoded_format: Literal["jpeg"]


class LiveFrameResult(BaseModel):
    type: Literal["frame.result"] = "frame.result"
    protocol_version: Literal[1] = 1
    session_id: UUID
    frame_id: UUID
    captured_at_ms: float
    source_width: int
    source_height: int
    detections: list[DetectedObject]
    model: ModelInfo
    inference_ms: float = Field(ge=0)
    processing_ms: float = Field(ge=0)
    result_at: datetime
    outcome: Literal["processed"] = "processed"
