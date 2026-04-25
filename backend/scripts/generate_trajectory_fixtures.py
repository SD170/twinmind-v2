#!/usr/bin/env python3
"""Emit tests/fixtures/trajectory_sessions.json from deep-research-test.md spec."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "trajectory_sessions.json"


def turn(tid: str, text: str, start_ms: int = 0, end_ms: int = 0) -> dict:
    return {"id": tid, "text": text, "start_ms": start_ms, "end_ms": end_ms}


def src(sid: str, title: str, content: str) -> dict:
    return {
        "source_id": sid,
        "type": "approved_cached_note",
        "title": title,
        "content": content,
        "uri": "unspecified",
    }


def batch(
    bid: str,
    ts: int,
    user: list[dict],
    topic: str,
    history: list[dict],
    approved: list[dict],
    web: bool = False,
) -> dict:
    return {
        "batch_id": bid,
        "timestamp_ms": ts,
        "request": {
            "session_id": "__SESSION_ID__",
            "recent_user_turns": user,
            "force_refresh": True,
            "source_policy": {
                "enable_conditional_web": web,
                "approved_sources": [],
                "approved_fact_sources": approved,
            },
        },
        "rolling_topic_summary": topic,
        "suggestion_history": history,
    }


def sessions() -> list[dict]:
    """Trajectory sessions S01–S16 aligned with deep-research-test.md."""
    out: list[dict] = []

    def add(sid: str, desc: str, batches: list[dict], **kw) -> None:
        out.append({"session_id": sid, "description": desc, "batches": batches, **kw})

    # S01
    add(
        "S01_explicit_user_question_answer",
        "Normal self-question. Answer should rank first.",
        [
            batch(
                "b1",
                30000,
                [
                    turn(
                        "u1",
                        "We can cut retries, but what should we do about API capacity next quarter?",
                    )
                ],
                "Capacity planning and load growth.",
                [],
                [],
                web=False,
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.88, "fact_check": 0.10, "talking_point": 0.56, "question": 0.42}
        },
        expected_display_order={"b1": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "urgent"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'I would size for peak plus headroom and validate with load tests.'",
                "fact_check": "unspecified",
                "talking_point": "Call out headroom targets and load-testing before launch.",
                "question": "Which service is driving the growth estimate?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "scores.answer > scores.talking_point"},
            {"batch_id": "b1", "check": "top3[0]=='answer'"},
            {"batch_id": "b1", "check": "omitted=='fact_check'"},
        ],
    )

    # S02
    add(
        "S02_inferred_reply_obligation",
        "Reply obligation inferred from user turn shape (no separate room track).",
        [
            batch(
                "b1",
                60000,
                [
                    turn(
                        "u1",
                        "Right, but if the proxy rollout fails again we need a back-out plan.",
                    )
                ],
                "Comparing capacity risk with rollout risk.",
                [],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.74, "fact_check": 0.21, "talking_point": 0.63, "question": 0.33}
        },
        expected_display_order={"b1": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'I see rollout risk as separate from capacity, so I'd add a staged back-out plan.'",
                "fact_check": "unspecified",
                "talking_point": "Stress rollback drills and staged rollout gates.",
                "question": "Which step needs a tested back-out path first?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "top3[0]=='answer'"},
            {"batch_id": "b1", "check": "scores.answer > scores.talking_point"},
        ],
    )

    # S03
    add(
        "S03_repair_disambiguation_question",
        "Repair and clarification. Question should outrank answer.",
        [
            batch(
                "b1",
                90000,
                [
                    turn(
                        "u1",
                        "Wait, which incident are we talking about exactly — the January routing issue or the March database one?",
                    )
                ],
                "Outage comparison with under-specified incident reference.",
                [],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.54, "fact_check": 0.29, "talking_point": 0.40, "question": 0.84}
        },
        expected_display_order={"b1": {"top3": ["question", "answer", "talking_point"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "urgent"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'If you mean January, the failure mode was different from capacity.'",
                "fact_check": "unspecified",
                "talking_point": "Separate incident type from mitigation pattern.",
                "question": "Do you mean the January routing incident or the March database incident?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "scores.question > scores.answer"},
            {"batch_id": "b1", "check": "top3[0]=='question'"},
        ],
    )

    # S04
    add(
        "S04_topic_drift_talking_point",
        "Talking point ranks one when no direct question.",
        [
            batch(
                "b1",
                120000,
                [
                    turn(
                        "u1",
                        "We've talked about retries for ten minutes. I still want to mention blast radius and rollback.",
                    )
                ],
                "Retries dominate; rollback and blast radius remain unresolved.",
                [],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.22, "fact_check": 0.18, "talking_point": 0.82, "question": 0.38}
        },
        expected_display_order={"b1": {"top3": ["talking_point", "question", "answer"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'Retries help, but rollback and blast radius still need decisions.'",
                "fact_check": "unspecified",
                "talking_point": "Bring up blast radius reduction and rollback readiness.",
                "question": "Which failure would cause the widest customer impact?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "top3[0]=='talking_point'"},
            {"batch_id": "b1", "check": "scores.talking_point >= 0.75"},
        ],
    )

    # S05
    add(
        "S05_late_join_rolling_memory",
        "Late-join catch-up; answer uses rolling memory.",
        [
            batch(
                "b1",
                540000,
                [
                    turn(
                        "u1",
                        "I joined late — where are we landing on rate limits and rollback?",
                    )
                ],
                "Earlier discussion converged on tighter rate limits, staged rollout, and explicit rollback drills; unresolved owner for final threshold.",
                [{"bucket": "talking_point", "text": "Mention blast radius before retry tuning."}],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.85, "fact_check": 0.14, "talking_point": 0.59, "question": 0.31}
        },
        expected_display_order={"b1": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "urgent"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'We're leaning towards tighter rate limits, staged rollout, and rollback drills; the final threshold owner is still open.'",
                "fact_check": "unspecified",
                "talking_point": "Mention the open owner for the final threshold.",
                "question": "Who will own the final threshold decision?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "top3[0]=='answer'"},
        ],
    )

    # S06
    add(
        "S06_fact_check_with_approved_source",
        "Strong fact-check with approved evidence.",
        [
            batch(
                "b1",
                150000,
                [
                    turn(
                        "u1",
                        "I want to avoid the Slack outage pattern; that was just capacity, right?",
                    )
                ],
                "User is comparing current API risk to a vendor outage.",
                [],
                [
                    src(
                        "src1",
                        "Vendor incident excerpt Jan 2024",
                        "A routing change caused requests to fail due to lack of available resources.",
                    )
                ],
                web=False,
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.67, "fact_check": 0.90, "talking_point": 0.41, "question": 0.48}
        },
        expected_display_order={"b1": {"top3": ["fact_check", "answer", "question"], "omitted": "talking_point"}},
        expected_signal_state={"b1": "urgent"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'That example was closer to a routing-change failure than pure capacity.'",
                "fact_check": "Slack Jan 2024 was tied to a routing change causing resource failures, not pure capacity.",
                "talking_point": "Separate control-plane failure from demand saturation.",
                "question": "Do we mean the January routing incident specifically?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "top3[0]=='fact_check'"},
        ],
    )

    # S07
    add(
        "S07_fact_check_omitted_without_evidence",
        "No approved evidence; fact-check omitted.",
        [
            batch(
                "b1",
                180000,
                [
                    turn(
                        "u1",
                        "I want to avoid the Slack outage pattern; that was just capacity, right?",
                    )
                ],
                "User is comparing current API risk to a vendor outage.",
                [],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.71, "fact_check": 0.22, "talking_point": 0.45, "question": 0.58}
        },
        expected_display_order={"b1": {"top3": ["answer", "question", "talking_point"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'I want to avoid that failure pattern, but I'd verify which incident we mean first.'",
                "fact_check": "unspecified",
                "talking_point": "Separate demand limits from rollout safeguards.",
                "question": "Which outage are we using as the comparison?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "omitted=='fact_check'"},
            {"batch_id": "b1", "check": "scores.fact_check < 0.40"},
        ],
    )

    # S08
    add(
        "S08_ambiguous_incident_reference",
        "Conflicting sources; question outranks.",
        [
            batch(
                "b1",
                210000,
                [
                    turn(
                        "u1",
                        "What was the failure mode when Slack went down last year? I want to avoid that pattern.",
                    )
                ],
                "User wants lessons from vendor outage; year reference ambiguous.",
                [],
                [
                    src(
                        "src1",
                        "Incident excerpt Jan 2024",
                        "A routing change caused requests to fail due to lack of available resources.",
                    ),
                    src(
                        "src2",
                        "Incident excerpt Mar 2024",
                        "A routine infrastructure process increased requests to an affected database.",
                    ),
                ],
                web=False,
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.70, "fact_check": 0.34, "talking_point": 0.39, "question": 0.83}
        },
        expected_display_order={"b1": {"top3": ["question", "answer", "talking_point"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "urgent"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'That depends on which 2024 incident you mean.'",
                "fact_check": "unspecified",
                "talking_point": "Frame the lesson as avoiding both rollout and dependency hot-spot failures.",
                "question": "Do you mean the January routing incident or the March database-load incident?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "top3[0]=='question'"},
            {"batch_id": "b1", "check": "omitted=='fact_check'"},
        ],
    )

    # S09
    add(
        "S09_privacy_sensitive_redaction",
        "Privacy-sensitive content redacted in cards.",
        [
            batch(
                "b1",
                240000,
                [
                    turn(
                        "u1",
                        "Should I mention Alice's diagnosis and customer ACME's outage in the recap?",
                    )
                ],
                "User is drafting a recap with personal and customer-identifying details.",
                [],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.52, "fact_check": 0.12, "talking_point": 0.63, "question": 0.69}
        },
        expected_display_order={"b1": {"top3": ["question", "talking_point", "answer"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'I'll keep personal and customer-identifying details out of the recap.'",
                "fact_check": "unspecified",
                "talking_point": "Use roles, incident IDs, and impact labels instead of names.",
                "question": "Can we redact health details and customer identifiers first?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "texts.answer !~ /Alice|ACME/"},
        ],
    )

    # S10 two batches
    add(
        "S10_repeated_suggestion_suppression",
        "Second batch avoids near-duplicate cards.",
        [
            batch(
                "b1",
                30000,
                [turn("u1", "What should I say about capacity during launch week?")],
                "Launch-week capacity planning.",
                [],
                [],
            ),
            batch(
                "b2",
                60000,
                [turn("u2", "And I also want one point on rollout safety.")],
                "Capacity plus rollout safety.",
                [
                    {"bucket": "answer", "text": "Say: 'We'll size for peak and validate with load tests.'"},
                    {"bucket": "talking_point", "text": "Call out headroom targets and load-testing before launch."},
                ],
                [],
            ),
        ],
        expected_router_scores={
            "b1": {"answer": 0.84, "fact_check": 0.07, "talking_point": 0.55, "question": 0.31},
            "b2": {"answer": 0.41, "fact_check": 0.10, "talking_point": 0.77, "question": 0.55},
        },
        expected_display_order={
            "b1": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"},
            "b2": {"top3": ["talking_point", "question", "answer"], "omitted": "fact_check"},
        },
        expected_signal_state={"b1": "urgent", "b2": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'We'll size for peak and validate with load tests.'",
                "fact_check": "unspecified",
                "talking_point": "Call out headroom targets and load-testing before launch.",
                "question": "Which service is the main launch risk?",
            },
            "b2": {
                "answer": "Say: 'I also want rollout guardrails, not just capacity.'",
                "fact_check": "unspecified",
                "talking_point": "Add staged rollout gates and a tested back-out path.",
                "question": "Which rollout step has the highest rollback cost?",
            },
        },
        verifiable_assertions=[
            {"batch_id": "b2", "check": "top3[0]=='talking_point'"},
        ],
    )

    # S11
    add(
        "S11_noisy_asr_weak_signal",
        "Noisy ASR lowers assertiveness.",
        [
            batch(
                "b1",
                270000,
                [turn("u1", "uh we should maybe cache cap city? not sure")],
                "Noisy utterance; likely discussing cache or API capacity.",
                [],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.28, "fact_check": 0.08, "talking_point": 0.34, "question": 0.36}
        },
        expected_display_order={"b1": {"top3": ["question", "talking_point", "answer"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "weak"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'I may be mixing cache and API capacity here.'",
                "fact_check": "unspecified",
                "talking_point": "If this is about capacity, keep the point narrow and provisional.",
                "question": "Do you mean cache capacity or API capacity?",
            }
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "state=='weak'"},
        ],
    )

    # S12
    add(
        "S12_rapid_fire_turns_timing",
        "Rapid-fire turns; answer timing tolerance.",
        [
            batch(
                "b1",
                300000,
                [turn("u1", "If they ask why we changed the proxy tier...")],
                "User is starting to formulate a reply.",
                [],
                [],
            ),
            batch(
                "b2",
                305000,
                [
                    turn(
                        "u2",
                        "If they ask why we changed the proxy tier, I want one clean sentence.",
                    )
                ],
                "User wants concise justification for proxy-tier change.",
                [],
                [],
            ),
        ],
        expected_router_scores={
            "b1": {"answer": 0.61, "fact_check": 0.09, "talking_point": 0.44, "question": 0.25},
            "b2": {"answer": 0.89, "fact_check": 0.10, "talking_point": 0.46, "question": 0.22},
        },
        expected_display_order={
            "b1": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"},
            "b2": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"},
        },
        expected_signal_state={"b1": "normal", "b2": "urgent"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'We changed tiers to reduce failure risk under peak load.'",
                "fact_check": "unspecified",
                "talking_point": "Pair the change with rollback and observability.",
                "question": "Which peak pattern justified the change?",
            },
            "b2": {
                "answer": "Say: 'We changed tiers to cut risk at peak and keep rollback simple.'",
                "fact_check": "unspecified",
                "talking_point": "Mention reduced blast radius and easier rollback.",
                "question": "Which metric best shows the benefit?",
            },
        },
        verifiable_assertions=[],
    )

    # S13 — orchestration doc only; mark in JSON
    add(
        "S13_manual_refresh_stale_response",
        "Manual refresh supersedes older auto refresh (harness-level).",
        [
            batch(
                "b1",
                330000,
                [turn("u1", "What should I say about rate limits?")],
                "User wants a rate-limit framing.",
                [],
                [],
            ),
            batch(
                "b2",
                334000,
                [turn("u2", "Actually make that rate limits plus rollback.")],
                "Rate limits plus rollback.",
                [],
                [],
            ),
        ],
        expected_router_scores={
            "b1": {"answer": 0.82, "fact_check": 0.07, "talking_point": 0.46, "question": 0.21},
            "b2": {"answer": 0.58, "fact_check": 0.09, "talking_point": 0.78, "question": 0.33},
        },
        expected_display_order={
            "b1": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"},
            "b2": {"top3": ["talking_point", "answer", "question"], "omitted": "fact_check"},
        },
        expected_signal_state={"b1": "urgent", "b2": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'We'll tighten rate limits to protect peak stability.'",
                "fact_check": "unspecified",
                "talking_point": "Connect limits to graceful degradation.",
                "question": "Which clients need exceptions?",
            },
            "b2": {
                "answer": "Say: 'We'll tighten rate limits and keep rollback simple.'",
                "fact_check": "unspecified",
                "talking_point": "Pair limits with rollback criteria and owner handoff.",
                "question": "Who owns rollback approval?",
            },
        },
        test_injections={
            "requests": [
                {"request_id": "r1", "kind": "auto", "batch_id": "b1", "delay_ms": 900},
                {"request_id": "r2", "kind": "manual", "batch_id": "b2", "delay_ms": 120},
            ]
        },
        harness_only=True,
    )

    # S14
    add(
        "S14_json_parse_failure_fallback",
        "Invalid JSON twice; fallback must render UI.",
        [
            batch(
                "b1",
                360000,
                [turn("u1", "What should I say if they ask whether we tested rollback?")],
                "Rollback testing answer needed.",
                [{"bucket": "talking_point", "text": "Mention rollback drills before launch."}],
                [],
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.80, "fact_check": 0.06, "talking_point": 0.49, "question": 0.24}
        },
        expected_display_order={"b1": {"top3": ["answer", "talking_point", "question"], "omitted": "fact_check"}},
        expected_signal_state={"b1": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'Yes, we tested rollback with staged drills and a clear back-out path.'",
                "fact_check": "unspecified",
                "talking_point": "Reference staged drills rather than generic readiness.",
                "question": "Which rollback drill matters most to mention?",
            }
        },
        test_injections={
            "simulate_router_invalid_json": True,
            "simulate_retry_invalid_json": True,
            "fallback_mode": "local_heuristic",
        },
        harness_only=True,
    )

    # S15
    add(
        "S15_optional_fact_verify_latency",
        "Fact-verify latency budget (harness-level).",
        [
            batch(
                "b1",
                390000,
                [turn("u1", "Was that Jan 2024 outage just a capacity problem?")],
                "User asks about cause of known incident.",
                [],
                [
                    src(
                        "src1",
                        "Incident excerpt Jan 2024",
                        "A routing change caused requests to fail due to lack of available resources.",
                    )
                ],
                web=False,
            )
        ],
        expected_router_scores={
            "b1": {"answer": 0.63, "fact_check": 0.81, "talking_point": 0.36, "question": 0.44}
        },
        expected_display_order={"b1": {"top3": ["fact_check", "answer", "question"], "omitted": "talking_point"}},
        expected_signal_state={"b1": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'It looks closer to a routing-change failure than pure capacity.'",
                "fact_check": "If you mean Jan 2024, treat it as a routing-change/resource issue rather than pure capacity.",
                "talking_point": "Separate demand spikes from control-plane changes.",
                "question": "Are we definitely talking about the January incident?",
            }
        },
        test_injections={"simulate_fact_verify_delay_ms": 1800, "latency_budget_ms": 600},
        harness_only=True,
    )

    # S16
    add(
        "S16_threshold_caps",
        "Evidence caps without sources; talking point default.",
        [
            batch(
                "b1",
                420000,
                [turn("u1", "The outage was definitely caused by DNS.")],
                "Bare factual assertion with no approved evidence.",
                [],
                [],
            ),
            batch(
                "b2",
                450000,
                [turn("u2", "Another thing is rollback drills.")],
                "Topic addition with no direct question.",
                [],
                [],
            ),
        ],
        expected_router_scores={
            "b1": {"answer": 0.41, "fact_check": 0.34, "talking_point": 0.58, "question": 0.49},
            "b2": {"answer": 0.37, "fact_check": 0.09, "talking_point": 0.79, "question": 0.44},
        },
        expected_display_order={
            "b1": {"top3": ["talking_point", "question", "answer"], "omitted": "fact_check"},
            "b2": {"top3": ["talking_point", "question", "answer"], "omitted": "fact_check"},
        },
        expected_signal_state={"b1": "normal", "b2": "normal"},
        expected_card_texts={
            "b1": {
                "answer": "Say: 'I'd verify the root cause before using DNS as the analogy.'",
                "fact_check": "unspecified",
                "talking_point": "Avoid anchoring on one root cause without evidence.",
                "question": "Which incident record supports DNS as the cause?",
            },
            "b2": {
                "answer": "unspecified",
                "fact_check": "unspecified",
                "talking_point": "Raise rollback drills as a separate readiness item.",
                "question": "Which rollback drill is still untested?",
            },
        },
        verifiable_assertions=[
            {"batch_id": "b1", "check": "scores.fact_check <= 0.40"},
            {"batch_id": "b1", "check": "omitted=='fact_check'"},
            {"batch_id": "b2", "check": "scores.answer <= 0.40"},
            {"batch_id": "b2", "check": "top3[0]=='talking_point'"},
        ],
    )

    return out


def main() -> None:
    data = sessions()
    for session in data:
        sid = session["session_id"]
        for batch in session["batches"]:
            req = batch["request"]
            req["session_id"] = sid
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"sessions": data}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
