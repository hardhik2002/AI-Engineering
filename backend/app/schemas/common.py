from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MediaDimensions(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SourceMedia(BaseModel):
    media_id: str
    kind: Literal["image", "video"]
    dimensions: MediaDimensions
    timestamp_ms: int | None = Field(default=None, ge=0)


class NormalizedBox(BaseModel):
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def valid_area(self) -> "NormalizedBox":
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("box must have positive width and height")
        return self


class ModelProvenance(BaseModel):
    provider: str
    model: str
    version: str | None = None


class Detection(BaseModel):
    label: str
    confidence: float = Field(ge=0, le=1)
    box: NormalizedBox
    tracking_id: str | None = None
