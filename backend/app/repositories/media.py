import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from app.schemas.media import MediaAsset


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
            connection.execute("CREATE INDEX IF NOT EXISTS idx_media_created ON media(created_at DESC)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def insert(self, asset: MediaAsset, storage_ref: str, thumbnail_ref: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO media VALUES (
                    :media_id, :original_filename, :media_type, :detected_mime_type,
                    :width, :height, :file_size_bytes, :duration_ms, :frame_rate,
                    :video_codec, :playback_compatibility, :created_at, :sha256,
                    :storage_ref, :thumbnail_ref
                )""",
                {**asset.model_dump(mode="json", exclude={"thumbnail_available"}),
                 "storage_ref": storage_ref, "thumbnail_ref": thumbnail_ref},
            )

    def get(self, media_id: str) -> sqlite3.Row | None:
        with self._connect() as connection:
            return connection.execute("SELECT * FROM media WHERE media_id = ?", (media_id,)).fetchone()

    def list(self, limit: int) -> list[sqlite3.Row]:
        with self._connect() as connection:
            return connection.execute(
                "SELECT * FROM media ORDER BY created_at DESC, media_id DESC LIMIT ?", (limit,)
            ).fetchall()

    def delete(self, media_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM media WHERE media_id = ?", (media_id,))


def public_asset(row: sqlite3.Row) -> MediaAsset:
    return MediaAsset.model_validate(
        {key: row[key] for key in row.keys() if key not in ("storage_ref", "thumbnail_ref")}
        | {"thumbnail_available": row["thumbnail_ref"] is not None}
    )
