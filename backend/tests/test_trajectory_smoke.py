"""Smoke: every trajectory batch POSTs successfully (real or fallback LLM)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.support.trajectory_loader import load_trajectory_sessions

client = TestClient(app)


def _cases():
    for session in load_trajectory_sessions():
        sid = session["session_id"]
        for batch in session["batches"]:
            bid = batch["batch_id"]
            yield pytest.param(sid, bid, session, batch, id=f"{sid}_{bid}")


@pytest.mark.parametrize("session_id,batch_id,session,batch", list(_cases()))
def test_trajectory_refresh_smoke(session_id: str, batch_id: str, session: dict, batch: dict) -> None:
    req = batch["request"].copy()
    req["session_id"] = session_id
    res = client.post("/api/v1/suggestions/refresh", json=req)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cards"]) == 3
    assert body["omitted_bucket"] in {"answer", "fact_check", "talking_point", "question"}
    assert set(body["scores"].keys()) == {"answer", "fact_check", "talking_point", "question"}
    assert body["signal_state"] in {"weak", "normal", "urgent"}
    buckets = [c["bucket"] for c in body["cards"]]
    assert len(buckets) == len(set(buckets)), "top3 must be three distinct buckets"
