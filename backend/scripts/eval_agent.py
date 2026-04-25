#!/usr/bin/env python3
"""
LLM-based eval agent for TwinMind suggestion quality.

Runs 5 realistic multi-turn transcript trajectories against the live server,
judges every batch response with a Groq-based judge, and when quality is below
threshold asks a Groq-based critic to generate a targeted patch for prompts.py.
The patch is applied, the trajectory re-run (after a reload wait), and a diff printed.
Unpatched file is restored if the re-run judge score is worse (or verify errors).

Throttling: sleeps after each Groq call and after each /refresh, plus retries on 429/502/503.

Usage (use uvicorn --reload so prompt edits are picked up):
  cd backend
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  .venv/bin/python scripts/eval_agent.py --base-url http://127.0.0.1:8000
  # tune: --groq-sleep 3 --http-sleep 1.5 --reload-wait 6
  # preview only: --dry-run
"""

from __future__ import annotations

import argparse
import difflib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
from openai import APIStatusError, OpenAI

T = TypeVar("T")


def _is_transient_api_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 502, 503)
    if isinstance(exc, APIStatusError):
        return exc.status_code in (429, 503, 502)
    msg = str(exc).lower()
    return "429" in msg or "rate" in msg or "overloaded" in msg


def _sleep_groq(delay: float) -> None:
    if delay > 0:
        time.sleep(delay)


def _retry_call(
    fn: Callable[[], T],
    *,
    label: str,
    max_attempts: int,
    base_delay: float,
    cap_delay: float = 90.0,
) -> T:
    last: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last = e
            if not _is_transient_api_error(e) or attempt == max_attempts - 1:
                raise
            wait = min(cap_delay, base_delay * (2**attempt))
            print(f"  ⚠  {label}: transient error ({e!r}); retry in {wait:.1f}s (attempt {attempt + 1}/{max_attempts})")
            time.sleep(wait)
    assert last is not None
    raise last

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
PROMPTS_FILE = ROOT / "src" / "app" / "llm" / "prompts.py"

# ---------------------------------------------------------------------------
# Trajectories — 5 scenarios, each with 3–6 turns at real millisecond timestamps
# ---------------------------------------------------------------------------
TRAJECTORIES: list[dict[str, Any]] = [
    {
        "id": "narration_news",
        "description": "User narrates a third-party news article about a political controversy. No direct question is asked; no reply obligation exists.",
        "expected_intent": "narration",
        "expected_dominant_bucket": "talking_point",
        "turns": [
            {"id": "t1", "text": "So there's this story about the chief minister coming down hard on the prime minister over some remarks he allegedly made about a university.", "start_ms": 0, "end_ms": 4200},
            {"id": "t2", "text": "She said she was pained by the attempt to associate anarchy with a section of students there.", "start_ms": 6000, "end_ms": 9800},
            {"id": "t3", "text": "And she's questioning whether those remarks were in keeping with the decorum expected from the country's highest office.", "start_ms": 11000, "end_ms": 15500},
        ],
    },
    {
        "id": "direct_question",
        "description": "User explicitly asks a question mid-meeting. Answer should be the dominant bucket.",
        "expected_intent": "question",
        "expected_dominant_bucket": "answer",
        "turns": [
            {"id": "t1", "text": "We've been going in circles on this for twenty minutes.", "start_ms": 0, "end_ms": 3000},
            {"id": "t2", "text": "Someone's going to ask us in the review: what was the root cause of the January outage?", "start_ms": 5000, "end_ms": 8500},
            {"id": "t3", "text": "What should I say when they ask me directly?", "start_ms": 10000, "end_ms": 12500},
        ],
    },
    {
        "id": "ambiguous_claim",
        "description": "User makes a factual claim with explicit uncertainty in their own words. Fact_check should surface the existing uncertainty — not invent new gaps.",
        "expected_intent": "claim",
        "expected_dominant_bucket": "fact_check",
        "turns": [
            {"id": "t1", "text": "The routing change was the cause — at least that's what I remember from the postmortem.", "start_ms": 0, "end_ms": 4000},
            {"id": "t2", "text": "Though I'm not totally sure if it was routing or a DNS issue, the postmortem doc was ambiguous on that.", "start_ms": 6000, "end_ms": 10500},
            {"id": "t3", "text": "Either way I need to explain this to the exec team next week.", "start_ms": 12000, "end_ms": 15000},
        ],
    },
    {
        "id": "decision_prep",
        "description": "User is preparing to push back on a proposal and needs help framing a response. Answer and talking_point should both score high.",
        "expected_intent": "decision",
        "expected_dominant_bucket": "answer",
        "turns": [
            {"id": "t1", "text": "They're going to propose cutting the cache layer entirely to reduce complexity.", "start_ms": 0, "end_ms": 4000},
            {"id": "t2", "text": "I think that's the wrong call given our read latency requirements but I need to articulate why clearly.", "start_ms": 6000, "end_ms": 10000},
            {"id": "t3", "text": "If they ask me to justify keeping it, what's the strongest argument?", "start_ms": 12000, "end_ms": 15500},
        ],
    },
    {
        "id": "context_drift_repetition",
        "description": "User starts with one topic then introduces a second. System should avoid repeating old suggestions from the first batch in the second.",
        "expected_intent": "narration",
        "expected_dominant_bucket": "talking_point",
        "turns": [
            {"id": "t1", "text": "So the rate limits are set, that's settled.", "start_ms": 0, "end_ms": 2800},
            {"id": "t2", "text": "Now the next thing is rollback strategy for the proxy change.", "start_ms": 5000, "end_ms": 8000},
            {"id": "t3", "text": "We need a staged plan with clear abort criteria and an owner for sign-off.", "start_ms": 10000, "end_ms": 14000},
            {"id": "t4", "text": "The rollback window is probably 48 hours max before it's too disruptive to revert.", "start_ms": 16000, "end_ms": 20000},
        ],
    },
]

# ---------------------------------------------------------------------------
# Judge prompt — evaluated against each API response
# ---------------------------------------------------------------------------
EVAL_JUDGE_PROMPT = """You are a senior quality judge for an AI real-time suggestion system called TwinMind.
You will receive:
- trajectory_id: identifier for the test scenario
- description: what the user is doing in this transcript
- expected_intent: the intent class we expect (narration / question / claim / decision)
- expected_dominant_bucket: the bucket that should score highest (answer / fact_check / talking_point / question)
- turns: the transcript turns sent to the system
- system_response: the JSON response from the suggestion API

Score each axis 0-10:
- intent_match: does the top bucket match expected_dominant_bucket?
- answer_quality: is the answer card a speakable line (not strategy/meta commentary)?
  If answer is suppressed when expected (narration intent), give 10. If answer is present but is "we should verify..." give 0.
- question_quality: is the question outward-facing, specific, conversation-driving?
  Not a listener curiosity question, not answerable from transcript alone.
- fact_check_quality: is fact_check grounded in transcript? No invented uncertainty, no "check online"?
  If fact_check is correctly suppressed, give 10.
- ranking_consistency: does the omitted_bucket have the lowest bucket_score? Are top_three sorted descending?

Flag violations as short strings in a violations list. Examples:
- "answer card is strategy not content"
- "fact_check invents uncertainty not in transcript"
- "question is listener curiosity, not speaker move"
- "omitted bucket has higher score than shown bucket"

Return JSON only:
{
  "scores": {
    "intent_match": <0-10>,
    "answer_quality": <0-10>,
    "question_quality": <0-10>,
    "fact_check_quality": <0-10>,
    "ranking_consistency": <0-10>
  },
  "violations": ["...", ...],
  "overall": <0-10 weighted average>,
  "summary": "<one sentence>"
}
"""

# ---------------------------------------------------------------------------
# Critic prompt — called when overall score < threshold
# ---------------------------------------------------------------------------
EVAL_CRITIC_PROMPT = """You are a prompt engineer for TwinMind, an AI real-time suggestion system.

You will receive:
- current_prompt: the current RANK_AND_DRAFT_PROMPT string
- judge_result: the quality judgment for a failing trajectory
- trajectory: the test case that failed (description + turns)

Your task: produce a minimal, targeted patch that fixes the specific violations identified.

Rules:
- Only change the specific section(s) responsible for the violations. Do not rewrite the whole prompt.
- patch_description must identify the exact section heading (e.g. "Answer selection rules (strict)") to be replaced.
- new_section must be a complete replacement for that section only (keep all other sections intact).
- Be precise: fix the root cause of each violation, not symptoms.

Return JSON only:
{
  "needs_change": <true|false>,
  "patch_description": "<exact heading of the section to replace, or 'append' to add a new section at the end>",
  "old_section_start": "<first line of the section to replace, verbatim>",
  "old_section_end": "<last line of the section to replace, verbatim>",
  "new_section": "<full replacement text for that section>"
}
"""

# ---------------------------------------------------------------------------
# Groq client wrapper (minimal, does not use app.llm.groq_client)
# ---------------------------------------------------------------------------
class EvalGroqClient:
    def __init__(self, *, groq_sleep: float, groq_retries: int, groq_retry_base: float) -> None:
        import os

        env = ROOT / ".env"
        if env.exists():
            try:
                from dotenv import load_dotenv

                load_dotenv(env)
            except ImportError:
                pass
        api_key = os.environ.get("GROQ_API_KEY", "")
        base_url = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
        if not api_key:
            raise SystemExit("GROQ_API_KEY not set. Cannot run eval agent.")
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self._groq_sleep = groq_sleep
        self._groq_retries = groq_retries
        self._groq_retry_base = groq_retry_base

    def chat_json(self, system_prompt: str, user_content: str, temperature: float = 0.2) -> dict[str, Any]:
        def _one() -> dict[str, Any]:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                timeout=120,
            )
            raw = response.choices[0].message.content or "{}"
            if raw.startswith("```"):
                lines = raw.splitlines()
                raw = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
            return json.loads(raw)

        out = _retry_call(
            _one,
            label="Groq",
            max_attempts=self._groq_retries,
            base_delay=self._groq_retry_base,
        )
        _sleep_groq(self._groq_sleep)
        return out


# ---------------------------------------------------------------------------
# Run a trajectory against the live server
# ---------------------------------------------------------------------------
def run_trajectory(
    client: httpx.Client,
    base_url: str,
    trajectory: dict[str, Any],
    *,
    http_sleep: float,
    http_retries: int,
    http_retry_base: float,
) -> dict[str, Any]:
    session_id = f"eval-{uuid.uuid4().hex[:10]}"
    payload = {
        "session_id": session_id,
        "recent_user_turns": trajectory["turns"],
        "force_refresh": True,
        "source_policy": {
            "enable_conditional_web": False,
            "approved_sources": [],
            "approved_fact_sources": [],
        },
    }
    t0 = time.perf_counter()

    def _post() -> httpx.Response:
        r = client.post(f"{base_url}/api/v1/suggestions/refresh", json=payload, timeout=120)
        if r.status_code == 200:
            return r
        if r.status_code in (429, 502, 503):
            r.raise_for_status()
        raise RuntimeError(f"API error {r.status_code}: {r.text[:400]}")

    resp = _retry_call(
        _post,
        label="suggestions/refresh",
        max_attempts=http_retries,
        base_delay=http_retry_base,
    )

    latency_ms = int((time.perf_counter() - t0) * 1000)
    if http_sleep > 0:
        time.sleep(http_sleep)
    return {"response": resp.json(), "latency_ms": latency_ms, "session_id": session_id}


# ---------------------------------------------------------------------------
# Judge a single trajectory run
# ---------------------------------------------------------------------------
def judge_trajectory(
    groq: EvalGroqClient,
    trajectory: dict[str, Any],
    run_result: dict[str, Any],
) -> dict[str, Any]:
    user_content = json.dumps(
        {
            "trajectory_id": trajectory["id"],
            "description": trajectory["description"],
            "expected_intent": trajectory["expected_intent"],
            "expected_dominant_bucket": trajectory["expected_dominant_bucket"],
            "turns": trajectory["turns"],
            "system_response": run_result["response"],
        },
        indent=2,
    )
    return groq.chat_json(EVAL_JUDGE_PROMPT, user_content)


# ---------------------------------------------------------------------------
# Apply a critic patch to prompts.py
# ---------------------------------------------------------------------------
def read_prompts_file() -> str:
    return PROMPTS_FILE.read_text(encoding="utf-8")


def write_prompts_file(content: str) -> None:
    PROMPTS_FILE.write_text(content, encoding="utf-8")


def apply_patch(
    current_content: str,
    patch: dict[str, Any],
) -> str | None:
    """Return patched content, or None if the section can't be located."""
    if patch.get("patch_description") == "append":
        # Append new_section before the closing triple-quote of RANK_AND_DRAFT_PROMPT
        marker = 'Return one JSON object only.\n"""'
        if marker not in current_content:
            return None
        new_section = patch.get("new_section", "").strip()
        return current_content.replace(
            marker,
            f"{new_section}\n\nReturn one JSON object only.\n\"\"\"",
        )

    old_start = patch.get("old_section_start", "").strip()
    old_end = patch.get("old_section_end", "").strip()
    new_section = patch.get("new_section", "").strip()

    if not old_start or not new_section:
        return None

    lines = current_content.splitlines(keepends=True)
    start_idx: int | None = None
    end_idx: int | None = None

    for i, line in enumerate(lines):
        if start_idx is None and old_start in line.strip():
            start_idx = i
        elif start_idx is not None and old_end and old_end in line.strip():
            end_idx = i
            break

    if start_idx is None:
        return None

    if end_idx is None:
        # Replace just the single matching line
        end_idx = start_idx

    before = lines[:start_idx]
    after = lines[end_idx + 1:]
    new_lines = [new_section + "\n"]
    return "".join(before + new_lines + after)


# ---------------------------------------------------------------------------
# Print a unified diff
# ---------------------------------------------------------------------------
def print_diff(before: str, after: str) -> None:
    diff = list(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="prompts.py (before)",
            tofile="prompts.py (after)",
        )
    )
    if diff:
        print("".join(diff))
    else:
        print("  (no textual diff)")


# ---------------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="LLM eval agent for TwinMind suggestions")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000", help="Live server base URL")
    ap.add_argument("--threshold", type=float, default=7.0, help="Score below which a patch is attempted (0-10)")
    ap.add_argument("--dry-run", action="store_true", help="Judge and show diffs but do not write prompts.py or verify")
    ap.add_argument(
        "--no-verify",
        action="store_true",
        help="After writing a patch, do not re-run the trajectory (skip reload wait + score check + revert).",
    )
    ap.add_argument(
        "--groq-sleep",
        type=float,
        default=2.5,
        help="Seconds to wait after each Groq call (reduces 429s). Default: 2.5",
    )
    ap.add_argument(
        "--http-sleep",
        type=float,
        default=1.0,
        help="Seconds to wait after each /suggestions/refresh. Default: 1.0",
    )
    ap.add_argument(
        "--between-trajectories",
        type=float,
        default=1.5,
        help="Extra pause before starting the next trajectory. Default: 1.5",
    )
    ap.add_argument(
        "--reload-wait",
        type=float,
        default=5.0,
        help="Seconds to wait after writing prompts.py for uvicorn --reload to import new code. Default: 5.0",
    )
    ap.add_argument("--groq-retries", type=int, default=6, help="Max attempts per Groq call (429/503 backoff). Default: 6")
    ap.add_argument(
        "--groq-retry-base",
        type=float,
        default=3.0,
        help="Base seconds for Groq exponential backoff. Default: 3.0",
    )
    ap.add_argument(
        "--http-retries", type=int, default=6, help="Max attempts for POST refresh (429/502/503). Default: 6"
    )
    ap.add_argument(
        "--http-retry-base", type=float, default=2.0, help="Base seconds for HTTP retry backoff. Default: 2.0"
    )
    args = ap.parse_args()
    base_url = args.base_url.rstrip("/")

    groq = EvalGroqClient(
        groq_sleep=args.groq_sleep,
        groq_retries=args.groq_retries,
        groq_retry_base=args.groq_retry_base,
    )

    run_kw = {
        "http_sleep": args.http_sleep,
        "http_retries": args.http_retries,
        "http_retry_base": args.http_retry_base,
    }

    results_summary: list[dict[str, Any]] = []
    patches_applied = 0
    patches_reverted = 0

    with httpx.Client() as http:
        def _health() -> httpx.Response:
            h = http.get(f"{base_url}/health", timeout=30)
            if h.status_code == 200:
                return h
            if h.status_code in (429, 502, 503):
                h.raise_for_status()
            raise RuntimeError(f"GET /health: {h.status_code} {h.text[:200]}")

        try:
            _retry_call(
                _health,
                label="/health",
                max_attempts=args.http_retries,
                base_delay=args.http_retry_base,
            )
        except Exception as exc:
            raise SystemExit(f"Server not reachable at {base_url}: {exc}") from exc
        if args.http_sleep > 0:
            time.sleep(args.http_sleep)

        for ti, trajectory in enumerate(TRAJECTORIES):
            if ti > 0 and args.between_trajectories > 0:
                time.sleep(args.between_trajectories)
            tid = trajectory["id"]
            print(f"\n{'='*60}")
            print(f"[eval] trajectory: {tid}")
            print(f"       {trajectory['description']}")
            print(f"       expected: intent={trajectory['expected_intent']}  dominant={trajectory['expected_dominant_bucket']}")

            try:
                run = run_trajectory(http, base_url, trajectory, **run_kw)
            except RuntimeError as exc:
                print(f"  ERROR running trajectory: {exc}")
                results_summary.append(
                    {
                        "trajectory_id": tid,
                        "overall": 0.0,
                        "violations": [str(exc)],
                        "latency_ms": 0,
                    }
                )
                continue

            resp = run["response"]
            top3 = [c["bucket"] for c in resp.get("cards", [])]
            scores = resp.get("scores", {})
            print(f"       latency: {run['latency_ms']}ms")
            print(f"       top3: {top3}  omitted: {resp.get('omitted_bucket')}  signal: {resp.get('signal_state')}")
            print(f"       scores: { {k: round(v, 2) for k, v in scores.items()} }")

            print("  → judging with Groq...")
            try:
                judgment = judge_trajectory(groq, trajectory, run)
            except Exception as exc:
                print(f"  JUDGE ERROR: {exc}")
                results_summary.append(
                    {
                        "trajectory_id": tid,
                        "overall": 0.0,
                        "violations": [f"judge: {exc!s}"],
                        "latency_ms": run["latency_ms"],
                    }
                )
                continue

            overall = float(judgment.get("overall", 0))
            violations = judgment.get("violations", [])
            sub = judgment.get("scores", {})
            print(f"  → overall: {overall:.1f}/10")
            print(f"     scores: {sub}")
            if violations:
                print("     violations:")
                for v in violations:
                    print(f"       - {v}")
            else:
                print("     violations: none")
            print(f"     summary: {judgment.get('summary', '')}")

            row: dict[str, Any] = {
                "trajectory_id": tid,
                "overall": overall,
                "before_patch_overall": overall,
                "violations": violations,
                "latency_ms": run["latency_ms"],
            }

            if overall < args.threshold and violations:
                print(f"\n  → score {overall:.1f} < threshold {args.threshold} — asking critic for patch...")

                current_content = read_prompts_file()
                prompt_text = current_content

                critic_input = json.dumps(
                    {
                        "current_prompt": prompt_text,
                        "judge_result": judgment,
                        "trajectory": {
                            "id": trajectory["id"],
                            "description": trajectory["description"],
                            "expected_intent": trajectory["expected_intent"],
                            "turns": trajectory["turns"],
                        },
                    },
                    indent=2,
                )

                try:
                    patch = groq.chat_json(EVAL_CRITIC_PROMPT, critic_input, temperature=0.1)
                except Exception as exc:
                    print(f"  CRITIC ERROR: {exc}")
                    results_summary.append(row)
                    continue

                if not patch.get("needs_change"):
                    print("  → critic: no change recommended")
                    results_summary.append(row)
                    continue

                print(f"  → critic: patching section {patch.get('patch_description')!r}")

                patched_content = apply_patch(current_content, patch)
                if patched_content is None:
                    print("  → patch location not found in prompts.py — skipping")
                    results_summary.append(row)
                    continue

                if args.dry_run:
                    print("  → DRY RUN — diff (not written):")
                    print_diff(current_content, patched_content)
                    results_summary.append(row)
                    continue

                write_prompts_file(patched_content)
                patches_applied += 1
                print("  → patch written — diff:")
                print_diff(current_content, patched_content)

                if args.no_verify:
                    print("  → --no-verify: skipped re-run")
                    results_summary.append(row)
                    continue

                print(
                    f"  → waiting {args.reload_wait:.1f}s for server to reload "
                    f"(set --reload-wait if needed; use uvicorn with --reload)"
                )
                time.sleep(args.reload_wait)

                print("  → re-run same trajectory to verify (live Groq in server + judge)...")
                try:
                    run2 = run_trajectory(http, base_url, trajectory, **run_kw)
                    judgment2 = judge_trajectory(groq, trajectory, run2)
                except Exception as exc:
                    print(f"  VERIFY ERROR (revert patch): {exc}")
                    write_prompts_file(current_content)
                    patches_applied -= 1
                    patches_reverted += 1
                    print("  → prompts.py reverted to pre-patch (verify failed)")
                    results_summary.append(row)
                    continue

                o2 = float(judgment2.get("overall", 0))
                v2 = judgment2.get("violations", [])
                print(f"  → re-run overall (judge): {o2:.1f}/10  (before patch: {overall:.1f})")
                if v2:
                    for v in v2:
                        print(f"     violation: {v}")
                if o2 < overall:
                    print(
                        f"  → re-run score regressed ({o2:.1f} < {overall:.1f}); "
                        f"reverting {PROMPTS_FILE.name}"
                    )
                    write_prompts_file(current_content)
                    patches_applied -= 1
                    patches_reverted += 1
                    row["overall"] = overall
                    row["after_patch_overall"] = o2
                    row["violations"] = v2
                    row["reverted"] = True
                else:
                    print(f"  → re-run score: {o2:.1f}/10 ✓ (kept patch)")
                    row["overall"] = o2
                    row["after_patch_overall"] = o2
                    row["violations"] = v2

            results_summary.append(row)

    # --- Final report ---
    print(f"\n{'='*60}")
    print("FINAL REPORT")
    print(f"{'='*60}")
    for r in results_summary:
        o = float(r.get("overall", 0))
        status = "✓" if o >= args.threshold else "✗"
        vcount = len(r.get("violations", []))
        line = (
            f"  {status} {r['trajectory_id']:35s} overall={o:.1f}/10  "
            f"violations={vcount}  latency={r['latency_ms']}ms"
        )
        if "after_patch_overall" in r and not r.get("reverted"):
            b = float(r["before_patch_overall"])
            a = float(r["after_patch_overall"])
            line += f"  (was {b:.1f} → {a:.1f} after patch)"
        print(line)
    if patches_applied:
        print(f"\n  {patches_applied} patch(es) kept in {PROMPTS_FILE.relative_to(ROOT)}")
    if patches_reverted:
        print(f"  {patches_reverted} patch(es) reverted (worse or broken verify).")
    if not patches_applied and not patches_reverted:
        print("\n  No net patches applied.")
    print()


if __name__ == "__main__":
    main()
