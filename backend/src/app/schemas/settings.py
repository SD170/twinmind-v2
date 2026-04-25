from pydantic import BaseModel, Field


class RuntimeSettings(BaseModel):
    live_prompt: str = Field(default="rank_and_draft_v1")
    fact_check_prompt: str = Field(default="verify_factcheck_v1")
    expand_prompt: str = Field(default="expand_v1")
    chat_prompt: str = Field(default="chat_v1")
    live_prompt_template: str = ""
    fact_check_prompt_template: str = ""
    expand_prompt_template: str = ""
    chat_prompt_template: str = ""
    context_window_turns: int = Field(default=12, ge=1, le=80)
    expand_context_window_turns: int = Field(default=24, ge=1, le=200)
    chat_context_window_turns: int = Field(default=24, ge=1, le=200)
    chat_history_window_messages: int = Field(default=12, ge=1, le=200)
    fact_check_score_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    enable_conditional_web: bool = True


class RuntimeApiKeyUpdate(BaseModel):
    api_key: str = Field(default="", max_length=500)


class RuntimeApiKeyStatus(BaseModel):
    has_api_key: bool
    source: str


class RuntimeSettingsEnvelope(BaseModel):
    version: int = 1
    settings: RuntimeSettings = Field(default_factory=RuntimeSettings)
