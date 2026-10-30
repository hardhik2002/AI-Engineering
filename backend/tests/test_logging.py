import io
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.core.logging import (
    ConsoleFormatter,
    JsonFormatter,
    configure_logging,
    log_event,
)
from app.main import create_app
from app.providers.detector import RawDetection, YOLO26Detector
from app.schemas.vision import DetectionParameters, ModelInfo, ModelStatus


class StubDetector:
    def __init__(self, detections: list[RawDetection] | None = None):
        self.detections = (
            detections
            if detections is not None
            else [RawDetection(0, "person", 0.9, (2, 2, 10, 10))]
        )

    def load_model(self) -> None:
        pass

    def detect(
        self, _image: Image.Image, _configuration: DetectionParameters
    ) -> list[RawDetection]:
        log_event(
            logging.getLogger("visionlab.test"),
            "test.thread_context",
            "COMPLETE Worker context observed",
        )
        return self.detections

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(name="yolo26n.pt", device="cpu", version="YOLO26", package_version="test")

    def get_status(self) -> ModelStatus:
        return ModelStatus(state="ready", name="yolo26n.pt", device="cpu")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        log_console_enabled=False,
        log_file_enabled=True,
        log_directory=tmp_path / "logs",
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        media_root=tmp_path / "media",
        thumbnail_root=tmp_path / "thumbs",
        model_root=tmp_path / "models",
        _env_file=None,
    )


def events(settings: Settings) -> list[dict]:
    return [
        json.loads(line)
        for line in (settings.log_directory / "visionlab.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def upload(client: TestClient, *, orientation: int | None = None) -> str:
    image = Image.new("RGB", (16, 12), "green")
    output = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(output, format="JPEG", **({"exif": exif} if orientation else {}))
    response = client.post(
        "/api/v1/media/upload",
        files={"file": ("private-name.jpg", output.getvalue(), "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    return response.json()["media_id"]


def test_console_and_jsonl_formatting_redact_private_fields() -> None:
    record = logging.LogRecord(
        "visionlab.analysis", logging.INFO, __file__, 1, "token=abc123", (), None
    )
    record.event = "analysis.completed"
    record.request_id = "08a937ff-72d5-4e0d-bbd6-fbf996ca634b"
    record.details = {"api_key": "top-secret", "filename": "private.jpg", "count": 2}
    line = JsonFormatter().format(record)
    payload = json.loads(line)
    assert payload["component"] == "analysis"
    assert payload["event"] == "analysis.completed"
    assert payload["request_id"] == record.request_id
    assert payload["details"] == {"api_key": "[REDACTED]", "filename": "[REDACTED]", "count": 2}
    assert "abc123" not in line and "top-secret" not in line and "private.jpg" not in line
    console = ConsoleFormatter().format(record)
    assert re.match(r"\d\d:\d\d:\d\d\.\d{3} \| INFO", console)
    assert "ANALYSIS" in console and "req=08a937ff" in console
    assert "\x1b[" not in console


def test_handlers_are_idempotent_and_access_log_is_owned(settings: Settings) -> None:
    configure_logging(settings)
    app_logger = logging.getLogger("visionlab")
    count = len(
        [handler for handler in app_logger.handlers if getattr(handler, "_visionlab_owned", False)]
    )
    configure_logging(settings)
    assert (
        len(
            [
                handler
                for handler in app_logger.handlers
                if getattr(handler, "_visionlab_owned", False)
            ]
        )
        == count
        == 1
    )
    assert logging.getLogger("uvicorn.access").disabled is True
    assert logging.getLogger("uvicorn.error").disabled is False


def test_request_ids_isolate_concurrent_requests_and_health_is_quiet(settings: Settings) -> None:
    app = create_app(settings, StubDetector())

    @app.get("/test/context")
    def inspect_context(request: Request):
        log_event(logging.getLogger("visionlab.test"), "test.context", "COMPLETE Context captured")
        return {"request_id": request.state.request_id}

    ids = ["08a937ff-72d5-4e0d-bbd6-fbf996ca634b", "fc69ea26-25f9-456c-a37c-5737ef4d1f4e"]
    with TestClient(app) as client:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda value: client.get("/test/context", headers={"X-Request-ID": value}), ids
                )
            )
        assert [response.json()["request_id"] for response in results] == ids
        assert [response.headers["X-Request-ID"] for response in results] == ids
        invalid = client.get("/api/v1/media/limits", headers={"X-Request-ID": "token=secret-value"})
        UUID(invalid.headers["X-Request-ID"])
        assert invalid.headers["X-Request-ID"] != "token=secret-value"
        client.get("/api/v1/health")
    records = events(settings)
    context = [item for item in records if item["event"] == "test.context"]
    assert {item["request_id"] for item in context} == set(ids)
    assert not any(
        item["event"].startswith("request.") and item.get("route") == "/api/v1/health"
        for item in records
    )
    completed = [
        item
        for item in records
        if item["event"] == "request.completed" and item.get("route") == "/test/context"
    ]
    assert len(completed) == 2
    assert all(item["duration_ms"] >= 0 for item in completed)
    assert "secret-value" not in (settings.log_directory / "visionlab.jsonl").read_text(
        encoding="utf-8"
    )


def test_upload_analysis_and_persistence_events_use_one_request_id(settings: Settings) -> None:
    with TestClient(create_app(settings, StubDetector())) as client:
        media_id = upload(client, orientation=6)
        uploaded_id = client.get(f"/api/v1/media/{media_id}").headers["X-Request-ID"]
        response = client.post(f"/api/v1/media/{media_id}/analyze")
        assert response.status_code == 201, response.text
        analysis_id = response.json()["analysis_id"]
        assert response.json()["timings_ms"]["model_initialization"] >= 0
        client.get(f"/api/v1/media/{media_id}/analyses/{analysis_id}")
        client.delete(f"/api/v1/media/{media_id}")
    records = events(settings)
    assert uploaded_id
    upload_events = {item["event"] for item in records if item.get("media_id") == media_id}
    assert {
        "upload.started",
        "upload.streaming",
        "upload.validated",
        "upload.metadata_extracted",
        "upload.thumbnail_created",
        "upload.persisted",
        "upload.completed",
    } - upload_events == {"upload.started"}
    assert {
        "media.persisted",
        "media.deleted",
        "analysis.persisted",
        "analysis.loaded",
        "analysis.deleted",
    } <= upload_events
    run = [item for item in records if item.get("analysis_id") == analysis_id]
    expected = {
        "analysis.started",
        "image.decode_started",
        "image.decode_completed",
        "image.orientation_normalized",
        "image.preprocess_completed",
        "inference.started",
        "inference.completed",
        "detections.validated",
        "analysis.summary_computed",
        "analysis.persistence_started",
        "analysis.persistence_completed",
        "analysis.completed",
    }
    assert expected <= {item["event"] for item in run}
    request_ids = {
        item["request_id"]
        for item in run
        if item["event"] != "analysis.loaded" and item["event"] != "analysis.deleted"
    }
    assert request_ids == {response.headers["X-Request-ID"]}
    complete = next(item for item in run if item["event"] == "analysis.completed")
    assert complete["detection_count"] == 1 and complete["class_counts"] == {"person": 1}
    assert all(
        complete[field] >= 0
        for field in ("duration_ms", "decode_ms", "inference_ms", "persistence_ms")
    )
    assert "private-name.jpg" not in (settings.log_directory / "visionlab.jsonl").read_text(
        encoding="utf-8"
    )


def test_validation_failure_missing_media_and_empty_inference(settings: Settings) -> None:
    with TestClient(create_app(settings, StubDetector([]))) as client:
        bad = client.post(
            "/api/v1/media/upload", files={"file": ("bad.gif", b"GIF89a", "image/gif")}
        )
        assert bad.status_code == 422
        malformed = client.post(
            "/api/v1/media/upload", files={"file": ("bad.png", b"not a png", "image/png")}
        )
        assert malformed.status_code == 422
        missing = client.get("/api/v1/media/00000000-0000-4000-8000-000000000000")
        assert missing.status_code == 404
        media_id = upload(client)
        result = client.post(f"/api/v1/media/{media_id}/analyze")
        assert result.json()["summary"]["total_objects"] == 0
    records = events(settings)
    assert any(
        item["event"] == "upload.failed" and item["error_code"] == "unsupported_format"
        for item in records
    )
    assert any(item["event"] == "upload.cleanup_completed" for item in records)
    assert any(
        item["event"] == "request.failed" and item["error_code"] == "media_not_found"
        for item in records
    )
    assert any(
        item["event"] == "inference.completed" and item["detection_count"] == 0 for item in records
    )
    assert any(
        item["event"] == "analysis.completed" and item["detection_count"] == 0 for item in records
    )
    assert not any(item["event"] == "image.orientation_normalized" for item in records)


def test_model_cold_load_cache_and_prediction_events(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = settings.model_root / "yolo26n.pt"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"test weights")

    class FakeArray:
        def __getitem__(self, _key):
            return self

        def copy(self):
            return self

    class FakeModel:
        def predict(self, **_kwargs):
            box = SimpleNamespace(
                cls=SimpleNamespace(item=lambda: 0),
                conf=SimpleNamespace(item=lambda: 0.8),
                xyxy=[SimpleNamespace(tolist=lambda: [1.0, 2.0, 9.0, 10.0])],
            )
            return [SimpleNamespace(names={0: "person"}, boxes=[box])]

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    )
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=lambda _path: FakeModel()))
    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace(asarray=lambda _image: FakeArray()))
    monkeypatch.setattr("app.providers.detector.importlib.metadata.version", lambda _name: "test")
    configure_logging(settings)
    detector = YOLO26Detector(settings)
    assert detector.get_status().state == "unavailable"
    detector.load_model()
    detector.load_model()
    assert detector.detect(Image.new("RGB", (16, 12)), DetectionParameters())[0].label == "person"
    records = events(settings)
    kinds = [item["event"] for item in records]
    assert kinds.count("model.load_started") == 1
    assert kinds.count("model.load_completed") == 1
    assert kinds.count("model.cache_hit") == 1
    assert "model.inference_started" in kinds and "model.inference_completed" in kinds
    assert (
        next(item for item in records if item["event"] == "model.load_completed")["duration_ms"]
        >= 0
    )


def test_jsonl_rotation_keeps_bounded_backups(settings: Settings) -> None:
    from logging.handlers import RotatingFileHandler

    settings.log_directory.mkdir()
    handler = RotatingFileHandler(
        settings.log_directory / "small.jsonl", maxBytes=300, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    isolated = logging.getLogger("rotation-test")
    isolated.setLevel(logging.INFO)
    isolated.propagate = False
    isolated.addHandler(handler)
    for index in range(20):
        isolated.info("entry %s", index)
    isolated.removeHandler(handler)
    handler.close()
    files = list(settings.log_directory.glob("small.jsonl*"))
    assert len(files) == 3
    assert all(path.stat().st_size <= 300 for path in files)
    assert all(json.loads(line) for path in files for line in path.read_text().splitlines())


def test_unhandled_error_has_safe_reference_and_one_traceback(settings: Settings) -> None:
    configured = settings.model_copy(update={"environment": "development"})
    app = create_app(configured, StubDetector())

    @app.get("/test/crash")
    def crash():
        raise RuntimeError("token=private-value")

    with TestClient(app) as client:
        response = client.get("/test/crash")
        assert response.status_code == 500
        assert response.json() == {
            "error": {"code": "internal_error", "message": "Internal server error."}
        }
        request_id = response.headers["X-Request-ID"]
    records = [item for item in events(configured) if item["request_id"] == request_id]
    failures = [item for item in records if item["event"] == "request.failed"]
    assert len(failures) == 1
    assert failures[0]["exception_type"] == "RuntimeError"
    assert failures[0]["traceback"]
    assert "private-value" not in (configured.log_directory / "visionlab.jsonl").read_text(
        encoding="utf-8"
    )


def test_body_limit_and_cleanup_failures_are_logged(settings: Settings) -> None:
    configured = settings.model_copy(update={"max_video_bytes": 64, "max_image_bytes": 64})
    with TestClient(create_app(configured, StubDetector())) as client:
        oversized = client.post(
            "/api/v1/media/upload", files={"file": ("large.png", b"x" * 70_000, "image/png")}
        )
        assert oversized.status_code == 413
        assert oversized.headers["X-Request-ID"]
    records = events(configured)
    assert any(
        item["event"] == "upload.failed" and item["error_code"] == "body_too_large"
        for item in records
    )
    assert any(item["event"] == "request.failed" and item["status_code"] == 413 for item in records)


def test_missing_model_and_invalid_boxes_log_real_failures(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        media_id = upload(client)
        response = client.post(f"/api/v1/media/{media_id}/analyze")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_not_installed"
    records = events(settings)
    assert any(
        item["event"] == "model.load_failed" and item["error_code"] == "model_not_installed"
        for item in records
    )
    assert not any(item["event"] == "model.load_completed" for item in records)

    other = settings.model_copy(
        update={"log_directory": settings.log_directory.parent / "other-logs"}
    )
    with TestClient(
        create_app(other, StubDetector([RawDetection(0, "person", 0.9, (float("nan"), 0, 5, 5))]))
    ) as client:
        media_id = upload(client)
        response = client.post(f"/api/v1/media/{media_id}/analyze")
        assert response.status_code == 500
    records = events(other)
    assert any(
        item["event"] == "detections.validation_failed"
        and item["error_code"] == "invalid_bounding_box"
        for item in records
    )
    assert not any(item["event"] == "analysis.completed" for item in records)


def test_slow_warning_and_debug_detection_cap(settings: Settings) -> None:
    configured = settings.model_copy(update={"log_level": "DEBUG", "log_slow_request_ms": 1})
    many = [RawDetection(0, "person", 0.8, (2, 2, 10, 10)) for _ in range(25)]
    with TestClient(create_app(configured, StubDetector(many))) as client:
        media_id = upload(client)
        response = client.post(f"/api/v1/media/{media_id}/analyze")
        assert response.status_code == 201
    records = events(configured)
    assert len([item for item in records if item["event"] == "detection.detail"]) == 20
    assert any(
        item["event"] == "request.slow" and item["level"] == "WARNING" and item["duration_ms"] >= 1
        for item in records
    )
