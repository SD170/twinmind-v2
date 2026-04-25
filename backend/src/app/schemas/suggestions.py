from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator

from app.schemas.common import BucketType, SignalState, SuggestionCard, TimingMetrics, TranscriptTurn


class ApprovedFactSource(BaseModel):
    """Embedded evidence for fact-check (doc: self-contained sessions without network)."""

    source_id: str = ""
    type: str = Field(default="approved_cached_note", max_length=120)
    title: str = Field(default="", max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    uri: str = Field(default="", max_length=500)


class SourcePolicy(BaseModel):
    enable_conditional_web: bool = True
    approved_sources: list[str] = Field(default_factory=list)
    approved_fact_sources: list[ApprovedFactSource] = Field(default_factory=list)


class RefreshSuggestionsRequest(BaseModel):
    session_id: str = Field(min_length=1)
    recent_user_turns: list[TranscriptTurn] = Field(default_factory=list)
    force_refresh: bool = False
    source_policy: SourcePolicy = Field(default_factory=SourcePolicy)

    @model_validator(mode="after")
    def validate_turns_present(self) -> "RefreshSuggestionsRequest":
        if not self.recent_user_turns:
            raise ValueError("At least one user transcript turn is required.")
        return self


class RefreshSuggestionsResponse(BaseModel):
    session_id: str
    batch_key: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    cards: list[SuggestionCard] = Field(min_length=3, max_length=3)
    omitted_bucket: BucketType
    scores: dict[BucketType, float]
    signal_state: SignalState
    timings: TimingMetrics
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ExpandSuggestionRequest(BaseModel):
    session_id: str
    clicked_card: SuggestionCard
    prompt: str | None = None


class ExpandSuggestionResponse(BaseModel):
    bucket: BucketType
    expanded_text: str
    supporting_points: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)


class ChatMessageRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageResponse(BaseModel):
    session_id: str
    answer: str
    supporting_points: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
