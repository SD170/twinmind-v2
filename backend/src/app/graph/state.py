from typing import Any, TypedDict

from app.schemas.llm import RankAndDraftOutput, VerifyFactCheckOutput
from app.schemas.suggestions import RefreshSuggestionsRequest


class WorkflowState(TypedDict, total=False):
    request: RefreshSuggestionsRequest
    rank_output: RankAndDraftOutput
    verify_output: VerifyFactCheckOutput
    timings: dict[str, int]
    metadata: dict[str, Any]
