import time
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.providers.multimodal import VisionResult
from app.providers.video_tracker import TrackedRawDetection
from app.schemas.caption import CaptionModelInfo
from app.schemas.multimodal import TokenUsage, VQAAnswer
from app.schemas.video import VideoAnalysis, VideoAnalyzeRequest, VideoJob
from app.schemas.vision import ModelInfo
from app.services.video_decode import (
    VideoDecodeError,
    iter_pts_frames,
    nearest_frames,
    sampled_frames,
)

av = pytest.importorskip("av")


def make_video(path: Path, pts: list[int] | None = None) -> bytes:
    import numpy as np

    points = pts or list(range(8))
    with av.open(str(path), "w") as container:
        stream = container.add_stream("mpeg4", rate=4)
        stream.width, stream.height, stream.pix_fmt = 64, 48, "yuv420p"
        for index, point in enumerate(points):
            array = np.zeros((48, 64, 3), dtype=np.uint8)
            array[:, :, 0] = 100 + index
            frame = av.VideoFrame.from_ndarray(array, format="rgb24")
            frame.pts = point
            frame.time_base = Fraction(1, 4)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path.read_bytes()


class FakeTracker:
    def __init__(self):
        self.starts = 0
        self.empty = False
        self.delay = 0.0
        self.missing_id = False
        self.fail = False

    def start(self):
        self.starts += 1

    def track(self, image, _configuration):
        if self.delay:
            time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("test tracker failure")
        if self.empty:
            return [], 1.5
        return [
            TrackedRawDetection(
                0, "object", 0.8, (2, 3, 20, 30), None if self.missing_id else 1
            )
        ], 1.5

    def detect(self, image, configuration):
        detections, duration = self.track(image, configuration)
        for item in detections:
            item.track_id = None
        return detections, duration

    def model_info(self):
        return ModelInfo(name="fake-yolo", device="cpu", version="test", package_version="test")


class FakeCaption:
    successful_tasks = set()

    def get_status(self):
        return {"state": "ready", "name": "fake", "revision": "test", "device": "cpu"}

    def load_model(self):
        return 0.0

    def generate(self, image, task):
        return {"<CAPTION>": "Actual provider caption."}, 2.0

    def model_info(self):
        return CaptionModelInfo(
            checkpoint="fake", revision="test", device="cpu", package_version="test"
        )


class FakeVision:
    frames = None

    def status(self):
        return {"provider": "openai", "state": "configured", "model": "fake"}

    async def answer_frames(self, frames, question, history):
        self.frames = frames
        return VisionResult(
            VQAAnswer(
                answer="Sampled frames show a colored field.",
                grounding_status="supported",
                uncertainty_note=None,
            ),
            4.0,
            TokenUsage(input_tokens=10, output_tokens=8, total_tokens=18),
            "fake",
        )


@pytest.fixture
def setup(tmp_path: Path):
    settings = Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        media_root=tmp_path / "media",
        thumbnail_root=tmp_path / "thumbs",
        model_root=tmp_path / "models",
        log_console_enabled=False,
        log_file_enabled=False,
        _env_file=None,
    )
    tracker, caption, vision = FakeTracker(), FakeCaption(), FakeVision()
    with TestClient(
        create_app(
            settings, caption_provider=caption, multimodal_provider=vision, video_tracker=tracker
        )
    ) as client:
        data = make_video(tmp_path / "clip.mp4")
        response = client.post(
            "/api/v1/media/upload", files={"file": ("clip.mp4", data, "video/mp4")}
        )
        assert response.status_code == 201, response.text
        yield client, response.json()["media_id"], tracker, vision, settings


def wait_job(client: TestClient, job_id: str, timeout: float = 20) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/video/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"completed", "failed", "cancelled", "interrupted"}:
            return job
        time.sleep(0.05)
    pytest.fail("Video job did not finish in time")


def test_pts_sampling_and_nearest_frame(tmp_path: Path):
    path = tmp_path / "variable.mp4"
    make_video(path, [0, 1, 3, 6])
    settings = Settings(environment="test", _env_file=None)
    pts = list(iter_pts_frames(path, settings))
    assert [item.timestamp_ms for item in pts] == [0, 250, 750, 1500]
    asset = type("Asset", (), {"width": 64, "height": 48})()
    sampled = list(sampled_frames(path, asset, settings, 2, 10))
    assert [item.timestamp_ms for item in sampled] == [0, 750, 1500]
    nearest = nearest_frames(path, asset, settings, [700, 1400], 64)
    assert [item[0] for item in nearest] == [750, 1500]


def test_video_job_tracking_captions_persistence_and_pagination(setup):
    client, media_id, tracker, _vision, settings = setup
    response = client.post(
        f"/api/v1/media/{media_id}/video/analyze",
        json={
            "detection_fps": 2,
            "caption_interval_seconds": 1,
        },
    )
    assert response.status_code == 202, response.text
    job = wait_job(client, response.json()["job_id"])
    assert job["status"] == "completed", job
    analysis_id = job["analysis_id"]
    analyses = client.get(f"/api/v1/media/{media_id}/video/analyses").json()
    assert analyses[0]["processed_frames"] == 4
    frames = client.get(f"/api/v1/video/analyses/{analysis_id}/frames").json()
    assert [item["timestamp_ms"] for item in frames] == [0, 500, 1000, 1500]
    assert all(item["source_pts"] is not None and item["time_base"] for item in frames)
    assert frames[0]["detections"][0]["track_id"] == 1
    assert frames[0]["detections"][0]["bounding_box"]["x"] == pytest.approx(2 / 64)
    assert (
        len(
            client.get(
                f"/api/v1/video/analyses/{analysis_id}/frames?start_ms=500&end_ms=1000&limit=1"
            ).json()
        )
        == 1
    )
    captions = client.get(f"/api/v1/video/analyses/{analysis_id}/captions").json()
    assert [item["timestamp_ms"] for item in captions] == [0, 1000]
    assert all(item["text"] == "Actual provider caption." for item in captions)
    assert (
        client.get(f"/api/v1/video/analyses/{analysis_id}/tracks").json()[0]["sampled_observations"]
        == 4
    )
    assert len(client.get(f"/api/v1/video/analyses/{analysis_id}/timeline").json()) == 4
    assert tracker.starts == 1
    patch = client.patch(
        f"/api/v1/video/analyses/{analysis_id}/captions/{captions[0]['caption_id']}",
        json={"edited_text": "Human edited.", "expected_version": 1},
    )
    assert patch.status_code == 200 and patch.json()["text"] == "Actual provider caption."
    assert patch.json()["edited_text"] == "Human edited."
    assert (
        client.patch(
            f"/api/v1/video/analyses/{analysis_id}/captions/{captions[0]['caption_id']}",
            json={"edited_text": "stale", "expected_version": 1},
        ).status_code
        == 409
    )
    with TestClient(
        create_app(
            settings,
            caption_provider=FakeCaption(),
            multimodal_provider=FakeVision(),
            video_tracker=FakeTracker(),
        )
    ) as reopened:
        assert reopened.get(f"/api/v1/video/analyses/{analysis_id}/frames").json() == frames
    assert client.delete(f"/api/v1/media/{media_id}").status_code == 204
    assert client.get(f"/api/v1/video/analyses/{analysis_id}/frames").status_code == 404


def test_tracking_reset_empty_detection_and_cancel(setup):
    client, media_id, tracker, _vision, _settings = setup
    tracker.empty = True
    first = client.post(
        f"/api/v1/media/{media_id}/video/analyze", json={"generate_captions": False}
    ).json()
    assert wait_job(client, first["job_id"])["status"] == "completed"
    frames = client.get(f"/api/v1/video/analyses/{first['analysis_id']}/frames").json()
    assert frames and all(item["detections"] == [] for item in frames)
    tracker.delay = 0.2
    second = client.post(
        f"/api/v1/media/{media_id}/video/analyze", json={"generate_captions": False}
    ).json()
    cancelled = client.post(f"/api/v1/video/jobs/{second['job_id']}/cancel")
    assert cancelled.status_code == 200
    assert wait_job(client, second["job_id"])["status"] == "cancelled"
    third = client.post(
        f"/api/v1/media/{media_id}/video/analyze", json={"generate_captions": False}
    ).json()
    assert wait_job(client, third["job_id"])["status"] == "completed"
    assert tracker.starts >= 2


def test_restart_marks_active_jobs_interrupted(setup):
    client, media_id, _tracker, _vision, settings = setup
    now = datetime.now(UTC)
    analysis = VideoAnalysis(
        analysis_id=str(uuid4()),
        media_id=media_id,
        job_id=str(uuid4()),
        parameters=VideoAnalyzeRequest(),
        status="running",
        created_at=now,
        duration_ms=2000,
    )
    job = VideoJob(
        job_id=analysis.job_id,
        analysis_id=analysis.analysis_id,
        media_id=media_id,
        status="running",
        stage="processing",
        created_at=now,
        updated_at=now,
    )
    client.app.state.video_service.repository.create(analysis, job)
    with TestClient(
        create_app(
            settings,
            caption_provider=FakeCaption(),
            multimodal_provider=FakeVision(),
            video_tracker=FakeTracker(),
        )
    ) as reopened:
        result = reopened.get(f"/api/v1/video/jobs/{job.job_id}").json()
        assert result["status"] == "interrupted"
        assert (
            reopened.get(f"/api/v1/video/analyses/{analysis.analysis_id}").json()["status"]
            == "interrupted"
        )


def test_video_vqa_consent_frame_selection_and_history(setup):
    client, media_id, _tracker, vision, _settings = setup
    url = f"/api/v1/media/{media_id}/video/vqa"
    body = {"question": "What is shown?", "start_ms": 0, "end_ms": 1500}
    assert client.post(url, json=body).status_code == 403
    assert vision.frames is None
    result = client.post(url, json=body | {"consent_external_transfer": True})
    assert result.status_code == 201, result.text
    assert result.json()["examined_timestamps_ms"] == [0, 1500]
    assert len(vision.frames) == 2
    assert all(url.startswith("data:image/jpeg;base64,") for _, url in vision.frames)
    conversation = result.json()["conversation"]
    assert conversation["messages"][1]["frame_timestamps_ms"] == [0, 1500]
    followup = client.post(
        url,
        json=body
        | {"conversation_id": conversation["conversation_id"], "consent_external_transfer": True},
    )
    assert followup.status_code == 201
    assert len(followup.json()["conversation"]["messages"]) == 4
    assert (
        client.post(
            url, json=body | {"end_ms": 999999, "consent_external_transfer": True}
        ).status_code
        == 422
    )


def test_decode_failure_and_sampling_limit(tmp_path: Path):
    with pytest.raises(VideoDecodeError) as error:
        list(iter_pts_frames(tmp_path / "missing.mp4", Settings(_env_file=None)))
    assert error.value.code == "video_probe_failed"
    path = tmp_path / "clip.mp4"
    make_video(path)
    asset = type("Asset", (), {"width": 64, "height": 48})()
    selected = list(sampled_frames(path, asset, Settings(_env_file=None), 4, 2))
    assert [item.timestamp_ms for item in selected] == [0, 250]


def test_missing_track_ids_provider_failure_and_retry(setup):
    client, media_id, tracker, _vision, _settings = setup
    tracker.missing_id = True
    first = client.post(
        f"/api/v1/media/{media_id}/video/analyze", json={"generate_captions": False}
    ).json()
    assert wait_job(client, first["job_id"])["status"] == "completed"
    frames = client.get(f"/api/v1/video/analyses/{first['analysis_id']}/frames").json()
    assert all(
        detection["track_id"] is None
        for frame in frames
        for detection in frame["detections"]
    )
    assert client.get(f"/api/v1/video/analyses/{first['analysis_id']}/tracks").json() == []
    tracker.fail = True
    failed = client.post(
        f"/api/v1/media/{media_id}/video/analyze", json={"generate_captions": False}
    ).json()
    assert wait_job(client, failed["job_id"])["status"] == "failed"
    tracker.fail = False
    retried = client.post(
        f"/api/v1/media/{media_id}/video/analyze", json={"generate_captions": False}
    ).json()
    assert wait_job(client, retried["job_id"])["status"] == "completed"
    assert tracker.starts == 3


def test_on_demand_caption_and_terminal_sse(setup):
    client, media_id, _tracker, _vision, _settings = setup
    first = client.post(
        f"/api/v1/media/{media_id}/video/analyze", json={"generate_captions": False}
    ).json()
    assert wait_job(client, first["job_id"])["status"] == "completed"
    created = client.post(
        f"/api/v1/media/{media_id}/video/analyses/{first['analysis_id']}/captions",
        json={"timestamp_ms": 625},
    )
    assert created.status_code == 202
    assert wait_job(client, created.json()["job_id"])["status"] == "completed"
    captions = client.get(f"/api/v1/video/analyses/{first['analysis_id']}/captions").json()
    assert len(captions) == 1
    assert captions[0]["timestamp_ms"] == 500
    assert captions[0]["frame_id"] is None
    event = client.get(
        f"/api/v1/video/jobs/{created.json()['job_id']}/events",
        headers={"Last-Event-ID": "0"},
    )
    assert event.status_code == 200
    assert "event: job" in event.text and '"status": "completed"' in event.text
