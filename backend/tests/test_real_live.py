"""Real local YOLO frame path; physical webcam validation remains manual."""

import io
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from PIL import Image

from app.core.config import Settings
from app.main import create_app
from app.services.live import MAGIC


@pytest.mark.real_live
def test_real_live_frame_inference(tmp_path: Path):
    source = Path("data/smoke/bus.jpg")
    weights = Path("data/models/yolo26n.pt")
    if not source.is_file() or not weights.is_file():
        pytest.skip("Install YOLO weights and put bus.jpg in data/smoke")
    settings = Settings(
        environment="test", database_url=f"sqlite:///{tmp_path / 'db.sqlite'}",
        media_root=tmp_path / "media", thumbnail_root=tmp_path / "thumbs",
        model_root=Path("data/models"), detection_device="cpu",
        log_console_enabled=False, log_file_enabled=False, _env_file=None,
    )
    app = create_app(settings)
    service = app.state.live_service
    session_id, frame_id = uuid4(), uuid4()
    with Image.open(source) as original:
        image = original.convert("RGB")
        image.thumbnail((settings.live_max_width, settings.live_max_height))
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=75)
    header = json.dumps({
        "type": "frame.submitted", "session_id": str(session_id),
        "frame_id": str(frame_id), "captured_at_ms": 1.0,
        "source_width": image.width, "source_height": image.height,
        "encoded_format": "jpeg",
    }).encode()
    packet = MAGIC + len(header).to_bytes(4, "big") + header + stream.getvalue()
    metadata, decoded = service.unpack(packet, session_id)
    cold = service.infer(metadata, decoded)
    assert cold.detections, "Real bus frame should contain detected objects"
    started = perf_counter()
    warm = service.infer(metadata, decoded)
    warm_wall_ms = (perf_counter() - started) * 1000
    assert warm.detections and warm.model.name == "yolo26n.pt"
    assert all(0 <= item.confidence <= 1 for item in warm.detections)
    assert all(item.bounding_box.x + item.bounding_box.width <= 1 for item in warm.detections)
    print(
        f"real live frame: {image.width}x{image.height}, "
        f"{len(warm.detections)} detections, cold processing {cold.processing_ms:.1f} ms, "
        f"warm inference {warm.inference_ms:.1f} ms, warm wall {warm_wall_ms:.1f} ms"
    )
