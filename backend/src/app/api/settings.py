from fastapi import APIRouter

from app.config import get_settings
from app.core.runtime_api_key_store import runtime_api_key_store
from app.core.runtime_settings_store import runtime_settings_store
from app.schemas.settings import (
    RuntimeApiKeyStatus,
    RuntimeApiKeyUpdate,
    RuntimeSettings,
    RuntimeSettingsEnvelope,
)

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=RuntimeSettingsEnvelope)
def get_settings_endpoint() -> RuntimeSettingsEnvelope:
    return runtime_settings_store.get()


@router.put("/settings", response_model=RuntimeSettingsEnvelope)
def update_settings_endpoint(settings: RuntimeSettings) -> RuntimeSettingsEnvelope:
    return runtime_settings_store.update(settings)


@router.get("/settings/api-key", response_model=RuntimeApiKeyStatus)
def get_api_key_status() -> RuntimeApiKeyStatus:
    if runtime_api_key_store.has_key():
        return RuntimeApiKeyStatus(has_api_key=True, source="runtime")
    return RuntimeApiKeyStatus(has_api_key=bool(get_settings().groq_api_key), source="env")


@router.put("/settings/api-key", response_model=RuntimeApiKeyStatus)
def update_api_key(payload: RuntimeApiKeyUpdate) -> RuntimeApiKeyStatus:
    runtime_api_key_store.set(payload.api_key)
    return RuntimeApiKeyStatus(
        has_api_key=runtime_api_key_store.has_key(),
        source="runtime" if runtime_api_key_store.has_key() else "env",
    )
