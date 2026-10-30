import importlib.metadata
import logging
from hashlib import sha256
from threading import Lock
from time import perf_counter
from typing import Protocol

from PIL import Image

from app.core.config import Settings
from app.core.logging import log_event
from app.schemas.vision import DetectionParameters, ModelInfo, ModelStatus

logger = logging.getLogger("visionlab.model")


class DetectorError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RawDetection:
    def __init__(
        self, class_id: int, label: str, confidence: float, xyxy: tuple[float, float, float, float]
    ):
        self.class_id = class_id
        self.label = label
        self.confidence = confidence
        self.xyxy = xyxy


class ObjectDetector(Protocol):
    def load_model(self) -> None: ...
    def detect(
        self, image: Image.Image, configuration: DetectionParameters
    ) -> list[RawDetection]: ...
    def get_model_info(self) -> ModelInfo: ...
    def get_status(self) -> ModelStatus: ...


class YOLO26Detector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.weights_path = (settings.model_root / settings.detection_model).resolve()
        self._lock = Lock()
        self._model = None
        self._device: str | None = None
        self._weights_sha256: str | None = None
        self._state: str = "not_installed"
        self._detail: str | None = None

    def get_status(self) -> ModelStatus:
        if not self.weights_path.is_file() and self._model is None:
            state = "not_installed"
            detail = "Install model weights with python -m app.scripts.install_model."
        else:
            state = self._state if self._state != "not_installed" else "unavailable"
            detail = self._detail or (
                "Weights installed; model loads on first analysis."
                if state == "unavailable"
                else None
            )
        return ModelStatus(
            state=state,
            name=self.settings.detection_model,
            device=self._device,
            detail=detail,
            defaults=DetectionParameters(
                confidence=self.settings.detection_confidence,
                iou=self.settings.detection_iou,
                image_size=self.settings.detection_image_size,
                max_detections=self.settings.detection_max_detections,
            ),
        )

    def load_model(self) -> None:
        if self._model is not None:
            log_event(
                logger,
                "model.cache_hit",
                "COMPLETE Cached model reused",
                model=self.settings.detection_model,
                device=self._device,
                model_state="ready",
                run_kind="warm",
            )
            return
        with self._lock:
            if self._model is not None:
                log_event(
                    logger,
                    "model.cache_hit",
                    "COMPLETE Cached model reused",
                    model=self.settings.detection_model,
                    device=self._device,
                    model_state="ready",
                    run_kind="warm",
                )
                return
            started = perf_counter()
            if not self.weights_path.is_file():
                log_event(
                    logger,
                    "model.load_failed",
                    "FAILED Model weights are not installed",
                    level=logging.WARNING,
                    model=self.settings.detection_model,
                    model_state="not_installed",
                    error_code="model_not_installed",
                )
                raise DetectorError(
                    "model_not_installed",
                    "YOLO26 Nano weights are not installed. Run the model install command.",
                )
            self._state = "loading"
            log_event(
                logger,
                "model.load_started",
                "START Cold model initialization",
                model=self.settings.detection_model,
                model_state="loading",
                run_kind="cold",
                device=self.settings.detection_device,
            )
            try:
                import torch
                from ultralytics import YOLO

                requested = self.settings.detection_device
                available = torch.cuda.is_available()
                if requested == "cuda" and not available:
                    self._state = "unavailable"
                    self._detail = (
                        "CUDA was requested but is unavailable. "
                        "Set VISIONLAB_DETECTION_DEVICE=cpu or auto."
                    )
                    raise DetectorError("device_unavailable", self._detail)
                self._device = (
                    "cuda:0"
                    if (requested == "cuda" or requested == "auto" and available)
                    else "cpu"
                )
                self._model = YOLO(str(self.weights_path))
                digest = sha256()
                with self.weights_path.open("rb") as weights:
                    for chunk in iter(lambda: weights.read(1024 * 1024), b""):
                        digest.update(chunk)
                self._weights_sha256 = digest.hexdigest()
                self._state = "ready"
                self._detail = None
                log_event(
                    logger,
                    "model.load_completed",
                    "COMPLETE Model initialized",
                    model=self.settings.detection_model,
                    model_version="YOLO26",
                    package_version=importlib.metadata.version("ultralytics"),
                    device=self._device,
                    model_state="ready",
                    run_kind="cold",
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
            except DetectorError as exc:
                log_event(
                    logger,
                    "model.load_failed",
                    "FAILED Model initialization unavailable",
                    level=logging.WARNING,
                    model=self.settings.detection_model,
                    model_state=self._state,
                    error_code=exc.code,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                raise
            except Exception as exc:
                self._state = "error"
                self._detail = (
                    "Model initialization failed. Check installed vision dependencies and weights."
                )
                log_event(
                    logger,
                    "model.load_failed",
                    "FAILED Model initialization error",
                    level=logging.ERROR,
                    model=self.settings.detection_model,
                    model_state="error",
                    error_code="model_initialization_failed",
                    exception_type=type(exc).__name__,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
                raise DetectorError("model_initialization_failed", self._detail) from exc

    def detect(self, image: Image.Image, configuration: DetectionParameters) -> list[RawDetection]:
        if self._model is None:
            self.load_model()
        started = perf_counter()
        log_event(
            logger,
            "model.inference_started",
            "START Model prediction",
            model=self.settings.detection_model,
            device=self._device,
            confidence=configuration.confidence,
            iou=configuration.iou,
            image_size=configuration.image_size,
        )
        try:
            import numpy as np

            assert self._model is not None
            result = self._model.predict(
                source=np.asarray(image)[:, :, ::-1].copy(),
                conf=configuration.confidence,
                iou=configuration.iou,
                imgsz=configuration.image_size,
                max_det=configuration.max_detections,
                device=self._device,
                verbose=False,
            )[0]
            names = result.names
            detections = []
            for box in result.boxes:
                class_id = int(box.cls.item())
                detections.append(
                    RawDetection(
                        class_id,
                        str(names[class_id]),
                        float(box.conf.item()),
                        tuple(float(value) for value in box.xyxy[0].tolist()),
                    )
                )
            log_event(
                logger,
                "model.inference_completed",
                "COMPLETE Model prediction",
                model=self.settings.detection_model,
                device=self._device,
                detection_count=len(detections),
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            return detections
        except Exception as exc:
            log_event(
                logger,
                "model.inference_failed",
                "FAILED Model prediction",
                level=logging.ERROR,
                model=self.settings.detection_model,
                device=self._device,
                error_code="inference_failed",
                exception_type=type(exc).__name__,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            raise DetectorError(
                "inference_failed", "Object detection failed for this image.", 500
            ) from exc

    def get_model_info(self) -> ModelInfo:
        if self._model is None or self._device is None:
            raise DetectorError("model_not_ready", "Model is not loaded.")
        return ModelInfo(
            name=self.settings.detection_model,
            device=self._device,
            version="YOLO26",
            package_version=importlib.metadata.version("ultralytics"),
            weights_sha256=self._weights_sha256,
        )
