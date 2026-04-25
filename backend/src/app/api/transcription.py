import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.session_store import session_store
from app.llm.transcription_client import transcription_client
from app.schemas.common import TranscriptTurn
from app.schemas.transcription import TranscriptionResponse

router = APIRouter(tags=["transcription"])


@router.post("/transcription", response_model=TranscriptionResponse)
async def transcribe_audio(
    session_id: str = Form(..., min_length=1),
    start_ms: int = Form(default=0, ge=0),
    end_ms: int = Form(default=0, ge=0),
    audio_file: UploadFile = File(...),
) -> TranscriptionResponse:
    payload = await audio_file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="audio_file is empty.")

    out = await transcription_client.transcribe(
        audio_bytes=payload,
        filename=audio_file.filename or "chunk.webm",
        content_type=audio_file.content_type or "audio/webm",
    )
    if not out.text:
        raise HTTPException(status_code=502, detail=out.error or "Transcription failed.")

    resolved_end_ms = end_ms if end_ms >= start_ms else start_ms
    turn = TranscriptTurn(
        id=f"user-voice-{int(time.time() * 1000)}",
        text=out.text,
        start_ms=start_ms,
        end_ms=resolved_end_ms,
    )
    session_store.append_transcript(session_id, [turn])

    return TranscriptionResponse(
        session_id=session_id,
        speaker="user",
        turns=[turn],
        provider="groq",
        model=transcription_client.model,
        fallback_used=out.fallback_used,
        error=out.error,
    )
