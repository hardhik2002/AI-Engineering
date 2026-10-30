import asyncio
import base64
import io
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.providers.multimodal import OpenAIVisionProvider, VisionProviderError, VisionResult
from app.schemas.caption import CaptionModelInfo, CaptionRecord
from app.schemas.multimodal import AccessibilityAnswer, TokenUsage, VQAAnswer
from app.services.multimodal import prepare_image_data_url


class FakeVision:
    def __init__(self):
        self.calls = []
        self.state = "configured"
        self.fail = False

    def status(self):
        return {"provider": "openai", "state": self.state, "model": "test-vision"}

    async def answer(self, image_url, question, history):
        self.calls.append((image_url, question, history))
        if self.fail:
            raise VisionProviderError("openai_unavailable", "OpenAI is unavailable.")
        self.state = "available"
        return VisionResult(
            VQAAnswer(answer="A red square.", grounding_status="supported", uncertainty_note=None),
            12,
            TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            "test-vision",
        )

    async def describe(self, image_url, purpose, context, audience, function):
        self.calls.append((image_url, purpose, context, audience, function))
        self.state = "available"
        return VisionResult(
            AccessibilityAnswer(
                alt_text="A red square.",
                detailed_description="Solid red square.",
                extended_description=None,
            ),
            14,
            None,
            "test-vision",
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
    provider = FakeVision()
    with TestClient(create_app(settings, multimodal_provider=provider)) as client:
        image = Image.new("RGB", (16, 12), "red")
        stream = io.BytesIO()
        image.save(stream, "JPEG", comment=b"private metadata")
        response = client.post(
            "/api/v1/media/upload", files={"file": ("red.jpg", stream.getvalue(), "image/jpeg")}
        )
        assert response.status_code == 201, response.text
        yield client, response.json()["media_id"], provider, settings


def test_vqa_consent_history_persistence_and_delete(setup):
    client, media_id, provider, settings = setup
    url = f"/api/v1/media/{media_id}/vqa"
    assert client.get("/api/v1/vision/providers").json()["vqa"]["state"] == "configured"
    assert client.post(url, json={"question": "What color?"}).status_code == 403
    assert provider.calls == []
    first = client.post(url, json={"question": "What color?", "consent_external_transfer": True})
    assert first.status_code == 201, first.text
    record = first.json()
    assert record["messages"][1]["text"] == "A red square."
    assert record["messages"][1]["usage"]["total_tokens"] == 15
    assert provider.calls[0][0].startswith("data:image/jpeg;base64,")
    assert provider.calls[0][2] == []
    second = client.post(
        url,
        json={
            "question": "And shape?",
            "conversation_id": record["conversation_id"],
            "consent_external_transfer": True,
        },
    )
    assert second.status_code == 201, second.text
    assert len(second.json()["messages"]) == 4
    assert provider.calls[1][2] == [("user", "What color?"), ("assistant", "A red square.")]
    for index in range(4):
        followup = client.post(
            url,
            json={
                "question": f"Follow-up {index}?",
                "conversation_id": record["conversation_id"],
                "consent_external_transfer": True,
            },
        )
        assert followup.status_code == 201
    assert len(provider.calls[-1][2]) == 8
    assert client.get("/api/v1/vision/providers").json()["vqa"]["state"] == "available"
    assert len(client.get(f"{url}/conversations").json()) == 1
    assert client.get(f"{url}/conversations/{record['conversation_id']}").status_code == 200
    other = client.post(
        "/api/v1/media/upload",
        files={
            "file": (
                "other.jpg",
                (settings.media_root / f"{media_id}.jpg").read_bytes(),
                "image/jpeg",
            )
        },
    ).json()["media_id"]
    assert (
        client.get(
            f"/api/v1/media/{other}/vqa/conversations/{record['conversation_id']}"
        ).status_code
        == 404
    )
    assert client.delete(f"{url}/conversations/{record['conversation_id']}").status_code == 204
    assert client.get(f"{url}/conversations").json() == []


def test_failed_provider_does_not_persist_and_missing_key_keeps_local(setup):
    client, media_id, provider, settings = setup
    provider.fail = True
    url = f"/api/v1/media/{media_id}"
    response = client.post(
        f"{url}/vqa", json={"question": "What?", "consent_external_transfer": True}
    )
    assert response.status_code == 503
    assert client.get(f"{url}/vqa/conversations").json() == []
    with TestClient(
        create_app(settings.model_copy(update={"openai_api_key": None}))
    ) as unconfigured:
        assert unconfigured.get("/api/v1/vision/providers").json()["vqa"]["state"] == "unconfigured"
        assert (
            unconfigured.post(
                f"{url}/vqa", json={"question": "What?", "consent_external_transfer": True}
            ).status_code
            == 503
        )
        decorative = unconfigured.post(f"{url}/accessibility", json={"purpose": "decorative"})
        assert decorative.status_code == 201
        assert decorative.json()["generated"]["alt_text"] == ""
        assert decorative.json()["source"] == "decorative_local"


def test_accessibility_edit_suggestion_and_cascade(setup):
    client, media_id, provider, _ = setup
    url = f"/api/v1/media/{media_id}/accessibility"
    assert client.post(url, json={"purpose": "informative"}).status_code == 403
    created = client.post(
        url,
        json={"purpose": "informative", "context": "Homepage", "consent_external_transfer": True},
    )
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["generated"]["alt_text"] == "A red square."
    patch = client.patch(
        f"{url}/{record['result_id']}", json={"alt_text": "Red square icon", "expected_version": 1}
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["generated"]["alt_text"] == "A red square."
    assert patch.json()["edited"]["alt_text"] == "Red square icon"
    assert (
        client.patch(
            f"{url}/{record['result_id']}", json={"alt_text": "stale", "expected_version": 1}
        ).status_code
        == 409
    )
    assert len(client.get(url).json()) == 1
    assert client.delete(f"/api/v1/media/{media_id}").status_code == 204
    assert client.get(url).status_code == 404


def test_florence_suggestion_is_local_and_media_scoped(setup):
    client, media_id, provider, _ = setup
    now = datetime.now(UTC)
    caption = CaptionRecord(
        analysis_id=str(uuid4()),
        media_id=media_id,
        task="short",
        created_at=now,
        completed_at=now,
        model=CaptionModelInfo(
            checkpoint="saved-florence", revision="test", device="cpu", package_version="test"
        ),
        duration_ms=1,
        model_load_ms=0,
        inference_ms=1,
        text="A real saved caption.",
    )
    client.app.state.caption_service.repository.insert_caption(caption)
    url = f"/api/v1/media/{media_id}/accessibility"
    response = client.post(
        url, json={"purpose": "informative", "source_caption_analysis_id": caption.analysis_id}
    )
    assert response.status_code == 201, response.text
    assert response.json()["source"] == "florence_suggestion"
    assert response.json()["generated"]["alt_text"] == caption.text
    assert provider.calls == []
    assert (
        client.post(
            url, json={"purpose": "informative", "source_caption_analysis_id": str(uuid4())}
        ).status_code
        == 404
    )


def test_prepared_image_is_resized_metadata_free(tmp_path: Path):
    path = tmp_path / "photo.jpg"
    image = Image.new("RGB", (200, 100), "blue")
    exif = Image.Exif()
    exif[274] = 6  # Rotate 90 degrees clockwise.
    exif[315] = "Private author metadata"
    image.save(path, "JPEG", exif=exif)
    encoded = prepare_image_data_url(path, (100, 200), 100)
    decoded = base64.b64decode(encoded.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as result:
        assert result.size == (50, 100)
        assert not result.getexif()


def test_openai_provider_request_payload_without_network():
    settings = Settings(environment="test", openai_api_key="test-only-key", _env_file=None)
    provider = OpenAIVisionProvider(settings)
    captured = []

    async def parse(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(
            status="completed",
            output=[],
            output_parsed=VQAAnswer(
                answer="A circle", grounding_status="uncertain", uncertainty_note="Shape is blurry"
            ),
            usage=SimpleNamespace(input_tokens=8, output_tokens=4, total_tokens=12),
        )

    provider._client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    result = asyncio.run(provider.answer("data:image/jpeg;base64,AAAA", "What shape?", []))
    assert result.output.answer == "A circle"
    assert captured[0]["store"] is False
    assert captured[0]["text_format"] is VQAAnswer
    assert captured[0]["input"][-1]["content"][-1]["detail"] == "auto"
    assert "test-only-key" not in str(provider.status())


@pytest.mark.live_openai
def test_live_openai_opt_in(tmp_path: Path):
    if os.getenv("RUN_LIVE_OPENAI_TESTS") != "1" or not os.getenv("OPENAI_API_KEY"):
        pytest.skip("Requires RUN_LIVE_OPENAI_TESTS=1 and OPENAI_API_KEY")
    image_path = tmp_path / "red.jpg"
    Image.new("RGB", (32, 32), "red").save(image_path, "JPEG")
    settings = Settings(
        environment="test", openai_api_key=os.environ["OPENAI_API_KEY"], _env_file=None
    )
    provider = OpenAIVisionProvider(settings)
    image_url = prepare_image_data_url(image_path, (32, 32), 1600)
    result = asyncio.run(provider.answer(image_url, "What is the dominant color?", []))
    assert result.output.answer.strip()
    assert provider.status()["state"] == "available"
