import time

from app.core.history import recent_suggestion_texts
from app.core.ranking import compute_signal_state, top_three
from app.core.session_store import session_store
from app.llm.groq_client import groq_client
from app.llm.prompts import RANK_AND_DRAFT_PROMPT
from app.graph.state import WorkflowState

async def rank_and_draft_node(state: WorkflowState) -> WorkflowState:
    started = time.perf_counter()
    req = state["request"]
    session = session_store.get_or_create(req.session_id)
    history = recent_suggestion_texts(session)

    payload = {
        "request": req.model_dump(),
        "recent_suggestion_history": history,
    }
    runtime_settings = state.get("runtime_settings")
    prompt = (
        runtime_settings.live_prompt_template.strip()
        if runtime_settings and runtime_settings.live_prompt_template.strip()
        else RANK_AND_DRAFT_PROMPT
    )
    model_out = await groq_client.rank_and_draft(prompt, payload)

    # Ranking is always derived from bucket_scores so top_three/omitted cannot disagree with scores.
    top3, omitted = top_three(model_out.bucket_scores)
    model_out.top_three = top3
    model_out.omitted_bucket = omitted
    if not model_out.signal_state:
        model_out.signal_state = compute_signal_state(model_out.bucket_scores)

    elapsed = int((time.perf_counter() - started) * 1000)
    timings = state.get("timings", {})
    timings["llm_main_ms"] = elapsed
    return {"rank_output": model_out, "timings": timings}
