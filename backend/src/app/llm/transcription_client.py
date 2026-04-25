import logging
from dataclasses import dataclass

from openai import APIError, OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    fallback_used: bool = False
    error: str | None = None


class GroqTranscriptionClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.transcription_model
        self.timeout = settings.request_timeout_seconds
        self._enabled = bool(settings.groq_api_key)
        self._client = (
            OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
            if self._enabled
            else None
        )

    async def transcribe(self, audio_bytes: bytes, filename: str, content_type: str) -> TranscriptionResult:
        if not self._enabled or self._client is None:
            return TranscriptionResult(
                text="",
                fallback_used=True,
                error="GROQ_API_KEY is not configured; transcription is disabled.",
            )
        try:
            response = self._client.audio.transcriptions.create(
                model=self.model,
                file=(filename, audio_bytes, content_type),
                timeout=self.timeout,
            )
            text = (getattr(response, "text", "") or "").strip()
            if not text:
                return TranscriptionResult(
                    text="",
                    fallback_used=True,
                    error="Transcription provider returned empty text.",
                )
            return TranscriptionResult(text=text)
        except APIError as exc:
            logger.warning("transcription API error; returning fallback: %s", exc)
            return TranscriptionResult(text="", fallback_used=True, error=f"Groq API error: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("transcription transport error; returning fallback: %s", exc)
            return TranscriptionResult(text="", fallback_used=True, error=f"Transcription transport error: {exc}")


transcription_client = GroqTranscriptionClient()
