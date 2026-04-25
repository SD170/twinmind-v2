import json

from app.llm.parser import diagnose_parse_failure, try_parse_with_repair
from app.schemas.llm import RankAndDraftOutput


def test_try_parse_strips_markdown_fence():
    inner = {
        "bucket_scores": {"answer": 0.5, "fact_check": 0.4, "talking_point": 0.7, "question": 0.6},
        "cards": [
            {"bucket": "answer", "text": "a", "confidence": 0.5, "rationale": ""},
            {"bucket": "fact_check", "text": "b", "confidence": 0.4, "rationale": ""},
            {"bucket": "talking_point", "text": "c", "confidence": 0.7, "rationale": ""},
            {"bucket": "question", "text": "d", "confidence": 0.6, "rationale": ""},
        ],
        "top_three": ["talking_point", "question", "answer"],
        "omitted_bucket": "fact_check",
        "signal_state": "normal",
        "metadata": {},
    }
    wrapped = "```json\n" + json.dumps(inner) + "\n```"
    out = try_parse_with_repair(wrapped, RankAndDraftOutput)
    assert out is not None
    assert len(out.cards) == 4


def test_diagnose_shows_pydantic_errors_for_short_cards():
    bad = json.dumps(
        {
            "bucket_scores": {"answer": 0.5, "fact_check": 0.4, "talking_point": 0.7, "question": 0.6},
            "cards": [
                {"bucket": "answer", "text": "only", "confidence": 0.5, "rationale": ""},
            ],
            "top_three": ["talking_point", "question", "answer"],
            "omitted_bucket": "fact_check",
            "signal_state": "normal",
            "metadata": {},
        }
    )
    msg = diagnose_parse_failure(bad, RankAndDraftOutput)
    assert "pydantic_errors" in msg
