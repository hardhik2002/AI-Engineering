"""Uploaded video jobs, sampled results, and explicit video cloud requests."""

import asyncio
import json

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from app.schemas.video import (
    VideoAnalysis,
    VideoAnalyzeRequest,
    VideoCaption,
    VideoCaptionEdit,
    VideoCaptionRequest,
    VideoFrameResult,
    VideoJob,
    VideoRefineRequest,
    VideoTimelineMarker,
    VideoTrack,
    VideoVQARequest,
    VideoVQAResponse,
)
from app.services.video import TERMINAL, VideoError

router = APIRouter(prefix="/api/v1", tags=["video"])


def _analysis(request: Request, analysis_id: str) -> VideoAnalysis:
    request.app.state.media_service.validate_id(analysis_id)
    result = request.app.state.video_service.repository.get_analysis(analysis_id)
    if result is None:
        raise VideoError("video_analysis_not_found", "Video analysis was not found.", 404)
    return result


def _range(start_ms: int, end_ms: int) -> None:
    if end_ms < start_ms:
        raise VideoError("invalid_time_range", "End time must follow start time.")


@router.post("/media/{media_id}/video/analyze", response_model=VideoJob, status_code=202)
def analyze_video(
    media_id: str, request: Request, body: VideoAnalyzeRequest | None = None
) -> VideoJob:
    return request.app.state.video_service.create_analysis(media_id, body)


@router.get("/media/{media_id}/video/analyses", response_model=list[VideoAnalysis])
def list_analyses(media_id: str, request: Request) -> list[VideoAnalysis]:
    return request.app.state.video_service.list_analyses(media_id)


@router.get("/video/analyses/{analysis_id}", response_model=VideoAnalysis)
def get_analysis(analysis_id: str, request: Request) -> VideoAnalysis:
    return _analysis(request, analysis_id)


@router.get("/video/jobs/{job_id}", response_model=VideoJob)
def get_job(job_id: str, request: Request) -> VideoJob:
    return request.app.state.video_service.get_job(job_id)


@router.post("/video/jobs/{job_id}/cancel", response_model=VideoJob)
def cancel_job(job_id: str, request: Request) -> VideoJob:
    return request.app.state.video_service.cancel(job_id)


@router.get("/video/jobs/{job_id}/events")
async def job_events(
    job_id: str, request: Request, last_event_id: str | None = Header(default=None)
) -> StreamingResponse:
    service = request.app.state.video_service
    service.get_job(job_id)
    try:
        seen = max(0, int(last_event_id or 0))
    except ValueError:
        seen = 0

    async def events():
        nonlocal seen
        while not await request.is_disconnected():
            job = await asyncio.to_thread(service.get_job, job_id)
            if job.revision > seen or job.status in TERMINAL:
                seen = job.revision
                yield f"id: {seen}\nevent: job\ndata: {json.dumps(job.model_dump(mode='json'))}\n\n"
            if job.status in TERMINAL:
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/video/analyses/{analysis_id}/frames", response_model=list[VideoFrameResult])
def frames(
    analysis_id: str,
    request: Request,
    start_ms: int = Query(0, ge=0),
    end_ms: int = Query(1_000_000_000, ge=0),
    limit: int = Query(100, ge=1, le=100),
) -> list[VideoFrameResult]:
    _range(start_ms, end_ms)
    _analysis(request, analysis_id)
    return request.app.state.video_service.repository.frames(analysis_id, start_ms, end_ms, limit)


@router.get("/video/analyses/{analysis_id}/timeline", response_model=list[VideoTimelineMarker])
def timeline(analysis_id: str, request: Request) -> list[VideoTimelineMarker]:
    _analysis(request, analysis_id)
    return request.app.state.video_service.repository.timeline(analysis_id)


@router.get("/video/analyses/{analysis_id}/tracks", response_model=list[VideoTrack])
def tracks(
    analysis_id: str,
    request: Request,
    start_ms: int = Query(0, ge=0),
    end_ms: int = Query(1_000_000_000, ge=0),
    limit: int = Query(100, ge=1, le=100),
) -> list[VideoTrack]:
    _range(start_ms, end_ms)
    _analysis(request, analysis_id)
    return request.app.state.video_service.repository.tracks(analysis_id, start_ms, end_ms, limit)


@router.get("/video/analyses/{analysis_id}/captions", response_model=list[VideoCaption])
def captions(
    analysis_id: str,
    request: Request,
    start_ms: int = Query(0, ge=0),
    end_ms: int = Query(1_000_000_000, ge=0),
    limit: int = Query(100, ge=1, le=100),
) -> list[VideoCaption]:
    _range(start_ms, end_ms)
    _analysis(request, analysis_id)
    return request.app.state.video_service.repository.captions(analysis_id, start_ms, end_ms, limit)


@router.post(
    "/media/{media_id}/video/analyses/{analysis_id}/captions",
    response_model=VideoJob,
    status_code=202,
)
def caption_frame(
    media_id: str, analysis_id: str, body: VideoCaptionRequest, request: Request
) -> VideoJob:
    return request.app.state.video_service.create_caption_job(
        media_id, analysis_id, body.timestamp_ms
    )


@router.patch("/video/analyses/{analysis_id}/captions/{caption_id}", response_model=VideoCaption)
def edit_caption(
    analysis_id: str, caption_id: str, body: VideoCaptionEdit, request: Request
) -> VideoCaption:
    return request.app.state.video_service.edit_caption(analysis_id, caption_id, body)


@router.post("/media/{media_id}/video/vqa", response_model=VideoVQAResponse, status_code=201)
async def ask_video(media_id: str, body: VideoVQARequest, request: Request) -> VideoVQAResponse:
    return await request.app.state.multimodal_service.ask_video(media_id, body)


@router.post(
    "/media/{media_id}/video/analyses/{analysis_id}/refine",
    response_model=VideoCaption,
    status_code=201,
)
async def refine_caption(
    media_id: str, analysis_id: str, body: VideoRefineRequest, request: Request
) -> VideoCaption:
    return await request.app.state.multimodal_service.refine_video_caption(
        media_id, analysis_id, body
    )
