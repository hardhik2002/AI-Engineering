from fastapi import APIRouter, Request

from app.schemas.vision import AnalysisRecord, AnalyzeRequest, DetectionParameters, ModelStatus

router = APIRouter(prefix="/api/v1", tags=["vision"])


@router.get("/vision/models", response_model=list[ModelStatus])
def models(request: Request) -> list[ModelStatus]:
    return [request.app.state.detector.get_status()]


@router.get("/vision/capabilities")
def vision_capabilities(request: Request) -> dict[str, str]:
    ready = request.app.state.detector.get_status().state == "ready"
    return {
        "object_detection_image": "available" if ready else "unavailable",
        "image_object_counting": "available" if ready else "unavailable",
        "image_detection_overlays": "available" if ready else "unavailable",
        **{
            name: "planned"
            for name in (
                "image_captioning",
                "visual_question_answering",
                "natural_language_scene_analysis",
                "region_captioning",
                "accessible_description_generation",
                "video_object_detection",
                "video_tracking",
                "live_webcam_inference",
                "advanced_segmentation",
            )
        },
    }


@router.post("/media/{media_id}/analyze", response_model=AnalysisRecord, status_code=201)
def analyze(media_id: str, request: Request, body: AnalyzeRequest | None = None) -> AnalysisRecord:
    settings = request.app.state.settings
    parameters = (
        body.parameters
        if body
        else DetectionParameters(
            confidence=settings.detection_confidence,
            iou=settings.detection_iou,
            image_size=settings.detection_image_size,
            max_detections=settings.detection_max_detections,
        )
    )
    return request.app.state.analysis_service.analyze(media_id, parameters)


@router.get("/media/{media_id}/analyses", response_model=list[AnalysisRecord])
def list_analyses(media_id: str, request: Request) -> list[AnalysisRecord]:
    return request.app.state.analysis_service.list(media_id)


@router.get("/media/{media_id}/analyses/{analysis_id}", response_model=AnalysisRecord)
def get_analysis(media_id: str, analysis_id: str, request: Request) -> AnalysisRecord:
    return request.app.state.analysis_service.get(media_id, analysis_id)
