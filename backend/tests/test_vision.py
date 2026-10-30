import io
import sys
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.providers.detector import DetectorError, RawDetection, YOLO26Detector
from app.repositories.media import MediaRepository
from app.schemas.media import MediaAsset
from app.schemas.vision import DetectionParameters, ModelInfo, ModelStatus
from app.services.analysis import normalized_detection


class FakeDetector:
    def __init__(self, results: list[RawDetection] | None = None):
        self.results = (
            results if results is not None else [RawDetection(0, "person", 0.92, (4, 2, 12, 10))]
        )
        self.calls = 0
        self.images: list[tuple[int, int]] = []
        self.error: DetectorError | None = None

    def load_model(self) -> None:
        pass

    def detect(self, image: Image.Image, configuration: DetectionParameters) -> list[RawDetection]:
        self.calls += 1
        self.images.append(image.size)
        if self.error:
            raise self.error
        return self.results

    def get_status(self) -> ModelStatus:
        return ModelStatus(state="ready", name="yolo26n.pt", device="cpu")

    def get_model_info(self) -> ModelInfo:
        return ModelInfo(name="yolo26n.pt", device="cpu", version="YOLO26", package_version="test")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'vision.sqlite3'}",
        media_root=tmp_path / "media",
        thumbnail_root=tmp_path / "thumbs",
        model_root=tmp_path / "models",
        _env_file=None,
    )


def upload_image(client: TestClient, orientation: int | None = None) -> str:
    image = Image.new("RGB", (16, 12), "green")
    output = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(output, format="JPEG", **({"exif": exif} if orientation else {}))
    response = client.post(
        "/api/v1/media/upload", files={"file": ("sample.jpg", output.getvalue(), "image/jpeg")}
    )
    assert response.status_code == 201, response.text
    return response.json()["media_id"]


def test_detection_persists_reanalysis_and_cascade(settings: Settings) -> None:
    fake = FakeDetector()
    with TestClient(create_app(settings, fake)) as client:
        media_id = upload_image(client)
        url = f"/api/v1/media/{media_id}/analyze"
        first = client.post(url)
        assert first.status_code == 201, first.text
        result = first.json()
        assert result["status"] == "completed"
        assert result["summary"] == {"total_objects": 1, "class_counts": {"person": 1}}
        assert result["image"] == {"width": 16, "height": 12, "coordinate_space": "exif_oriented"}
        assert result["detections"][0]["bounding_box"] == {
            "x": 0.25,
            "y": 2 / 12,
            "width": 0.5,
            "height": 8 / 12,
        }
        assert result["timings_ms"]["total"] >= result["timings_ms"]["inference"]
        UUID(result["detections"][0]["id"])
        second = client.post(
            url, json={"tasks": ["object_detection"], "parameters": {"confidence": 0.5}}
        )
        assert second.status_code == 201
        assert second.json()["analysis_id"] != result["analysis_id"]
        assert second.json()["parameters"]["confidence"] == 0.5
        assert fake.calls == 2
        assert len(client.get(f"/api/v1/media/{media_id}/analyses").json()) == 2
        assert (
            client.get(f"/api/v1/media/{media_id}/analyses/{result['analysis_id']}").json()
            == result
        )
        assert client.delete(f"/api/v1/media/{media_id}").status_code == 204
        assert client.get(f"/api/v1/media/{media_id}/analyses").status_code == 404
    import sqlite3

    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0


def test_empty_result_and_exif_orientation(settings: Settings) -> None:
    fake = FakeDetector([])
    with TestClient(create_app(settings, fake)) as client:
        media_id = upload_image(client, orientation=6)
        result = client.post(f"/api/v1/media/{media_id}/analyze").json()
        assert fake.images == [(12, 16)]
        assert result["image"]["width"] == 12
        assert result["image"]["height"] == 16
        assert result["detections"] == []
        assert result["summary"] == {"total_objects": 0, "class_counts": {}}


def test_validation_errors_and_capabilities(settings: Settings) -> None:
    fake = FakeDetector()
    with TestClient(create_app(settings, fake)) as client:
        assert (
            client.get("/api/v1/vision/capabilities").json()["object_detection_image"]
            == "available"
        )
        assert client.get("/api/v1/capabilities").json()[3]["status"] == "available"
        assert client.post("/api/v1/media/../../analyze").status_code in (404, 405)
        assert (
            client.post("/api/v1/media/00000000-0000-4000-8000-000000000000/analyze").status_code
            == 404
        )
        media_id = upload_image(client)
        endpoint = f"/api/v1/media/{media_id}/analyze"
        for body in ({"parameters": {"confidence": 0}}, {"parameters": {"iou": 2}}, {"tasks": []}):
            response = client.post(endpoint, json=body)
            assert response.status_code == 422
        assert fake.calls == 0
        fake.error = DetectorError("model_initialization_failed", "Model cannot load.")
        response = client.post(endpoint)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "model_initialization_failed"
        assert client.get(f"/api/v1/media/{media_id}/analyses").json()[0]["status"] == "failed"


def test_server_defaults_and_partial_overrides(settings: Settings) -> None:
    configured = settings.model_copy(update={"detection_confidence": 0.35, "detection_iou": 0.6})
    with TestClient(create_app(configured, FakeDetector([]))) as client:
        media_id = upload_image(client)
        assert (
            client.post(f"/api/v1/media/{media_id}/analyze", json={}).json()["parameters"][
                "confidence"
            ]
            == 0.35
        )
        overridden = client.post(
            f"/api/v1/media/{media_id}/analyze", json={"parameters": {"confidence": 0.7}}
        ).json()["parameters"]
        assert overridden["confidence"] == 0.7
        assert overridden["iou"] == 0.6


def test_invalid_detector_coordinates() -> None:
    for box in ((float("nan"), 0, 5, 5), (8, 0, 3, 5), (-10, 0, -1, 5)):
        with pytest.raises(ValueError):
            normalized_detection(RawDetection(0, "person", 0.9, box), 10, 10)
    clipped = normalized_detection(RawDetection(0, "person", 0.7, (-2, 2, 12, 8)), 10, 10)
    assert clipped.bounding_box.x == 0
    assert clipped.bounding_box.width == 1


def test_model_status_missing_weights(settings: Settings) -> None:
    detector = YOLO26Detector(settings)
    assert detector.get_status().state == "not_installed"
    with pytest.raises(DetectorError, match="not installed"):
        detector.load_model()
    assert detector.get_status().state == "not_installed"


def test_model_load_is_cached_and_cuda_failure_is_reported(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    weights = settings.model_root / "yolo26n.pt"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"test weights")
    loaded: list[str] = []
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
    )
    monkeypatch.setitem(
        sys.modules,
        "ultralytics",
        SimpleNamespace(YOLO=lambda path: loaded.append(path) or object()),
    )
    detector = YOLO26Detector(settings)
    assert detector.get_status().state == "unavailable"
    detector.load_model()
    detector.load_model()
    assert len(loaded) == 1
    assert detector.get_status().state == "ready"
    assert len(detector.get_model_info().weights_sha256 or "") == 64
    cuda = YOLO26Detector(settings.model_copy(update={"detection_device": "cuda"}))
    with pytest.raises(DetectorError) as error:
        cuda.load_model()
    assert error.value.code == "device_unavailable"
    assert cuda.get_status().state == "unavailable"


def test_video_analysis_is_explicitly_unsupported(settings: Settings) -> None:
    fake = FakeDetector()
    with TestClient(create_app(settings, fake)) as client:
        media_id = "92f98d26-e6e6-49e7-bf9c-f1b7d31de121"
        MediaRepository(settings.database_path).insert(
            MediaAsset(
                media_id=media_id,
                original_filename="clip.mp4",
                media_type="video",
                detected_mime_type="video/mp4",
                width=640,
                height=360,
                file_size_bytes=8,
                duration_ms=1000,
                frame_rate=30,
                video_codec="h264",
                playback_compatibility="likely",
                created_at=datetime.now(UTC),
                sha256="0" * 64,
                thumbnail_available=False,
            ),
            f"{media_id}.mp4",
            None,
        )
        response = client.post(f"/api/v1/media/{media_id}/analyze")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unsupported_media_task"
        assert fake.calls == 0


def test_large_image_boxes_normalize_to_original_dimensions(settings: Settings) -> None:
    fake = FakeDetector([RawDetection(0, "person", 0.8, (160, 80, 320, 240))])
    resized_settings = settings.model_copy(update={"detection_max_source_side": 640})
    with TestClient(create_app(resized_settings, fake)) as client:
        image = Image.new("RGB", (800, 400), "green")
        output = io.BytesIO()
        image.save(output, format="PNG")
        uploaded = client.post(
            "/api/v1/media/upload", files={"file": ("large.png", output.getvalue(), "image/png")}
        )
        media_id = uploaded.json()["media_id"]
        result = client.post(f"/api/v1/media/{media_id}/analyze").json()
        assert fake.images == [(640, 320)]
        assert result["image"] == {"width": 800, "height": 400, "coordinate_space": "exif_oriented"}
        assert result["detections"][0]["bounding_box"] == {
            "x": 0.25,
            "y": 0.25,
            "width": 0.25,
            "height": 0.5,
        }


def test_capacity_rejects_parallel_analysis(settings: Settings) -> None:
    entered, release = Event(), Event()

    class SlowDetector(FakeDetector):
        def detect(
            self, image: Image.Image, configuration: DetectionParameters
        ) -> list[RawDetection]:
            entered.set()
            release.wait(5)
            return super().detect(image, configuration)

    with TestClient(create_app(settings, SlowDetector())) as client:
        media_id = upload_image(client)
        endpoint = f"/api/v1/media/{media_id}/analyze"
        worker = Thread(target=lambda: client.post(endpoint))
        worker.start()
        assert entered.wait(5)
        busy = client.post(endpoint)
        assert busy.status_code == 429
        assert busy.json()["error"]["code"] == "model_busy"
        release.set()
        worker.join(5)
