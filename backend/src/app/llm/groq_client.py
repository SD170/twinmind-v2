import json
import logging
from typing import Any

from openai import APIError, OpenAI

from app.config import get_settings
from app.schemas.common import BucketType, SignalState
from app.schemas.llm import ChatOutput, ExpandOutput, RankAndDraftOutput, VerifyFactCheckOutput
from app.llm.parser import diagnose_parse_failure, try_parse_with_repair

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.groq_model
        self.timeout = settings.request_timeout_seconds
        self._enabled = bool(settings.groq_api_key)
        self._client = (
            OpenAI(api_key=settings.groq_api_key, base_url=settings.groq_base_url)
            if self._enabled
            else None
        )

    async def rank_and_draft(self, prompt: str, payload: dict[str, Any]) -> RankAndDraftOutput:
        if not self._enabled:
            return self._fallback_rank_and_draft()
        try:
            raw = self._chat_json(prompt, payload)
        except APIError as exc:
            logger.warning("rank_and_draft API error; using fallback: %s", exc)
            return self._fallback_rank_and_draft()
        except Exception as exc:  # noqa: BLE001
            logger.warning("rank_and_draft transport error; using fallback: %s", exc)
            return self._fallback_rank_and_draft()
        parsed = try_parse_with_repair(raw, RankAndDraftOutput)
        if parsed:
            return parsed  # type: ignore[return-value]
        logger.warning(
            "rank_and_draft parse failed; using fallback | %s",
            diagnose_parse_failure(raw, RankAndDraftOutput),
        )
        return self._fallback_rank_and_draft()

    async def verify_factcheck(self, prompt: str, payload: dict[str, Any]) -> VerifyFactCheckOutput:
        if not self._enabled:
            return VerifyFactCheckOutput(
                verdict="uncertain",
                revised_card_text=(
                    "Say that point with one concrete anchor (time, number, or scope) so it lands clearly—"
                    "without adding new claims."
                ),
                confidence=0.35,
                evidence_summary=[],
            )
        try:
            raw = self._chat_json(prompt, payload)
        except (APIError, Exception) as exc:  # noqa: BLE001
            logger.warning("verify_factcheck API error; using fallback: %s", exc)
            return VerifyFactCheckOutput(
                verdict="uncertain",
                revised_card_text=(
                    "Say that point with one concrete anchor (time, number, or scope) so it lands clearly—"
                    "without adding new claims."
                ),
                confidence=0.35,
                evidence_summary=[],
            )
        parsed = try_parse_with_repair(raw, VerifyFactCheckOutput)
        if parsed:
            return parsed  # type: ignore[return-value]
        logger.warning("verify_factcheck parse failed; using fallback")
        return VerifyFactCheckOutput(
            verdict="uncertain",
            revised_card_text=(
                "Say that point with one concrete anchor (time, number, or scope) so it lands clearly—"
                "without adding new claims."
            ),
            confidence=0.35,
            evidence_summary=[],
        )

    async def expand(self, prompt: str, payload: dict[str, Any]) -> ExpandOutput:
        if not self._enabled:
            text = payload.get("clicked_text", "Suggestion")
            return ExpandOutput(
                expanded_text=f"{text}. Use this as a cautious next move.",
                supporting_points=[],
                uncertainties=["LLM key not configured; using fallback expansion."],
                evidence_used=[],
            )
        try:
            raw = self._chat_json(prompt, payload)
        except (APIError, Exception) as exc:  # noqa: BLE001
            logger.warning("expand API error; using fallback: %s", exc)
            return ExpandOutput(
                expanded_text="Use the suggestion carefully and confirm details before speaking.",
                supporting_points=[],
                uncertainties=["LLM request failed; using fallback expansion."],
                evidence_used=[],
            )
        parsed = try_parse_with_repair(raw, ExpandOutput)
        if parsed:
            return parsed  # type: ignore[return-value]
        logger.warning(
            "expand parse failed; using fallback | %s",
            diagnose_parse_failure(raw, ExpandOutput),
        )
        return ExpandOutput(
            expanded_text="Use the suggestion carefully and confirm details before speaking.",
            supporting_points=[],
            uncertainties=["Parser fallback used due to malformed LLM output."],
            evidence_used=[],
        )

    async def chat(self, prompt: str, payload: dict[str, Any]) -> ChatOutput:
        if not self._enabled:
            user_message = str(payload.get("message", ""))
            return ChatOutput(
                answer=f"{user_message or 'Good question.'} Here is a concise reply you can use right now.",
                supporting_points=[],
                uncertainties=["LLM key not configured; using fallback chat response."],
                evidence_used=[],
            )
        try:
            raw = self._chat_json(prompt, payload)
        except (APIError, Exception) as exc:  # noqa: BLE001
            logger.warning("chat API error; using fallback: %s", exc)
            return ChatOutput(
                answer="I can help with that. Use one concrete, specific line and avoid broad claims.",
                supporting_points=[],
                uncertainties=["LLM request failed; using fallback chat response."],
                evidence_used=[],
            )
        parsed = try_parse_with_repair(raw, ChatOutput)
        if parsed:
            return parsed  # type: ignore[return-value]
        logger.warning(
            "chat parse failed; using fallback | %s",
            diagnose_parse_failure(raw, ChatOutput),
        )
        return ChatOutput(
            answer="Give one specific, grounded response and keep it short.",
            supporting_points=[],
            uncertainties=["Parser fallback used due to malformed chat output."],
            evidence_used=[],
        )

    def _chat_json(self, prompt: str, payload: dict[str, Any]) -> str:
        assert self._client is not None
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=self.timeout,
        )
        return response.choices[0].message.content or "{}"

    def _fallback_rank_and_draft(self) -> RankAndDraftOutput:
        scores = {
            BucketType.answer: 0.52,
            BucketType.fact_check: 0.35,
            BucketType.talking_point: 0.68,
            BucketType.question: 0.61,
        }
        cards = [
            {"bucket": "answer", "text": "Respond directly with one concrete next step.", "confidence": 0.52},
            {
                "bucket": "fact_check",
                "text": (
                    "Tighten how you state the key point—name one concrete anchor (time, number, or scope) "
                    "so listeners know exactly what you mean."
                ),
                "confidence": 0.35,
            },
            {"bucket": "talking_point", "text": "Highlight the most impactful unresolved tradeoff.", "confidence": 0.68},
            {"bucket": "question", "text": "Ask one specific question to remove the main ambiguity.", "confidence": 0.61},
        ]
        return RankAndDraftOutput(
            bucket_scores=scores,
            cards=cards,
            top_three=[BucketType.talking_point, BucketType.question, BucketType.answer],
            omitted_bucket=BucketType.fact_check,
            signal_state=SignalState.normal,
            metadata={"fallback": True},
        )


groq_client = GroqClient()
