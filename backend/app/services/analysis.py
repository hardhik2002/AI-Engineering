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
from app.core.logging import log_event, safe_traceback
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


def prepare_image(path: Path, max_side: int) -> tuple[Image.Image, int, int, int, float, float]:
    decode_started = perf_counter()
    with Image.open(path) as source:
        orientation = int(source.getexif().get(274, 1))
        oriented = ImageOps.exif_transpose(source)
        width, height = oriented.size
        decode_ms = (perf_counter() - decode_started) * 1000
        preprocess_started = perf_counter()
        if max(width, height) > max_side:
            oriented.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        image = oriented.convert("RGB")
    return (
        image,
        width,
        height,
        orientation,
        decode_ms,
        (perf_counter() - preprocess_started) * 1000,
    )


class AnalysisService:
    def __init__(self, settings: Settings, media: MediaService, detector: ObjectDetector):
        self.settings = settings
        self.media = media
        self.detector = detector
        self.repository = AnalysisRepository(settings.database_path)
        self.capacity = BoundedSemaphore(settings.detection_concurrency)

    def analyze(self, media_id: str, parameters: DetectionParameters) -> AnalysisRecord:
        lookup_started = perf_counter()
        log_event(logger, "media.lookup_started", "START Resolving saved media", media_id=media_id)
        try:
            asset, path, _ = self.media.paths(media_id)
        except MediaError as exc:
            log_event(
                logger,
                "media.lookup_failed",
                "FAILED Saved media could not be resolved",
                level=logging.WARNING,
                media_id=media_id,
                error_code=exc.code,
                duration_ms=round((perf_counter() - lookup_started) * 1000, 2),
            )
            raise
        if asset.media_type != "image":
            log_event(
                logger,
                "analysis.skipped",
                "SKIPPED Video detection is not available",
                media_id=media_id,
                media_type=asset.media_type,
                error_code="unsupported_media_task",
            )
            raise MediaError(
                "unsupported_media_task", "Video object detection is planned for Phase 6.", 422
            )
        if not path.is_file():
            log_event(
                logger,
                "media.lookup_failed",
                "FAILED Saved media content missing",
                level=logging.WARNING,
                media_id=media_id,
                error_code="media_not_found",
            )
            raise MediaError("media_not_found", "Media content was not found.", 404)
        log_event(
            logger,
            "media.lookup_completed",
            "COMPLETE Saved media resolved",
            media_id=media_id,
            media_type=asset.media_type,
            mime_type=asset.detected_mime_type,
            width=asset.width,
            height=asset.height,
            duration_ms=round((perf_counter() - lookup_started) * 1000, 2),
        )
        if not self.capacity.acquire(blocking=False):
            log_event(
                logger,
                "analysis.skipped",
                "SKIPPED Detector capacity is busy",
                level=logging.WARNING,
                media_id=media_id,
                error_code="model_busy",
            )
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
        log_event(
            logger,
            "analysis.started",
            "START Image analysis started",
            media_id=media_id,
            analysis_id=analysis_id,
            model=self.settings.detection_model,
            confidence=parameters.confidence,
            iou=parameters.iou,
            image_size=parameters.image_size,
            max_detections=parameters.max_detections,
        )
        try:
            self.repository.insert_started(analysis_id, media_id, created_at)
        except sqlite3.IntegrityError as exc:
            raise MediaError("media_not_found", "Media item was not found.", 404) from exc
        try:
            log_event(
                logger,
                "image.decode_started",
                "START Decoding saved image",
                media_id=media_id,
                analysis_id=analysis_id,
            )
            image, source_width, source_height, orientation, decode_ms, transform_ms = (
                prepare_image(path, self.settings.detection_max_source_side)
            )
            log_event(
                logger,
                "image.decode_completed",
                "COMPLETE Image decoded",
                media_id=media_id,
                analysis_id=analysis_id,
                width=source_width,
                height=source_height,
                decode_ms=round(decode_ms, 2),
            )
            if orientation in range(2, 9):
                log_event(
                    logger,
                    "image.orientation_normalized",
                    "COMPLETE EXIF orientation applied",
                    media_id=media_id,
                    analysis_id=analysis_id,
                    orientation=orientation,
                )
            log_event(
                logger,
                "image.preprocess_completed",
                "COMPLETE Model input prepared",
                media_id=media_id,
                analysis_id=analysis_id,
                width=image.width,
                height=image.height,
                preprocessing_ms=round(decode_ms + transform_ms, 2),
            )
            if (source_width, source_height) != (width, height):
                raise MediaError(
                    "media_changed", "Image dimensions no longer match stored metadata.", 409
                )
            preprocess_ms = decode_ms + transform_ms
            model_state_before = self.detector.get_status().state
            run_kind = "warm" if model_state_before == "ready" else "cold"
            model_started = perf_counter()
            self.detector.load_model()
            model_load_ms = (perf_counter() - model_started) * 1000
            inference_start = perf_counter()
            log_event(
                logger,
                "inference.started",
                "START Object detection inference",
                media_id=media_id,
                analysis_id=analysis_id,
                model=self.settings.detection_model,
                device=self.detector.get_status().device,
                run_kind=run_kind,
            )
            raw = self.detector.detect(image, parameters)
            inference_ms = (perf_counter() - inference_start) * 1000
            log_event(
                logger,
                "inference.completed",
                "COMPLETE Object detection inference",
                media_id=media_id,
                analysis_id=analysis_id,
                model=self.settings.detection_model,
                device=self.detector.get_status().device,
                run_kind=run_kind,
                detection_count=len(raw),
                inference_ms=round(inference_ms, 2),
            )
            post_start = perf_counter()
            try:
                detections = sorted(
                    (normalized_detection(item, image.width, image.height) for item in raw),
                    key=lambda item: item.confidence,
                    reverse=True,
                )
            except ValueError:
                log_event(
                    logger,
                    "detections.validation_failed",
                    "FAILED Detector returned invalid coordinates",
                    level=logging.ERROR,
                    media_id=media_id,
                    analysis_id=analysis_id,
                    error_code="invalid_bounding_box",
                )
                raise
            log_event(
                logger,
                "detections.validated",
                "COMPLETE Detection coordinates validated",
                media_id=media_id,
                analysis_id=analysis_id,
                valid_box_count=len(detections),
            )
            if self.settings.log_inference_details and logger.isEnabledFor(logging.DEBUG):
                for item in detections[:20]:
                    log_event(
                        logger,
                        "detection.detail",
                        "COMPLETE Validated detection",
                        level=logging.DEBUG,
                        media_id=media_id,
                        analysis_id=analysis_id,
                        details={
                            "detection_id": item.id,
                            "class_id": item.class_id,
                            "label": item.label,
                            "confidence": item.confidence,
                            "bounding_box": item.bounding_box.model_dump(),
                        },
                    )
            counts = dict(sorted(Counter(item.label for item in detections).items()))
            log_event(
                logger,
                "analysis.summary_computed",
                "COMPLETE 0 detections above inference threshold"
                if not detections
                else "COMPLETE Detection summary computed",
                media_id=media_id,
                analysis_id=analysis_id,
                detection_count=len(detections),
                class_counts=counts,
            )
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
                    model_initialization=model_load_ms,
                    inference=inference_ms,
                    postprocessing=post_ms,
                    total=(perf_counter() - started) * 1000,
                ),
            )
            persistence_started = perf_counter()
            log_event(
                logger,
                "analysis.persistence_started",
                "START Saving analysis results",
                media_id=media_id,
                analysis_id=analysis_id,
            )
            self.repository.finish(record)
            persistence_ms = (perf_counter() - persistence_started) * 1000
            log_event(
                logger,
                "analysis.persistence_completed",
                "COMPLETE Analysis results saved",
                media_id=media_id,
                analysis_id=analysis_id,
                persistence_ms=round(persistence_ms, 2),
            )
            log_event(
                logger,
                "analysis.completed",
                "COMPLETE Image analysis finished",
                media_id=media_id,
                analysis_id=analysis_id,
                model=self.settings.detection_model,
                device=record.model.device if record.model else None,
                run_kind=run_kind,
                detection_count=len(detections),
                class_counts=counts,
                model_load_ms=round(model_load_ms, 2),
                decode_ms=round(decode_ms, 2),
                preprocessing_ms=round(preprocess_ms, 2),
                inference_ms=round(inference_ms, 2),
                postprocessing_ms=round(post_ms, 2),
                persistence_ms=round(persistence_ms, 2),
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            return record
        except Exception as exc:
            code = exc.code if isinstance(exc, (DetectorError, MediaError)) else "inference_failed"
            log_event(
                logger,
                "analysis.failed",
                "FAILED Image analysis could not be completed",
                level=logging.WARNING
                if isinstance(exc, (DetectorError, MediaError))
                else logging.ERROR,
                media_id=media_id,
                analysis_id=analysis_id,
                error_code=code,
                exception_type=type(exc).__name__
                if not isinstance(exc, (DetectorError, MediaError))
                else None,
                traceback=safe_traceback(exc)
                if not isinstance(exc, (DetectorError, MediaError))
                and self.settings.environment == "development"
                else None,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            failed = AnalysisRecord(
                analysis_id=analysis_id,
                media_id=media_id,
                status="failed",
                created_at=created_at,
                completed_at=datetime.now(UTC),
                parameters=parameters,
                error_code=code,
            )
            try:
                self.repository.finish(failed)
            except Exception as persistence_exc:
                log_event(
                    logger,
                    "analysis.persistence_failed",
                    "FAILED Analysis record could not be saved",
                    level=logging.ERROR,
                    media_id=media_id,
                    analysis_id=analysis_id,
                    error_code="analysis_persistence_failed",
                    exception_type=type(persistence_exc).__name__,
                )
                raise MediaError(
                    "analysis_persistence_failed", "Could not save analysis results.", 500
                ) from persistence_exc
            if isinstance(exc, (DetectorError, MediaError)):
                raise
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
