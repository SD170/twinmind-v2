from fastapi import APIRouter

from app.core.runtime_settings_store import runtime_settings_store
from app.schemas.settings import RuntimeSettings, RuntimeSettingsEnvelope

router = APIRouter(tags=["settings"])


@router.get("/settings", response_model=RuntimeSettingsEnvelope)
def get_settings_endpoint() -> RuntimeSettingsEnvelope:
    return runtime_settings_store.get()


@router.put("/settings", response_model=RuntimeSettingsEnvelope)
def update_settings_endpoint(settings: RuntimeSettings) -> RuntimeSettingsEnvelope:
    return runtime_settings_store.update(settings)
