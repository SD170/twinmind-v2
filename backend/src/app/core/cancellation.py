from threading import RLock


class NewestWinsController:
    def __init__(self) -> None:
        self._current_batch_keys: dict[str, str] = {}
        self._lock = RLock()

    def begin(self, session_id: str, batch_key: str) -> None:
        with self._lock:
            self._current_batch_keys[session_id] = batch_key

    def is_stale(self, session_id: str, batch_key: str) -> bool:
        with self._lock:
            return self._current_batch_keys.get(session_id) != batch_key


cancellation_controller = NewestWinsController()
