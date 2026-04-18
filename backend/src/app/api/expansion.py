from fastapi import APIRouter

from app.llm.groq_client import groq_client
from app.llm.prompts import EXPAND_PROMPT
from app.schemas.suggestions import ExpandSuggestionRequest, ExpandSuggestionResponse
from app.core.session_store import session_store

router = APIRouter(tags=["expansion"])


@router.post("/suggestions/expand", response_model=ExpandSuggestionResponse)
async def expand_suggestion(req: ExpandSuggestionRequest) -> ExpandSuggestionResponse:
    payload = {
        "session_id": req.session_id,
        "bucket": req.clicked_card.bucket.value,
        "clicked_text": req.clicked_card.text,
        "prompt": req.prompt or "",
    }
    out = await groq_client.expand(EXPAND_PROMPT, payload)
    session_store.append_chat(req.session_id, "user", req.clicked_card.text)
    session_store.append_chat(req.session_id, "assistant", out.expanded_text)
    return ExpandSuggestionResponse(
        bucket=req.clicked_card.bucket,
        expanded_text=out.expanded_text,
        supporting_points=out.supporting_points,
        uncertainties=out.uncertainties,
        evidence_used=out.evidence_used,
    )
