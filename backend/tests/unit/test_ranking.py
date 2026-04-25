from app.core.ranking import top_three
from app.schemas.common import BucketType


def test_top_three_returns_three_and_omitted():
    scores = {
        BucketType.answer: 0.81,
        BucketType.fact_check: 0.27,
        BucketType.talking_point: 0.65,
        BucketType.question: 0.54,
    }
    selected, omitted = top_three(scores)
    assert len(selected) == 3
    assert omitted in BucketType
