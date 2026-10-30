"""SQLite persistence for image conversations and accessibility revisions."""

import sqlite3
from pathlib import Path

from app.schemas.multimodal import AccessibilityRecord, VQAConversation, VQAMessage


class MultimodalRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def save_turn(
        self, conversation: VQAConversation, user: VQAMessage, assistant: VQAMessage, create: bool
    ) -> None:
        with self._connect() as connection:
            if create:
                connection.execute(
                    "INSERT INTO vqa_conversations VALUES (?,?,?,?)",
                    (
                        conversation.conversation_id,
                        conversation.media_id,
                        conversation.created_at.isoformat(),
                        conversation.updated_at.isoformat(),
                    ),
                )
            else:
                connection.execute(
                    "UPDATE vqa_conversations SET updated_at=? "
                    "WHERE conversation_id=? AND media_id=?",
                    (
                        conversation.updated_at.isoformat(),
                        conversation.conversation_id,
                        conversation.media_id,
                    ),
                )
            for message in (user, assistant):
                connection.execute(
                    "INSERT INTO vqa_messages VALUES (?,?,?,?,?)",
                    (
                        message.message_id,
                        conversation.conversation_id,
                        message.role,
                        message.model_dump_json(),
                        message.created_at.isoformat(),
                    ),
                )

    def get_conversation(self, media_id: str, conversation_id: str) -> VQAConversation | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM vqa_conversations WHERE media_id=? AND conversation_id=?",
                (media_id, conversation_id),
            ).fetchone()
            if not row:
                return None
            messages = connection.execute(
                "SELECT record_json FROM vqa_messages WHERE conversation_id=? "
                "ORDER BY created_at, rowid",
                (conversation_id,),
            ).fetchall()
        return VQAConversation(
            conversation_id=row["conversation_id"],
            media_id=row["media_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            messages=[VQAMessage.model_validate_json(item["record_json"]) for item in messages],
        )

    def list_conversations(self, media_id: str) -> list[VQAConversation]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT conversation_id FROM vqa_conversations WHERE media_id=? "
                "ORDER BY updated_at DESC LIMIT 50",
                (media_id,),
            ).fetchall()
        return [
            item
            for row in rows
            if (item := self.get_conversation(media_id, row["conversation_id"]))
        ]

    def delete_conversation(self, media_id: str, conversation_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM vqa_conversations WHERE media_id=? AND conversation_id=?",
                (media_id, conversation_id),
            )
            return cursor.rowcount > 0

    def insert_accessibility(self, record: AccessibilityRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO accessibility_results VALUES (?,?,?,?,?,?)",
                (
                    record.result_id,
                    record.media_id,
                    record.model_dump_json(),
                    record.version,
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                ),
            )

    def list_accessibility(self, media_id: str) -> list[AccessibilityRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM accessibility_results WHERE media_id=? "
                "ORDER BY created_at DESC LIMIT 50",
                (media_id,),
            ).fetchall()
        return [AccessibilityRecord.model_validate_json(row["record_json"]) for row in rows]

    def get_accessibility(self, media_id: str, result_id: str) -> AccessibilityRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM accessibility_results WHERE media_id=? AND result_id=?",
                (media_id, result_id),
            ).fetchone()
        return AccessibilityRecord.model_validate_json(row["record_json"]) if row else None

    def update_accessibility(self, record: AccessibilityRecord, expected_version: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE accessibility_results SET record_json=?,version=?,updated_at=? "
                "WHERE media_id=? AND result_id=? AND version=?",
                (
                    record.model_dump_json(),
                    record.version,
                    record.updated_at.isoformat(),
                    record.media_id,
                    record.result_id,
                    expected_version,
                ),
            )
            return cursor.rowcount > 0
