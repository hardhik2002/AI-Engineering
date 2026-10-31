"""PTS-driven streaming decode. Only selected frames are converted to image arrays."""

import json
import math
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from PIL import Image

from app.core.config import Settings
from app.schemas.media import MediaAsset


class VideoDecodeError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(message)


@dataclass
class PTSFrame:
    timestamp_ms: int
    source_pts: int
    time_base: str
    raw: object
    rotation: int


def display_rotation(path: Path, settings: Settings) -> int:
    try:
        result = subprocess.run(
            [
                settings.ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=settings.probe_timeout_seconds,
            check=False,
        )
        if result.returncode:
            raise ValueError("ffprobe failed")
        stream = json.loads(result.stdout)["streams"][0]
        rotation = stream.get("tags", {}).get("rotate", 0)
        for side in stream.get("side_data_list", []):
            if "rotation" in side:
                rotation = side["rotation"]
        return int(rotation) % 360
    except (OSError, ValueError, KeyError, IndexError, subprocess.TimeoutExpired) as exc:
        raise VideoDecodeError(
            "video_probe_failed", "Video orientation could not be read."
        ) from exc


def iter_pts_frames(
    path: Path, settings: Settings, stop: Event | None = None, max_decoded: int | None = None
) -> Iterator[PTSFrame]:
    try:
        import av
    except ImportError as exc:
        raise VideoDecodeError("pyav_missing", "Install the video backend extra.") from exc
    rotation = display_rotation(path, settings)
    try:
        with av.open(str(path)) as container:
            stream = container.streams.video[0]
            origin: float | None = None
            previous: int | None = None
            decoded = 0
            for frame in container.decode(stream):
                if stop is not None and stop.is_set():
                    return
                decoded += 1
                if decoded > (max_decoded or settings.video_max_decoded_frames):
                    raise VideoDecodeError("video_decode_limit", "Video decode limit reached.")
                if frame.pts is None or frame.time_base is None:
                    continue
                seconds = float(frame.pts * frame.time_base)
                if not math.isfinite(seconds):
                    continue
                if origin is None:
                    origin = seconds
                timestamp = round((seconds - origin) * 1000)
                if timestamp < 0 or previous is not None and timestamp <= previous:
                    continue
                previous = timestamp
                yield PTSFrame(timestamp, int(frame.pts), str(frame.time_base), frame, rotation)
    except VideoDecodeError:
        raise
    except Exception as exc:
        raise VideoDecodeError("video_decode_failed", "Video decoding failed.") from exc


def frame_image(item: PTSFrame, asset: MediaAsset, max_side: int) -> Image.Image:
    try:
        import cv2

        bgr = item.raw.to_ndarray(format="bgr24")
        if item.rotation == 90:
            bgr = cv2.rotate(bgr, cv2.ROTATE_90_CLOCKWISE)
        elif item.rotation == 180:
            bgr = cv2.rotate(bgr, cv2.ROTATE_180)
        elif item.rotation == 270:
            bgr = cv2.rotate(bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if bgr.shape[1] != asset.width or bgr.shape[0] != asset.height:
            raise VideoDecodeError(
                "video_dimensions_changed", "Decoded video dimensions differ from saved metadata."
            )
        scale = min(1.0, max_side / max(asset.width, asset.height))
        if scale < 1:
            bgr = cv2.resize(
                bgr,
                (max(1, round(asset.width * scale)), max(1, round(asset.height * scale))),
                interpolation=cv2.INTER_AREA,
            )
        return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    except VideoDecodeError:
        raise
    except Exception as exc:
        raise VideoDecodeError(
            "video_frame_invalid", "A video frame could not be decoded."
        ) from exc


def sampled_frames(
    path: Path,
    asset: MediaAsset,
    settings: Settings,
    fps: float,
    max_frames: int,
    stop: Event | None = None,
) -> Iterator[PTSFrame]:
    interval = 1000 / fps
    next_due = 0.0
    count = 0
    for item in iter_pts_frames(path, settings, stop):
        if item.timestamp_ms + 0.001 < next_due:
            continue
        yield item
        count += 1
        if count >= max_frames:
            return
        next_due = (math.floor(item.timestamp_ms / interval) + 1) * interval


def nearest_frames(
    path: Path, asset: MediaAsset, settings: Settings, targets_ms: list[int], max_side: int
) -> list[tuple[int, Image.Image]]:
    """Choose actual decoded frames nearest requested playback timestamps."""
    if not targets_ms:
        return []
    targets = sorted(set(targets_ms))
    results: list[tuple[int, Image.Image]] = []
    previous: PTSFrame | None = None
    target_index = 0
    for item in iter_pts_frames(path, settings):
        while target_index < len(targets) and item.timestamp_ms >= targets[target_index]:
            target = targets[target_index]
            chosen = (
                previous
                if previous and target - previous.timestamp_ms <= item.timestamp_ms - target
                else item
            )
            if not results or results[-1][0] != chosen.timestamp_ms:
                results.append((chosen.timestamp_ms, frame_image(chosen, asset, max_side)))
            target_index += 1
        if target_index == len(targets):
            break
        previous = item
    if target_index < len(targets) and previous is not None:
        if not results or results[-1][0] != previous.timestamp_ms:
            results.append((previous.timestamp_ms, frame_image(previous, asset, max_side)))
    return results
