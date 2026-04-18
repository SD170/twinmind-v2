import time

from app.core.fact_policy import enforce_uncertain_factcheck_text
from app.schemas.common import BucketType
from app.graph.state import WorkflowState


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

    if rank_output.signal_state.value == "weak":
        for idx, card in enumerate(rank_output.cards):
            rank_output.cards[idx].text = f"Consider: {card.text}"

    elapsed = int((time.perf_counter() - started) * 1000)
    timings = state.get("timings", {})
    timings["finalize_ms"] = elapsed
    return {"rank_output": rank_output, "timings": timings}
