"""Bounded Florence tasks on validated, EXIF-oriented stored images."""

import logging
import math
import sqlite3
from datetime import UTC, datetime
from threading import BoundedSemaphore
from time import perf_counter
from uuid import uuid4

from PIL import Image, ImageOps

from app.core.config import Settings
from app.core.logging import log_event
from app.providers.captioner import CaptionError, CaptionProvider
from app.repositories.analyses import AnalysisRepository
from app.schemas.caption import CaptionRecord, CaptionRegion, CaptionTask
from app.schemas.vision import BoundingBox
from app.services.media import MediaError, MediaService

logger = logging.getLogger("visionlab.caption")


def normalize_region(values: object, width: int, height: int) -> BoundingBox:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise CaptionError("invalid_region", "Florence-2 returned invalid region coordinates.", 500)
    try:
        x1, y1, x2, y2 = (float(value) for value in values)
    except (ValueError, TypeError) as exc:
        raise CaptionError(
            "invalid_region", "Florence-2 returned invalid region coordinates.", 500
        ) from exc
    if not all(math.isfinite(value) for value in (x1, y1, x2, y2)) or x2 <= x1 or y2 <= y1:
        raise CaptionError("invalid_region", "Florence-2 returned invalid region coordinates.", 500)
    left, top = max(0, min(width, x1)), max(0, min(height, y1))
    right, bottom = max(0, min(width, x2)), max(0, min(height, y2))
    if right <= left or bottom <= top:
        raise CaptionError("invalid_region", "Florence-2 returned an out-of-image region.", 500)
    return BoundingBox(
        x=left / width, y=top / height, width=(right - left) / width, height=(bottom - top) / height
    )


class CaptionService:
    def __init__(self, settings: Settings, media: MediaService, provider: CaptionProvider):
        self.settings, self.media, self.provider = settings, media, provider
        self.repository = AnalysisRepository(settings.database_path)
        self.capacity = BoundedSemaphore(1)

    def list(self, media_id: str) -> list[CaptionRecord]:
        self.media.get(media_id)
        return self.repository.list_captions(media_id)

    def run(
        self,
        media_id: str,
        task: CaptionTask,
        detection_analysis_id: str | None = None,
        detection_id: str | None = None,
    ) -> CaptionRecord:
        asset, path, _ = self.media.paths(media_id)
        if asset.media_type != "image":
            raise MediaError(
                "unsupported_media_task", "Florence-2 requires an uploaded image.", 422
            )
        if not path.is_file():
            raise MediaError("media_not_found", "Media content was not found.", 404)
        if not self.capacity.acquire(blocking=False):
            raise CaptionError("caption_busy", "Florence-2 is busy. Retry shortly.", 429)
        started = perf_counter()
        analysis_id = str(uuid4())
        created = datetime.now(UTC)
        log_event(
            logger,
            "caption.started",
            "START Florence analysis",
            media_id=media_id,
            analysis_id=analysis_id,
            caption_mode=task,
        )
        try:
            with Image.open(path) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
            if image.size != (asset.width, asset.height):
                raise MediaError(
                    "media_changed", "Image dimensions no longer match saved metadata.", 409
                )
            if task == "selected_object":
                if not detection_analysis_id or not detection_id:
                    raise CaptionError("invalid_detection", "Select a saved YOLO detection.", 422)
                self.media.validate_id(detection_analysis_id)
                self.media.validate_id(detection_id)
                detection_run = self.repository.get(media_id, detection_analysis_id)
                if detection_run is None or detection_run.status != "completed":
                    raise CaptionError(
                        "invalid_detection", "Saved YOLO analysis was not found.", 404
                    )
                detection = next(
                    (item for item in detection_run.detections if item.id == detection_id), None
                )
                if detection is None:
                    raise CaptionError(
                        "invalid_detection", "Saved YOLO detection was not found.", 404
                    )
                box = detection.bounding_box
                x1, y1 = int(box.x * image.width), int(box.y * image.height)
                x2, y2 = (
                    math.ceil((box.x + box.width) * image.width),
                    math.ceil((box.y + box.height) * image.height),
                )
                image = image.crop((x1, y1, x2, y2))
                log_event(
                    logger,
                    "caption.crop_completed",
                    "COMPLETE Validated object crop prepared",
                    media_id=media_id,
                    analysis_id=analysis_id,
                    detection_id=detection_id,
                    crop_width=image.width,
                    crop_height=image.height,
                )
            if max(image.size) > self.settings.florence_max_source_side:
                image.thumbnail(
                    (self.settings.florence_max_source_side,) * 2, Image.Resampling.LANCZOS
                )
            model_load_ms = self.provider.load_model()
            log_event(
                logger,
                "caption.inference_started",
                "START Florence generation",
                media_id=media_id,
                analysis_id=analysis_id,
                caption_mode=task,
                run_kind="cold" if model_load_ms else "warm",
            )
            parsed, inference_ms = self.provider.generate(image, task)
            log_event(
                logger,
                "caption.inference_completed",
                "COMPLETE Florence generation",
                media_id=media_id,
                analysis_id=analysis_id,
                caption_mode=task,
                inference_ms=round(inference_ms, 2),
            )
            prompt = {
                "short": "<CAPTION>",
                "detailed": "<DETAILED_CAPTION>",
                "extended": "<MORE_DETAILED_CAPTION>",
                "dense": "<DENSE_REGION_CAPTION>",
                "selected_object": "<MORE_DETAILED_CAPTION>",
            }[task]
            if not isinstance(parsed, dict):
                raise CaptionError(
                    "malformed_caption", "Florence-2 returned malformed output.", 500
                )
            result = parsed.get(prompt)
            text: str | None = None
            regions: list[CaptionRegion] = []
            model = self.provider.model_info()
            if task == "dense":
                if (
                    not isinstance(result, dict)
                    or not isinstance(result.get("bboxes"), list)
                    or not isinstance(result.get("labels"), list)
                    or len(result["bboxes"]) != len(result["labels"])
                ):
                    raise CaptionError(
                        "malformed_caption", "Florence-2 returned malformed regions.", 500
                    )
                for values, label in list(zip(result["bboxes"], result["labels"], strict=True))[
                    : self.settings.florence_max_regions
                ]:
                    if not isinstance(label, str) or not label.strip():
                        raise CaptionError(
                            "malformed_caption", "Florence-2 returned a region without text.", 500
                        )
                    regions.append(
                        CaptionRegion(
                            id=str(uuid4()),
                            description=label.strip(),
                            bounding_box=normalize_region(values, image.width, image.height),
                            model=model,
                        )
                    )
                log_event(
                    logger,
                    "caption.regions_validated",
                    "COMPLETE Dense regions validated",
                    media_id=media_id,
                    analysis_id=analysis_id,
                    region_count=len(regions),
                )
            elif isinstance(result, str) and result.strip():
                text = result.strip()
            else:
                raise CaptionError(
                    "malformed_caption", "Florence-2 returned an empty caption.", 500
                )
            completed = datetime.now(UTC)
            record = CaptionRecord(
                analysis_id=analysis_id,
                media_id=media_id,
                task=task,
                created_at=created,
                completed_at=completed,
                model=model,
                duration_ms=(perf_counter() - started) * 1000,
                model_load_ms=model_load_ms,
                inference_ms=inference_ms,
                text=text,
                regions=regions,
                detection_analysis_id=detection_analysis_id,
                detection_id=detection_id,
            )
            try:
                self.repository.insert_caption(record)
            except sqlite3.IntegrityError as exc:
                raise MediaError("media_not_found", "Media item was not found.", 404) from exc
            self.provider.successful_tasks.add(task)
            log_event(
                logger,
                "caption.completed",
                "COMPLETE Florence analysis saved",
                media_id=media_id,
                analysis_id=analysis_id,
                caption_mode=task,
                region_count=len(regions),
                model_load_ms=round(model_load_ms, 2),
                inference_ms=round(inference_ms, 2),
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            return record
        except Exception as exc:
            log_event(
                logger,
                "caption.failed",
                "FAILED Florence analysis",
                level=logging.WARNING,
                media_id=media_id,
                analysis_id=analysis_id,
                error_code=getattr(exc, "code", "caption_failed"),
                exception_type=type(exc).__name__,
            )
            raise
        finally:
            self.capacity.release()
