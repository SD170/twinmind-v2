# TwinMind Backend Skeleton

Backend-first skeleton for the live suggestions assignment.

## Stack
- Python 3.11+
- FastAPI
- LangGraph
- Groq (OpenAI-compatible client); chat model ID must match GroqCloud, e.g. `openai/gpt-oss-120b` ([models](https://console.groq.com/docs/models))

## Quickstart
1. Create a virtual env and install:
   - `pip install -e .[dev]`
2. Copy env template:
   - `cp .env.example .env`
3. Run API:
   - `uvicorn app.main:app --reload`

## API
- `GET /health`
- `GET /ready`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- `POST /api/v1/suggestions/refresh`
- `POST /api/v1/suggestions/expand`
- `POST /api/v1/export`

## Notes
- Session-scoped in-memory state only.
- Live flow uses one main `rank_and_draft` call plus conditional fact-check verification.
- If LLM parsing fails, service falls back to conservative heuristic suggestions.

## Tests and logging
- `pytest` prints **INFO logs** from the `app` logger to the terminal (`log_cli` in `pyproject.toml`).
- By default, tests **do not call Groq** (see `tests/conftest.py`: outbound LLM is disabled so the suite stays fast). For real-network LLM tests, set `RUN_LIVE_GROQ_TESTS=1` (slow; needs valid `GROQ_API_KEY` and model id in `.env`).
- Long HTTP E2E (server must be running): `python scripts/simulate_long_conversation.py --base-url http://127.0.0.1:8000 --refreshes 50 --strict -v` (`-v` prints each refresh/expand).

## Trajectory tests (from `.context/deep-research-test.md`)
- Fixture: `tests/fixtures/trajectory_sessions.json` (regenerate: `python3 scripts/generate_trajectory_fixtures.py`).
- Smoke: `tests/test_trajectory_smoke.py` — every session batch returns 200 + valid shape (uses fast path under pytest; no Groq unless `RUN_LIVE_GROQ_TESTS=1`).
- Mocked contracts: `tests/test_trajectory_mocked_contracts.py` — patches LLM to fixture `expected_*` values; asserts DSL + top3 + scores.
- Harness-only sessions (S13–S15): `harness_only: true` in JSON — need async concurrency / injection (not automated yet).
