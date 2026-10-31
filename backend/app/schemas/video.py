"""Typed contracts for sampled video analysis and job lifecycle."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.caption import CaptionModelInfo
from app.schemas.multimodal import TokenUsage, VQAConversation
from app.schemas.vision import BoundingBox, DetectionParameters, ModelInfo

JobState = Literal[
    "queued", "running", "completed", "failed", "cancel_requested", "cancelled", "interrupted"
]


class VideoAnalyzeRequest(BaseModel):
    detection_fps: float = Field(default=2.0, ge=0.25, le=8)
    caption_interval_seconds: float = Field(default=10.0, ge=1, le=120)
    generate_captions: bool = True
    track_objects: bool = True
    detection: DetectionParameters = Field(default_factory=DetectionParameters)


class VideoAnalysis(BaseModel):
    analysis_id: str
    media_id: str
    job_id: str
    parameters: VideoAnalyzeRequest
    status: JobState
    created_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = Field(ge=0)
    coverage_end_ms: int = Field(default=0, ge=0)
    processed_frames: int = Field(default=0, ge=0)
    caption_frames: int = Field(default=0, ge=0)
    elapsed_ms: float = Field(default=0, ge=0)
    error_code: str | None = None


class VideoJob(BaseModel):
    job_id: str
    analysis_id: str
    media_id: str
    kind: Literal["analysis", "caption_frame"] = "analysis"
    status: JobState
    stage: str
    processed_frames: int = Field(default=0, ge=0)
    total_frames_estimate: int | None = None
    current_timestamp_ms: int | None = None
    elapsed_ms: float = Field(default=0, ge=0)
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
    revision: int = 1
    target_timestamp_ms: int | None = None


class VideoDetection(BaseModel):
    id: str
    class_id: int = Field(ge=0)
    label: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox
    track_id: int | None = Field(default=None, ge=0)


class VideoFrameResult(BaseModel):
    frame_id: str
    analysis_id: str
    timestamp_ms: int = Field(ge=0)
    source_pts: int
    time_base: str
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    detections: list[VideoDetection]
    model: ModelInfo
    inference_ms: float = Field(ge=0)


class VideoTrack(BaseModel):
    track_id: int
    class_id: int
    label: str
    first_timestamp_ms: int
    last_timestamp_ms: int
    sampled_observations: int


class VideoTimelineMarker(BaseModel):
    timestamp_ms: int
    object_count: int
    track_ids: list[int]


class VideoCaption(BaseModel):
    caption_id: str
    analysis_id: str
    frame_id: str | None = None
    timestamp_ms: int = Field(ge=0)
    text: str = Field(min_length=1)
    edited_text: str | None = None
    source: Literal["florence", "openai"]
    model: CaptionModelInfo | str
    inference_ms: float = Field(ge=0)
    usage: TokenUsage | None = None
    created_at: datetime
    version: int = 1


class VideoCaptionEdit(BaseModel):
    edited_text: str = Field(min_length=1, max_length=8000)
    expected_version: int = Field(ge=1)


class VideoCaptionRequest(BaseModel):
    timestamp_ms: int = Field(ge=0)


class VideoVQARequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    conversation_id: str | None = None
    consent_external_transfer: bool = False

    @model_validator(mode="after")
    def valid_range(self) -> "VideoVQARequest":
        self.question = self.question.strip()
        if not self.question or self.end_ms < self.start_ms:
            raise ValueError("A nonblank question and ordered time range are required.")
        return self


class VideoVQAResponse(BaseModel):
    conversation: VQAConversation
    examined_timestamps_ms: list[int]


class VideoRefineRequest(BaseModel):
    timestamp_ms: int = Field(ge=0)
    context: str = Field(default="", max_length=1000)
    consent_external_transfer: bool = False
