from fastapi import APIRouter

from app.core.runtime_settings_store import runtime_settings_store
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
    runtime_settings = runtime_settings_store.get().settings
    session = session_store.get_or_create(req.session_id)
    transcript_window = [
        turn.model_dump() for turn in session.transcript[-runtime_settings.expand_context_window_turns :]
    ]
    payload = {
        "session_id": req.session_id,
        "bucket": req.clicked_card.bucket.value,
        "clicked_text": req.clicked_card.text,
        "prompt": req.prompt or "",
        "transcript_window": transcript_window,
    }
    expand_prompt = (
        runtime_settings.expand_prompt_template.strip()
        if runtime_settings.expand_prompt_template.strip()
        else EXPAND_PROMPT
    )
    out = await groq_client.expand(expand_prompt, payload)
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
    runtime_settings = runtime_settings_store.get().settings
    session = session_store.get_or_create(req.session_id)
    transcript_window = [turn.model_dump() for turn in session.transcript[-runtime_settings.chat_context_window_turns :]]
    chat_window = [
        message.model_dump()
        for message in session.chat_history[-runtime_settings.chat_history_window_messages :]
    ]
    payload = {
        "session_id": req.session_id,
        "message": req.message,
        "transcript_window": transcript_window,
        "chat_history": chat_window,
    }
    chat_prompt = (
        runtime_settings.chat_prompt_template.strip()
        if runtime_settings.chat_prompt_template.strip()
        else CHAT_PROMPT
    )
    out = await groq_client.chat(chat_prompt, payload)
    session_store.append_chat(req.session_id, "user", req.message)
    session_store.append_chat(req.session_id, "assistant", out.answer)
    return ChatMessageResponse(
        session_id=req.session_id,
        answer=out.answer,
        supporting_points=out.supporting_points,
        uncertainties=out.uncertainties,
        evidence_used=out.evidence_used,
    )
