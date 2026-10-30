import sqlite3
from datetime import datetime
from pathlib import Path

from app.schemas.vision import AnalysisRecord


class AnalysisRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def insert_started(self, analysis_id: str, media_id: str, created_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO analyses(analysis_id,media_id,task,status,created_at)
                VALUES(?,?,?,?,?)""",
                (analysis_id, media_id, "object_detection", "running", created_at.isoformat()),
            )

    def finish(self, record: AnalysisRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE analyses SET status=?,completed_at=?,result_json=?,error_code=?
                WHERE analysis_id=?""",
                (
                    record.status,
                    record.completed_at.isoformat(),
                    record.model_dump_json(),
                    record.error_code,
                    record.analysis_id,
                ),
            )

    def get(self, media_id: str, analysis_id: str) -> AnalysisRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result_json FROM analyses WHERE media_id=? AND analysis_id=?",
                (media_id, analysis_id),
            ).fetchone()
        return (
            AnalysisRecord.model_validate_json(row["result_json"])
            if row and row["result_json"]
            else None
        )

    def list(self, media_id: str) -> list[AnalysisRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT result_json FROM analyses WHERE media_id=? AND result_json IS NOT NULL
                ORDER BY created_at DESC, analysis_id DESC LIMIT 100""",
                (media_id,),
            ).fetchall()
        return [AnalysisRecord.model_validate_json(row["result_json"]) for row in rows]
