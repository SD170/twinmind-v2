from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    groq_model: str = Field(default="gpt-oss-120b", alias="GROQ_MODEL")
    transcription_model: str = Field(default="whisper-large-v3", alias="TRANSCRIPTION_MODEL")

    request_timeout_seconds: int = Field(default=25, alias="REQUEST_TIMEOUT_SECONDS")
    max_transcript_window: int = Field(default=30, alias="MAX_TRANSCRIPT_WINDOW")
    fact_check_score_threshold: float = Field(default=0.65, alias="FACT_CHECK_SCORE_THRESHOLD")
    enable_conditional_web_retrieval: bool = Field(
        default=True, alias="ENABLE_CONDITIONAL_WEB_RETRIEVAL"
    )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()  # type: ignore[call-arg]
