import time
import logging

from app.core.fact_policy import enforce_uncertain_factcheck_text
from app.schemas.common import BucketType
from app.graph.state import WorkflowState

logger = logging.getLogger(__name__)


GENERIC_UNCERTAIN_PREFIXES = (
    "evidence is incomplete",
    "insufficient evidence",
    "unable to verify",
    "cannot verify",
)


def _is_generic_uncertain_text(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    return any(normalized.startswith(prefix) for prefix in GENERIC_UNCERTAIN_PREFIXES)


def _demote_fact_check_from_top_three(state: WorkflowState) -> None:
    rank_output = state["rank_output"]
    if BucketType.fact_check not in rank_output.top_three:
        return

    non_fact_buckets = [
        bucket for bucket in rank_output.bucket_scores.keys() if bucket != BucketType.fact_check
    ]
    if len(non_fact_buckets) < 3:
        return

    # Re-rank top-3 without fact_check to avoid promoting low-score answer to index 0.
    ordered = sorted(
        non_fact_buckets,
        key=lambda bucket: rank_output.bucket_scores.get(bucket, 0.0),
        reverse=True,
    )
    rank_output.top_three = ordered[:3]
    rank_output.omitted_bucket = BucketType.fact_check
    logger.info(
        "fact_check_card_demoted",
        extra={
            "reason": "uncertain_or_generic",
            "top3": [bucket.value for bucket in rank_output.top_three],
        },
    )


def finalize_node(state: WorkflowState) -> WorkflowState:
    started = time.perf_counter()
    rank_output = state["rank_output"]
    verify_output = state.get("verify_output")

    if verify_output:
        for idx, card in enumerate(rank_output.cards):
            if card.bucket == BucketType.fact_check:
                text = verify_output.revised_card_text
                if verify_output.verdict == "uncertain":
                    text = enforce_uncertain_factcheck_text(text)
                rank_output.cards[idx].text = text
                rank_output.cards[idx].confidence = verify_output.confidence
                break
        # Never show a generic "can't verify" card in top-three UX.
        if verify_output.verdict == "uncertain" and _is_generic_uncertain_text(verify_output.revised_card_text):
            _demote_fact_check_from_top_three(state)

    if rank_output.signal_state.value == "weak":
        for idx, card in enumerate(rank_output.cards):
            rank_output.cards[idx].text = f"Consider: {card.text}"

    elapsed = int((time.perf_counter() - started) * 1000)
    timings = state.get("timings", {})
    timings["finalize_ms"] = elapsed
    return {"rank_output": rank_output, "timings": timings}
