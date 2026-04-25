from threading import RLock

from app.schemas.session import ChatMessageLog, SessionState, SuggestionBatchLog
from app.schemas.common import TranscriptTurn


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._lock = RLock()

    def get_or_create(self, session_id: str) -> SessionState:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionState(session_id=session_id)
            return self._sessions[session_id]

    def append_transcript(self, session_id: str, turns: list[TranscriptTurn]) -> None:
        session = self.get_or_create(session_id)
        with self._lock:
            session.transcript.extend(turns)

    def append_batch(self, session_id: str, batch: SuggestionBatchLog) -> None:
        session = self.get_or_create(session_id)
        with self._lock:
            session.suggestion_batches.append(batch)

    def append_chat(self, session_id: str, role: str, content: str) -> None:
        session = self.get_or_create(session_id)
        with self._lock:
            session.chat_history.append(ChatMessageLog(role=role, content=content))


session_store = InMemorySessionStore()
