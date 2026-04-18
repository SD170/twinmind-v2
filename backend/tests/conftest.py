"""
Pytest defaults: visible app logs + no live Groq calls (fast, deterministic).

Integration/smoke tests exercise HTTP + graph shape only. For real Groq E2E, run:
  uvicorn + scripts/simulate_long_conversation.py
or set RUN_LIVE_GROQ_TESTS=1 (then tests may be slow and require a valid key + model).
"""

from __future__ import annotations

import logging
import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Emit app + uvicorn-style logs to terminal during pytest (not swallowed)."""
    if not logging.root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            force=True,
        )
    logging.getLogger("app").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@pytest.fixture(autouse=True)
def _pytest_live_groq_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Default: disable outbound Groq so tests finish in seconds and logs stay readable.

    Opt-in live calls: RUN_LIVE_GROQ_TESTS=1
    """
    if os.environ.get("RUN_LIVE_GROQ_TESTS", "").strip().lower() in ("1", "true", "yes"):
        return
    import app.llm.groq_client as gc

    monkeypatch.setattr(gc.groq_client, "_enabled", False, raising=False)
    monkeypatch.setattr(gc.groq_client, "_client", None, raising=False)
