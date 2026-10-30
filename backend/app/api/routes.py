from fastapi import APIRouter, Request

from app.schemas.health import Capability, HealthResponse

router = APIRouter(prefix="/api/v1")


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok", service="visionlab-api", version="0.1.0", environment=settings.environment
    )


@router.get("/capabilities", response_model=list[Capability], tags=["system"])
def capabilities() -> list[Capability]:
    return [
        Capability(id="captioning", name="Image Captioning", status="planned", phase=4),
        Capability(id="vqa", name="Visual Question Answering", status="planned", phase=5),
        Capability(id="analysis", name="Image Analysis", status="planned", phase=4),
        Capability(id="objects", name="Object and Region Understanding", status="planned", phase=3),
        Capability(
            id="accessibility", name="Accessible Image Descriptions", status="planned", phase=5
        ),
    ]

