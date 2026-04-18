from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "trajectory_sessions.json"


def load_trajectory_sessions() -> list[dict[str, Any]]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return data["sessions"]
