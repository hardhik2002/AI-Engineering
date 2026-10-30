import io
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'media.sqlite3'}",
        media_root=tmp_path / "media",
        thumbnail_root=tmp_path / "thumbnails",
        _env_file=None,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def image_bytes(
    format: str = "PNG", size: tuple[int, int] = (24, 16), orientation: int | None = None
) -> bytes:
    image = Image.new("RGB", size, "#4c9a87")
    buffer = io.BytesIO()
    exif = Image.Exif()
    if orientation:
        exif[274] = orientation
    image.save(buffer, format=format, exif=exif if orientation else None)
    return buffer.getvalue()


def upload(client: TestClient, name: str, content: bytes, mime: str = "image/png"):
    return client.post("/api/v1/media/upload", files={"file": (name, content, mime)})


def test_image_upload_persistence_listing_thumbnail_and_delete(
    settings: Settings, client: TestClient
) -> None:
    content = image_bytes("JPEG", (24, 16), orientation=6)
    response = upload(client, r"C:\unsafe\portrait.jpg", content, "image/jpeg")
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["original_filename"] == "portrait.jpg"
    assert (asset["width"], asset["height"]) == (16, 24)
    assert asset["file_size_bytes"] == len(content)
    assert asset["thumbnail_available"] is True
    assert len(asset["sha256"]) == 64
    media_id = asset["media_id"]
    assert client.get(f"/api/v1/media/{media_id}").json() == asset
    assert client.get("/api/v1/media").json() == [asset]
    served = client.get(f"/api/v1/media/{media_id}/content")
    assert served.content == content
    assert served.headers["content-type"] == "image/jpeg"
    thumbnail = client.get(f"/api/v1/media/{media_id}/thumbnail")
    assert thumbnail.status_code == 200
    with Image.open(io.BytesIO(thumbnail.content)) as preview:
        assert preview.size == (16, 24)
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/v1/media").json() == [asset]
    assert client.delete(f"/api/v1/media/{media_id}").status_code == 204
    assert client.get(f"/api/v1/media/{media_id}").status_code == 404
    assert list(settings.media_root.iterdir()) == []
    assert list(settings.thumbnail_root.iterdir()) == []


def test_upload_rejects_invalid_files_and_cleans_up(settings: Settings, client: TestClient) -> None:
    assert client.post("/api/v1/media/upload").status_code == 422
    assert (
        upload(client, "bad.gif", b"GIF89a", "image/gif").json()["error"]["code"]
        == "unsupported_format"
    )
    assert (
        upload(client, "bad.png", image_bytes(), "image/jpeg").json()["error"]["code"]
        == "invalid_mime_type"
    )
    assert upload(client, "bad.png", b"not a png").json()["error"]["code"] == "invalid_media"
    assert (
        upload(client, "bad.png", b"\x89PNG\r\n\x1a\nbroken").json()["error"]["code"]
        == "invalid_media"
    )
    assert list(settings.media_root.iterdir()) == []
    assert list(settings.thumbnail_root.iterdir()) == []
    assert client.get("/api/v1/media").json() == []


def test_upload_limits(settings: Settings) -> None:
    with TestClient(create_app(settings.model_copy(update={"max_image_bytes": 32}))) as client:
        response = upload(client, "large.png", image_bytes())
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "file_too_large"
    with TestClient(create_app(settings.model_copy(update={"max_image_pixels": 100}))) as client:
        response = upload(client, "large.png", image_bytes())
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "image_too_large"
    assert list(settings.media_root.iterdir()) == []


def test_invalid_ids_and_range_requests(client: TestClient) -> None:
    content = image_bytes()
    media_id = upload(client, "test.png", content).json()["media_id"]
    base = f"/api/v1/media/{media_id}/content"
    partial = client.get(base, headers={"Range": "bytes=0-7"})
    assert partial.status_code == 206
    assert partial.content == content[:8]
    assert partial.headers["content-range"] == f"bytes 0-7/{len(content)}"
    assert partial.headers["accept-ranges"] == "bytes"
    assert client.get(base, headers={"Range": "bytes=-4"}).content == content[-4:]
    invalid = client.get(base, headers={"Range": "bytes=999999-"})
    assert invalid.status_code == 416
    assert invalid.headers["content-range"] == f"bytes */{len(content)}"
    assert invalid.json()["error"]["code"] == "invalid_range"
    assert client.get(base, headers={"Range": "bytes=0-1,3-4"}).status_code == 416
    assert client.head(base).headers["content-length"] == str(len(content))
    assert client.get("/api/v1/media/not-a-uuid").status_code == 404
    assert client.get("/api/v1/media/%2e%2e%5csecret/content").status_code == 404


@pytest.fixture
def video_file(tmp_path: Path) -> bytes:
    binary = shutil.which("ffmpeg")
    if not binary:
        pytest.skip("FFmpeg is not installed")
    path = tmp_path / "sample.mp4"
    command = [
        binary,
        "-v",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=red:s=64x48:d=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, timeout=20, check=False)
    if result.returncode != 0:
        pytest.skip("Installed FFmpeg cannot generate the video test fixture")
    return path.read_bytes()


def test_video_upload_metadata_range_and_duration(
    settings: Settings, client: TestClient, video_file: bytes
) -> None:
    response = upload(client, "clip.mp4", video_file, "video/mp4")
    assert response.status_code == 201, response.text
    asset = response.json()
    assert asset["media_type"] == "video"
    assert (asset["width"], asset["height"]) == (64, 48)
    assert asset["duration_ms"] > 0
    assert asset["frame_rate"] > 0
    assert asset["video_codec"] == "h264"
    assert asset["thumbnail_available"] is True
    media_id = asset["media_id"]
    segment = client.get(f"/api/v1/media/{media_id}/content", headers={"Range": "bytes=0-31"})
    assert segment.status_code == 206
    assert segment.content == video_file[:32]
    assert segment.headers["content-type"] == "video/mp4"
    assert client.get(f"/api/v1/media/{media_id}/thumbnail").status_code == 200
    with TestClient(
        create_app(settings.model_copy(update={"max_video_duration_ms": 100}))
    ) as limited:
        too_long = upload(limited, "clip.mp4", video_file, "video/mp4")
        assert too_long.status_code == 413
        assert too_long.json()["error"]["code"] == "video_too_long"
    assert client.get("/api/v1/media").json() == [asset]


def test_missing_ffprobe_reports_dependency(settings: Settings, video_file: bytes) -> None:
    missing = settings.model_copy(update={"ffprobe_binary": "nonexistent-visionlab-ffprobe"})
    with TestClient(create_app(missing)) as client:
        response = upload(client, "clip.mp4", video_file, "video/mp4")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "media_dependency_unavailable"
