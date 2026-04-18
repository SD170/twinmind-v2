from threading import RLock

from app.schemas.suggestions import RefreshSuggestionsResponse


class ResultCache:
    def __init__(self) -> None:
        self._cache: dict[str, RefreshSuggestionsResponse] = {}
        self._lock = RLock()

    def get(self, batch_key: str) -> RefreshSuggestionsResponse | None:
        with self._lock:
            return self._cache.get(batch_key)

    def put(self, batch_key: str, result: RefreshSuggestionsResponse) -> None:
        with self._lock:
            self._cache[batch_key] = result


result_cache = ResultCache()
