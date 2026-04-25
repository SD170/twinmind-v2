from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.schemas.common import SuggestionCard, TranscriptTurn


class SuggestionBatchLog(BaseModel):
    batch_key: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cards: list[SuggestionCard]
    omitted_bucket: str
    scores: dict[str, float]
    signal_state: str
    timing_ms: int = 0


class ChatMessageLog(BaseModel):
    role: str
    content: str
    at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SessionState(BaseModel):
    session_id: str
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    suggestion_batches: list[SuggestionBatchLog] = Field(default_factory=list)
    chat_history: list[ChatMessageLog] = Field(default_factory=list)
    settings_version: int = 1


class ExportRequest(BaseModel):
    session_id: str
    format: str = Field(default="json", pattern="^(json|text)$")


class ExportResponse(BaseModel):
    session_id: str
    exported_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    content: dict | str
