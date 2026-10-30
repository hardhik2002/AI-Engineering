import importlib.metadata
from hashlib import sha256
from threading import Lock
from typing import Protocol

from PIL import Image

from app.core.config import Settings
from app.schemas.vision import DetectionParameters, ModelInfo, ModelStatus


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
            return
        with self._lock:
            if self._model is not None:
                return
            if not self.weights_path.is_file():
                raise DetectorError(
                    "model_not_installed",
                    "YOLO26 Nano weights are not installed. Run the model install command.",
                )
            self._state = "loading"
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
            except DetectorError:
                raise
            except Exception as exc:
                self._state = "error"
                self._detail = (
                    "Model initialization failed. Check installed vision dependencies and weights."
                )
                raise DetectorError("model_initialization_failed", self._detail) from exc

    def detect(self, image: Image.Image, configuration: DetectionParameters) -> list[RawDetection]:
        self.load_model()
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
            return detections
        except Exception as exc:
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
