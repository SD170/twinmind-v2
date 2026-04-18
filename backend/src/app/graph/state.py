from typing import Any, TypedDict

from app.core.state_builder import BatchState
from app.schemas.llm import RankAndDraftOutput, VerifyFactCheckOutput
from app.schemas.suggestions import RefreshSuggestionsRequest


class WorkflowState(TypedDict, total=False):
    request: RefreshSuggestionsRequest
    batch_state: BatchState
    rank_output: RankAndDraftOutput
    verify_output: VerifyFactCheckOutput
    timings: dict[str, int]
    metadata: dict[str, Any]
