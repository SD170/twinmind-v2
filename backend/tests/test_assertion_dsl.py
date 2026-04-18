from tests.support.assertion_dsl import evaluate


def test_dsl_score_compare():
    body = {
        "scores": {"answer": 0.9, "talking_point": 0.5},
        "cards": [{"bucket": "answer", "text": "x"}],
        "omitted_bucket": "fact_check",
        "signal_state": "normal",
    }
    assert evaluate("scores.answer > scores.talking_point", body)


def test_dsl_top3_and_omitted():
    body = {
        "scores": {},
        "cards": [
            {"bucket": "question", "text": "a"},
            {"bucket": "answer", "text": "b"},
            {"bucket": "talking_point", "text": "c"},
        ],
        "omitted_bucket": "fact_check",
        "signal_state": "urgent",
    }
    assert evaluate("top3[0]=='question'", body)
    assert evaluate("omitted=='fact_check'", body)


def test_dsl_regex_negative():
    body = {
        "scores": {},
        "cards": [{"bucket": "answer", "text": "Say: keep details private."}],
        "omitted_bucket": "fact_check",
        "signal_state": "normal",
    }
    assert evaluate("texts.answer !~ /Alice|ACME/", body)
