import json
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.main import create_app
from app.schemas.common import NormalizedBox


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app(Settings(environment="test", _env_file=None))) as test_client:
        yield test_client


def test_health_and_request_id(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "visionlab-api",
        "version": "0.4.0",
        "environment": "test",
    }
    assert response.headers["X-Request-ID"]


def test_capabilities_report_only_media_as_available(client: TestClient) -> None:
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    capabilities = response.json()
    assert len(capabilities) == 8
    assert {item["id"] for item in capabilities if item["status"] == "available"} == {
        "media_upload",
        "image_preview",
        "video_preview",
    }
    assert len([item for item in capabilities if item["status"] == "planned"]) == 2
    assert (
        next(item for item in capabilities if item["id"] == "captioning")["status"] == "unavailable"
    )
    assert len([item for item in capabilities if item["status"] == "unavailable"]) == 3


def test_cors_allows_local_frontend(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "http://localhost:5180"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5180"


def test_normalized_box_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        NormalizedBox(x1=0.8, y1=0.2, x2=0.1, y2=0.9)
    with pytest.raises(ValidationError):
        NormalizedBox(x1=-0.1, y1=0.2, x2=0.5, y2=0.9)


def test_log_formatter_emits_json() -> None:
    record = logging.LogRecord("visionlab", logging.INFO, __file__, 1, "ready", (), None)
    record.request_id = "test-id"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["message"] == "ready"
    assert payload["request_id"] == "test-id"
