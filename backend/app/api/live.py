"""Versioned, origin-restricted live camera WebSocket."""

import asyncio
import json
import logging
from time import monotonic
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.core.logging import log_event, request_id_context
from app.providers.detector import DetectorError
from app.services.live import LiveFrameError, LiveFrameSkipped

logger = logging.getLogger("visionlab.live")
router = APIRouter()


@router.websocket("/ws/v1/live")
async def live_camera(websocket: WebSocket) -> None:
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin", "")
    if (
        origin not in settings.allowed_origins
        or urlsplit(origin).hostname not in {"localhost", "127.0.0.1"}
    ):
        await websocket.close(code=1008, reason="Origin is not allowed")
        return
    service = websocket.app.state.live_service
    if not service.enter():
        await websocket.close(code=1013, reason="Live camera capacity is full")
        return
    session_id = uuid4()
    token = request_id_context.set(str(session_id))
    processed = skipped = bad_frames = 0
    last_received = -1.0
    try:
        await websocket.accept()
        await websocket.send_json({
            "type": "session.started", "protocol_version": 1,
            "session_id": str(session_id), "active_sessions": service.active_sessions,
            "max_width": settings.live_max_width,
            "max_height": settings.live_max_height,
            "max_frame_bytes": settings.live_max_frame_bytes,
            "max_in_flight_frames": settings.live_max_in_flight_frames,
            "max_fps": settings.live_target_fps,
        })
        log_event(
            logger, "live.session_started", "START Live camera session",
            session_id=str(session_id), active_sessions=service.active_sessions,
            model=settings.detection_model,
        )
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(), timeout=settings.live_idle_timeout_seconds
                )
            except TimeoutError:
                await websocket.send_json({
                    "type": "session.error", "session_id": str(session_id),
                    "code": "session_idle", "message": "Live camera session timed out.",
                })
                await websocket.close(code=1000)
                break
            if message["type"] == "websocket.disconnect":
                break
            if message.get("text") is not None:
                try:
                    control = json.loads(message["text"])
                except (ValueError, TypeError):
                    control = None
                if control == {"type": "session.stop"}:
                    await websocket.send_json({
                        "type": "session.stopped", "session_id": str(session_id),
                        "processed_frames": processed, "skipped_frames": skipped,
                    })
                    await websocket.close(code=1000)
                    break
                await websocket.send_json({
                    "type": "session.error", "session_id": str(session_id),
                    "code": "invalid_control", "message": "Unknown live control message.",
                })
                continue
            packet = message.get("bytes")
            if not isinstance(packet, bytes):
                continue
            if len(packet) > settings.live_max_frame_bytes + 1031:
                await websocket.send_json({
                    "type": "session.error", "session_id": str(session_id),
                    "code": "frame_too_large", "message": "Camera frame exceeds the size limit.",
                })
                await websocket.close(code=1009)
                break
            try:
                metadata, image = await asyncio.to_thread(service.unpack, packet, session_id)
            except LiveFrameError as exc:
                bad_frames += 1
                await websocket.send_json({
                    "type": "session.error", "session_id": str(session_id),
                    "code": exc.code, "message": exc.message,
                })
                if exc.code == "frame_too_large":
                    await websocket.close(code=1009)
                    break
                if bad_frames >= 3:
                    await websocket.close(code=1008)
                    break
                continue
            log_event(
                logger, "live.frame_received", "COMPLETE Live frame received",
                level=logging.DEBUG, session_id=str(session_id),
                frame_id=str(metadata.frame_id), width=image.width, height=image.height,
            )
            received = monotonic()
            if last_received >= 0 and received - last_received < 1 / settings.live_target_fps:
                skipped += 1
                await websocket.send_json({
                    "type": "frame.skipped", "session_id": str(session_id),
                    "frame_id": str(metadata.frame_id), "reason": "rate_limited",
                })
                log_event(
                    logger, "live.frame_skipped", "SKIPPED Live frame rate limit",
                    level=logging.DEBUG, session_id=str(session_id),
                    frame_id=str(metadata.frame_id), skip_reason="rate_limited",
                )
                continue
            last_received = received
            try:
                result = await asyncio.to_thread(service.infer, metadata, image)
            except LiveFrameSkipped as exc:
                skipped += 1
                await websocket.send_json({
                    "type": "frame.skipped", "session_id": str(session_id),
                    "frame_id": str(metadata.frame_id), "reason": exc.code,
                })
                log_event(
                    logger, "live.frame_skipped", "SKIPPED Busy live detector",
                    level=logging.DEBUG, session_id=str(session_id),
                    frame_id=str(metadata.frame_id), skip_reason=exc.code,
                )
                continue
            except DetectorError as exc:
                await websocket.send_json({
                    "type": "session.error", "session_id": str(session_id),
                    "code": exc.code, "message": exc.message,
                })
                log_event(
                    logger, "live.session_failed", "FAILED Live camera model",
                    level=logging.ERROR, session_id=str(session_id), error_code=exc.code,
                )
                await websocket.close(code=1011)
                break
            except Exception as exc:
                await websocket.send_json({
                    "type": "session.error", "session_id": str(session_id),
                    "code": "live_inference_failed", "message": "Live detection failed.",
                })
                log_event(
                    logger, "live.session_failed", "FAILED Live camera inference",
                    level=logging.ERROR, session_id=str(session_id),
                    error_code="live_inference_failed", exception_type=type(exc).__name__,
                )
                await websocket.close(code=1011)
                break
            processed += 1
            await websocket.send_json(result.model_dump(mode="json"))
            if processed % 10 == 0:
                log_event(
                    logger, "live.progress", "COMPLETE Live frame batch",
                    session_id=str(session_id), processed_frames=processed,
                    skipped_frames=skipped, inference_ms=result.inference_ms,
                )
    except WebSocketDisconnect:
        pass
    finally:
        service.leave()
        log_event(
            logger, "live.session_stopped", "COMPLETE Live camera session ended",
            session_id=str(session_id), active_sessions=service.active_sessions,
            processed_frames=processed, skipped_frames=skipped,
        )
        request_id_context.reset(token)
