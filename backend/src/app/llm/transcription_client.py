import asyncio
import logging
from dataclasses import dataclass

from openai import APIError, OpenAI

from app.config import get_settings
from app.core.runtime_api_key_store import runtime_api_key_store

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
        self.base_url = settings.groq_base_url
        self._default_api_key = settings.groq_api_key.strip()

    async def transcribe(self, audio_bytes: bytes, filename: str, content_type: str) -> TranscriptionResult:
        api_key = self._resolve_api_key()
        if not api_key:
            return TranscriptionResult(
                text="",
                fallback_used=True,
                error="GROQ_API_KEY is not configured; transcription is disabled.",
            )
        try:
            response = await asyncio.to_thread(
                self._transcribe_sync,
                api_key,
                audio_bytes,
                filename,
                content_type,
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

    def _resolve_api_key(self) -> str:
        runtime_key = runtime_api_key_store.get()
        return runtime_key or self._default_api_key

    def _transcribe_sync(
        self, api_key: str, audio_bytes: bytes, filename: str, content_type: str
    ):
        client = OpenAI(api_key=api_key, base_url=self.base_url)
        return client.audio.transcriptions.create(
            model=self.model,
            file=(filename, audio_bytes, content_type),
            timeout=self.timeout,
        )


transcription_client = GroqTranscriptionClient()
