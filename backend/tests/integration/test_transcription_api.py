from fastapi.testclient import TestClient

from app.main import app
from app.llm.transcription_client import TranscriptionResult

client = TestClient(app)


def test_transcription_endpoint_appends_user_turn(monkeypatch):
    async def _fake_transcribe(audio_bytes: bytes, filename: str, content_type: str) -> TranscriptionResult:
        assert audio_bytes
        assert filename == "sample.webm"
        assert content_type == "audio/webm"
        return TranscriptionResult(text="we should shard by user cohort")

    monkeypatch.setattr("app.api.transcription.transcription_client.transcribe", _fake_transcribe)
    res = client.post(
        "/api/v1/transcription",
        data={"session_id": "voice-session", "start_ms": 100, "end_ms": 600},
        files={"audio_file": ("sample.webm", b"audio-bytes", "audio/webm")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["speaker"] == "user"
    assert len(body["turns"]) == 1
    assert body["turns"][0]["text"] == "we should shard by user cohort"


def test_transcription_endpoint_handles_provider_failure(monkeypatch):
    async def _fake_transcribe(audio_bytes: bytes, filename: str, content_type: str) -> TranscriptionResult:
        assert audio_bytes and filename and content_type
        return TranscriptionResult(text="", fallback_used=True, error="provider failed")

    monkeypatch.setattr("app.api.transcription.transcription_client.transcribe", _fake_transcribe)
    res = client.post(
        "/api/v1/transcription",
        data={"session_id": "voice-session"},
        files={"audio_file": ("sample.webm", b"audio-bytes", "audio/webm")},
    )
    assert res.status_code == 502
    assert "provider failed" in res.json()["detail"]
