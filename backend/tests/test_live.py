import io
import json
import logging
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app
from app.providers.detector import DetectorError, RawDetection
from app.schemas.vision import DetectionParameters, ModelInfo, ModelStatus
from app.services.live import MAGIC, LiveFrameError


class FakeDetector:
    def __init__(self):
        self.results = [RawDetection(0, "person", 0.9, (16, 12, 48, 36))]
        self.error = None
        self.calls = 0

    def load_model(self):
        pass

    def detect(self, image: Image.Image, _parameters: DetectionParameters):
        self.calls += 1
        if self.error:
            raise self.error
        return self.results

    def get_model_info(self):
        return ModelInfo(name="fake-yolo", device="cpu", version="test", package_version="test")

    def get_status(self):
        return ModelStatus(state="ready", name="fake-yolo", device="cpu")


@pytest.fixture
def setup(tmp_path: Path):
    settings = Settings(
        environment="test", database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        media_root=tmp_path / "media", thumbnail_root=tmp_path / "thumbs",
        model_root=tmp_path / "models", log_console_enabled=False,
        log_file_enabled=True, log_directory=tmp_path / "logs", _env_file=None,
    )
    detector = FakeDetector()
    with TestClient(create_app(settings, detector=detector)) as client:
        yield client, detector, settings


def packet(session_id: str, frame_id: str | None = None, width: int = 64,
           height: int = 48, image: bytes | None = None) -> bytes:
    if image is None:
        stream = io.BytesIO()
        Image.new("RGB", (64, 48), (110, 80, 60)).save(stream, "JPEG")
        image = stream.getvalue()
    metadata = json.dumps({
        "type": "frame.submitted", "session_id": session_id,
        "frame_id": frame_id or str(uuid4()), "captured_at_ms": 120.5,
        "source_width": width, "source_height": height, "encoded_format": "jpeg",
    }).encode()
    return MAGIC + len(metadata).to_bytes(4, "big") + metadata + image


def connect(client: TestClient):
    return client.websocket_connect(
        "/ws/v1/live", headers={"origin": "http://localhost:5180"}
    )


def test_websocket_lifecycle_and_normalized_detection(setup):
    client, detector, _settings = setup
    with connect(client) as socket:
        started = socket.receive_json()
        assert started["type"] == "session.started"
        assert started["protocol_version"] == 1
        assert started["max_in_flight_frames"] == 1
        UUID(started["session_id"])
        frame_id = str(uuid4())
        socket.send_bytes(packet(started["session_id"], frame_id))
        result = socket.receive_json()
        assert result["type"] == "frame.result"
        assert result["frame_id"] == frame_id
        assert result["session_id"] == started["session_id"]
        assert result["source_width"] == 64 and result["source_height"] == 48
        assert result["detections"][0]["bounding_box"] == {
            "x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5,
        }
        assert result["detections"][0]["confidence"] == 0.9
        assert result["inference_ms"] >= 0 and result["processing_ms"] >= 0
        assert result["model"]["name"] == "fake-yolo"
        socket.send_text('{"type": "session.stop"}')
        assert socket.receive_json()["type"] == "session.stopped"
    assert detector.calls == 1
    assert client.app.state.live_service.active_sessions == 0


def test_origin_and_session_limit(setup):
    client, _detector, _settings = setup
    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(
            "/ws/v1/live", headers={"origin": "https://evil.example"}
        ):
            pass
    assert rejected.value.code == 1008
    with connect(client) as first:
        first.receive_json()
        with pytest.raises(WebSocketDisconnect) as full:
            with connect(client):
                pass
        assert full.value.code == 1013
        first.send_text('{"type":"session.stop"}')
        first.receive_json()
    with connect(client) as reopened:
        assert reopened.receive_json()["type"] == "session.started"
        reopened.send_text('{"type":"session.stop"}')
        reopened.receive_json()


def test_invalid_frames_and_session_isolation(setup):
    client, detector, settings = setup
    with connect(client) as socket:
        session = socket.receive_json()["session_id"]
        socket.send_bytes(packet(str(uuid4())))
        assert socket.receive_json()["code"] == "invalid_session"
        socket.send_bytes(packet(session, width=settings.live_max_width + 1))
        assert socket.receive_json()["code"] == "invalid_dimensions"
        socket.send_bytes(packet(session, image=b"not jpeg"))
        assert socket.receive_json()["code"] == "invalid_frame_encoding"
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1008
    assert detector.calls == 0
    with connect(client) as socket:
        session = socket.receive_json()["session_id"]
        socket.send_bytes(packet(session, image=b"x" * (settings.live_max_frame_bytes + 1)))
        assert socket.receive_json()["code"] == "frame_too_large"
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 1009


def test_empty_detection_rate_limit_busy_and_model_error(setup):
    client, detector, _settings = setup
    detector.results = []
    with connect(client) as socket:
        session = socket.receive_json()["session_id"]
        socket.send_bytes(packet(session))
        assert socket.receive_json()["detections"] == []
        socket.send_bytes(packet(session))
        assert socket.receive_json()["reason"] == "rate_limited"
        assert detector.calls == 1
        socket.send_text('{"type":"session.stop"}')
        socket.receive_json()
    capacity = client.app.state.analysis_service.capacity
    assert capacity.acquire(blocking=False)
    try:
        with connect(client) as socket:
            session = socket.receive_json()["session_id"]
            socket.send_bytes(packet(session))
            assert socket.receive_json()["reason"] == "model_busy"
            socket.send_text('{"type":"session.stop"}')
            socket.receive_json()
    finally:
        capacity.release()
    detector.error = DetectorError("model_not_installed", "Install weights.")
    with connect(client) as socket:
        session = socket.receive_json()["session_id"]
        socket.send_bytes(packet(session))
        assert socket.receive_json()["code"] == "model_not_installed"


def test_frame_validation_without_websocket(setup):
    client, _detector, _settings = setup
    service = client.app.state.live_service
    session = uuid4()
    with pytest.raises(LiveFrameError) as error:
        service.unpack(packet(str(session), image=b"\xff\xd8\xffbad"), session)
    assert error.value.code == "invalid_frame_encoding"
    with pytest.raises(LiveFrameError) as error:
        service.unpack(packet(str(session), width=32), session)
    assert error.value.code == "invalid_dimensions"


def test_live_structured_events_include_session_and_frame_ids(setup, caplog):
    client, _detector, settings = setup
    frame_id = str(uuid4())
    with caplog.at_level(logging.DEBUG, logger="visionlab.live"):
        with connect(client) as socket:
            session_id = socket.receive_json()["session_id"]
            socket.send_bytes(packet(session_id, frame_id))
            assert socket.receive_json()["type"] == "frame.result"
            socket.send_bytes(packet(session_id))
            assert socket.receive_json()["type"] == "frame.skipped"
            socket.send_text('{"type":"session.stop"}')
            socket.receive_json()
    events = {getattr(item, "event", None): item for item in caplog.records}
    for event in (
        "live.session_started", "live.frame_received", "live.inference_started",
        "live.inference_completed", "live.frame_skipped", "live.session_stopped",
    ):
        assert event in events
    assert events["live.inference_completed"].session_id == session_id
    assert events["live.inference_completed"].frame_id == frame_id
    saved = [json.loads(line) for line in
             (settings.log_directory / "visionlab.jsonl").read_text().splitlines()]
    completed = next(item for item in saved if item["event"] == "live.inference_completed")
    assert completed["request_id"] == session_id
    assert completed["session_id"] == session_id
    assert completed["frame_id"] == frame_id
