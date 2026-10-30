"""Opt-in end-to-end checkpoint check with a real uploaded photograph."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.real_model
def test_real_florence_tasks_and_yolo_crop(tmp_path: Path):
    if os.getenv("VISIONLAB_RUN_REAL_FLORENCE") != "1":
        pytest.skip("Set VISIONLAB_RUN_REAL_FLORENCE=1 to run real Florence inference")
    image_path = Path(os.getenv("VISIONLAB_SMOKE_IMAGE", "data/smoke/bus.jpg"))
    model_root = Path("data/models").resolve()
    if not image_path.is_file() or not (model_root / "florence2/model.safetensors").is_file():
        pytest.skip("Install Florence-2 and provide a real smoke-test image")
    settings = Settings(environment="test", model_root=model_root,
        database_url=f"sqlite:///{tmp_path / 'smoke.sqlite'}",
        media_root=tmp_path / "media", thumbnail_root=tmp_path / "thumbs", _env_file=None)
    with TestClient(create_app(settings)) as client:
        with image_path.open("rb") as stream:
            uploaded = client.post("/api/v1/media/upload", files={"file": ("sample.jpg", stream, "image/jpeg")})
        assert uploaded.status_code == 201, uploaded.text
        media_id = uploaded.json()["media_id"]
        root = f"/api/v1/media/{media_id}"
        for mode in ("short", "detailed", "extended"):
            response = client.post(f"{root}/caption", json={"mode": mode})
            assert response.status_code == 201, response.text
            assert response.json()["text"]
            print(mode, response.json()["text"], response.json()["model_load_ms"],
                  response.json()["inference_ms"], flush=True)
        dense = client.post(f"{root}/dense-regions")
        assert dense.status_code == 201, dense.text
        assert dense.json()["regions"], "Sample image should yield real Florence regions"
        print("dense", len(dense.json()["regions"]), dense.json()["inference_ms"], flush=True)
        for region in dense.json()["regions"]:
            box = region["bounding_box"]
            assert box["x"] + box["width"] <= 1.000001
            assert box["y"] + box["height"] <= 1.000001
        detection = client.post(f"{root}/analyze")
        assert detection.status_code == 201, detection.text
        assert detection.json()["detections"]
        described = client.post(f"{root}/regions/describe", json={
            "detection_analysis_id": detection.json()["analysis_id"],
            "detection_id": detection.json()["detections"][0]["id"]})
        assert described.status_code == 201, described.text
        assert described.json()["text"]
        print("selected_object", described.json()["text"], described.json()["inference_ms"], flush=True)
        assert len(client.get(f"{root}/captions").json()) == 5
        assert len(client.get(f"{root}/analyses").json()) == 1
