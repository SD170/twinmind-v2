# TwinMind Backend Skeleton

Backend-first skeleton for the live suggestions assignment.

## Stack
- Python 3.11+
- FastAPI
- LangGraph
- Groq (OpenAI-compatible client)

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
