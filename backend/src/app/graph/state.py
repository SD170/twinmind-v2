from typing import Any, TypedDict

from app.schemas.llm import RankAndDraftOutput, VerifyFactCheckOutput
from app.schemas.settings import RuntimeSettings
from app.schemas.suggestions import RefreshSuggestionsRequest


class WorkflowState(TypedDict, total=False):
    request: RefreshSuggestionsRequest
    runtime_settings: RuntimeSettings
    rank_output: RankAndDraftOutput
    verify_output: VerifyFactCheckOutput
    timings: dict[str, int]
    metadata: dict[str, Any]
