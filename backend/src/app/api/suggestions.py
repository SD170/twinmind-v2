import logging
import time
from fastapi import APIRouter, HTTPException

from app.core.cancellation import cancellation_controller
from app.core.dedup import compute_batch_key
from app.core.result_cache import result_cache
from app.core.runtime_settings_store import runtime_settings_store
from app.core.session_store import session_store
from app.graph.workflow import live_suggestions_graph
from app.schemas.common import SuggestionCard, TimingMetrics
from app.schemas.session import SuggestionBatchLog
from app.schemas.suggestions import RefreshSuggestionsRequest, RefreshSuggestionsResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["suggestions"])


@router.post("/suggestions/refresh", response_model=RefreshSuggestionsResponse)
async def refresh_suggestions(req: RefreshSuggestionsRequest) -> RefreshSuggestionsResponse:
    started = time.perf_counter()
    settings = runtime_settings_store.get()
    batch_key = compute_batch_key(req, settings)

    if not req.force_refresh:
        cached = result_cache.get(batch_key)
        if cached is not None:
            return cached

    cancellation_controller.begin(req.session_id, batch_key)
    session_store.append_transcript(req.session_id, req.recent_user_turns, req.recent_ambient_turns)

    graph_state = await live_suggestions_graph.ainvoke({"request": req, "timings": {}})
    if cancellation_controller.is_stale(req.session_id, batch_key):
        raise HTTPException(status_code=409, detail="Stale refresh response discarded.")

    rank_output = graph_state["rank_output"]
    cards_by_bucket = {card.bucket: card for card in rank_output.cards}
    selected: list[SuggestionCard] = []
    for bucket in rank_output.top_three:
        source = cards_by_bucket.get(bucket)
        if source:
            selected.append(
                SuggestionCard(
                    bucket=source.bucket,
                    text=source.text,
                    confidence=source.confidence,
                    evidence=[],
                )
            )

    if len(selected) != 3:
        raise HTTPException(status_code=500, detail="Graph did not produce exactly three cards.")

    timings = graph_state.get("timings", {})
    total_ms = int((time.perf_counter() - started) * 1000)
    timing_model = TimingMetrics(
        total_ms=total_ms,
        state_ms=timings.get("state_ms", 0),
        llm_main_ms=timings.get("llm_main_ms", 0),
        retrieval_ms=timings.get("retrieval_ms", 0),
        verify_ms=timings.get("verify_ms", 0),
        finalize_ms=timings.get("finalize_ms", 0),
    )
    response = RefreshSuggestionsResponse(
        session_id=req.session_id,
        batch_key=batch_key,
        cards=selected,
        omitted_bucket=rank_output.omitted_bucket,
        scores=rank_output.bucket_scores,
        signal_state=rank_output.signal_state,
        timings=timing_model,
        metadata={"settings_version": settings.version},
    )
    result_cache.put(batch_key, response)
    session_store.append_batch(
        req.session_id,
        SuggestionBatchLog(
            batch_key=batch_key,
            cards=selected,
            omitted_bucket=rank_output.omitted_bucket.value,
            scores={k.value: v for k, v in rank_output.bucket_scores.items()},
            signal_state=rank_output.signal_state.value,
            timing_ms=total_ms,
        ),
    )
    logger.info(
        "suggestions_refresh",
        extra={
            "session_id": req.session_id,
            "batch_key": batch_key,
            "scores": {k.value: v for k, v in rank_output.bucket_scores.items()},
            "signal_state": rank_output.signal_state.value,
            "timing_ms": total_ms,
        },
    )
    return response
