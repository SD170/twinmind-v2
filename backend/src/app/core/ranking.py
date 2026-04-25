from app.schemas.common import BucketType, SignalState


def compute_signal_state(scores: dict[BucketType, float]) -> SignalState:
    strength = max(scores.values())
    if strength < 0.48:
        return SignalState.weak
    if strength < 0.72:
        return SignalState.normal
    return SignalState.urgent


def top_three(scores: dict[BucketType, float]) -> tuple[list[BucketType], BucketType]:
    ordered = sorted(scores, key=scores.get, reverse=True)
    return ordered[:3], ordered[3]
