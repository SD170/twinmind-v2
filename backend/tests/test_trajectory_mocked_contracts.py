"""Deterministic contracts: mock LLM outputs from fixture expected_* fields."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.support.assertion_dsl import evaluate
from tests.support.build_mock_llm import build_rank_and_draft_from_expected, build_verify_factcheck_from_expected
from tests.support.trajectory_loader import load_trajectory_sessions

client = TestClient(app)


class _FakeGroq:
    def __init__(self, session: dict[str, Any], batch_id: str) -> None:
        self._session = session
        self._batch_id = batch_id

    async def rank_and_draft(self, prompt: str, payload: dict[str, Any]) -> Any:
        return build_rank_and_draft_from_expected(self._batch_id, self._session)

    async def verify_factcheck(self, prompt: str, payload: dict[str, Any]) -> Any:
        return build_verify_factcheck_from_expected(self._batch_id, self._session)

    async def expand(self, prompt: str, payload: dict[str, Any]) -> Any:
        from app.schemas.llm import ExpandOutput

        return ExpandOutput(
            expanded_text="fixture expand",
            supporting_points=[],
            uncertainties=[],
            evidence_used=[],
        )


def _mock_cases():
    for session in load_trajectory_sessions():
        if session.get("harness_only"):
            continue
        sid = session["session_id"]
        for batch in session["batches"]:
            bid = batch["batch_id"]
            yield pytest.param(sid, bid, session, batch, id=f"{sid}_{bid}")


@pytest.mark.parametrize("session_id,batch_id,session,batch", list(_mock_cases()))
def test_trajectory_mocked_assertions(
    session_id: str,
    batch_id: str,
    session: dict[str, Any],
    batch: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.graph.nodes.rank_and_draft as rank_mod
    import app.graph.nodes.verify_factcheck as verify_mod

    fake = _FakeGroq(session, batch_id)
    monkeypatch.setattr(rank_mod, "groq_client", fake)
    monkeypatch.setattr(verify_mod, "groq_client", fake)

    async def _no_web(*_a: Any, **_k: Any) -> list[str]:
        return []

    monkeypatch.setattr("app.graph.nodes.verify_factcheck.web_search_client.search", _no_web)

    req = batch["request"].copy()
    req["session_id"] = session_id
    res = client.post("/api/v1/suggestions/refresh", json=req)
    assert res.status_code == 200, res.text
    body = res.json()

    assertions = []
    for a in session.get("verifiable_assertions", []):
        if a.get("batch_id") == batch_id:
            assertions.append(a["check"])

    dsl_body = {
        "scores": body["scores"],
        "cards": body["cards"],
        "omitted_bucket": body["omitted_bucket"],
        "signal_state": body["signal_state"],
    }
    for check in assertions:
        assert evaluate(check, dsl_body), f"Failed: {check} body={dsl_body}"

    # Scores within doc tolerance vs expected router scores (mocked = exact source)
    exp_scores = session["expected_router_scores"][batch_id]
    for k, v in exp_scores.items():
        assert abs(float(body["scores"][k]) - float(v)) <= 0.001

    top3 = [c["bucket"] for c in body["cards"]]
    assert top3 == session["expected_display_order"][batch_id]["top3"]
    assert body["omitted_bucket"] == session["expected_display_order"][batch_id]["omitted"]
