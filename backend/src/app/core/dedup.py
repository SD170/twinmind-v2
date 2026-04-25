import hashlib

from app.schemas.settings import RuntimeSettingsEnvelope
from app.schemas.suggestions import RefreshSuggestionsRequest


def compute_batch_key(
    req: RefreshSuggestionsRequest, settings: RuntimeSettingsEnvelope, source_policy_version: str = "v1"
) -> str:
    payload = {
        "session_id": req.session_id,
        "user_turns": [t.model_dump() for t in req.recent_user_turns],
        "settings_version": settings.version,
        "source_policy_version": source_policy_version,
        "force_refresh": req.force_refresh,
        "source_policy": req.source_policy.model_dump(),
    }
    raw = str(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]
