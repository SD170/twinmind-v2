import time

from app.config import get_settings
from app.core.fact_policy import should_verify_factcheck
from app.llm.groq_client import groq_client
from app.llm.prompts import VERIFY_FACTCHECK_PROMPT
from app.retrieval.evidence_cache import evidence_cache
from app.retrieval.web_search import web_search_client
from app.graph.state import WorkflowState


async def verify_factcheck_node(state: WorkflowState) -> WorkflowState:
    started = time.perf_counter()
    req = state["request"]
    rank_output = state["rank_output"]
    runtime_settings = state.get("runtime_settings")
    threshold = (
        runtime_settings.fact_check_score_threshold
        if runtime_settings is not None
        else get_settings().fact_check_score_threshold
    )
    if not should_verify_factcheck(
        rank_output, req.source_policy, threshold
    ):
        return {"verify_output": None, "timings": state.get("timings", {})}

    claim_text = next(
        (card.text for card in rank_output.cards if card.bucket.value == "fact_check"),
        "",
    )
    evidence = evidence_cache.get(req.session_id)
    for src in req.source_policy.approved_fact_sources:
        snippet = f"{src.title}: {src.content}".strip()
        if snippet:
            evidence.append(snippet)
    retrieval_ms = 0
    if req.source_policy.enable_conditional_web:
        retr_start = time.perf_counter()
        web_results = await web_search_client.search(claim_text, max_results=3)
        retrieval_ms = int((time.perf_counter() - retr_start) * 1000)
        evidence.extend(web_results)
        evidence_cache.put(req.session_id, evidence)

    payload = {
        "claim": claim_text,
        "card": claim_text,
        "approved_sources": req.source_policy.approved_sources,
        "approved_fact_sources": [s.model_dump() for s in req.source_policy.approved_fact_sources],
        "evidence": evidence,
    }
    prompt = (
        runtime_settings.fact_check_prompt_template.strip()
        if runtime_settings and runtime_settings.fact_check_prompt_template.strip()
        else VERIFY_FACTCHECK_PROMPT
    )
    verify_out = await groq_client.verify_factcheck(prompt, payload)

    total = int((time.perf_counter() - started) * 1000)
    timings = state.get("timings", {})
    timings["retrieval_ms"] = retrieval_ms
    timings["verify_ms"] = max(0, total - retrieval_ms)
    return {"verify_output": verify_out, "timings": timings}
