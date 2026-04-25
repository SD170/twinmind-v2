from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException

from app.core.session_store import session_store
from app.schemas.session import ExportRequest, ExportResponse

router = APIRouter(tags=["export"])


@router.post("/export", response_model=ExportResponse)
def export_session(req: ExportRequest) -> ExportResponse:
    session = session_store.get_or_create(req.session_id)
    if not session.transcript and not session.suggestion_batches and not session.chat_history:
        raise HTTPException(status_code=404, detail="Session not found or empty.")

    payload = {
        "session_id": session.session_id,
        "transcript": [t.model_dump() for t in session.transcript],
        "suggestion_batches": [b.model_dump() for b in session.suggestion_batches],
        "chat_history": [m.model_dump() for m in session.chat_history],
    }
    if req.format == "json":
        return ExportResponse(session_id=req.session_id, content=payload)

    text_output = [
        f"Session: {req.session_id}",
        f"ExportedAt: {datetime.now(timezone.utc).isoformat()}",
        "",
        "Transcript:",
    ]
    for row in payload["transcript"]:
        text_output.append(f"- [{row['id']}] {row['text']}")
    text_output.append("")
    text_output.append("SuggestionBatches:")
    for batch in payload["suggestion_batches"]:
        text_output.append(f"- Batch {batch['batch_key']}: {batch['signal_state']}")
        for card in batch["cards"]:
            text_output.append(f"  - ({card['bucket']}) {card['text']}")
    text_output.append("")
    text_output.append("ChatHistory:")
    for msg in payload["chat_history"]:
        text_output.append(f"- [{msg['at']}] {msg['role']}: {msg['content']}")

    return ExportResponse(session_id=req.session_id, content="\n".join(text_output))
