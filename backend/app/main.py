import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.media import router as media_router
from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.upload_limit import UploadBodyLimitMiddleware
from app.schemas.media import ApiError, ApiErrorDetail
from app.services.media import MediaError, MediaService

logger = logging.getLogger("visionlab.http")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    media_service = MediaService(settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        media_service.initialize()
        yield

    app = FastAPI(title="VisionLab AI API", version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.media_service = media_service
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
    async def media_error_handler(_request: Request, error: MediaError) -> JSONResponse:
        body = ApiError(error=ApiErrorDetail(code=error.code, message=error.message))
        return JSONResponse(
            status_code=error.status_code, content=body.model_dump(), headers=error.headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        body = ApiError(
            error=ApiErrorDetail(code="invalid_request", message="Request validation failed.")
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.middleware("http")
    async def log_request(request: Request, call_next):
        request_id = str(uuid4())
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            },
        )
        return response

    app.include_router(router)
    app.include_router(media_router)
    return app


app = create_app()
