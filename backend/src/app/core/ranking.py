from app.core.state_builder import BatchState
from app.schemas.common import BucketType, SignalState


def _clip(score: float) -> float:
    return max(0.0, min(1.0, score))


def compute_bucket_scores(state: BatchState, novelty: float = 0.7) -> dict[BucketType, float]:
    answer = (
        0.35 * state.explicit_user_question_score
        + 0.25 * state.inferred_reply_obligation_score
        + 0.15 * state.likely_to_speak_now_score
        + 0.15 * state.transcript_evidence_score
        + 0.10 * state.user_value_score
    )
    fact_check = (
        0.35 * state.checkworthy_claim_score
        + 0.30 * state.transcript_evidence_score
        + 0.20 * state.user_value_score
        + 0.15 * novelty
    )
    talking_point = (
        0.35 * state.salient_topic_score
        + 0.25 * state.user_value_score
        + 0.20 * novelty
        + 0.20 * state.timing_window_score
    )
    question = (
        0.40 * state.open_information_gap_score
        + 0.20 * state.user_value_score
        + 0.20 * novelty
        + 0.20 * state.timing_window_score
    )
    return {
        BucketType.answer: _clip(answer),
        BucketType.fact_check: _clip(fact_check),
        BucketType.talking_point: _clip(talking_point),
        BucketType.question: _clip(question),
    }


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
