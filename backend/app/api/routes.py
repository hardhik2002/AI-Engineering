from fastapi import APIRouter, Request

from app.schemas.health import Capability, HealthResponse

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok", service="visionlab-api", version="0.3.0", environment=settings.environment
    )


@router.get("/capabilities", response_model=list[Capability], tags=["system"])
def capabilities(request: Request) -> list[Capability]:
    detection_ready = request.app.state.detector.get_status().state == "ready"
    detection_status = "available" if detection_ready else "unavailable"
    return [
        Capability(
            id="captioning",
            name="Image Captioning",
            status="available"
            if request.app.state.caption_provider.successful_tasks.intersection(
                {"short", "detailed", "extended"}
            )
            else "unavailable",
            phase=4,
        ),
        Capability(id="vqa", name="Visual Question Answering", status="planned", phase=5),
        Capability(id="analysis", name="Image Analysis", status=detection_status, phase=3),
        Capability(
            id="objects", name="Object and Region Understanding", status=detection_status, phase=4
        ),
        Capability(
            id="accessibility", name="Accessible Image Descriptions", status="planned", phase=5
        ),
        Capability(id="media_upload", name="Media Upload", status="available", phase=2),
        Capability(id="image_preview", name="Image Preview", status="available", phase=2),
        Capability(id="video_preview", name="Video Preview", status="available", phase=2),
    ]
