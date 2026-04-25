from pydantic import BaseModel, Field

from app.schemas.common import BucketType, SignalState


class BucketCardDraft(BaseModel):
    bucket: BucketType
    text: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=500)


class RankAndDraftOutput(BaseModel):
    bucket_scores: dict[BucketType, float]
    cards: list[BucketCardDraft] = Field(min_length=4, max_length=4)
    top_three: list[BucketType] = Field(min_length=3, max_length=3)
    omitted_bucket: BucketType
    signal_state: SignalState
    metadata: dict[str, str | float | int | bool] = Field(default_factory=dict)


class VerifyFactCheckOutput(BaseModel):
    verdict: str = Field(pattern="^(supported|refuted|uncertain)$")
    revised_card_text: str = Field(min_length=1, max_length=300)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_summary: list[str] = Field(default_factory=list)


class ExpandOutput(BaseModel):
    expanded_text: str = Field(min_length=1, max_length=2000)
    supporting_points: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)


class ChatOutput(BaseModel):
    answer: str = Field(min_length=1, max_length=3000)
    supporting_points: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
