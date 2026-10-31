"""Bounded in-process video jobs with incremental SQLite results."""

import logging
import math
from concurrent.futures import Future, ThreadPoolExecutor
from contextvars import copy_context
from datetime import UTC, datetime
from pathlib import Path
from threading import BoundedSemaphore, Event, Lock
from time import perf_counter
from uuid import uuid4

from PIL import Image

from app.core.config import Settings
from app.core.logging import log_event
from app.providers.captioner import CaptionError
from app.providers.video_tracker import VideoTracker
from app.repositories.video import VideoRepository
from app.schemas.media import MediaAsset
from app.schemas.video import (
    VideoAnalysis,
    VideoAnalyzeRequest,
    VideoCaption,
    VideoCaptionEdit,
    VideoDetection,
    VideoFrameResult,
    VideoJob,
)
from app.services.analysis import normalized_detection
from app.services.caption import CaptionService
from app.services.media import MediaError, MediaService
from app.services.video_decode import (
    VideoDecodeError,
    frame_image,
    nearest_frames,
    sampled_frames,
)

logger = logging.getLogger("visionlab.video")
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


class VideoError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        self.code, self.message, self.status_code = code, message, status_code
        super().__init__(message)


class VideoCancelled(Exception):
    code = "video_cancelled"


class VideoAnalysisService:
    def __init__(
        self,
        settings: Settings,
        media: MediaService,
        tracker: VideoTracker,
        caption: CaptionService,
    ):
        self.settings, self.media, self.tracker, self.caption = settings, media, tracker, caption
        self.repository = VideoRepository(settings.database_path)
        self.executor = ThreadPoolExecutor(
            max_workers=settings.video_analysis_concurrency, thread_name_prefix="visionlab-video"
        )
        self.slots = BoundedSemaphore(settings.video_analysis_concurrency + 1)
        self._lock = Lock()
        self._stops: dict[str, Event] = {}
        self._futures: dict[str, Future] = {}

    def recover(self) -> int:
        return self.repository.interrupt_active()

    def shutdown(self) -> None:
        with self._lock:
            for event in self._stops.values():
                event.set()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _video(self, media_id: str) -> tuple[MediaAsset, Path]:
        asset, path, _ = self.media.paths(media_id)
        if asset.media_type != "video":
            raise MediaError("unsupported_media_task", "This feature requires an uploaded video.")
        if not path.is_file():
            raise MediaError("media_not_found", "Media content was not found.", 404)
        return asset, path

    def _schedule(self, job: VideoJob, worker, *args) -> None:
        stop = Event()
        with self._lock:
            self._stops[job.job_id] = stop
        context = copy_context()
        try:
            future = self.executor.submit(context.run, worker, job, stop, *args)
        except RuntimeError as exc:
            with self._lock:
                self._stops.pop(job.job_id, None)
            raise VideoError(
                "video_worker_unavailable", "Video worker is unavailable.", 503
            ) from exc
        with self._lock:
            self._futures[job.job_id] = future

        def done(_future: Future) -> None:
            with self._lock:
                self._stops.pop(job.job_id, None)
                self._futures.pop(job.job_id, None)
            self.slots.release()

        future.add_done_callback(done)

    def create_analysis(self, media_id: str, request: VideoAnalyzeRequest | None) -> VideoJob:
        asset, _ = self._video(media_id)
        if not self.slots.acquire(blocking=False):
            raise VideoError("video_queue_full", "Video worker queue is full.", 429)
        defaults = VideoAnalyzeRequest(
            detection_fps=self.settings.video_detection_fps,
            caption_interval_seconds=self.settings.video_caption_interval_seconds,
            detection={
                "confidence": self.settings.detection_confidence,
                "iou": self.settings.detection_iou,
                "image_size": self.settings.detection_image_size,
                "max_detections": self.settings.detection_max_detections,
            },
        )
        overrides = request.model_dump(exclude_unset=True) if request else {}
        if "detection" in overrides:
            overrides["detection"] = defaults.detection.model_dump() | overrides["detection"]
        parameters = VideoAnalyzeRequest.model_validate(defaults.model_dump() | overrides)
        now = datetime.now(UTC)
        analysis_id, job_id = str(uuid4()), str(uuid4())
        analysis = VideoAnalysis(
            analysis_id=analysis_id,
            media_id=media_id,
            job_id=job_id,
            parameters=parameters,
            status="queued",
            created_at=now,
            duration_ms=asset.duration_ms or 0,
        )
        estimate = min(
            self.settings.video_max_processed_frames,
            math.ceil(analysis.duration_ms * parameters.detection_fps / 1000),
        )
        job = VideoJob(
            job_id=job_id,
            analysis_id=analysis_id,
            media_id=media_id,
            status="queued",
            stage="queued",
            total_frames_estimate=estimate,
            created_at=now,
            updated_at=now,
        )
        try:
            self.repository.create(analysis, job)
            self._schedule(job, self._run_analysis, analysis)
        except Exception:
            # A queued row can be recovered as interrupted after a scheduling failure.
            if job_id not in self._futures:
                try:
                    self.slots.release()
                except ValueError:
                    pass
            raise
        log_event(
            logger,
            "video.job_created",
            "COMPLETE Video job queued",
            job_id=job_id,
            media_id=media_id,
            analysis_id=analysis_id,
        )
        return job

    def create_caption_job(self, media_id: str, analysis_id: str, timestamp_ms: int) -> VideoJob:
        asset, _ = self._video(media_id)
        analysis = self.get_analysis(media_id, analysis_id)
        if timestamp_ms > (asset.duration_ms or 0):
            raise VideoError("invalid_timestamp", "Timestamp exceeds video duration.")
        if analysis.status not in {"completed", "interrupted"}:
            raise VideoError("analysis_not_ready", "Complete video analysis first.", 409)
        if not self.slots.acquire(blocking=False):
            raise VideoError("video_queue_full", "Video worker queue is full.", 429)
        now = datetime.now(UTC)
        job = VideoJob(
            job_id=str(uuid4()),
            analysis_id=analysis_id,
            media_id=media_id,
            kind="caption_frame",
            status="queued",
            stage="queued",
            total_frames_estimate=1,
            target_timestamp_ms=timestamp_ms,
            created_at=now,
            updated_at=now,
        )
        try:
            self.repository.create_caption_job(job)
            self._schedule(job, self._run_caption_frame, analysis)
        except Exception:
            if job.job_id not in self._futures:
                try:
                    self.slots.release()
                except ValueError:
                    pass
            raise
        return job

    def _state(
        self,
        analysis: VideoAnalysis,
        job: VideoJob,
        *,
        status: str,
        stage: str,
        started: float,
        error_code: str | None = None,
        finished: bool = False,
    ) -> tuple[VideoAnalysis, VideoJob]:
        now = datetime.now(UTC)
        analysis = analysis.model_copy(
            update={
                "status": status,
                "completed_at": now if finished else None,
                "elapsed_ms": (perf_counter() - started) * 1000,
                "error_code": error_code,
            }
        )
        job = job.model_copy(
            update={
                "status": status,
                "stage": stage,
                "updated_at": now,
                "elapsed_ms": analysis.elapsed_ms,
                "error_code": error_code,
                "revision": job.revision + 1,
                "processed_frames": analysis.processed_frames,
                "current_timestamp_ms": analysis.coverage_end_ms,
            }
        )
        if not self.repository.save_state(analysis, job):
            raise VideoError("media_not_found", "Media item was removed.", 404)
        return analysis, job

    def _run_analysis(self, job: VideoJob, stop: Event, analysis: VideoAnalysis) -> None:
        started = perf_counter()
        try:
            if stop.is_set():
                raise VideoCancelled()
            asset, path = self._video(job.media_id)
            analysis, job = self._state(
                analysis, job, status="running", stage="loading_model", started=started
            )
            self.tracker.start()
            model = self.tracker.model_info()
            log_event(
                logger,
                "video.processing_started",
                "START Video analysis",
                media_id=job.media_id,
                job_id=job.job_id,
                analysis_id=job.analysis_id,
                model=model.name,
                device=model.device,
            )
            next_caption_ms = 0
            for item in sampled_frames(
                path,
                asset,
                self.settings,
                analysis.parameters.detection_fps,
                self.settings.video_max_processed_frames,
                stop,
            ):
                if stop.is_set():
                    raise VideoCancelled()
                image = frame_image(item, asset, self.settings.detection_max_source_side)
                log_event(logger, "video.frame_decoded", "COMPLETE Sampled frame decoded",
                          level=logging.DEBUG, job_id=job.job_id,
                          current_timestamp_ms=item.timestamp_ms)
                detect = (
                    self.tracker.track if analysis.parameters.track_objects else self.tracker.detect
                )
                raw, inference_ms = detect(image, analysis.parameters.detection)
                detections = []
                for object_ in raw:
                    normalized = normalized_detection(object_, image.width, image.height)
                    detections.append(
                        VideoDetection(**normalized.model_dump(), track_id=object_.track_id)
                    )
                frame_id = str(uuid4())
                frame = VideoFrameResult(
                    frame_id=frame_id,
                    analysis_id=analysis.analysis_id,
                    timestamp_ms=item.timestamp_ms,
                    source_pts=item.source_pts,
                    time_base=item.time_base,
                    source_width=asset.width,
                    source_height=asset.height,
                    detections=detections,
                    model=model,
                    inference_ms=inference_ms,
                )
                self.repository.add_frame(frame)
                log_event(logger, "video.detection_completed",
                          "COMPLETE Sampled frame detections saved", level=logging.DEBUG,
                          job_id=job.job_id, current_timestamp_ms=item.timestamp_ms,
                          detection_count=len(detections), inference_ms=inference_ms)
                if analysis.parameters.track_objects:
                    log_event(logger, "video.tracking_updated",
                              "COMPLETE ByteTrack state updated", level=logging.DEBUG,
                              job_id=job.job_id, current_timestamp_ms=item.timestamp_ms,
                              result_count=sum(item.track_id is not None for item in detections))
                analysis = analysis.model_copy(
                    update={
                        "processed_frames": analysis.processed_frames + 1,
                        "coverage_end_ms": item.timestamp_ms,
                    }
                )
                if analysis.parameters.generate_captions and (
                    item.timestamp_ms >= next_caption_ms
                    and analysis.caption_frames < self.settings.video_max_caption_frames
                ):
                    if stop.is_set():
                        raise VideoCancelled()
                    self._caption(image, analysis.analysis_id, frame_id, item.timestamp_ms, stop)
                    analysis = analysis.model_copy(
                        update={
                            "caption_frames": analysis.caption_frames + 1,
                        }
                    )
                    next_caption_ms = item.timestamp_ms + round(
                        analysis.parameters.caption_interval_seconds * 1000
                    )
                analysis, job = self._state(
                    analysis, job, status="running", stage="processing", started=started
                )
                if analysis.processed_frames == 1 or analysis.processed_frames % 10 == 0:
                    log_event(
                        logger,
                        "video.progress_updated",
                        "COMPLETE Video progress",
                        media_id=job.media_id,
                        job_id=job.job_id,
                        processed_frames=analysis.processed_frames,
                        current_timestamp_ms=item.timestamp_ms,
                    )
            if stop.is_set():
                raise VideoCancelled()
            if analysis.processed_frames == 0:
                raise VideoDecodeError("video_no_timestamps", "No usable video frames had PTS.")
            analysis, job = self._state(
                analysis, job, status="completed", stage="completed", started=started, finished=True
            )
            log_event(
                logger,
                "video.processing_completed",
                "COMPLETE Video analysis",
                media_id=job.media_id,
                job_id=job.job_id,
                processed_frames=analysis.processed_frames,
                duration_ms=analysis.elapsed_ms,
            )
        except Exception as exc:
            cancelled = isinstance(exc, VideoCancelled) or stop.is_set()
            status = "cancelled" if cancelled else "failed"
            code = (
                "video_cancelled" if cancelled else getattr(exc, "code", "video_processing_failed")
            )
            try:
                self._state(
                    analysis,
                    job,
                    status=status,
                    stage=status,
                    started=started,
                    error_code=code,
                    finished=True,
                )
            except Exception:
                pass
            log_event(
                logger,
                "video.processing_cancelled" if cancelled else "video.processing_failed",
                "CANCELLED Video analysis" if cancelled else "FAILED Video analysis",
                level=logging.INFO if cancelled else logging.ERROR,
                media_id=job.media_id,
                job_id=job.job_id,
                error_code=code,
                exception_type=type(exc).__name__,
            )

    def _caption(
        self,
        image: Image.Image,
        analysis_id: str,
        frame_id: str | None,
        timestamp_ms: int,
        stop: Event,
    ) -> VideoCaption:
        while not self.caption.capacity.acquire(timeout=0.5):
            if stop.is_set():
                raise VideoCancelled()
        try:
            self.caption.provider.load_model()
            if max(image.size) > self.settings.florence_max_source_side:
                image = image.copy()
                image.thumbnail(
                    (self.settings.florence_max_source_side,) * 2, Image.Resampling.LANCZOS
                )
            parsed, inference_ms = self.caption.provider.generate(image, "short")
            text = parsed.get("<CAPTION>") if isinstance(parsed, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise CaptionError(
                    "malformed_caption", "Florence-2 returned no frame caption.", 500
                )
            record = VideoCaption(
                caption_id=str(uuid4()),
                analysis_id=analysis_id,
                frame_id=frame_id,
                timestamp_ms=timestamp_ms,
                text=text.strip(),
                source="florence",
                model=self.caption.provider.model_info(),
                inference_ms=inference_ms,
                created_at=datetime.now(UTC),
            )
            self.repository.add_caption(record)
            log_event(
                logger,
                "video.caption_completed",
                "COMPLETE Frame caption saved",
                analysis_id=analysis_id,
                current_timestamp_ms=timestamp_ms,
                inference_ms=inference_ms,
            )
            return record
        finally:
            self.caption.capacity.release()

    def _run_caption_frame(self, job: VideoJob, stop: Event, analysis: VideoAnalysis) -> None:
        started = perf_counter()
        try:
            if stop.is_set():
                raise VideoCancelled()
            asset, path = self._video(job.media_id)
            job = job.model_copy(
                update={
                    "status": "running",
                    "stage": "decoding",
                    "revision": job.revision + 1,
                    "updated_at": datetime.now(UTC),
                }
            )
            self.repository.save_job(job)
            selected = nearest_frames(
                path,
                asset,
                self.settings,
                [job.target_timestamp_ms],
                self.settings.florence_max_source_side,
            )
            if not selected:
                raise VideoDecodeError("video_no_timestamps", "No frame found at this time.")
            if stop.is_set():
                raise VideoCancelled()
            timestamp_ms, image = selected[0]
            self._caption(image, analysis.analysis_id, None, timestamp_ms, stop)
            analysis = analysis.model_copy(
                update={
                    "caption_frames": analysis.caption_frames + 1,
                }
            )
            self.repository.save_analysis(analysis)
            status, error = "completed", None
        except Exception as exc:
            status = "cancelled" if isinstance(exc, VideoCancelled) or stop.is_set() else "failed"
            error = (
                "video_cancelled"
                if status == "cancelled"
                else getattr(exc, "code", "video_caption_failed")
            )
        job = job.model_copy(
            update={
                "status": status,
                "stage": status,
                "error_code": error,
                "processed_frames": 1 if status == "completed" else 0,
                "current_timestamp_ms": timestamp_ms if status == "completed" else None,
                "elapsed_ms": (perf_counter() - started) * 1000,
                "updated_at": datetime.now(UTC),
                "revision": job.revision + 1,
            }
        )
        self.repository.save_job(job)

    def get_analysis(self, media_id: str, analysis_id: str) -> VideoAnalysis:
        self._video(media_id)
        self.media.validate_id(analysis_id)
        analysis = self.repository.get_analysis(analysis_id, media_id)
        if analysis is None:
            raise VideoError("video_analysis_not_found", "Video analysis was not found.", 404)
        return analysis

    def list_analyses(self, media_id: str) -> list[VideoAnalysis]:
        self._video(media_id)
        return self.repository.list_analyses(media_id)

    def get_job(self, job_id: str) -> VideoJob:
        self.media.validate_id(job_id)
        job = self.repository.get_job(job_id)
        if job is None:
            raise VideoError("video_job_not_found", "Video job was not found.", 404)
        return job

    def cancel(self, job_id: str) -> VideoJob:
        job = self.get_job(job_id)
        if job.status in TERMINAL:
            return job
        with self._lock:
            stop = self._stops.get(job_id)
            future = self._futures.get(job_id)
            if stop:
                stop.set()
        if future and future.cancel():
            status = "cancelled"
        else:
            status = "cancel_requested"
        job = job.model_copy(
            update={
                "status": status,
                "stage": status,
                "updated_at": datetime.now(UTC),
                "revision": job.revision + 1,
            }
        )
        if job.kind == "analysis":
            analysis = self.repository.get_analysis(job.analysis_id)
            if analysis:
                analysis = analysis.model_copy(update={"status": status})
                self.repository.save_state(analysis, job)
        else:
            self.repository.save_job(job)
        return job

    def edit_caption(
        self, analysis_id: str, caption_id: str, edit: VideoCaptionEdit
    ) -> VideoCaption:
        self.media.validate_id(analysis_id)
        self.media.validate_id(caption_id)
        if self.repository.get_analysis(analysis_id) is None:
            raise VideoError("video_analysis_not_found", "Video analysis was not found.", 404)
        caption = self.repository.get_caption(analysis_id, caption_id)
        if caption is None:
            raise VideoError("video_caption_not_found", "Video caption was not found.", 404)
        if caption.version != edit.expected_version:
            raise VideoError("version_conflict", "Caption changed. Reload it before saving.", 409)
        revised = caption.model_copy(
            update={"edited_text": edit.edited_text.strip(), "version": caption.version + 1}
        )
        if not self.repository.update_caption(revised, edit.expected_version):
            raise VideoError("version_conflict", "Caption changed. Reload it before saving.", 409)
        return revised
