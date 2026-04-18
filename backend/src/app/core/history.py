from app.schemas.common import BucketType, SuggestionCard
from app.schemas.session import SessionState


def recent_suggestion_texts(session: SessionState, limit: int = 12) -> list[str]:
    items: list[str] = []
    for batch in reversed(session.suggestion_batches):
        for card in batch.cards:
            items.append(card.text.lower())
            if len(items) >= limit:
                return items
    return items


def novelty_score(candidate: str, history: list[str]) -> float:
    if not history:
        return 1.0
    normalized = candidate.lower().strip()
    if not normalized:
        return 0.0
    overlap_count = sum(1 for prev in history if normalized in prev or prev in normalized)
    ratio = overlap_count / max(len(history), 1)
    return max(0.0, 1.0 - ratio)


def bucket_counts(session: SessionState, limit: int = 6) -> dict[BucketType, int]:
    counts: dict[BucketType, int] = {b: 0 for b in BucketType}
    for batch in reversed(session.suggestion_batches):
        for card in batch.cards:
            counts[card.bucket] += 1
        if sum(counts.values()) >= limit:
            break
    return counts
