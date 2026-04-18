"""Build deterministic LLM outputs from trajectory fixture expected_* fields."""

from __future__ import annotations

from typing import Any

from app.schemas.common import BucketType, SignalState
from app.schemas.llm import BucketCardDraft, RankAndDraftOutput, VerifyFactCheckOutput


def _hedge_fact_check() -> str:
    return "Verify this claim with an approved source before stating it as fact."


def build_rank_and_draft_from_expected(
    batch_id: str,
    session: dict[str, Any],
) -> RankAndDraftOutput:
    scores_raw = session["expected_router_scores"][batch_id]
    order = session["expected_display_order"][batch_id]
    texts = session["expected_card_texts"][batch_id]
    signal = SignalState(session["expected_signal_state"][batch_id])

    bucket_scores = {BucketType(k): float(v) for k, v in scores_raw.items()}
    top_three = [BucketType(b) for b in order["top3"]]
    omitted_bucket = BucketType(order["omitted"])

    cards: list[BucketCardDraft] = []
    for b in BucketType:
        key = b.value
        raw = texts.get(key, "unspecified")
        if raw == "unspecified" and b == BucketType.fact_check:
            text = _hedge_fact_check()
        elif raw == "unspecified":
            text = f"Provisional {key.replace('_', ' ')} suggestion for this moment."
        else:
            text = str(raw)[:300]
        cards.append(
            BucketCardDraft(
                bucket=b,
                text=text,
                confidence=bucket_scores.get(b, 0.5),
                rationale="fixture",
            )
        )

    return RankAndDraftOutput(
        bucket_scores=bucket_scores,
        cards=cards,
        top_three=top_three,
        omitted_bucket=omitted_bucket,
        signal_state=signal,
        metadata={"fixture_batch_id": batch_id},
    )


def build_verify_factcheck_from_expected(batch_id: str, session: dict[str, Any]) -> VerifyFactCheckOutput | None:
    texts = session["expected_card_texts"][batch_id]
    fc = texts.get("fact_check", "unspecified")
    if fc == "unspecified":
        return VerifyFactCheckOutput(
            verdict="uncertain",
            revised_card_text=_hedge_fact_check(),
            confidence=0.4,
            evidence_summary=[],
        )
    return VerifyFactCheckOutput(
        verdict="supported",
        revised_card_text=str(fc)[:300],
        confidence=0.85,
        evidence_summary=["fixture-approved"],
    )
