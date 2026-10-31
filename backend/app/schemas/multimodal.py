from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

GroundingStatus = Literal["supported", "uncertain", "insufficient_evidence"]
ImagePurpose = Literal["informative", "decorative", "functional", "complex"]


class TokenUsage(BaseModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class VQAAnswer(BaseModel):
    answer: str = Field(min_length=1)
    grounding_status: GroundingStatus
    uncertainty_note: str | None

    @field_validator("answer")
    @classmethod
    def nonempty_answer(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Answer must not be blank.")
        return value


class AccessibilityAnswer(BaseModel):
    alt_text: str
    detailed_description: str | None
    extended_description: str | None


class VQARequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None
    consent_external_transfer: bool = False

    @field_validator("question")
    @classmethod
    def nonempty_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be blank.")
        return value


class VQAMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime
    grounding_status: GroundingStatus | None = None
    uncertainty_note: str | None = None
    provider: str | None = None
    model: str | None = None
    duration_ms: float | None = None
    usage: TokenUsage | None = None
    frame_timestamps_ms: list[int] | None = None


class VQAConversation(BaseModel):
    conversation_id: str
    media_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[VQAMessage]


class AccessibilityRequest(BaseModel):
    purpose: ImagePurpose
    context: str = Field(default="", max_length=1000)
    audience: str = Field(default="", max_length=300)
    function: str = Field(default="", max_length=300)
    consent_external_transfer: bool = False
    source_caption_analysis_id: str | None = None


class AccessibilityEdit(BaseModel):
    alt_text: str = Field(max_length=1000)
    detailed_description: str | None = Field(default=None, max_length=5000)
    extended_description: str | None = Field(default=None, max_length=8000)
    expected_version: int = Field(ge=1)


class AccessibilityRecord(BaseModel):
    result_id: str
    media_id: str
    purpose: ImagePurpose
    context: str
    audience: str
    function: str
    source: Literal["openai", "decorative_local", "florence_suggestion"]
    generated: AccessibilityAnswer
    edited: AccessibilityAnswer | None = None
    model: str | None = None
    provider: str | None = None
    duration_ms: float | None = None
    usage: TokenUsage | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime
