"""Cached YOLO26 model with per-analysis ByteTrack state."""

import importlib.metadata
from hashlib import sha256
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Protocol

from PIL import Image

from app.core.config import Settings
from app.providers.detector import DetectorError, RawDetection
from app.schemas.vision import DetectionParameters, ModelInfo


class TrackedRawDetection(RawDetection):
    def __init__(
        self,
        class_id: int,
        label: str,
        confidence: float,
        xyxy: tuple[float, float, float, float],
        track_id: int | None,
    ):
        super().__init__(class_id, label, confidence, xyxy)
        self.track_id = track_id


class VideoTracker(Protocol):
    def start(self) -> None: ...
    def track(
        self, image: Image.Image, configuration: DetectionParameters
    ) -> tuple[list[TrackedRawDetection], float]: ...
    def model_info(self) -> ModelInfo: ...
    def detect(
        self, image: Image.Image, configuration: DetectionParameters
    ) -> tuple[list[TrackedRawDetection], float]: ...


class YOLO26ByteTracker:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.weights_path: Path = (settings.model_root / settings.detection_model).resolve()
        self._model = None
        self._device: str | None = None
        self._digest: str | None = None
        self._lock = Lock()

    def _load(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            if not self.weights_path.is_file():
                raise DetectorError("model_not_installed", "YOLO26 weights are not installed.")
            try:
                import torch
                from ultralytics import YOLO

                requested = self.settings.detection_device
                if requested == "cuda" and not torch.cuda.is_available():
                    raise DetectorError("device_unavailable", "CUDA is unavailable for YOLO26.")
                self._device = (
                    "cuda:0"
                    if requested == "cuda" or (requested == "auto" and torch.cuda.is_available())
                    else "cpu"
                )
                self._model = YOLO(str(self.weights_path))
                digest = sha256()
                with self.weights_path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                self._digest = digest.hexdigest()
            except DetectorError:
                raise
            except Exception as exc:
                raise DetectorError(
                    "model_initialization_failed", "YOLO26 video tracker could not initialize."
                ) from exc

    def start(self) -> None:
        self._load()
        # Preserve weights while discarding ByteTrack predictor state between videos.
        self._model.predictor = None

    def track(
        self, image: Image.Image, configuration: DetectionParameters
    ) -> tuple[list[TrackedRawDetection], float]:
        if self._model is None:
            raise DetectorError("model_not_ready", "Video tracker is not initialized.")
        started = perf_counter()
        try:
            import numpy as np

            result = self._model.track(
                source=np.asarray(image)[:, :, ::-1].copy(),
                persist=True,
                tracker="bytetrack.yaml",
                conf=configuration.confidence,
                iou=configuration.iou,
                imgsz=configuration.image_size,
                max_det=configuration.max_detections,
                device=self._device,
                verbose=False,
            )[0]
            ids = result.boxes.id
            tracking_ids = ids.int().cpu().tolist() if ids is not None else []
            objects = []
            for index, box in enumerate(result.boxes):
                class_id = int(box.cls.item())
                objects.append(
                    TrackedRawDetection(
                        class_id,
                        str(result.names[class_id]),
                        float(box.conf.item()),
                        tuple(float(value) for value in box.xyxy[0].tolist()),
                        tracking_ids[index] if index < len(tracking_ids) else None,
                    )
                )
            return objects, (perf_counter() - started) * 1000
        except Exception as exc:
            raise DetectorError(
                "video_tracking_failed", "YOLO26 video tracking failed.", 500
            ) from exc

    def detect(
        self, image: Image.Image, configuration: DetectionParameters
    ) -> tuple[list[TrackedRawDetection], float]:
        if self._model is None:
            raise DetectorError("model_not_ready", "Video detector is not initialized.")
        started = perf_counter()
        try:
            import numpy as np

            result = self._model.predict(
                source=np.asarray(image)[:, :, ::-1].copy(),
                conf=configuration.confidence,
                iou=configuration.iou,
                imgsz=configuration.image_size,
                max_det=configuration.max_detections,
                device=self._device,
                verbose=False,
            )[0]
            objects = [
                TrackedRawDetection(
                    int(box.cls.item()),
                    str(result.names[int(box.cls.item())]),
                    float(box.conf.item()),
                    tuple(float(value) for value in box.xyxy[0].tolist()),
                    None,
                )
                for box in result.boxes
            ]
            return objects, (perf_counter() - started) * 1000
        except Exception as exc:
            raise DetectorError(
                "video_detection_failed", "YOLO26 video detection failed.", 500
            ) from exc

    def model_info(self) -> ModelInfo:
        if self._model is None or self._device is None:
            raise DetectorError("model_not_ready", "Video tracker is not initialized.")
        return ModelInfo(
            name=self.settings.detection_model,
            device=self._device,
            version="YOLO26",
            package_version=importlib.metadata.version("ultralytics"),
            weights_sha256=self._digest,
        )
