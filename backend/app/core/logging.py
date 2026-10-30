"""VisionLab application events, request context, and bounded JSONL retention."""

import json
import logging
import math
import os
import re
import sys
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.config import Settings

request_id_context: ContextVar[str | None] = ContextVar("visionlab_request_id", default=None)
_configuration_lock = Lock()
_configured_key: tuple[object, ...] | None = None
_FIELDS = (
    "event",
    "status",
    "outcome",
    "request_id",
    "method",
    "route",
    "status_code",
    "error_code",
    "error_category",
    "exception_type",
    "traceback",
    "media_id",
    "analysis_id",
    "media_type",
    "mime_type",
    "received_bytes",
    "width",
    "height",
    "duration_ms",
    "video_duration_ms",
    "model",
    "model_version",
    "package_version",
    "device",
    "model_state",
    "run_kind",
    "model_load_ms",
    "decode_ms",
    "preprocessing_ms",
    "inference_ms",
    "postprocessing_ms",
    "persistence_ms",
    "detection_count",
    "valid_box_count",
    "class_counts",
    "confidence",
    "iou",
    "image_size",
    "max_detections",
    "orientation",
    "thumbnail_created",
    "records_deleted",
    "result_count",
    "cuda_available",
    "environment",
    "python_version",
    "application_version",
    "storage_ready",
    "sqlite_ready",
    "log_format",
    "log_directory",
    "capabilities",
    "details",
    "caption_mode",
    "region_count",
    "detection_id",
    "crop_width",
    "crop_height",
    "revision",
)
_SENSITIVE = re.compile(
    r"password|secret|token|authorization|cookie|api[_-]?key|credential|path|filename", re.I
)
_SECRET_VALUE = re.compile(
    r"(?i)\b(password|secret|token|authorization|cookie|api[_-]?key)\s*[:=]\s*[^\s,;]+"
)
_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:[\\/][^\r\n]+")


def _safe(value: Any, key: str = "") -> Any:
    if _SENSITIVE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _safe(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, Path):
        return value.name
    if isinstance(value, str):
        return _WINDOWS_PATH.sub("[PATH]", _SECRET_VALUE.sub(r"\1=[REDACTED]", value))
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return type(value).__name__


def safe_traceback(exc: BaseException) -> list[dict[str, object]]:
    """Keep stack locations without source lines, arguments, or absolute paths."""
    return [
        {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
        for frame in traceback.extract_tb(exc.__traceback__)[-12:]
    ]


def _payload(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
        "level": record.levelname,
        "component": record.name.removeprefix("visionlab.")
        if record.name != "visionlab"
        else "app",
        "event": getattr(record, "event", "log.message"),
        "message": _safe(record.getMessage()),
        "request_id": getattr(record, "request_id", None),
    }
    for field in _FIELDS:
        if field != "request_id" and hasattr(record, field):
            payload[field] = _safe(getattr(record, field), field)
    return payload


class RequestContextFilter(logging.Filter):
    def __init__(self, include_request_id: bool = True):
        super().__init__()
        self.include_request_id = include_request_id

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_context.get() if self.include_request_id else None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(_payload(record), ensure_ascii=False, allow_nan=False)


class ConsoleFormatter(logging.Formatter):
    _COLORS = {
        "DEBUG": "\x1b[36m",
        "INFO": "\x1b[32m",
        "WARNING": "\x1b[33m",
        "ERROR": "\x1b[31m",
        "CRITICAL": "\x1b[35m",
    }

    def __init__(self, colors: bool = False):
        super().__init__()
        self.colors = colors

    def format(self, record: logging.LogRecord) -> str:
        payload = _payload(record)
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S.%f")[:-3]
        level = f"{record.levelname:<8}"
        if self.colors:
            level = f"{self._COLORS.get(record.levelname, '')}{level}\x1b[0m"
        request_id = payload["request_id"]
        req = f"req={str(request_id)[:8]}" if request_id else "req=--------"
        parts: list[str] = []
        if payload.get("method") and payload.get("route"):
            parts.append(f"{payload['method']} {payload['route']}")
        for field in ("media_id", "analysis_id"):
            if payload.get(field):
                parts.append(f"{field}={str(payload[field])[:8]}")
        for field in ("model", "device", "model_state", "run_kind", "media_type", "mime_type"):
            if payload.get(field):
                parts.append(f"{field}={payload[field]}")
        if payload.get("width") is not None and payload.get("height") is not None:
            parts.append(f"size={payload['width']}x{payload['height']}")
        if payload.get("detection_count") is not None:
            parts.append(f"detections={payload['detection_count']}")
        if payload.get("valid_box_count") is not None:
            parts.append(f"valid_boxes={payload['valid_box_count']}")
        if isinstance(payload.get("class_counts"), dict):
            classes = ",".join(
                f"{label}={count}" for label, count in payload["class_counts"].items()
            )
            if classes:
                parts.append(f"classes={classes}")
        for field in (
            "received_bytes",
            "video_duration_ms",
            "status_code",
            "error_code",
            "confidence",
            "iou",
            "image_size",
            "max_detections",
            "model_load_ms",
            "decode_ms",
            "preprocessing_ms",
            "inference_ms",
            "postprocessing_ms",
            "persistence_ms",
            "duration_ms",
            "application_version",
            "environment",
            "python_version",
            "cuda_available",
            "storage_ready",
            "sqlite_ready",
            "log_format",
            "log_directory",
        ):
            if field in payload and payload[field] is not None:
                parts.append(f"{field}={payload[field]}")
        if record.levelno == logging.DEBUG and isinstance(payload.get("details"), dict):
            parts.extend(f"{key}={value}" for key, value in payload["details"].items())
        context = " ".join(parts)
        suffix = f" | {context}" if context else ""
        header = f"{timestamp} | {level} | {str(payload['component']).upper():<10} | {req}"
        return f"{header} | {payload['message']}{suffix}"


def log_event(
    logger: logging.Logger, event: str, message: str, *, level: int = logging.INFO, **fields: Any
) -> None:
    extra = {"event": event}
    extra.update({key: value for key, value in fields.items() if key in _FIELDS and key != "event"})
    logger.log(level, message, extra=extra)


def configure_logging(settings: Settings | str) -> None:
    """Own only VisionLab handlers; leave Uvicorn server errors and root handlers alone."""
    global _configured_key
    if isinstance(settings, str):
        settings = Settings(log_level=settings, _env_file=None)
    key = (
        settings.log_level,
        settings.log_console_enabled,
        settings.log_file_enabled,
        settings.log_format,
        str(settings.log_directory.resolve()),
        settings.log_file_max_mb,
        settings.log_file_backup_count,
        settings.log_request_id_enabled,
        settings.log_colors,
    )
    with _configuration_lock:
        if _configured_key == key:
            return
        app_logger = logging.getLogger("visionlab")
        app_logger.setLevel(settings.log_level)
        app_logger.propagate = False
        for handler in list(app_logger.handlers):
            if getattr(handler, "_visionlab_owned", False):
                app_logger.removeHandler(handler)
                handler.close()
        if settings.log_console_enabled:
            handler = logging.StreamHandler(sys.stdout)
            colors = settings.log_colors == "always" or (
                settings.log_colors == "auto"
                and sys.stdout.isatty()
                and not os.environ.get("NO_COLOR")
            )
            handler.setFormatter(
                ConsoleFormatter(colors) if settings.log_format == "pretty" else JsonFormatter()
            )
            handler.addFilter(RequestContextFilter(settings.log_request_id_enabled))
            handler._visionlab_owned = True
            app_logger.addHandler(handler)
        if settings.log_file_enabled:
            settings.log_directory.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                settings.log_directory / "visionlab.jsonl",
                maxBytes=settings.log_file_max_mb * 1024 * 1024,
                backupCount=settings.log_file_backup_count,
                encoding="utf-8",
                delay=True,
            )
            handler.setFormatter(JsonFormatter())
            handler.addFilter(RequestContextFilter(settings.log_request_id_enabled))
            handler._visionlab_owned = True
            app_logger.addHandler(handler)
        for name in ("ultralytics", "torch", "PIL", "urllib3", "httpx"):
            logging.getLogger(name).setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").disabled = True
        _configured_key = key
