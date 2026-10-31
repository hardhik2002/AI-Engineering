"""Opt-in to installed local weights and a short real-content video; no cloud calls."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.real_video
def test_real_yolo_bytetrack_florence_video(tmp_path: Path):
    source = Path("data/smoke/bus-4s.mp4")
    weights = Path("data/models/yolo26n.pt")
    florence = Path("data/models/florence2/model.safetensors")
    if not all(path.is_file() for path in (source, weights, florence)):
        pytest.skip("Install YOLO and Florence, then place bus-4s.mp4 in data/smoke")
    settings = Settings(
        environment="test", database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        media_root=tmp_path / "media", thumbnail_root=tmp_path / "thumbs",
        model_root=Path("data/models"), detection_device="cpu", florence_device="cpu",
        log_console_enabled=False, log_file_enabled=False, _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        uploaded = client.post(
            "/api/v1/media/upload",
            files={"file": ("bus-4s.mp4", source.read_bytes(), "video/mp4")},
        )
        assert uploaded.status_code == 201, uploaded.text
        media_id = uploaded.json()["media_id"]
        queued = client.post(
            f"/api/v1/media/{media_id}/video/analyze",
            json={"detection_fps": 1, "caption_interval_seconds": 120},
        )
        assert queued.status_code == 202, queued.text
        job_id, analysis_id = queued.json()["job_id"], queued.json()["analysis_id"]
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            job = client.get(f"/api/v1/video/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.5)
        else:
            pytest.fail("Real local video job timed out")
        assert job["status"] == "completed", job
        frames = client.get(f"/api/v1/video/analyses/{analysis_id}/frames").json()
        captions = client.get(f"/api/v1/video/analyses/{analysis_id}/captions").json()
        assert len(frames) == 4
        assert [frame["timestamp_ms"] for frame in frames] == [0, 1000, 2000, 3000]
        assert all(frame["model"]["name"] == "yolo26n.pt" for frame in frames)
        detections = [item for frame in frames for item in frame["detections"]]
        assert detections, "The bus image should produce real YOLO detections"
        assert all(0 <= item["confidence"] <= 1 for item in detections)
        assert all(0 <= item["bounding_box"]["x"] <= 1 for item in detections)
        assert all(item["track_id"] is None or isinstance(item["track_id"], int)
                   for item in detections)
        assert len(captions) == 1 and captions[0]["source"] == "florence"
        assert captions[0]["timestamp_ms"] == 0 and captions[0]["text"].strip()
        timeline = client.get(f"/api/v1/video/analyses/{analysis_id}/timeline").json()
        assert timeline[0]["timestamp_ms"] == 0
        print(f"real video: {len(frames)} frames, {len(detections)} detections, "
              f"{len({item['track_id'] for item in detections if item['track_id'] is not None})} "
              f"sampled track IDs, {len(captions)} caption, {job['elapsed_ms']:.0f} ms")
