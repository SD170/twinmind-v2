from threading import RLock


class RuntimeApiKeyStore:
    def __init__(self) -> None:
        self._api_key = ""
        self._lock = RLock()

    def get(self) -> str:
        with self._lock:
            return self._api_key

    def set(self, api_key: str) -> None:
        with self._lock:
            self._api_key = api_key.strip()

    def has_key(self) -> bool:
        with self._lock:
            return bool(self._api_key)


runtime_api_key_store = RuntimeApiKeyStore()
