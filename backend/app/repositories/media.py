import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

from app.core.logging import log_event
from app.schemas.media import MediaAsset

logger = logging.getLogger("visionlab.database")


class MediaRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS media (
                    media_id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    detected_mime_type TEXT NOT NULL,
                    width INTEGER NOT NULL,
                    height INTEGER NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    duration_ms INTEGER,
                    frame_rate REAL,
                    video_codec TEXT,
                    playback_compatibility TEXT,
                    created_at TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    storage_ref TEXT NOT NULL,
                    thumbnail_ref TEXT
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_created ON media(created_at DESC)"
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS analyses (
                analysis_id TEXT PRIMARY KEY,
                media_id TEXT NOT NULL REFERENCES media(media_id) ON DELETE CASCADE,
                task TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                result_json TEXT,
                error_code TEXT
            )""")
            connection.execute(
                """CREATE INDEX IF NOT EXISTS idx_analyses_media
                ON analyses(media_id, created_at DESC)"""
            )
            connection.execute("""CREATE TABLE IF NOT EXISTS vqa_conversations (
                conversation_id TEXT PRIMARY KEY,
                media_id TEXT NOT NULL REFERENCES media(media_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS idx_vqa_media
                ON vqa_conversations(media_id, updated_at DESC)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS vqa_messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES vqa_conversations(conversation_id)
                    ON DELETE CASCADE,
                role TEXT NOT NULL,
                record_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS idx_vqa_messages
                ON vqa_messages(conversation_id, created_at)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS accessibility_results (
                result_id TEXT PRIMARY KEY,
                media_id TEXT NOT NULL REFERENCES media(media_id) ON DELETE CASCADE,
                record_json TEXT NOT NULL,
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS idx_accessibility_media
                ON accessibility_results(media_id, created_at DESC)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS video_analyses (
                analysis_id TEXT PRIMARY KEY,
                media_id TEXT NOT NULL REFERENCES media(media_id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                record_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS idx_video_analyses_media
                ON video_analyses(media_id, created_at DESC)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS video_jobs (
                job_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL REFERENCES video_analyses(analysis_id) ON DELETE CASCADE,
                media_id TEXT NOT NULL REFERENCES media(media_id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                revision INTEGER NOT NULL,
                record_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS idx_video_jobs_media
                ON video_jobs(media_id, created_at DESC)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS video_frames (
                frame_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL REFERENCES video_analyses(analysis_id) ON DELETE CASCADE,
                timestamp_ms INTEGER NOT NULL,
                record_json TEXT NOT NULL,
                UNIQUE(analysis_id, timestamp_ms)
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS idx_video_frames_time
                ON video_frames(analysis_id, timestamp_ms)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS video_captions (
                caption_id TEXT PRIMARY KEY,
                analysis_id TEXT NOT NULL REFERENCES video_analyses(analysis_id) ON DELETE CASCADE,
                timestamp_ms INTEGER NOT NULL,
                version INTEGER NOT NULL,
                record_json TEXT NOT NULL
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS idx_video_captions_time
                ON video_captions(analysis_id, timestamp_ms)""")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def insert(self, asset: MediaAsset, storage_ref: str, thumbnail_ref: str | None) -> None:
        started = perf_counter()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO media VALUES (
                    :media_id, :original_filename, :media_type, :detected_mime_type,
                    :width, :height, :file_size_bytes, :duration_ms, :frame_rate,
                    :video_codec, :playback_compatibility, :created_at, :sha256,
                    :storage_ref, :thumbnail_ref
                )""",
                {
                    **asset.model_dump(mode="json", exclude={"thumbnail_available"}),
                    "storage_ref": storage_ref,
                    "thumbnail_ref": thumbnail_ref,
                },
            )
        log_event(
            logger,
            "media.persisted",
            "COMPLETE Media metadata saved",
            media_id=asset.media_id,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def get(self, media_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM media WHERE media_id = ?", (media_id,)
            ).fetchone()

    def list(self, limit: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM media ORDER BY created_at DESC, media_id DESC LIMIT ?", (limit,)
            ).fetchall()

    def delete(self, media_id: str) -> None:
        started = perf_counter()
        analysis_count = 0
        with self._connect() as connection:
            analysis_count = connection.execute(
                "SELECT COUNT(*) FROM analyses WHERE media_id = ?", (media_id,)
            ).fetchone()[0]
            connection.execute("DELETE FROM media WHERE media_id = ?", (media_id,))
        if analysis_count:
            log_event(
                logger,
                "analysis.deleted",
                "COMPLETE Related analyses removed",
                media_id=media_id,
                records_deleted=analysis_count,
            )
        log_event(
            logger,
            "media.deleted",
            "COMPLETE Media metadata removed",
            media_id=media_id,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )


def public_asset(row: sqlite3.Row) -> MediaAsset:
    return MediaAsset.model_validate(
        {key: row[key] for key in row.keys() if key not in ("storage_ref", "thumbnail_ref")}
        | {"thumbnail_available": row["thumbnail_ref"] is not None}
    )
