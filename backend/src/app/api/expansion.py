from fastapi import APIRouter

from app.llm.groq_client import groq_client
from app.llm.prompts import CHAT_PROMPT, EXPAND_PROMPT
from app.schemas.suggestions import (
    ChatMessageRequest,
    ChatMessageResponse,
    ExpandSuggestionRequest,
    ExpandSuggestionResponse,
)
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


@router.post("/chat/message", response_model=ChatMessageResponse)
async def chat_message(req: ChatMessageRequest) -> ChatMessageResponse:
    session = session_store.get_or_create(req.session_id)
    transcript_window = [turn.model_dump() for turn in session.transcript[-24:]]
    chat_window = session.chat_history[-12:]
    payload = {
        "session_id": req.session_id,
        "message": req.message,
        "transcript_window": transcript_window,
        "chat_history": chat_window,
    }
    out = await groq_client.chat(CHAT_PROMPT, payload)
    session_store.append_chat(req.session_id, "user", req.message)
    session_store.append_chat(req.session_id, "assistant", out.answer)
    return ChatMessageResponse(
        session_id=req.session_id,
        answer=out.answer,
        supporting_points=out.supporting_points,
        uncertainties=out.uncertainties,
        evidence_used=out.evidence_used,
    )
