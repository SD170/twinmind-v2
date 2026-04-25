from pydantic import BaseModel, Field

from app.schemas.common import TranscriptTurn


class TranscriptionResponse(BaseModel):
    session_id: str = Field(min_length=1)
    speaker: str = Field(default="user", pattern="^user$")
    turns: list[TranscriptTurn] = Field(default_factory=list)
    provider: str = "groq"
    model: str
    fallback_used: bool = False
    error: str | None = None
