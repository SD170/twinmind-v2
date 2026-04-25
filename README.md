# TwinMind Live Suggestions

Live meeting copilot app for the TwinMind assignment:
- Left: microphone + transcript
- Middle: live suggestion cards (3 per refresh)
- Right: chat and expanded answers

## Submission Links

- Deployed app URL: `ADD_YOUR_DEPLOY_URL_HERE`
- GitHub repository: `ADD_YOUR_GITHUB_REPO_URL_HERE`

## Tech Stack and Why

### Frontend
- React + TypeScript + Vite
- Tailwind-style utility classes
- Reasoning: fast iteration speed, simple component model, good DX for real-time UI updates

### Backend
- Python 3.11
- FastAPI
- LangGraph (routing between rank -> optional verify -> finalize)
- Groq via OpenAI-compatible SDK
- Reasoning: low overhead API server, strong typing/validation with Pydantic, explicit graph flow for suggestion pipeline

### Models
- Transcription: Groq Whisper Large V3
- Suggestions / expand / chat: Groq GPT-OSS 120B

## Project Structure

- `frontend/` - React web client
- `backend/` - FastAPI + graph pipeline + LLM clients
- `.context/` - assignment and notes

## Local Setup

## 1) Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Notes:
- You can keep a default key in `.env` (`GROQ_API_KEY`) for local development.
- The UI can also inject a runtime key from Settings (stored in browser localStorage and pushed to backend runtime memory on load).

## 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

If needed:
- `VITE_API_BASE_URL` defaults to `http://127.0.0.1:8000`

## Docker (Backend)

Build backend image:

```bash
cd backend
docker build -t twinmind-backend:latest .
```

Run backend container:

```bash
docker run --rm -p 8000:8000 --env-file .env twinmind-backend:latest
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

## Runtime Features

- Start/stop microphone and stream transcript chunks
- Auto-refresh suggestions from transcript flow
- Manual refresh
- Click card -> expanded long-form response
- Chat with transcript-aware context
- Settings panel for API key and prompt/context tuning
- Session export as downloadable JSON file

## API Endpoints (Core)

- `GET /health`
- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- `GET /api/v1/settings/api-key`
- `PUT /api/v1/settings/api-key`
- `POST /api/v1/transcription`
- `POST /api/v1/suggestions/refresh`
- `POST /api/v1/suggestions/expand`
- `POST /api/v1/chat/message`
- `POST /api/v1/export`

## Prompt Strategy and Design Decisions

The core prompt is designed as a single-pass `rank_and_draft` prompt for live suggestions. I chose a single prompt instead of multiple agent calls because the assignment values latency and real-time usefulness. Every refresh should feel fast, so the model classifies, scores, drafts, and ranks suggestions in one call.

The system always considers exactly four suggestion buckets:

- `answer`
- `fact_check`
- `talking_point`
- `question`

For every transcript refresh, the model scores all four buckets and returns the top three. The omitted bucket must always be the lowest-scoring bucket. This keeps the output predictable and prevents ranking contradictions.

The prompt first performs intent detection internally. It classifies the current user transcript as one of:

- narration / storytelling
- question / information seeking
- argument / claim making
- decision / response preparation

This matters because the same text can need different help depending on the user’s intent. For example, if the user is narrating, the system should usually prefer a talking point instead of forcing an answer. If the user asks a direct question, the answer bucket becomes more important.

A major design rule is egocentricity. The transcript comes from the focal user’s microphone, so every suggestion must help the user’s next move. The system should not generate listener-style questions or generic commentary. Suggestions should sound like something the user can say, ask, or keep in mind next.

The `answer` bucket is intentionally strict. It is only used when the user clearly needs a line to say, such as answering a question, making a decision, explaining a point, or preparing a response. Answer suggestions must be actual speakable content, not strategy like “we should verify this” or “we need to check.”

The `fact_check` bucket is also strict because this MVP is transcript-only. The system does not browse the web or assume external evidence. Fact-check suggestions are only used when the transcript contains a check-worthy claim that matters to the user’s next line. When there is no clear factual claim, the prompt avoids useless meta text like “no fact to check” and instead produces a soft epistemic nudge, such as tightening wording, reducing vagueness, or clarifying scope.

The `question` bucket is constrained to questions the user could plausibly ask another person next. It rejects curiosity-only questions, listener-style questions, and questions already answered by the transcript. Good questions should unblock a decision, clarify direction, or move the conversation forward.

The `talking_point` bucket acts as the default proactive suggestion when there is a useful theme to raise but no stronger answer, fact-check, or question need. This is especially useful during narration, brainstorming, or early discussion.

I also added anti-repetition through `recent_suggestion_history`, so the model avoids repeating similar cards across refreshes. The prompt includes scoring stability rules so scores do not swing wildly unless the transcript actually changes with a new question, claim, uncertainty, or decision need.

The system uses strict JSON outputs so the frontend can reliably parse and render suggestions. Each response includes bucket scores, four candidate cards, the top three buckets, omitted bucket, signal state, and metadata.

There are separate prompts for:
- verifying a fact-check card when evidence is available
- expanding a clicked suggestion
- answering direct user chat questions

This keeps the live path fast while still supporting deeper answers when the user clicks a suggestion.

## Tradeoffs

- **In-memory runtime settings and session state:** very fast and simple; resets on backend restart.
- **Prompt overrides in UI:** great for evaluator experimentation; increases surface area and needs guardrails in production.
- **Single-pass live generation:** best latency/UX; less decomposition than multi-agent alternatives.
- **Transcript-first fact-check policy:** avoids external dependency and drift; less coverage for truly external verification.
- **Export via backend endpoint:** canonical session snapshot from server state; still single-node/local persistence only.

## Validation Commands

Frontend:
```bash
cd frontend
npm run build
```

Backend:
```bash
cd backend
python -m compileall src/app
```
