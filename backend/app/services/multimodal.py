"""Bounded image-only multimodal workflows; SQLite operations run off the event loop."""

import asyncio
import base64
import io
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from app.core.config import Settings
from app.core.logging import log_event
from app.providers.multimodal import MultimodalVisionProvider, VisionProviderError
from app.repositories.multimodal import MultimodalRepository
from app.schemas.multimodal import (
    AccessibilityAnswer,
    AccessibilityEdit,
    AccessibilityRecord,
    AccessibilityRequest,
    VQAConversation,
    VQAMessage,
    VQARequest,
)
from app.services.caption import CaptionService
from app.services.media import MediaError, MediaService

logger = logging.getLogger("visionlab.multimodal")


def prepare_image_data_url(path: Path, expected_size: tuple[int, int], max_side: int) -> str:
    """Decode a validated local image, orient it, resize it, and remove metadata."""
    try:
        with Image.open(path) as source:
            if source.width * source.height != expected_size[0] * expected_size[1]:
                raise MediaError(
                    "media_changed", "Image dimensions no longer match saved metadata.", 409
                )
            oriented = ImageOps.exif_transpose(source)
            if oriented.size != expected_size:
                raise MediaError(
                    "media_changed", "Image dimensions no longer match saved metadata.", 409
                )
            if oriented.mode in ("RGBA", "LA") or "transparency" in oriented.info:
                rgba = oriented.convert("RGBA")
                image = Image.new("RGB", rgba.size, "white")
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image = oriented.convert("RGB")
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, "JPEG", quality=85)
            return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    except MediaError:
        raise
    except (OSError, ValueError) as exc:
        raise MediaError("invalid_media", "Saved image could not be decoded.", 422) from exc


class MultimodalService:
    def __init__(
        self,
        settings: Settings,
        media: MediaService,
        caption: CaptionService,
        provider: MultimodalVisionProvider,
    ):
        self.settings, self.media, self.caption, self.provider = settings, media, caption, provider
        self.repository = MultimodalRepository(settings.database_path)
        self.capacity = asyncio.BoundedSemaphore(settings.openai_max_concurrency)
        self.active_conversations: set[str] = set()

    async def _image(self, media_id: str) -> tuple[Path, tuple[int, int]]:
        asset, path, _ = await asyncio.to_thread(self.media.paths, media_id)
        if asset.media_type != "image":
            raise MediaError(
                "unsupported_media_task", "This feature requires an uploaded image.", 422
            )
        if not path.is_file():
            raise MediaError("media_not_found", "Media content was not found.", 404)
        return path, (asset.width, asset.height)

    async def _data_url(self, path: Path, size: tuple[int, int]) -> str:
        return await asyncio.to_thread(
            prepare_image_data_url, path, size, self.settings.openai_max_image_side
        )

    async def ask(self, media_id: str, body: VQARequest) -> VQAConversation:
        path, size = await self._image(media_id)
        if not body.consent_external_transfer:
            raise VisionProviderError(
                "external_consent_required", "Allow this image to be sent to OpenAI first.", 403
            )
        if self.provider.status()["state"] == "unconfigured":
            raise VisionProviderError(
                "openai_not_configured", "OpenAI vision needs a backend API key."
            )
        conversation = None
        if body.conversation_id:
            self.media.validate_id(body.conversation_id)
            conversation = await asyncio.to_thread(
                self.repository.get_conversation, media_id, body.conversation_id
            )
            if conversation is None:
                raise MediaError("conversation_not_found", "Conversation was not found.", 404)
            if len(conversation.messages) >= 100:
                raise VisionProviderError(
                    "conversation_limit", "Start a new conversation after 50 questions.", 409
                )
        key = body.conversation_id or str(uuid4())
        if key in self.active_conversations:
            raise VisionProviderError(
                "conversation_busy", "This conversation is processing a question.", 409
            )
        if self.capacity.locked():
            raise VisionProviderError("vision_busy", "OpenAI vision is busy. Retry shortly.", 429)
        self.active_conversations.add(key)
        await self.capacity.acquire()
        try:
            history = [
                (item.role, item.text) for item in (conversation.messages if conversation else [])
            ][-8:]
            image_url = await self._data_url(path, size)
            log_event(
                logger,
                "vqa.started",
                "START Image question",
                media_id=media_id,
                conversation_id=key,
                provider="openai",
            )
            result = await self.provider.answer(image_url, body.question.strip(), history)
            now = datetime.now(UTC)
            user = VQAMessage(
                message_id=str(uuid4()), role="user", text=body.question.strip(), created_at=now
            )
            assistant = VQAMessage(
                message_id=str(uuid4()),
                role="assistant",
                text=result.output.answer,
                created_at=now,
                grounding_status=result.output.grounding_status,
                uncertainty_note=result.output.uncertainty_note,
                provider="openai",
                model=result.model,
                duration_ms=result.duration_ms,
                usage=result.usage,
            )
            updated = VQAConversation(
                conversation_id=key,
                media_id=media_id,
                created_at=conversation.created_at if conversation else now,
                updated_at=now,
                messages=[*(conversation.messages if conversation else []), user, assistant],
            )
            try:
                await asyncio.to_thread(
                    self.repository.save_turn, updated, user, assistant, conversation is None
                )
            except sqlite3.IntegrityError as exc:
                raise MediaError("media_not_found", "Media item was not found.", 404) from exc
            log_event(
                logger,
                "vqa.completed",
                "COMPLETE Image question saved",
                media_id=media_id,
                conversation_id=key,
                provider="openai",
                model=result.model,
                duration_ms=result.duration_ms,
                total_tokens=result.usage.total_tokens if result.usage else None,
            )
            return updated
        finally:
            self.capacity.release()
            self.active_conversations.discard(key)

    async def list_conversations(self, media_id: str) -> list[VQAConversation]:
        await asyncio.to_thread(self.media.get, media_id)
        return await asyncio.to_thread(self.repository.list_conversations, media_id)

    async def get_conversation(self, media_id: str, conversation_id: str) -> VQAConversation:
        await asyncio.to_thread(self.media.get, media_id)
        self.media.validate_id(conversation_id)
        record = await asyncio.to_thread(
            self.repository.get_conversation, media_id, conversation_id
        )
        if record is None:
            raise MediaError("conversation_not_found", "Conversation was not found.", 404)
        return record

    async def delete_conversation(self, media_id: str, conversation_id: str) -> None:
        await self.get_conversation(media_id, conversation_id)
        if conversation_id in self.active_conversations:
            raise VisionProviderError(
                "conversation_busy", "This conversation is processing a question.", 409
            )
        await asyncio.to_thread(self.repository.delete_conversation, media_id, conversation_id)

    async def describe(self, media_id: str, body: AccessibilityRequest) -> AccessibilityRecord:
        path, size = await self._image(media_id)
        source = "openai"
        model = provider = None
        duration = usage = None
        if body.purpose == "decorative":
            generated = AccessibilityAnswer(
                alt_text="", detailed_description=None, extended_description=None
            )
            source = "decorative_local"
        elif body.source_caption_analysis_id:
            self.media.validate_id(body.source_caption_analysis_id)
            captions = await asyncio.to_thread(self.caption.list, media_id)
            caption = next(
                (
                    item
                    for item in captions
                    if item.analysis_id == body.source_caption_analysis_id and item.text
                ),
                None,
            )
            if caption is None:
                raise MediaError("caption_not_found", "Saved Florence caption was not found.", 404)
            generated = AccessibilityAnswer(
                alt_text=caption.text, detailed_description=None, extended_description=None
            )
            source, model, provider = "florence_suggestion", caption.model.checkpoint, "florence"
        else:
            if not body.consent_external_transfer:
                raise VisionProviderError(
                    "external_consent_required", "Allow this image to be sent to OpenAI first.", 403
                )
            if self.provider.status()["state"] == "unconfigured":
                raise VisionProviderError(
                    "openai_not_configured", "OpenAI vision needs a backend API key."
                )
            if self.capacity.locked():
                raise VisionProviderError(
                    "vision_busy", "OpenAI vision is busy. Retry shortly.", 429
                )
            await self.capacity.acquire()
            try:
                image_url = await self._data_url(path, size)
                log_event(
                    logger,
                    "accessibility.started",
                    "START Accessible description",
                    media_id=media_id,
                    purpose=body.purpose,
                    provider="openai",
                )
                result = await self.provider.describe(
                    image_url, body.purpose, body.context, body.audience, body.function
                )
                if not result.output.alt_text.strip():
                    raise VisionProviderError(
                        "openai_invalid_response", "OpenAI returned empty alt text.", 502
                    )
                generated, model, provider = result.output, result.model, "openai"
                duration, usage = result.duration_ms, result.usage
            finally:
                self.capacity.release()
        now = datetime.now(UTC)
        record = AccessibilityRecord(
            result_id=str(uuid4()),
            media_id=media_id,
            purpose=body.purpose,
            context=body.context,
            audience=body.audience,
            function=body.function,
            source=source,
            generated=generated,
            model=model,
            provider=provider,
            duration_ms=duration,
            usage=usage,
            created_at=now,
            updated_at=now,
        )
        try:
            await asyncio.to_thread(self.repository.insert_accessibility, record)
        except sqlite3.IntegrityError as exc:
            raise MediaError("media_not_found", "Media item was not found.", 404) from exc
        log_event(
            logger,
            "accessibility.completed",
            "COMPLETE Description saved",
            media_id=media_id,
            purpose=body.purpose,
            provider=provider or source,
            duration_ms=duration,
            total_tokens=usage.total_tokens if usage else None,
        )
        return record

    async def list_accessibility(self, media_id: str) -> list[AccessibilityRecord]:
        await asyncio.to_thread(self.media.get, media_id)
        return await asyncio.to_thread(self.repository.list_accessibility, media_id)

    async def edit_accessibility(
        self, media_id: str, result_id: str, body: AccessibilityEdit
    ) -> AccessibilityRecord:
        await asyncio.to_thread(self.media.get, media_id)
        self.media.validate_id(result_id)
        record = await asyncio.to_thread(self.repository.get_accessibility, media_id, result_id)
        if record is None:
            raise MediaError("description_not_found", "Description was not found.", 404)
        if record.version != body.expected_version:
            raise MediaError(
                "version_conflict", "Description changed. Reload it before saving.", 409
            )
        revised = record.model_copy(
            update={
                "edited": AccessibilityAnswer(
                    alt_text=body.alt_text,
                    detailed_description=body.detailed_description,
                    extended_description=body.extended_description,
                ),
                "version": record.version + 1,
                "updated_at": datetime.now(UTC),
            }
        )
        if not await asyncio.to_thread(
            self.repository.update_accessibility, revised, body.expected_version
        ):
            raise MediaError(
                "version_conflict", "Description changed. Reload it before saving.", 409
            )
        return revised
