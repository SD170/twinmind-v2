from app.graph.nodes.finalize import finalize_node
from app.schemas.common import BucketType, SignalState
from app.schemas.llm import BucketCardDraft, RankAndDraftOutput, VerifyFactCheckOutput


def _rank_output() -> RankAndDraftOutput:
    return RankAndDraftOutput(
        bucket_scores={
            BucketType.answer: 0.52,
            BucketType.fact_check: 0.63,
            BucketType.talking_point: 0.68,
            BucketType.question: 0.61,
        },
        cards=[
            BucketCardDraft(bucket=BucketType.answer, text="Respond directly.", confidence=0.52, rationale=""),
            BucketCardDraft(
                bucket=BucketType.fact_check,
                text="Possible claim to verify.",
                confidence=0.63,
                rationale="",
            ),
            BucketCardDraft(
                bucket=BucketType.talking_point, text="Highlight tradeoffs.", confidence=0.68, rationale=""
            ),
            BucketCardDraft(bucket=BucketType.question, text="Ask one clarifier.", confidence=0.61, rationale=""),
        ],
        top_three=[BucketType.talking_point, BucketType.fact_check, BucketType.question],
        omitted_bucket=BucketType.answer,
        signal_state=SignalState.normal,
        metadata={},
    )


def test_finalize_demotes_generic_uncertain_factcheck():
    state = {
        "rank_output": _rank_output(),
        "verify_output": VerifyFactCheckOutput(
            verdict="uncertain",
            revised_card_text="Evidence is incomplete. Confirm before stating this as fact.",
            confidence=0.35,
            evidence_summary=[],
        ),
        "timings": {},
    }
    out = finalize_node(state)
    top_three = out["rank_output"].top_three
    assert BucketType.fact_check not in top_three
    assert out["rank_output"].omitted_bucket == BucketType.fact_check


def test_finalize_keeps_supported_factcheck():
    state = {
        "rank_output": _rank_output(),
        "verify_output": VerifyFactCheckOutput(
            verdict="supported",
            revised_card_text="Fact-check: outage was config related.",
            confidence=0.82,
            evidence_summary=["Internal postmortem note"],
        ),
        "timings": {},
    }
    out = finalize_node(state)
    assert BucketType.fact_check in out["rank_output"].top_three
    fc_card = next(c for c in out["rank_output"].cards if c.bucket == BucketType.fact_check)
    assert fc_card.text == "Fact-check: outage was config related."
