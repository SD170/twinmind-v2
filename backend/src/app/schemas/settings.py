from pydantic import BaseModel, Field


class RuntimeSettings(BaseModel):
    live_prompt: str = Field(default="rank_and_draft_v1")
    fact_check_prompt: str = Field(default="verify_factcheck_v1")
    expand_prompt: str = Field(default="expand_v1")
    context_window_turns: int = Field(default=12, ge=1, le=80)
    fact_check_score_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    enable_conditional_web: bool = True


class RuntimeSettingsEnvelope(BaseModel):
    version: int = 1
    settings: RuntimeSettings = Field(default_factory=RuntimeSettings)
