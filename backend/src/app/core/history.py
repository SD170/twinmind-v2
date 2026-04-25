from app.schemas.common import SuggestionCard
from app.schemas.session import SessionState


def recent_suggestion_texts(session: SessionState, limit: int = 12) -> list[str]:
    items: list[str] = []
    for batch in reversed(session.suggestion_batches):
        for card in batch.cards:
            items.append(card.text.lower())
            if len(items) >= limit:
                return items
    return items
