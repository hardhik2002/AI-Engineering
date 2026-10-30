import io
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.providers.captioner import PROMPTS, CaptionError, Florence2CaptionProvider
from app.providers.detector import RawDetection
from app.schemas.caption import CaptionModelInfo
from app.schemas.vision import ModelInfo, ModelStatus
from app.services.caption import normalize_region


class FakeDetector:
    def load_model(self):
        pass

    def detect(self, image, configuration):
        return [RawDetection(0, "person", 0.9, (2, 2, 10, 10))]

    def get_status(self):
        return ModelStatus(state="ready", name="yolo26n.pt", device="cpu")

    def get_model_info(self):
        return ModelInfo(name="yolo26n.pt", device="cpu", version="YOLO26", package_version="test")


class FakeCaptioner:
    successful_tasks: set[str]

    def __init__(self):
        self.successful_tasks = set()
        self.loads = 0
        self.sizes: list[tuple[int, int]] = []
        self.bad = False

    def get_status(self):
        return {"state": "ready", "name": "fake", "revision": "test", "device": "cpu"}

    def load_model(self):
        self.loads += 1
        return 10.0 if self.loads == 1 else 0.0

    def generate(self, image, task):
        self.sizes.append(image.size)
        if self.bad:
            return {PROMPTS[task]: ""}, 3.0
        if task == "dense":
            return {
                "<DENSE_REGION_CAPTION>": {"bboxes": [[1, 1, 8, 8]], "labels": ["A person"]}
            }, 3.0
        return {PROMPTS[task]: f"Actual provider text for {task}"}, 3.0

    def model_info(self):
        return CaptionModelInfo(
            checkpoint="fake", revision="test", device="cpu", package_version="test"
        )


@pytest.fixture
def setup(tmp_path: Path):
    settings = Settings(
        environment="test",
        log_console_enabled=False,
        log_file_enabled=True,
        log_directory=tmp_path / "logs",
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        media_root=tmp_path / "media",
        thumbnail_root=tmp_path / "thumbs",
        model_root=tmp_path / "models",
        _env_file=None,
    )
    provider = FakeCaptioner()
    with TestClient(create_app(settings, FakeDetector(), provider)) as client:
        image = Image.new("RGB", (16, 12), "red")
        stream = io.BytesIO()
        image.save(stream, format="JPEG")
        uploaded = client.post(
            "/api/v1/media/upload", files={"file": ("photo.jpg", stream.getvalue(), "image/jpeg")}
        )
        assert uploaded.status_code == 201
        yield client, uploaded.json()["media_id"], provider, settings


def test_task_mapping():
    assert PROMPTS == {
        "short": "<CAPTION>",
        "detailed": "<DETAILED_CAPTION>",
        "extended": "<MORE_DETAILED_CAPTION>",
        "dense": "<DENSE_REGION_CAPTION>",
        "selected_object": "<MORE_DETAILED_CAPTION>",
    }


def test_caption_modes_persistence_capabilities_and_logs(setup):
    client, media_id, provider, settings = setup
    url = f"/api/v1/media/{media_id}"
    assert (
        client.get("/api/v1/vision/capabilities").json()["image_captioning_short"] == "unavailable"
    )
    for mode in ("short", "detailed", "extended"):
        response = client.post(f"{url}/caption", json={"mode": mode})
        assert response.status_code == 201, response.text
        assert response.json()["text"] == f"Actual provider text for {mode}"
        assert response.headers["X-Request-ID"]
    assert provider.loads == 3
    assert len(client.get(f"{url}/captions").json()) == 3
    assert client.get(f"{url}/analyses").json() == []
    assert (
        client.get("/api/v1/vision/capabilities").json()["image_captioning_extended"] == "available"
    )
    text = (settings.log_directory / "visionlab.jsonl").read_text(encoding="utf-8")
    assert "caption.inference_completed" in text and "caption.persisted" in text
    assert "Actual provider text" not in text


def test_dense_regions_selected_object_and_cascade(setup):
    client, media_id, provider, settings = setup
    url = f"/api/v1/media/{media_id}"
    dense = client.post(f"{url}/dense-regions")
    assert dense.status_code == 201, dense.text
    assert dense.json()["regions"][0]["bounding_box"] == {
        "x": 1 / 16,
        "y": 1 / 12,
        "width": 7 / 16,
        "height": 7 / 12,
    }
    detection = client.post(f"{url}/analyze").json()
    selected = client.post(
        f"{url}/regions/describe",
        json={
            "detection_analysis_id": detection["analysis_id"],
            "detection_id": detection["detections"][0]["id"],
        },
    )
    assert selected.status_code == 201, selected.text
    assert provider.sizes[-1] == (8, 8)
    assert selected.json()["detection_id"] == detection["detections"][0]["id"]
    assert len(client.get(f"{url}/captions").json()) == 2
    assert len(client.get(f"{url}/analyses").json()) == 1
    assert client.delete(url).status_code == 204
    import sqlite3

    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0


def test_errors_are_safe_and_capabilities_remain_unavailable(setup):
    client, media_id, provider, _ = setup
    url = f"/api/v1/media/{media_id}"
    assert client.post(f"{url}/caption", json={"mode": "invalid"}).status_code == 422
    assert (
        client.post(
            f"{url}/regions/describe",
            json={"detection_analysis_id": media_id, "detection_id": media_id},
        ).status_code
        == 404
    )
    provider.bad = True
    failed = client.post(f"{url}/caption", json={"mode": "short"})
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "malformed_caption"
    assert failed.headers["X-Request-ID"]
    assert (
        client.get("/api/v1/vision/capabilities").json()["image_captioning_short"] == "unavailable"
    )


def test_normalized_box_validation():
    assert normalize_region([0, 0, 10, 20], 20, 40).model_dump() == {
        "x": 0,
        "y": 0,
        "width": 0.5,
        "height": 0.5,
    }
    for values in ([math.nan, 0, 1, 1], [4, 4, 2, 2], [30, 0, 40, 10], [1, 2]):
        with pytest.raises(CaptionError):
            normalize_region(values, 20, 40)


def test_exif_oriented_caption_and_bounded_capacity(setup):
    client, _, provider, _ = setup
    image = Image.new("RGB", (16, 12), "blue")
    exif = Image.Exif()
    exif[274] = 6
    stream = io.BytesIO()
    image.save(stream, format="JPEG", exif=exif)
    uploaded = client.post(
        "/api/v1/media/upload", files={"file": ("rotated.jpg", stream.getvalue(), "image/jpeg")}
    )
    assert uploaded.status_code == 201
    media_id = uploaded.json()["media_id"]
    assert uploaded.json()["width"] == 12 and uploaded.json()["height"] == 16
    captioned = client.post(f"/api/v1/media/{media_id}/caption", json={"mode": "short"})
    assert captioned.status_code == 201
    assert provider.sizes[-1] == (12, 16)
    service = client.app.state.caption_service
    assert service.capacity.acquire(blocking=False)
    try:
        busy = client.post(f"/api/v1/media/{media_id}/caption", json={"mode": "short"})
        assert busy.status_code == 429
        assert busy.json()["error"]["code"] == "caption_busy"
    finally:
        service.capacity.release()


def test_local_provider_requires_pinned_installation(tmp_path: Path):
    settings = Settings(model_root=tmp_path, _env_file=None)
    provider = Florence2CaptionProvider(settings)
    assert provider.get_status()["state"] == "not_installed"
    with pytest.raises(CaptionError) as error:
        provider.load_model()
    assert error.value.code == "caption_model_not_installed"
