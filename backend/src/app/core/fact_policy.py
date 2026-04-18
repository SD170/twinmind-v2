from app.schemas.common import BucketType
from app.schemas.llm import RankAndDraftOutput
from app.schemas.suggestions import SourcePolicy


def should_verify_factcheck(
    rank_output: RankAndDraftOutput, source_policy: SourcePolicy, threshold: float
) -> bool:
    if BucketType.fact_check not in rank_output.top_three:
        return False
    if rank_output.bucket_scores.get(BucketType.fact_check, 0.0) < threshold:
        return False
    has_evidence = bool(source_policy.approved_fact_sources) or bool(source_policy.approved_sources)
    if not source_policy.enable_conditional_web and not has_evidence:
        return False
    return True


def enforce_uncertain_factcheck_text(text: str) -> str:
    if "uncertain" in text.lower() or "not enough evidence" in text.lower():
        return text
    return f"{text} (uncertain: verify before stating this as fact)"
