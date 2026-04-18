import re
from dataclasses import dataclass, field

from app.schemas.suggestions import RefreshSuggestionsRequest

QUESTION_MARKERS = ("?", "what", "why", "how", "when", "where", "who", "could", "should")
CLAIM_MARKERS = ("is", "are", "was", "were", "caused", "because", "increased", "decreased")
GAP_MARKERS = ("not sure", "unclear", "what do you mean", "which one", "confused")


@dataclass
class BatchState:
    explicit_user_question_score: float = 0.0
    inferred_reply_obligation_score: float = 0.0
    checkworthy_claim_score: float = 0.0
    open_information_gap_score: float = 0.0
    salient_topic_score: float = 0.0
    likely_to_speak_now_score: float = 0.0
    transcript_evidence_score: float = 0.6
    user_value_score: float = 0.6
    timing_window_score: float = 0.6
    claims: list[str] = field(default_factory=list)
    open_gaps: list[str] = field(default_factory=list)
    salient_topics: list[str] = field(default_factory=list)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _extract_claims(texts: list[str]) -> list[str]:
    claims: list[str] = []
    for text in texts:
        if re.search(r"\b\d{4}\b", text) or _contains_any(text, CLAIM_MARKERS):
            claims.append(text.strip())
    return claims[:4]


def build_batch_state(req: RefreshSuggestionsRequest) -> BatchState:
    user_texts = [turn.text.lower() for turn in req.recent_user_turns]
    ambient_texts = [turn.text.lower() for turn in req.recent_ambient_turns]
    merged = user_texts + ambient_texts
    merged_text = " ".join(merged)

    state = BatchState()
    if any(_contains_any(text, QUESTION_MARKERS) for text in user_texts):
        state.explicit_user_question_score = 0.9
    if any(text.endswith("?") for text in ambient_texts):
        state.inferred_reply_obligation_score = 0.8
    elif state.explicit_user_question_score > 0.0:
        state.inferred_reply_obligation_score = 0.6

    claims = _extract_claims(merged)
    state.claims = claims
    if claims:
        state.checkworthy_claim_score = 0.7

    gaps = [text for text in merged if _contains_any(text, GAP_MARKERS)]
    state.open_gaps = gaps[:4]
    if gaps:
        state.open_information_gap_score = 0.85

    tokens = [token for token in re.split(r"\W+", merged_text) if len(token) > 4]
    top_tokens = tokens[:20]
    state.salient_topics = list(dict.fromkeys(top_tokens))[:5]
    if state.salient_topics:
        state.salient_topic_score = 0.6

    if req.recent_user_turns:
        latest = req.recent_user_turns[-1].text.strip()
        if latest.endswith("?"):
            state.likely_to_speak_now_score = 0.4
        else:
            state.likely_to_speak_now_score = 0.7

    return state
