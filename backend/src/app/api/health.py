from datetime import datetime, timezone
from fastapi import APIRouter

from app.config import get_settings
from app.core.runtime_api_key_store import runtime_api_key_store

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
    settings = get_settings()
    has_runtime_key = runtime_api_key_store.has_key()
    has_env_key = bool(settings.groq_api_key)
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "groq_model": settings.groq_model,
        "transcription_model": settings.transcription_model,
        "api_key_source": "runtime" if has_runtime_key else ("env" if has_env_key else "none"),
        "has_api_key": has_runtime_key or has_env_key,
    }


@router.get("/ready")
def ready() -> dict[str, str]:
    return {"status": "ready", "ts": datetime.now(timezone.utc).isoformat()}
