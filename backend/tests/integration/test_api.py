import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _fixture(name: str) -> dict:
    path = Path(__file__).parent.parent / "fixtures" / name
    return json.loads(path.read_text())


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_refresh_suggestions_returns_three_cards():
    payload = _fixture("sample_refresh_request.json")
    res = client.post("/api/v1/suggestions/refresh", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert len(body["cards"]) == 3
    assert body["omitted_bucket"] in {"answer", "fact_check", "talking_point", "question"}


def test_settings_roundtrip():
    current = client.get("/api/v1/settings")
    assert current.status_code == 200
    next_settings = current.json()["settings"]
    next_settings["context_window_turns"] = 8
    updated = client.put("/api/v1/settings", json=next_settings)
    assert updated.status_code == 200
    assert updated.json()["settings"]["context_window_turns"] == 8
