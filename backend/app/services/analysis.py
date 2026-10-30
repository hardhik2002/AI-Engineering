import logging
import math
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from threading import BoundedSemaphore
from time import perf_counter
from uuid import uuid4

from PIL import Image, ImageOps

from app.core.config import Settings
from app.providers.detector import DetectorError, ObjectDetector, RawDetection
from app.repositories.analyses import AnalysisRepository
from app.schemas.vision import (
    AnalysisRecord,
    AnalysisSummary,
    AnalysisTimings,
    BoundingBox,
    DetectedObject,
    DetectionParameters,
    ImageInfo,
)
from app.services.media import MediaError, MediaService

logger = logging.getLogger("visionlab.analysis")


def normalized_detection(raw: RawDetection, width: int, height: int) -> DetectedObject:
    values = (*raw.xyxy, raw.confidence)
    if (
        len(raw.xyxy) != 4
        or not all(math.isfinite(value) for value in values)
        or not 0 <= raw.confidence <= 1
        or raw.class_id < 0
        or not raw.label
    ):
        raise ValueError("Detector returned invalid values")
    x1, y1, x2, y2 = raw.xyxy
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Detector returned an invalid box")
    left, top = max(0.0, min(width, x1)), max(0.0, min(height, y1))
    right, bottom = max(0.0, min(width, x2)), max(0.0, min(height, y2))
    if right <= left or bottom <= top:
        raise ValueError("Detector returned an out-of-image box")
    return DetectedObject(
        id=str(uuid4()),
        class_id=raw.class_id,
        label=raw.label,
        confidence=raw.confidence,
        bounding_box=BoundingBox(
            x=left / width,
            y=top / height,
            width=(right - left) / width,
            height=(bottom - top) / height,
        ),
    )


def prepare_image(path: Path, max_side: int) -> tuple[Image.Image, int, int]:
    with Image.open(path) as source:
        oriented = ImageOps.exif_transpose(source)
        width, height = oriented.size
        if max(width, height) > max_side:
            oriented.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        image = oriented.convert("RGB")
    return image, width, height


class AnalysisService:
    def __init__(self, settings: Settings, media: MediaService, detector: ObjectDetector):
        self.settings = settings
        self.media = media
        self.detector = detector
        self.repository = AnalysisRepository(settings.database_path)
        self.capacity = BoundedSemaphore(settings.detection_concurrency)

    def analyze(self, media_id: str, parameters: DetectionParameters) -> AnalysisRecord:
        asset, path, _ = self.media.paths(media_id)
        if asset.media_type != "image":
            raise MediaError(
                "unsupported_media_task", "Video object detection is planned for Phase 6.", 422
            )
        if not path.is_file():
            raise MediaError("media_not_found", "Media content was not found.", 404)
        if not self.capacity.acquire(blocking=False):
            raise MediaError(
                "model_busy",
                "The detector is busy. Retry after the current analysis.",
                429,
                {"Retry-After": "2"},
            )
        try:
            return self._run(asset.media_id, path, asset.width, asset.height, parameters)
        finally:
            self.capacity.release()

    def _run(
        self, media_id: str, path: Path, width: int, height: int, parameters: DetectionParameters
    ) -> AnalysisRecord:
        started = perf_counter()
        created_at = datetime.now(UTC)
        analysis_id = str(uuid4())
        try:
            self.repository.insert_started(analysis_id, media_id, created_at)
        except sqlite3.IntegrityError as exc:
            raise MediaError("media_not_found", "Media item was not found.", 404) from exc
        try:
            image, source_width, source_height = prepare_image(
                path, self.settings.detection_max_source_side
            )
            if (source_width, source_height) != (width, height):
                raise MediaError(
                    "media_changed", "Image dimensions no longer match stored metadata.", 409
                )
            preprocess_ms = (perf_counter() - started) * 1000
            inference_start = perf_counter()
            raw = self.detector.detect(image, parameters)
            inference_ms = (perf_counter() - inference_start) * 1000
            post_start = perf_counter()
            detections = sorted(
                (normalized_detection(item, image.width, image.height) for item in raw),
                key=lambda item: item.confidence,
                reverse=True,
            )
            counts = dict(sorted(Counter(item.label for item in detections).items()))
            post_ms = (perf_counter() - post_start) * 1000
            completed_at = datetime.now(UTC)
            record = AnalysisRecord(
                analysis_id=analysis_id,
                media_id=media_id,
                status="completed",
                created_at=created_at,
                completed_at=completed_at,
                model=self.detector.get_model_info(),
                image=ImageInfo(width=width, height=height),
                parameters=parameters,
                detections=detections,
                summary=AnalysisSummary(total_objects=len(detections), class_counts=counts),
                timings_ms=AnalysisTimings(
                    preprocessing=preprocess_ms,
                    inference=inference_ms,
                    postprocessing=post_ms,
                    total=(perf_counter() - started) * 1000,
                ),
            )
            self.repository.finish(record)
            return record
        except Exception as exc:
            code = exc.code if isinstance(exc, (DetectorError, MediaError)) else "inference_failed"
            failed = AnalysisRecord(
                analysis_id=analysis_id,
                media_id=media_id,
                status="failed",
                created_at=created_at,
                completed_at=datetime.now(UTC),
                parameters=parameters,
                error_code=code,
            )
            self.repository.finish(failed)
            if isinstance(exc, (DetectorError, MediaError)):
                raise
            logger.exception(
                "analysis_failed", extra={"analysis_id": analysis_id, "media_id": media_id}
            )
            raise MediaError(
                "inference_failed", "Object detection failed for this image.", 500
            ) from exc

    def list(self, media_id: str) -> list[AnalysisRecord]:
        self.media.get(media_id)
        return self.repository.list(media_id)

    def get(self, media_id: str, analysis_id: str) -> AnalysisRecord:
        self.media.get(media_id)
        self.media.validate_id(analysis_id)
        record = self.repository.get(media_id, analysis_id)
        if record is None:
            raise MediaError("analysis_not_found", "Analysis was not found.", 404)
        return record
