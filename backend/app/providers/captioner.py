"""Native, locally installed Florence-2 provider. No runtime model downloads."""

import importlib.metadata
import json
import logging
import re
from threading import Lock
from time import perf_counter
from typing import Any, Protocol

from PIL import Image

from app.core.config import Settings
from app.core.logging import log_event
from app.schemas.caption import CaptionModelInfo, CaptionTask

logger = logging.getLogger("visionlab.caption")
PROMPTS: dict[CaptionTask, str] = {
    "short": "<CAPTION>",
    "detailed": "<DETAILED_CAPTION>",
    "extended": "<MORE_DETAILED_CAPTION>",
    "dense": "<DENSE_REGION_CAPTION>",
    "selected_object": "<MORE_DETAILED_CAPTION>",
}


class CaptionError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 503):
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class CaptionProvider(Protocol):
    successful_tasks: set[str]

    def get_status(self) -> dict[str, str | None]: ...
    def load_model(self) -> float: ...
    def generate(self, image: Image.Image, task: CaptionTask) -> tuple[Any, float]: ...
    def model_info(self) -> CaptionModelInfo: ...


class Florence2CaptionProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.directory = (settings.model_root / "florence2").resolve()
        self._lock = Lock()
        self._model: Any = None
        self._processor: Any = None
        self._device: str | None = None
        self._state = "not_installed"
        self.successful_tasks: set[str] = set()

    def get_status(self) -> dict[str, str | None]:
        if self._model is not None:
            state = "ready"
        elif self._state in {"loading", "error"}:
            state = self._state
        elif self._installed():
            state = "installed_not_loaded"
        else:
            state = "not_installed"
        return {
            "state": state,
            "name": self.settings.florence_checkpoint,
            "revision": self.settings.florence_revision,
            "device": self._device,
        }

    def _installed(self) -> bool:
        manifest = self.directory / "visionlab-model.json"
        try:
            actual = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        return (self.directory / "model.safetensors").is_file() and actual == {
            "checkpoint": self.settings.florence_checkpoint,
            "revision": self.settings.florence_revision,
        }

    def load_model(self) -> float:
        if self._model is not None:
            log_event(
                logger,
                "caption.model_ready",
                "COMPLETE Cached Florence model reused",
                model=self.settings.florence_checkpoint,
                run_kind="warm",
            )
            return 0.0
        with self._lock:
            if self._model is not None:
                return 0.0
            if not self._installed():
                raise CaptionError(
                    "caption_model_not_installed",
                    "Florence-2 is not installed. Run the Florence model install command.",
                )
            started = perf_counter()
            self._state = "loading"
            log_event(
                logger,
                "caption.model_loading",
                "START Loading Florence model",
                model=self.settings.florence_checkpoint,
                run_kind="cold",
            )
            try:
                import torch
                from transformers import AutoProcessor, Florence2ForConditionalGeneration

                requested = self.settings.florence_device
                if requested == "cuda" and not torch.cuda.is_available():
                    self._state = "error"
                    raise CaptionError(
                        "caption_device_unavailable", "CUDA is unavailable for Florence-2."
                    )
                device = (
                    "cuda:0"
                    if requested == "cuda" or requested == "auto" and torch.cuda.is_available()
                    else "cpu"
                )
                dtype = torch.float16 if device.startswith("cuda") else torch.float32
                model = Florence2ForConditionalGeneration.from_pretrained(
                    self.directory,
                    dtype=dtype,
                    local_files_only=True,
                    trust_remote_code=False,
                ).to(device)
                processor = AutoProcessor.from_pretrained(
                    self.directory,
                    local_files_only=True,
                    trust_remote_code=False,
                    use_fast=False,
                )
                model.eval()
                self._model, self._processor, self._device = model, processor, device
                self._state = "ready"
            except CaptionError:
                raise
            except Exception as exc:
                self._state = "error"
                log_event(
                    logger,
                    "caption.failed",
                    "FAILED Florence model load",
                    level=logging.ERROR,
                    error_code="caption_model_load_failed",
                    exception_type=type(exc).__name__,
                )
                raise CaptionError(
                    "caption_model_load_failed", "Florence-2 could not be loaded."
                ) from exc
            elapsed = (perf_counter() - started) * 1000
            log_event(
                logger,
                "caption.model_ready",
                "COMPLETE Florence model ready",
                model=self.settings.florence_checkpoint,
                device=device,
                run_kind="cold",
                model_load_ms=round(elapsed, 2),
            )
            return elapsed

    def generate(self, image: Image.Image, task: CaptionTask) -> tuple[Any, float]:
        if self._model is None or self._processor is None or self._device is None:
            raise CaptionError("caption_model_not_ready", "Florence-2 is not loaded.")
        import torch

        prompt = PROMPTS[task]
        started = perf_counter()
        try:
            inputs = self._processor(text=prompt, images=image, return_tensors="pt")
            inputs = {
                key: value.to(self._device, dtype=torch.float16)
                if key == "pixel_values" and self._device.startswith("cuda")
                else value.to(self._device)
                for key, value in inputs.items()
            }
            with torch.inference_mode():
                generated = self._model.generate(
                    **inputs,
                    max_new_tokens=self.settings.florence_max_new_tokens,
                    num_beams=self.settings.florence_num_beams,
                )
            raw = self._processor.batch_decode(generated, skip_special_tokens=False)[0]
            if task == "dense":
                # This parser expects contiguous location tokens; generation inserts spaces.
                raw = re.sub(r">\s+(?=<loc_\d+>)", ">", raw)
            parsed = self._processor.post_process_generation(
                raw, task=prompt, image_size=image.size
            )
        except Exception as exc:
            log_event(
                logger,
                "caption.failed",
                "FAILED Florence inference",
                level=logging.ERROR,
                error_code="caption_inference_failed",
                exception_type=type(exc).__name__,
            )
            raise CaptionError(
                "caption_inference_failed", "Florence-2 inference failed.", 500
            ) from exc
        return parsed, (perf_counter() - started) * 1000

    def model_info(self) -> CaptionModelInfo:
        if self._device is None:
            raise CaptionError("caption_model_not_ready", "Florence-2 is not loaded.")
        return CaptionModelInfo(
            checkpoint=self.settings.florence_checkpoint,
            revision=self.settings.florence_revision,
            device=self._device,
            package_version=importlib.metadata.version("transformers"),
        )
