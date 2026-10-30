"""Optional end-to-end smoke test with real local weights and a known local photograph."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.real_model
def test_yolo26_image_inference(tmp_path: Path) -> None:
    if os.environ.get("VISIONLAB_RUN_REAL_MODEL") != "1":
        pytest.skip("Set VISIONLAB_RUN_REAL_MODEL=1 for the optional real-model smoke test")
    photograph = Path(os.environ.get("VISIONLAB_SMOKE_IMAGE", "data/smoke/bus.jpg"))
    weights = Path("data/models/yolo26n.pt")
    if not photograph.is_file() or not weights.is_file():
        pytest.skip("Install yolo26n.pt and provide VISIONLAB_SMOKE_IMAGE to run real inference")
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'smoke.sqlite3'}",
        media_root=tmp_path / "media",
        thumbnail_root=tmp_path / "thumbs",
        model_root=weights.parent,
        detection_device="cpu",
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        uploaded = client.post(
            "/api/v1/media/upload",
            files={"file": ("smoke.jpg", photograph.read_bytes(), "image/jpeg")},
        )
        assert uploaded.status_code == 201, uploaded.text
        media_id = uploaded.json()["media_id"]
        response = client.post(f"/api/v1/media/{media_id}/analyze")
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["status"] == "completed"
        assert result["model"]["provider"] == "ultralytics"
        assert result["model"]["name"] == "yolo26n.pt"
        assert result["model"]["device"] == "cpu"
        assert len(result["model"]["weights_sha256"]) == 64
        assert result["summary"]["total_objects"] == len(result["detections"])
        print("real inference:", result["summary"], result["timings_ms"])
        assert client.get("/api/v1/vision/models").json()[0]["state"] == "ready"
        repeat = client.post(f"/api/v1/media/{media_id}/analyze")
        assert repeat.status_code == 201, repeat.text
        assert repeat.json()["analysis_id"] != result["analysis_id"]
        print("warm inference:", repeat.json()["timings_ms"])
        for detection in result["detections"]:
            box = detection["bounding_box"]
            assert all(0 <= box[key] <= 1 for key in ("x", "y", "width", "height"))
            assert box["x"] + box["width"] <= 1.000001
            assert box["y"] + box["height"] <= 1.000001
