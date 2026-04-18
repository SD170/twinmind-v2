from threading import RLock

from app.schemas.settings import RuntimeSettings, RuntimeSettingsEnvelope


class RuntimeSettingsStore:
    def __init__(self) -> None:
        self._envelope = RuntimeSettingsEnvelope()
        self._lock = RLock()

    def get(self) -> RuntimeSettingsEnvelope:
        with self._lock:
            return self._envelope.model_copy(deep=True)

    def update(self, settings: RuntimeSettings) -> RuntimeSettingsEnvelope:
        with self._lock:
            self._envelope.version += 1
            self._envelope.settings = settings
            return self._envelope.model_copy(deep=True)


runtime_settings_store = RuntimeSettingsStore()
