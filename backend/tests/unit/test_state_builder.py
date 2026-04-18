from app.core.state_builder import build_batch_state
from app.schemas.suggestions import RefreshSuggestionsRequest
from app.schemas.common import TranscriptTurn


def test_state_builder_extracts_question_and_claim():
    req = RefreshSuggestionsRequest(
        session_id="s1",
        recent_user_turns=[TranscriptTurn(id="u1", text="What happened in 2024 outage?", start_ms=0, end_ms=1)],
        recent_ambient_turns=[
            TranscriptTurn(id="a1", text="The routing change caused failures.", start_ms=2, end_ms=3)
        ],
    )
    state = build_batch_state(req)
    assert state.explicit_user_question_score > 0.0
    assert state.checkworthy_claim_score > 0.0
    assert len(state.claims) >= 1
