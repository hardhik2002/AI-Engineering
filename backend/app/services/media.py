import hashlib
import json
import math
import re
import shutil
import subprocess
import warnings
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import Settings
from app.repositories.media import MediaRepository, public_asset
from app.schemas.media import MediaAsset

FORMATS: dict[str, tuple[str, str]] = {
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".webp": ("image", "image/webp"),
    ".mp4": ("video", "video/mp4"),
    ".webm": ("video", "video/webm"),
}
STORED_EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                     "video/mp4": ".mp4", "video/webm": ".webm"}
CHUNK_SIZE = 1024 * 1024


class MediaError(Exception):
    def __init__(
        self, code: str, message: str, status_code: int = 422,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.headers = headers or {}
        super().__init__(message)


def _safe_name(filename: str | None) -> str:
    name = (filename or "").replace("\\", "/").split("/")[-1].strip()
    name = "".join(character for character in name if character.isprintable())[:255]
    if not name or name in {".", ".."}:
        raise MediaError("invalid_filename", "A valid filename is required.")
    return name


def _check_signature(path: Path, mime: str) -> None:
    with path.open("rb") as source:
        header = source.read(512)
    valid = {
        "image/jpeg": header.startswith(b"\xff\xd8\xff"),
        "image/png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
        "video/mp4": header[4:8] == b"ftyp",
        "video/webm": header.startswith(b"\x1a\x45\xdf\xa3") and b"\x42\x82\x84webm" in header,
    }[mime]
    if not valid:
        raise MediaError("invalid_media", "File content does not match the declared format.")


def _inspect_image(path: Path, mime: str, settings: Settings, thumbnail: Path) -> tuple[int, int]:
    expected = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[mime]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format != expected:
                    raise MediaError("invalid_media", "Image content does not match its format.")
                width, height = image.size
                if width * height > settings.max_image_pixels:
                    raise MediaError("image_too_large", "Image pixel count exceeds the configured limit.", 413)
                image.verify()
            with Image.open(path) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                width, height = oriented.size
                oriented.thumbnail((512, 512), Image.Resampling.LANCZOS)
                if oriented.mode in ("RGBA", "LA") or "transparency" in oriented.info:
                    with_alpha = oriented.convert("RGBA")
                    background = Image.new("RGB", oriented.size, "white")
                    background.paste(with_alpha, mask=with_alpha.getchannel("A"))
                    preview = background
                else:
                    preview = oriented.convert("RGB")
                preview.save(thumbnail, format="JPEG", quality=85)
                return width, height
    except MediaError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            UnidentifiedImageError) as exc:
        raise MediaError("invalid_media", "Image is malformed or truncated.") from exc


def _probe_video(path: Path, mime: str, settings: Settings, thumbnail: Path) -> dict[str, object]:
    if shutil.which(settings.ffprobe_binary) is None:
        raise MediaError("media_dependency_unavailable", "FFprobe is required for video upload.", 503)
    try:
        probe = subprocess.run(
            [settings.ffprobe_binary, "-v", "error", "-print_format", "json", "-show_format",
             "-show_streams", str(path)],
            capture_output=True, text=True, timeout=settings.probe_timeout_seconds, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaError("video_probe_failed", "Video metadata inspection failed or timed out.") from exc
    if probe.returncode != 0:
        raise MediaError("invalid_media", "Video is malformed or unsupported.")
    try:
        data = json.loads(probe.stdout)
        container = data["format"]["format_name"].split(",")
        expected_container = "mp4" if mime == "video/mp4" else "webm"
        if expected_container not in container:
            raise MediaError("invalid_media", "Video container does not match its format.")
        streams = data["streams"]
        video = next(stream for stream in streams if stream["codec_type"] == "video")
        width, height = int(video["width"]), int(video["height"])
        if width <= 0 or height <= 0:
            raise ValueError("invalid video dimensions")
        duration_value = data["format"].get("duration") or video.get("duration")
        duration = float(duration_value)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid duration")
        duration_ms = round(duration * 1000)
        if duration_ms > settings.max_video_duration_ms:
            raise MediaError("video_too_long", "Video duration exceeds the configured limit.", 413)
        rotation = int(video.get("tags", {}).get("rotate", 0))
        for side_data in video.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = int(side_data["rotation"])
        if abs(rotation) % 180 == 90:
            width, height = height, width
        raw_rate = video.get("avg_frame_rate") or video.get("r_frame_rate")
        frame_rate = float(Fraction(raw_rate)) if raw_rate and raw_rate != "0/0" else None
        if frame_rate is not None and (not math.isfinite(frame_rate) or frame_rate <= 0):
            frame_rate = None
        codec = str(video["codec_name"])
        audio = next((s.get("codec_name") for s in streams if s.get("codec_type") == "audio"), None)
        likely_video = codec == "h264" if mime == "video/mp4" else codec in {"vp8", "vp9"}
        likely_audio = audio is None or audio in ({"aac", "mp3"} if mime == "video/mp4" else {"opus", "vorbis"})
        compatibility = "likely" if likely_video and likely_audio else "uncertain"
    except MediaError:
        raise
    except (KeyError, TypeError, ValueError, StopIteration, ZeroDivisionError, OverflowError) as exc:
        raise MediaError("invalid_media", "Video metadata is incomplete or invalid.") from exc

    if shutil.which(settings.ffmpeg_binary) is not None:
        try:
            poster = subprocess.run(
                [settings.ffmpeg_binary, "-v", "error", "-y", "-i", str(path),
                 "-frames:v", "1", "-vf", "scale=512:-2", str(thumbnail)],
                capture_output=True, timeout=settings.probe_timeout_seconds, check=False,
            )
            if poster.returncode != 0 or not thumbnail.is_file() or thumbnail.stat().st_size == 0:
                raise MediaError("invalid_media", "Video could not be decoded for preview.")
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise MediaError("video_probe_failed", "Video preview extraction failed or timed out.") from exc
    return {"width": width, "height": height, "duration_ms": duration_ms,
            "frame_rate": round(frame_rate, 3) if frame_rate else None,
            "video_codec": codec, "playback_compatibility": compatibility}


class MediaService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.media_root = settings.media_root.resolve()
        self.thumbnail_root = settings.thumbnail_root.resolve()
        self.repository = MediaRepository(settings.database_path.resolve())

    def initialize(self) -> None:
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.thumbnail_root.mkdir(parents=True, exist_ok=True)
        self.repository.initialize()

    def upload(self, file: UploadFile) -> MediaAsset:
        original_name = _safe_name(file.filename)
        extension = Path(original_name).suffix.lower()
        if extension not in FORMATS:
            raise MediaError("unsupported_format", "Supported formats: JPEG, PNG, WebP, MP4, WebM.")
        kind, mime = FORMATS[extension]
        declared = (file.content_type or "").split(";", 1)[0].lower().strip()
        if declared != mime:
            raise MediaError("invalid_mime_type", "Declared MIME type does not match the file format.")
        media_id = str(uuid4())
        temporary = self.media_root / f".{media_id}.upload"
        final = self.media_root / f"{media_id}{STORED_EXTENSIONS[mime]}"
        thumbnail = self.thumbnail_root / f"{media_id}.jpg"
        maximum = self.settings.max_image_bytes if kind == "image" else self.settings.max_video_bytes
        size = 0
        checksum = hashlib.sha256()
        committed = False
        try:
            with temporary.open("xb") as target:
                while chunk := file.file.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > maximum:
                        raise MediaError("file_too_large", "File exceeds the configured size limit.", 413)
                    target.write(chunk)
                    checksum.update(chunk)
            if size == 0:
                raise MediaError("invalid_media", "Uploaded file is empty.")
            _check_signature(temporary, mime)
            if kind == "image":
                width, height = _inspect_image(temporary, mime, self.settings, thumbnail)
                details: dict[str, object] = {"width": width, "height": height,
                    "duration_ms": None, "frame_rate": None, "video_codec": None,
                    "playback_compatibility": None}
            else:
                details = _probe_video(temporary, mime, self.settings, thumbnail)
            thumbnail_ref = thumbnail.name if thumbnail.exists() else None
            asset = MediaAsset(
                media_id=media_id, original_filename=original_name, media_type=kind,
                detected_mime_type=mime, file_size_bytes=size, created_at=datetime.now(UTC),
                sha256=checksum.hexdigest(), thumbnail_available=thumbnail_ref is not None, **details,
            )
            temporary.replace(final)
            self.repository.insert(asset, final.name, thumbnail_ref)
            committed = True
            return asset
        finally:
            temporary.unlink(missing_ok=True)
            if not committed:
                final.unlink(missing_ok=True)
                thumbnail.unlink(missing_ok=True)

    @staticmethod
    def validate_id(media_id: str) -> str:
        try:
            parsed = UUID(media_id)
            if parsed.version != 4 or str(parsed) != media_id:
                raise ValueError("noncanonical media ID")
        except ValueError as exc:
            raise MediaError("media_not_found", "Media item was not found.", 404) from exc
        return media_id

    def get(self, media_id: str) -> MediaAsset:
        row = self.repository.get(self.validate_id(media_id))
        if row is None:
            raise MediaError("media_not_found", "Media item was not found.", 404)
        return public_asset(row)

    def list(self, limit: int) -> list[MediaAsset]:
        return [public_asset(row) for row in self.repository.list(limit)]

    def paths(self, media_id: str) -> tuple[MediaAsset, Path, Path | None]:
        row = self.repository.get(self.validate_id(media_id))
        if row is None:
            raise MediaError("media_not_found", "Media item was not found.", 404)
        asset = public_asset(row)
        expected = f"{media_id}{STORED_EXTENSIONS[asset.detected_mime_type]}"
        if row["storage_ref"] != expected:
            raise MediaError("media_not_found", "Media item was not found.", 404)
        thumbnail_ref = row["thumbnail_ref"]
        if thumbnail_ref is not None and thumbnail_ref != f"{media_id}.jpg":
            raise MediaError("media_not_found", "Media item was not found.", 404)
        return asset, self.media_root / expected, self.thumbnail_root / thumbnail_ref if thumbnail_ref else None

    def delete(self, media_id: str) -> None:
        _, source, thumbnail = self.paths(media_id)
        source.unlink(missing_ok=True)
        if thumbnail:
            thumbnail.unlink(missing_ok=True)
        self.repository.delete(media_id)


def parse_byte_range(header: str | None, size: int) -> tuple[int, int] | None:
    if header is None:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if not match or (not match[1] and not match[2]):
        raise MediaError("invalid_range", "Invalid byte range.", 416,
                         {"Content-Range": f"bytes */{size}"})
    if not match[1]:
        suffix = int(match[2])
        if suffix == 0:
            raise MediaError("invalid_range", "Invalid byte range.", 416,
                             {"Content-Range": f"bytes */{size}"})
        return max(0, size - suffix), size - 1
    start = int(match[1])
    end = int(match[2]) if match[2] else size - 1
    if start >= size or start > end:
        raise MediaError("invalid_range", "Byte range is outside the file.", 416,
                         {"Content-Range": f"bytes */{size}"})
    return start, min(end, size - 1)
