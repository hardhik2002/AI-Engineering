from fastapi import APIRouter, Request

from app.schemas.caption import CaptionRecord, CaptionRequest, DescribeObjectRequest
from app.schemas.health import CapabilityStatus
from app.schemas.vision import AnalysisRecord, AnalyzeRequest, DetectionParameters, ModelStatus

router = APIRouter(prefix="/api/v1", tags=["vision"])


@router.get("/vision/models", response_model=list[ModelStatus])
def models(request: Request) -> list[ModelStatus]:
    return [request.app.state.detector.get_status()]


@router.get("/vision/caption-model")
def caption_model(request: Request) -> dict[str, str | None]:
    return request.app.state.caption_provider.get_status()


@router.get("/vision/capabilities", response_model=dict[str, CapabilityStatus])
def vision_capabilities(request: Request) -> dict[str, CapabilityStatus]:
    ready = request.app.state.detector.get_status().state == "ready"
    completed = request.app.state.caption_provider.successful_tasks
    vision_ready = request.app.state.multimodal_provider.status()["state"] == "available"
    video_repository = request.app.state.video_service.repository
    video_ready = video_repository.has_completed_analysis()
    tracking_ready = video_repository.has_completed_analysis(tracking=True)
    return {
        "object_detection_image": "available" if ready else "unavailable",
        "image_object_counting": "available" if ready else "unavailable",
        "image_detection_overlays": "available" if ready else "unavailable",
        "image_captioning_short": "available" if "short" in completed else "unavailable",
        "image_captioning_detailed": "available" if "detailed" in completed else "unavailable",
        "image_captioning_extended": "available" if "extended" in completed else "unavailable",
        "dense_region_captioning": "available" if "dense" in completed else "unavailable",
        "selected_region_description": "available"
        if "selected_object" in completed
        else "unavailable",
        "visual_question_answering": "available" if vision_ready else "unavailable",
        "accessible_description_generation": "available",
        **{
            name: "planned"
            for name in (
                "natural_language_scene_analysis",
                "advanced_segmentation",
            )
        },
        "video_object_detection": "available" if video_ready else "unavailable",
        "video_tracking": "available" if tracking_ready else "unavailable",
        "live_webcam_inference": "available" if ready else "unavailable",
    }


@router.post("/media/{media_id}/caption", response_model=CaptionRecord, status_code=201)
def caption(media_id: str, request: Request, body: CaptionRequest) -> CaptionRecord:
    return request.app.state.caption_service.run(media_id, body.mode)


@router.post("/media/{media_id}/dense-regions", response_model=CaptionRecord, status_code=201)
def dense_regions(media_id: str, request: Request) -> CaptionRecord:
    return request.app.state.caption_service.run(media_id, "dense")


@router.post("/media/{media_id}/regions/describe", response_model=CaptionRecord, status_code=201)
def describe_region(media_id: str, request: Request, body: DescribeObjectRequest) -> CaptionRecord:
    return request.app.state.caption_service.run(
        media_id, "selected_object", body.detection_analysis_id, body.detection_id
    )


@router.get("/media/{media_id}/captions", response_model=list[CaptionRecord])
def list_captions(media_id: str, request: Request) -> list[CaptionRecord]:
    return request.app.state.caption_service.list(media_id)


@router.post("/media/{media_id}/analyze", response_model=AnalysisRecord, status_code=201)
def analyze(media_id: str, request: Request, body: AnalyzeRequest | None = None) -> AnalysisRecord:
    settings = request.app.state.settings
    defaults = DetectionParameters(
        confidence=settings.detection_confidence,
        iou=settings.detection_iou,
        image_size=settings.detection_image_size,
        max_detections=settings.detection_max_detections,
    )
    overrides = body.parameters.model_dump(exclude_none=True) if body and body.parameters else {}
    parameters = DetectionParameters.model_validate(defaults.model_dump() | overrides)
    return request.app.state.analysis_service.analyze(media_id, parameters)


@router.get("/media/{media_id}/analyses", response_model=list[AnalysisRecord])
def list_analyses(media_id: str, request: Request) -> list[AnalysisRecord]:
    return request.app.state.analysis_service.list(media_id)


@router.get("/media/{media_id}/analyses/{analysis_id}", response_model=AnalysisRecord)
def get_analysis(media_id: str, analysis_id: str, request: Request) -> AnalysisRecord:
    return request.app.state.analysis_service.get(media_id, analysis_id)
