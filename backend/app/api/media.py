from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.schemas.media import ApiError, MediaAsset
from app.services.media import CHUNK_SIZE, MediaError, MediaService, parse_byte_range

router = APIRouter(prefix="/api/v1/media", tags=["media"])
ERRORS = {
    404: {"model": ApiError},
    413: {"model": ApiError},
    416: {"model": ApiError},
    422: {"model": ApiError},
    503: {"model": ApiError},
}


def service(request: Request) -> MediaService:
    return request.app.state.media_service


@router.post("/upload", response_model=MediaAsset, status_code=201, responses=ERRORS)
def upload_media(request: Request, file: Annotated[UploadFile, File()]) -> MediaAsset:
    return service(request).upload(file)


@router.get("", response_model=list[MediaAsset], responses=ERRORS)
def list_media(request: Request, limit: int = Query(default=50, ge=1, le=100)) -> list[MediaAsset]:
    return service(request).list(limit)


@router.get("/{media_id}", response_model=MediaAsset, responses=ERRORS)
def get_media(media_id: str, request: Request) -> MediaAsset:
    return service(request).get(media_id)


def _read_file(path: Path, start: int, end: int) -> Iterator[bytes]:
    with path.open("rb") as source:
        source.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = source.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.api_route("/{media_id}/content", methods=["GET", "HEAD"], responses=ERRORS)
def media_content(media_id: str, request: Request) -> Response:
    asset, path, _ = service(request).paths(media_id)
    if not path.is_file():
        raise MediaError("media_not_found", "Media content was not found.", 404)
    size = path.stat().st_size
    byte_range = parse_byte_range(request.headers.get("range"), size)
    start, end = byte_range if byte_range else (0, size - 1)
    status = 206 if byte_range else 200
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "X-Content-Type-Options": "nosniff",
    }
    if byte_range:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if request.method == "HEAD":
        return Response(status_code=status, headers=headers, media_type=asset.detected_mime_type)
    return StreamingResponse(
        _read_file(path, start, end),
        status_code=status,
        headers=headers,
        media_type=asset.detected_mime_type,
    )


@router.get("/{media_id}/thumbnail", responses=ERRORS)
def media_thumbnail(media_id: str, request: Request) -> FileResponse:
    _, _, thumbnail = service(request).paths(media_id)
    if thumbnail is None or not thumbnail.is_file():
        raise MediaError("thumbnail_not_found", "Thumbnail was not found.", 404)
    return FileResponse(
        thumbnail,
        media_type="image/jpeg",
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/{media_id}", status_code=204, responses=ERRORS)
def delete_media(media_id: str, request: Request) -> Response:
    service(request).delete(media_id)
    return Response(status_code=204)
