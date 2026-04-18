from threading import RLock


class EvidenceCache:
    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {}
        self._lock = RLock()

    def get(self, session_id: str) -> list[str]:
        with self._lock:
            return list(self._store.get(session_id, []))

    def put(self, session_id: str, evidence: list[str]) -> None:
        with self._lock:
            deduped = list(dict.fromkeys(evidence))
            self._store[session_id] = deduped[:20]


evidence_cache = EvidenceCache()
