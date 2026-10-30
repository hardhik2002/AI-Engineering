from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from time import perf_counter

from app.core.logging import log_event
from app.schemas.caption import CaptionRecord
from app.schemas.vision import AnalysisRecord

logger = logging.getLogger("visionlab.database")


class AnalysisRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def insert_started(self, analysis_id: str, media_id: str, created_at: datetime) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO analyses(analysis_id,media_id,task,status,created_at)
                VALUES(?,?,?,?,?)""",
                (analysis_id, media_id, "object_detection", "running", created_at.isoformat()),
            )

    def finish(self, record: AnalysisRecord) -> None:
        started = perf_counter()
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
        log_event(
            logger,
            "analysis.persisted",
            "COMPLETE Analysis record saved",
            media_id=record.media_id,
            analysis_id=record.analysis_id,
            status=record.status,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def get(self, media_id: str, analysis_id: str) -> AnalysisRecord | None:
        started = perf_counter()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT result_json FROM analyses WHERE media_id=? AND analysis_id=?
                AND task='object_detection'""",
                (media_id, analysis_id),
            ).fetchone()
        result = (
            AnalysisRecord.model_validate_json(row["result_json"])
            if row and row["result_json"]
            else None
        )
        if result:
            log_event(
                logger,
                "analysis.loaded",
                "COMPLETE Saved analysis loaded",
                media_id=media_id,
                analysis_id=analysis_id,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
        return result

    def list(self, media_id: str) -> list[AnalysisRecord]:
        started = perf_counter()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT result_json FROM analyses WHERE media_id=?
                AND task='object_detection' AND result_json IS NOT NULL
                ORDER BY created_at DESC, analysis_id DESC LIMIT 100""",
                (media_id,),
            ).fetchall()
        results = [AnalysisRecord.model_validate_json(row["result_json"]) for row in rows]
        log_event(
            logger,
            "analysis.loaded",
            "COMPLETE Saved analyses listed",
            media_id=media_id,
            result_count=len(results),
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return results

    def insert_caption(self, record: CaptionRecord) -> None:
        started = perf_counter()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO analyses
                (analysis_id,media_id,task,status,created_at,completed_at,result_json)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    record.analysis_id,
                    record.media_id,
                    record.task,
                    record.status,
                    record.created_at.isoformat(),
                    record.completed_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
        log_event(
            logger,
            "caption.persisted",
            "COMPLETE Caption result saved",
            media_id=record.media_id,
            analysis_id=record.analysis_id,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )

    def list_captions(self, media_id: str) -> list[CaptionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT result_json FROM analyses WHERE media_id=? AND task IN
                ('short','detailed','extended','dense','selected_object')
                ORDER BY created_at DESC, analysis_id DESC LIMIT 100""",
                (media_id,),
            ).fetchall()
        return [CaptionRecord.model_validate_json(row["result_json"]) for row in rows]
