"""Indexed, incremental video result persistence in the existing SQLite database."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.video import (
    VideoAnalysis,
    VideoCaption,
    VideoFrameResult,
    VideoJob,
    VideoTimelineMarker,
    VideoTrack,
)


class VideoRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def create(self, analysis: VideoAnalysis, job: VideoJob) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO video_analyses VALUES(?,?,?,?,?)",
                (
                    analysis.analysis_id,
                    analysis.media_id,
                    analysis.status,
                    analysis.model_dump_json(),
                    analysis.created_at.isoformat(),
                ),
            )
            connection.execute(
                "INSERT INTO video_jobs VALUES(?,?,?,?,?,?,?)",
                (
                    job.job_id,
                    job.analysis_id,
                    job.media_id,
                    job.status,
                    job.revision,
                    job.model_dump_json(),
                    job.created_at.isoformat(),
                ),
            )

    def save_state(self, analysis: VideoAnalysis, job: VideoJob) -> bool:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE video_analyses SET status=?,record_json=? WHERE analysis_id=?",
                (analysis.status, analysis.model_dump_json(), analysis.analysis_id),
            ).rowcount
            connection.execute(
                "UPDATE video_jobs SET status=?,revision=?,record_json=? WHERE job_id=?",
                (job.status, job.revision, job.model_dump_json(), job.job_id),
            )
        return changed > 0

    def create_caption_job(self, job: VideoJob) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO video_jobs VALUES(?,?,?,?,?,?,?)",
                (
                    job.job_id,
                    job.analysis_id,
                    job.media_id,
                    job.status,
                    job.revision,
                    job.model_dump_json(),
                    job.created_at.isoformat(),
                ),
            )

    def save_job(self, job: VideoJob) -> bool:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE video_jobs SET status=?,revision=?,record_json=? WHERE job_id=?",
                (job.status, job.revision, job.model_dump_json(), job.job_id),
            ).rowcount
        return changed > 0

    def save_analysis(self, analysis: VideoAnalysis) -> bool:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE video_analyses SET status=?,record_json=? WHERE analysis_id=?",
                (analysis.status, analysis.model_dump_json(), analysis.analysis_id),
            ).rowcount
        return changed > 0

    def get_analysis(self, analysis_id: str, media_id: str | None = None) -> VideoAnalysis | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM video_analyses WHERE analysis_id=? "
                "AND (? IS NULL OR media_id=?)",
                (analysis_id, media_id, media_id),
            ).fetchone()
        return VideoAnalysis.model_validate_json(row[0]) if row else None

    def list_analyses(self, media_id: str) -> list[VideoAnalysis]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM video_analyses WHERE media_id=? "
                "ORDER BY created_at DESC LIMIT 50",
                (media_id,),
            ).fetchall()
        return [VideoAnalysis.model_validate_json(row[0]) for row in rows]

    def has_completed_analysis(self, *, tracking: bool = False) -> bool:
        predicate = (
            " AND json_extract(record_json, '$.parameters.track_objects')=1"
            if tracking
            else ""
        )
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM video_analyses WHERE status='completed'"
                + predicate
                + " LIMIT 1"
            ).fetchone()
        return row is not None

    def get_job(self, job_id: str) -> VideoJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM video_jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
        return VideoJob.model_validate_json(row[0]) if row else None

    def add_frame(self, frame: VideoFrameResult) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO video_frames VALUES(?,?,?,?)",
                (frame.frame_id, frame.analysis_id, frame.timestamp_ms, frame.model_dump_json()),
            )

    def add_caption(self, caption: VideoCaption) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO video_captions VALUES(?,?,?,?,?)",
                (
                    caption.caption_id,
                    caption.analysis_id,
                    caption.timestamp_ms,
                    caption.version,
                    caption.model_dump_json(),
                ),
            )

    def update_caption(self, caption: VideoCaption, expected_version: int) -> bool:
        with self._connect() as connection:
            changed = connection.execute(
                "UPDATE video_captions SET version=?,record_json=? "
                "WHERE caption_id=? AND analysis_id=? AND version=?",
                (
                    caption.version,
                    caption.model_dump_json(),
                    caption.caption_id,
                    caption.analysis_id,
                    expected_version,
                ),
            ).rowcount
        return changed > 0

    def get_caption(self, analysis_id: str, caption_id: str) -> VideoCaption | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM video_captions WHERE analysis_id=? AND caption_id=?",
                (analysis_id, caption_id),
            ).fetchone()
        return VideoCaption.model_validate_json(row[0]) if row else None

    def frames(
        self, analysis_id: str, start_ms: int, end_ms: int, limit: int
    ) -> list[VideoFrameResult]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM video_frames WHERE analysis_id=? AND timestamp_ms>=? "
                "AND timestamp_ms<=? ORDER BY timestamp_ms LIMIT ?",
                (analysis_id, start_ms, end_ms, limit),
            ).fetchall()
        return [VideoFrameResult.model_validate_json(row[0]) for row in rows]

    def captions(
        self, analysis_id: str, start_ms: int, end_ms: int, limit: int
    ) -> list[VideoCaption]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM video_captions WHERE analysis_id=? AND timestamp_ms>=? "
                "AND timestamp_ms<=? ORDER BY timestamp_ms, rowid LIMIT ?",
                (analysis_id, start_ms, end_ms, limit),
            ).fetchall()
        return [VideoCaption.model_validate_json(row[0]) for row in rows]

    def timeline(self, analysis_id: str) -> list[VideoTimelineMarker]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM video_frames WHERE analysis_id=? ORDER BY timestamp_ms "
                "LIMIT 3600",
                (analysis_id,),
            ).fetchall()
        return [
            VideoTimelineMarker(
                timestamp_ms=frame.timestamp_ms,
                object_count=len(frame.detections),
                track_ids=sorted(
                    {item.track_id for item in frame.detections if item.track_id is not None}
                ),
            )
            for row in rows
            if (frame := VideoFrameResult.model_validate_json(row[0]))
        ]

    def tracks(self, analysis_id: str, start_ms: int, end_ms: int, limit: int) -> list[VideoTrack]:
        frames = self.frames(analysis_id, start_ms, end_ms, 3600)
        tracks: dict[int, VideoTrack] = {}
        for frame in frames:
            for detection in frame.detections:
                if detection.track_id is None:
                    continue
                existing = tracks.get(detection.track_id)
                if existing is None:
                    tracks[detection.track_id] = VideoTrack(
                        track_id=detection.track_id,
                        class_id=detection.class_id,
                        label=detection.label,
                        first_timestamp_ms=frame.timestamp_ms,
                        last_timestamp_ms=frame.timestamp_ms,
                        sampled_observations=1,
                    )
                else:
                    existing.last_timestamp_ms = frame.timestamp_ms
                    existing.sampled_observations += 1
        return sorted(tracks.values(), key=lambda item: item.track_id)[:limit]

    def interrupt_active(self) -> int:
        now = datetime.now(UTC)
        count = 0
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM video_jobs WHERE status IN "
                "('queued','running','cancel_requested')"
            ).fetchall()
            for row in rows:
                job = VideoJob.model_validate_json(row[0]).model_copy(
                    update={
                        "status": "interrupted",
                        "stage": "interrupted",
                        "updated_at": now,
                        "revision": VideoJob.model_validate_json(row[0]).revision + 1,
                    }
                )
                analysis_row = connection.execute(
                    "SELECT record_json FROM video_analyses WHERE analysis_id=?",
                    (job.analysis_id,),
                ).fetchone()
                if not analysis_row:
                    continue
                analysis = VideoAnalysis.model_validate_json(analysis_row[0]).model_copy(
                    update={
                        "status": "interrupted",
                        "completed_at": now,
                        "error_code": "server_restarted",
                    }
                )
                connection.execute(
                    "UPDATE video_jobs SET status=?,revision=?,record_json=? WHERE job_id=?",
                    (job.status, job.revision, job.model_dump_json(), job.job_id),
                )
                if job.kind == "analysis":
                    connection.execute(
                        "UPDATE video_analyses SET status=?,record_json=? WHERE analysis_id=?",
                        (analysis.status, analysis.model_dump_json(), analysis.analysis_id),
                    )
                count += 1
        return count
