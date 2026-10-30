import logging
import platform
from contextlib import asynccontextmanager
from importlib.util import find_spec
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.routing import Match

from app.api.media import router as media_router
from app.api.routes import router
from app.api.vision import router as vision_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, log_event, request_id_context, safe_traceback
from app.core.upload_limit import UploadBodyLimitMiddleware
from app.providers.detector import DetectorError, ObjectDetector, YOLO26Detector
from app.schemas.media import ApiError, ApiErrorDetail
from app.services.analysis import AnalysisService
from app.services.media import MediaError, MediaService

logger = logging.getLogger("visionlab.http")


def _route_template(request: Request) -> str:
    """Resolve registered route patterns without logging user-controlled URL segments."""
    for outer in request.app.router.routes:
        candidates = getattr(getattr(outer, "original_router", None), "routes", None) or [outer]
        for candidate in candidates:
            if candidate.matches(request.scope)[0] == Match.FULL:
                path = getattr(candidate, "path", None)
                if path:
                    return path
    return "unmatched"


def create_app(settings: Settings | None = None, detector: ObjectDetector | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    media_service = MediaService(settings)
    detector = detector or YOLO26Detector(settings)
    analysis_service = AnalysisService(settings, media_service, detector)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        media_service.initialize()
        cuda_available: bool | None = None
        if settings.environment != "test" and find_spec("torch") is not None:
            try:
                import torch

                cuda_available = torch.cuda.is_available()
            except (ImportError, OSError, RuntimeError):
                pass
        model_status = detector.get_status()
        model_installed_unloaded = (
            model_status.state == "unavailable"
            and bool(model_status.detail)
            and model_status.detail.startswith("Weights installed")
        )
        log_event(
            logging.getLogger("visionlab.server"),
            "server.started",
            "COMPLETE VisionLab API started",
            application_version="0.3.0",
            environment=settings.environment,
            python_version=platform.python_version(),
            storage_ready=media_service.media_root.is_dir(),
            sqlite_ready=settings.database_path.is_file(),
            model=settings.detection_model,
            device=settings.detection_device,
            cuda_available=cuda_available,
            model_state="installed_not_loaded" if model_installed_unloaded else model_status.state,
            log_format=settings.log_format,
            log_directory=settings.log_directory.name,
            capabilities={
                "image_object_detection": "ready"
                if model_status.state == "ready"
                else "installed_not_loaded"
                if model_installed_unloaded
                else "unavailable",
                "captioning": "planned",
                "vqa": "planned",
                "video_detection": "planned",
            },
        )
        log_event(
            logging.getLogger("visionlab.model"),
            "model.status",
            "MODEL INSTALLED, NOT LOADED"
            if model_installed_unloaded
            else f"MODEL {model_status.state.replace('_', ' ').upper()}",
            model=settings.detection_model,
            model_state="installed_not_loaded" if model_installed_unloaded else model_status.state,
            device=model_status.device,
        )
        yield
        log_event(
            logging.getLogger("visionlab.server"),
            "server.stopped",
            "COMPLETE VisionLab API stopped",
        )

    app = FastAPI(title="VisionLab AI API", version="0.3.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.media_service = media_service
    app.state.detector = detector
    app.state.analysis_service = analysis_service
    app.add_middleware(UploadBodyLimitMiddleware, maximum_bytes=settings.max_video_bytes + 65536)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "POST", "DELETE"],
        allow_headers=["Content-Type", "Accept", "Range"],
        expose_headers=["Content-Range", "Accept-Ranges", "X-Request-ID"],
    )

    @app.exception_handler(MediaError)
    async def media_error_handler(request: Request, error: MediaError) -> JSONResponse:
        request.state.error_code = error.code
        request.state.error_message = error.message
        body = ApiError(error=ApiErrorDetail(code=error.code, message=error.message))
        return JSONResponse(
            status_code=error.status_code, content=body.model_dump(), headers=error.headers
        )

    @app.exception_handler(DetectorError)
    async def detector_error_handler(request: Request, error: DetectorError) -> JSONResponse:
        request.state.error_code = error.code
        request.state.error_message = error.message
        body = ApiError(error=ApiErrorDetail(code=error.code, message=error.message))
        return JSONResponse(status_code=error.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        request.state.error_code = "invalid_request"
        request.state.error_message = "Request validation failed."
        body = ApiError(
            error=ApiErrorDetail(code="invalid_request", message="Request validation failed.")
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        try:
            parsed = UUID(incoming)
            request_id = (
                incoming if parsed.version == 4 and str(parsed) == incoming else str(uuid4())
            )
        except (ValueError, AttributeError):
            request_id = str(uuid4())
        request.state.request_id = request_id
        context_token = request_id_context.set(request_id)
        started = perf_counter()
        route = _route_template(request)
        quiet_health = route == "/api/v1/health" and not settings.log_health_requests
        level = logging.DEBUG if quiet_health else logging.INFO
        log_event(
            logger,
            "request.started",
            "START HTTP request received",
            level=level,
            method=request.method,
            route=route,
        )
        try:
            response = await call_next(request)
        except Exception as exc:
            duration = round((perf_counter() - started) * 1000, 2)
            log_event(
                logger,
                "request.failed",
                "FAILED Unhandled server error",
                level=logging.ERROR,
                method=request.method,
                route=route,
                status_code=500,
                duration_ms=duration,
                error_code="internal_error",
                error_category="server",
                exception_type=type(exc).__name__,
                traceback=safe_traceback(exc) if settings.environment == "development" else None,
            )
            body = ApiError(
                error=ApiErrorDetail(code="internal_error", message="Internal server error.")
            )
            response = JSONResponse(status_code=500, content=body.model_dump())
        else:
            duration = round((perf_counter() - started) * 1000, 2)
            if response.status_code >= 400:
                code = getattr(request.state, "error_code", f"http_{response.status_code}")
                message = getattr(request.state, "error_message", "Request could not be completed.")
                log_event(
                    logger,
                    "request.failed",
                    f"FAILED {message}",
                    level=logging.ERROR if response.status_code >= 500 else logging.WARNING,
                    method=request.method,
                    route=route,
                    status_code=response.status_code,
                    duration_ms=duration,
                    error_code=code,
                    error_category="server" if response.status_code >= 500 else "client",
                )
            else:
                log_event(
                    logger,
                    "request.completed",
                    "COMPLETE HTTP request completed",
                    level=level,
                    method=request.method,
                    route=route,
                    status_code=response.status_code,
                    duration_ms=duration,
                    outcome="success",
                )
            if not quiet_health and duration >= settings.log_slow_request_ms:
                reason = "image analysis" if route.endswith("/analyze") else "request processing"
                log_event(
                    logger,
                    "request.slow",
                    f"WARNING Slow {reason} exceeded threshold",
                    level=logging.WARNING,
                    method=request.method,
                    route=route,
                    duration_ms=duration,
                    status_code=response.status_code,
                )
        finally:
            request_id_context.reset(context_token)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(router)
    app.include_router(media_router)
    app.include_router(vision_router)
    return app


app = create_app()
