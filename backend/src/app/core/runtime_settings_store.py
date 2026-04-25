from threading import RLock

from app.llm.prompts import CHAT_PROMPT, EXPAND_PROMPT, RANK_AND_DRAFT_PROMPT, VERIFY_FACTCHECK_PROMPT
from app.schemas.settings import RuntimeSettings, RuntimeSettingsEnvelope


class RuntimeSettingsStore:
    def __init__(self) -> None:
        self._envelope = RuntimeSettingsEnvelope(
            settings=RuntimeSettings(
                live_prompt_template=RANK_AND_DRAFT_PROMPT,
                fact_check_prompt_template=VERIFY_FACTCHECK_PROMPT,
                expand_prompt_template=EXPAND_PROMPT,
                chat_prompt_template=CHAT_PROMPT,
            )
        )
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
