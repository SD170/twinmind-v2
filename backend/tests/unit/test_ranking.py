from app.core.ranking import compute_bucket_scores, top_three
from app.core.state_builder import BatchState
from app.schemas.common import BucketType


def test_top_three_returns_three_and_omitted():
    state = BatchState(
        explicit_user_question_score=0.8,
        inferred_reply_obligation_score=0.7,
        checkworthy_claim_score=0.2,
        open_information_gap_score=0.5,
        salient_topic_score=0.6,
    )
    scores = compute_bucket_scores(state)
    selected, omitted = top_three(scores)
    assert len(selected) == 3
    assert omitted in BucketType
