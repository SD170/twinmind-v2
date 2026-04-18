import time

from app.core.history import novelty_score, recent_suggestion_texts
from app.core.ranking import compute_bucket_scores, compute_signal_state, top_three
from app.core.session_store import session_store
from app.llm.groq_client import groq_client
from app.llm.prompts import RANK_AND_DRAFT_PROMPT
from app.schemas.llm import RankAndDraftOutput
from app.graph.state import WorkflowState


async def rank_and_draft_node(state: WorkflowState) -> WorkflowState:
    started = time.perf_counter()
    req = state["request"]
    batch_state = state["batch_state"]
    session = session_store.get_or_create(req.session_id)
    history = recent_suggestion_texts(session)
    novelty = novelty_score(" ".join(batch_state.salient_topics), history)
    heuristic_scores = compute_bucket_scores(batch_state, novelty=novelty)

    payload = {
        "request": req.model_dump(),
        "batch_state": batch_state.__dict__,
        "heuristic_scores": {k.value: v for k, v in heuristic_scores.items()},
    }
    model_out = await groq_client.rank_and_draft(RANK_AND_DRAFT_PROMPT, payload)

    # Ensure required ranking fields exist even in partial model outputs.
    if not model_out.bucket_scores:
        model_out.bucket_scores = heuristic_scores
    if not model_out.top_three or len(model_out.top_three) != 3:
        top3, omitted = top_three(heuristic_scores)
        model_out.top_three = top3
        model_out.omitted_bucket = omitted
    if not model_out.signal_state:
        model_out.signal_state = compute_signal_state(model_out.bucket_scores)

    elapsed = int((time.perf_counter() - started) * 1000)
    timings = state.get("timings", {})
    timings["llm_main_ms"] = elapsed
    return {"rank_output": model_out, "timings": timings}
