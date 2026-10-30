from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DetectionParameters(BaseModel):
    confidence: float = Field(default=0.25, gt=0, le=1)
    iou: float = Field(default=0.45, ge=0, le=1)
    image_size: int = Field(default=640, ge=160, le=1280)
    max_detections: int = Field(default=100, ge=1, le=300)


class DetectionParameterOverrides(BaseModel):
    confidence: float | None = Field(default=None, gt=0, le=1)
    iou: float | None = Field(default=None, ge=0, le=1)
    image_size: int | None = Field(default=None, ge=160, le=1280)
    max_detections: int | None = Field(default=None, ge=1, le=300)


class AnalyzeRequest(BaseModel):
    tasks: list[Literal["object_detection"]] = Field(default_factory=lambda: ["object_detection"])
    parameters: DetectionParameterOverrides | None = None

    @model_validator(mode="after")
    def one_task(self) -> "AnalyzeRequest":
        if self.tasks != ["object_detection"]:
            raise ValueError("Only object_detection is supported")
        return self


class BoundingBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def inside_image(self) -> "BoundingBox":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("Bounding box exceeds image")
        return self


class DetectedObject(BaseModel):
    id: str
    class_id: int = Field(ge=0)
    label: str
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox


class ModelInfo(BaseModel):
    provider: str = "ultralytics"
    name: str
    device: str
    version: str
    package_version: str
    weights_sha256: str | None = None


class ModelStatus(BaseModel):
    state: Literal["not_installed", "loading", "ready", "unavailable", "error"]
    name: str
    device: str | None = None
    detail: str | None = None
    defaults: DetectionParameters | None = None


class ImageInfo(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    coordinate_space: Literal["exif_oriented"] = "exif_oriented"


class AnalysisSummary(BaseModel):
    total_objects: int = Field(ge=0)
    class_counts: dict[str, int]


class AnalysisTimings(BaseModel):
    preprocessing: float = Field(ge=0)
    inference: float = Field(ge=0)
    postprocessing: float = Field(ge=0)
    total: float = Field(ge=0)


class AnalysisRecord(BaseModel):
    analysis_id: str
    media_id: str
    status: Literal["completed", "failed"]
    task: Literal["object_detection"] = "object_detection"
    created_at: datetime
    completed_at: datetime
    model: ModelInfo | None = None
    image: ImageInfo | None = None
    parameters: DetectionParameters
    detections: list[DetectedObject] = Field(default_factory=list)
    summary: AnalysisSummary | None = None
    timings_ms: AnalysisTimings | None = None
    error_code: str | None = None
