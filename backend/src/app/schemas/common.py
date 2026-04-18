from enum import Enum
from pydantic import BaseModel, Field


class BucketType(str, Enum):
    answer = "answer"
    fact_check = "fact_check"
    talking_point = "talking_point"
    question = "question"


class SignalState(str, Enum):
    weak = "weak"
    normal = "normal"
    urgent = "urgent"


class TranscriptTurn(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=4000)
    start_ms: int = Field(default=0, ge=0)
    end_ms: int = Field(default=0, ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class SuggestionCard(BaseModel):
    bucket: BucketType
    text: str = Field(min_length=1, max_length=300)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    verdict: str | None = None


class TimingMetrics(BaseModel):
    total_ms: int = Field(default=0, ge=0)
    state_ms: int = Field(default=0, ge=0)
    llm_main_ms: int = Field(default=0, ge=0)
    retrieval_ms: int = Field(default=0, ge=0)
    verify_ms: int = Field(default=0, ge=0)
    finalize_ms: int = Field(default=0, ge=0)
