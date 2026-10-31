"""Bounded webcam frame parsing and real cached-detector inference."""

import io
import logging
from datetime import UTC, datetime
from threading import BoundedSemaphore
from time import perf_counter
from uuid import UUID

from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import log_event
from app.providers.detector import ObjectDetector
from app.schemas.live import LiveFrameMetadata, LiveFrameResult
from app.schemas.vision import DetectionParameters
from app.services.analysis import AnalysisService, normalized_detection

logger = logging.getLogger("visionlab.live")
MAGIC = b"VL1"
MAX_HEADER_BYTES = 1024


class LiveFrameError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


class LiveFrameSkipped(LiveFrameError):
    pass


class LiveService:
    def __init__(
        self, settings: Settings, detector: ObjectDetector, analysis_service: AnalysisService
    ) -> None:
        self.settings, self.detector = settings, detector
        self.detector_capacity = analysis_service.capacity
        self.sessions = BoundedSemaphore(settings.live_max_active_sessions)
        self.active_sessions = 0

    def enter(self) -> bool:
        if not self.sessions.acquire(blocking=False):
            return False
        self.active_sessions += 1
        return True

    def leave(self) -> None:
        self.active_sessions -= 1
        self.sessions.release()

    def unpack(self, packet: bytes, session_id: UUID) -> tuple[LiveFrameMetadata, Image.Image]:
        if len(packet) > self.settings.live_max_frame_bytes + MAX_HEADER_BYTES + 7:
            raise LiveFrameError("frame_too_large", "Camera frame exceeds the size limit.")
        if len(packet) < 8 or packet[:3] != MAGIC:
            raise LiveFrameError("invalid_frame", "Invalid live frame envelope.")
        header_size = int.from_bytes(packet[3:7], "big")
        if not 1 <= header_size <= MAX_HEADER_BYTES or len(packet) <= 7 + header_size:
            raise LiveFrameError("invalid_frame", "Invalid live frame header length.")
        try:
            metadata = LiveFrameMetadata.model_validate_json(packet[7:7 + header_size])
        except ValidationError as exc:
            raise LiveFrameError("invalid_frame_metadata", "Invalid live frame metadata.") from exc
        if metadata.session_id != session_id:
            raise LiveFrameError("invalid_session", "Frame belongs to another camera session.")
        if (
            metadata.source_width > self.settings.live_max_width
            or metadata.source_height > self.settings.live_max_height
        ):
            raise LiveFrameError("invalid_dimensions", "Camera frame dimensions exceed limits.")
        payload = packet[7 + header_size:]
        if len(payload) > self.settings.live_max_frame_bytes:
            raise LiveFrameError("frame_too_large", "Camera frame exceeds the size limit.")
        if not payload.startswith(b"\xff\xd8\xff"):
            raise LiveFrameError("invalid_frame_encoding", "Expected JPEG camera frame.")
        try:
            with Image.open(io.BytesIO(payload)) as source:
                if source.format != "JPEG" or source.size != (
                    metadata.source_width, metadata.source_height
                ):
                    raise LiveFrameError(
                        "invalid_dimensions", "Encoded frame dimensions do not match metadata."
                    )
                source.load()
                image = source.convert("RGB")
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise LiveFrameError(
                "invalid_frame_encoding", "Camera JPEG could not be decoded."
            ) from exc
        return metadata, image

    def infer(self, metadata: LiveFrameMetadata, image: Image.Image) -> LiveFrameResult:
        if not self.detector_capacity.acquire(blocking=False):
            raise LiveFrameSkipped("model_busy", "Detector is processing another image.")
        started = perf_counter()
        try:
            self.detector.load_model()
            infer_started = perf_counter()
            parameters = DetectionParameters(
                confidence=self.settings.detection_confidence,
                iou=self.settings.detection_iou,
                image_size=self.settings.detection_image_size,
                max_detections=self.settings.detection_max_detections,
            )
            log_event(
                logger, "live.inference_started", "START Live detection",
                level=logging.DEBUG, session_id=str(metadata.session_id),
                frame_id=str(metadata.frame_id), model=self.settings.detection_model,
            )
            raw = self.detector.detect(image, parameters)
            inference_ms = (perf_counter() - infer_started) * 1000
            detections = [
                normalized_detection(item, image.width, image.height) for item in raw
            ]
            model = self.detector.get_model_info()
            log_event(
                logger, "live.inference_completed", "COMPLETE Live detection",
                level=logging.DEBUG, session_id=str(metadata.session_id),
                frame_id=str(metadata.frame_id), model=model.name, device=model.device,
                inference_ms=inference_ms, detection_count=len(detections),
            )
            return LiveFrameResult(
                session_id=metadata.session_id, frame_id=metadata.frame_id,
                captured_at_ms=metadata.captured_at_ms,
                source_width=image.width, source_height=image.height,
                detections=detections, model=model, inference_ms=inference_ms,
                processing_ms=(perf_counter() - started) * 1000,
                result_at=datetime.now(UTC),
            )
        finally:
            self.detector_capacity.release()
