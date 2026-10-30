from fastapi import APIRouter, Request, Response

from app.schemas.multimodal import (
    AccessibilityEdit,
    AccessibilityRecord,
    AccessibilityRequest,
    VQAConversation,
    VQARequest,
)

router = APIRouter(prefix="/api/v1", tags=["multimodal"])


@router.get("/vision/providers")
def providers(request: Request) -> dict[str, dict[str, str]]:
    return {
        "vqa": request.app.state.multimodal_provider.status(),
        "accessibility": request.app.state.multimodal_provider.status(),
    }


@router.post("/media/{media_id}/vqa", response_model=VQAConversation, status_code=201)
async def ask(media_id: str, body: VQARequest, request: Request) -> VQAConversation:
    return await request.app.state.multimodal_service.ask(media_id, body)


@router.get("/media/{media_id}/vqa/conversations", response_model=list[VQAConversation])
async def list_conversations(media_id: str, request: Request) -> list[VQAConversation]:
    return await request.app.state.multimodal_service.list_conversations(media_id)


@router.get("/media/{media_id}/vqa/conversations/{conversation_id}", response_model=VQAConversation)
async def get_conversation(
    media_id: str, conversation_id: str, request: Request
) -> VQAConversation:
    return await request.app.state.multimodal_service.get_conversation(media_id, conversation_id)


@router.delete("/media/{media_id}/vqa/conversations/{conversation_id}", status_code=204)
async def delete_conversation(media_id: str, conversation_id: str, request: Request) -> Response:
    await request.app.state.multimodal_service.delete_conversation(media_id, conversation_id)
    return Response(status_code=204)


@router.post("/media/{media_id}/accessibility", response_model=AccessibilityRecord, status_code=201)
async def describe(
    media_id: str, body: AccessibilityRequest, request: Request
) -> AccessibilityRecord:
    return await request.app.state.multimodal_service.describe(media_id, body)


@router.get("/media/{media_id}/accessibility", response_model=list[AccessibilityRecord])
async def list_descriptions(media_id: str, request: Request) -> list[AccessibilityRecord]:
    return await request.app.state.multimodal_service.list_accessibility(media_id)


@router.patch("/media/{media_id}/accessibility/{result_id}", response_model=AccessibilityRecord)
async def edit_description(
    media_id: str, result_id: str, body: AccessibilityEdit, request: Request
) -> AccessibilityRecord:
    return await request.app.state.multimodal_service.edit_accessibility(media_id, result_id, body)
