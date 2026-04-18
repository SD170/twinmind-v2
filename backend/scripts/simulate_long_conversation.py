#!/usr/bin/env python3
"""
Long-running E2E: multi-agent asyncio simulation + strict checks on every API touch.

Covers:
  - GET /health, GET /ready
  - GET/PUT /api/v1/settings (round-trip, restores prior settings)
  - POST /api/v1/suggestions/refresh (many rounds; validates body shape)
  - POST /api/v1/suggestions/expand (cycles through all 3 visible cards)
  - POST /api/v1/export (json + text)

Agents (asyncio tasks):
  - user_voice, ambient_voice → coordinator drains into refresh payloads.

Usage:
  cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
  .venv/bin/python scripts/simulate_long_conversation.py --base-url http://127.0.0.1:8000 --refreshes 50 --strict
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class MeetingState:
    session_id: str
    pending_user: list[dict] = field(default_factory=list)
    pending_ambient: list[dict] = field(default_factory=list)
    turn_seq: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def next_id(self, prefix: str) -> str:
        self.turn_seq += 1
        return f"{prefix}{self.turn_seq}"


def _user_line(i: int) -> str:
    topics = [
        "Let's align on SLOs before we talk about autoscaling.",
        "I'm worried about tail latency during the marketing push next week.",
        "What was the failure mode when Slack had that routing incident in 2024?",
        "If we tighten rate limits, do we have a rollback story for enterprise tenants?",
        "I want one clean sentence for why we changed the proxy tier.",
        "Should we mention blast radius in the exec summary or keep it technical?",
        "Are we confident the cache layer won't become the new bottleneck?",
        "I'll own the postmortem template unless someone else wants it.",
        "Can we separate control-plane risk from demand saturation in the narrative?",
        "What's the smallest experiment we can run Friday to validate this?",
    ]
    return topics[i % len(topics)] + f" (beat {i})"


def _ambient_line(i: int) -> str:
    topics = [
        "Agreed — we should pair SLOs with error budget policy before autoscaling.",
        "Marketing push is Tuesday; we can stage a canary on Monday night.",
        "There were multiple Slack incidents in 2024; which month do you mean?",
        "Rollback is staged; we still need an owner for exception approvals.",
        "Proxy tier change was about reducing failure blast radius under peak.",
        "Exec summary should lead with customer impact, then technical mechanism.",
        "Cache hit rate is healthy; watch hot keys on the new feature flag.",
        "I'll take the postmortem template if you drive the timeline section.",
        "Yes — treat routing changes separately from pure capacity exhaustion.",
        "Friday experiment: shadow traffic 5% with guardrails and automatic abort.",
    ]
    return topics[i % len(topics)] + f" [room {i}]"


def _assert_refresh(body: dict[str, Any], round_idx: int) -> None:
    assert len(body.get("cards", [])) == 3, f"r{round_idx}: expected 3 cards"
    buckets = {c["bucket"] for c in body["cards"]}
    assert len(buckets) == 3, f"r{round_idx}: duplicate buckets {buckets}"
    assert body.get("omitted_bucket") in {
        "answer",
        "fact_check",
        "talking_point",
        "question",
    }, f"r{round_idx}: bad omitted {body.get('omitted_bucket')}"
    scores = body.get("scores") or {}
    assert set(scores.keys()) == {"answer", "fact_check", "talking_point", "question"}, f"r{round_idx}: scores {scores}"
    assert body.get("signal_state") in {"weak", "normal", "urgent"}
    assert body.get("batch_key"), f"r{round_idx}: missing batch_key"
    for c in body["cards"]:
        assert c.get("text"), f"r{round_idx}: empty card text"
        assert 0.0 <= float(c.get("confidence", -1)) <= 1.0


def _assert_expand(body: dict[str, Any], round_idx: int, card_idx: int) -> None:
    assert body.get("expanded_text"), f"r{round_idx} expand[{card_idx}]: no expanded_text"
    assert body.get("bucket") in {"answer", "fact_check", "talking_point", "question"}


def _assert_export_json(content: dict[str, Any], session_id: str, min_transcript: int) -> None:
    assert content.get("session_id") == session_id
    tr = content.get("transcript") or []
    assert len(tr) >= min_transcript, (
        f"export: transcript len {len(tr)} < {min_transcript} (expected accumulated turns)"
    )
    batches = content.get("suggestion_batches") or []
    assert batches, "export: no suggestion_batches"
    chat = content.get("chat_history") or []
    assert isinstance(chat, list), "export: chat_history not list"


async def user_voice(state: MeetingState, stop: asyncio.Event, max_lines: int, pause_s: float) -> None:
    for i in range(max_lines):
        if stop.is_set():
            return
        await asyncio.sleep(pause_s * random.uniform(0.7, 1.3))
        if stop.is_set():
            return
        t_ms = 30_000 * (i + 1)
        async with state.lock:
            if stop.is_set():
                return
            state.pending_user.append(
                {
                    "id": state.next_id("u"),
                    "text": _user_line(i),
                    "start_ms": t_ms,
                    "end_ms": t_ms + 4000,
                }
            )


async def ambient_voice(state: MeetingState, stop: asyncio.Event, max_lines: int, pause_s: float) -> None:
    for i in range(max_lines):
        if stop.is_set():
            return
        await asyncio.sleep(pause_s * random.uniform(0.8, 1.4))
        if stop.is_set():
            return
        t_ms = 30_000 * (i + 1) + 5_000
        async with state.lock:
            if stop.is_set():
                return
            state.pending_ambient.append(
                {
                    "id": state.next_id("a"),
                    "text": _ambient_line(i),
                    "start_ms": t_ms,
                    "end_ms": t_ms + 4500,
                    "confidence": round(random.uniform(0.55, 0.95), 2),
                }
            )


def _fact_source_payload() -> list[dict[str, Any]]:
    return [
        {
            "source_id": "e2e-src1",
            "type": "approved_cached_note",
            "title": "Jan 2024 routing incident (excerpt)",
            "content": "A routing change caused requests to fail due to lack of available resources.",
            "uri": "internal://incidents/jan-2024",
        }
    ]


async def coordinator(
    client: httpx.AsyncClient,
    base: str,
    state: MeetingState,
    stop: asyncio.Event,
    target_refreshes: int,
    poll_s: float,
    strict: bool,
    verbose: bool,
) -> dict[str, Any]:
    log = logging.getLogger("simulate_e2e")
    stats: dict[str, Any] = {
        "refreshes_ok": 0,
        "refreshes_409": 0,
        "refreshes_err": 0,
        "expands_ok": 0,
        "expand_err": 0,
        "latency_ms": [],
        "errors": [],
    }
    done = 0
    while done < target_refreshes:
        await asyncio.sleep(poll_s)
        async with state.lock:
            if not state.pending_user and not state.pending_ambient:
                continue
            use_evidence = done % 10 == 3 and done > 0
            payload: dict[str, Any] = {
                "session_id": state.session_id,
                "recent_user_turns": list(state.pending_user),
                "recent_ambient_turns": list(state.pending_ambient),
                "force_refresh": True,
                "source_policy": {
                    "enable_conditional_web": False,
                    "approved_sources": [],
                    "approved_fact_sources": _fact_source_payload() if use_evidence else [],
                },
            }
            state.pending_user.clear()
            state.pending_ambient.clear()
        t0 = time.perf_counter()
        try:
            r = await client.post(f"{base}/api/v1/suggestions/refresh", json=payload, timeout=180.0)
        except Exception as e:  # noqa: BLE001
            stats["errors"].append(f"refresh transport: {e}")
            if strict:
                raise
            done += 1
            continue
        dt = int((time.perf_counter() - t0) * 1000)
        stats["latency_ms"].append(dt)
        if r.status_code == 200:
            stats["refreshes_ok"] += 1
            body = r.json()
            if verbose:
                msg = (
                    f"refresh ok round={done} batch_key={body.get('batch_key')} "
                    f"top3={[c['bucket'] for c in body.get('cards', [])]} "
                    f"omitted={body.get('omitted_bucket')} ms={dt}"
                )
                log.info(msg)
                print(msg, flush=True)
            try:
                if strict:
                    _assert_refresh(body, done)
            except AssertionError as e:
                stats["errors"].append(str(e))
                if strict:
                    raise
            if done % 5 == 0:
                for ci, card in enumerate(body.get("cards") or []):
                    try:
                        ex = await client.post(
                            f"{base}/api/v1/suggestions/expand",
                            json={"session_id": state.session_id, "clicked_card": card},
                            timeout=180.0,
                        )
                        if ex.status_code == 200:
                            stats["expands_ok"] += 1
                            if verbose:
                                em = f"expand ok round={done} card={ci} bucket={card.get('bucket')}"
                                log.info(em)
                                print(em, flush=True)
                            if strict:
                                _assert_expand(ex.json(), done, ci)
                        else:
                            stats["expand_err"] += 1
                            stats["errors"].append(f"expand {ci} HTTP {ex.status_code} {ex.text[:200]}")
                            if strict:
                                raise RuntimeError(stats["errors"][-1])
                    except AssertionError:
                        raise
                    except Exception as e:  # noqa: BLE001
                        stats["expand_err"] += 1
                        stats["errors"].append(f"expand {ci}: {e}")
                        if strict:
                            raise
        elif r.status_code == 409:
            stats["refreshes_409"] += 1
        else:
            stats["refreshes_err"] += 1
            stats["errors"].append(f"refresh HTTP {r.status_code} {r.text[:300]}")
            if strict:
                raise RuntimeError(stats["errors"][-1])
        done += 1

    # Mid-session already has data; final export both formats
    ex_json = await client.post(
        f"{base}/api/v1/export",
        json={"session_id": state.session_id, "format": "json"},
        timeout=120.0,
    )
    stats["export_json_status"] = ex_json.status_code
    if ex_json.status_code == 200:
        outer = ex_json.json()
        content = outer.get("content")
        if isinstance(content, dict) and strict:
            min_tr = max(20, target_refreshes)
            _assert_export_json(content, state.session_id, min_tr)
        stats["export_json_batches"] = (
            len(content.get("suggestion_batches", [])) if isinstance(content, dict) else 0
        )
        stats["export_json_chat_len"] = len(content.get("chat_history", [])) if isinstance(content, dict) else 0
    else:
        stats["errors"].append(f"export json {ex_json.status_code} {ex_json.text[:200]}")
        if strict:
            raise RuntimeError(stats["errors"][-1])

    ex_txt = await client.post(
        f"{base}/api/v1/export",
        json={"session_id": state.session_id, "format": "text"},
        timeout=120.0,
    )
    stats["export_text_status"] = ex_txt.status_code
    if ex_txt.status_code == 200:
        txt = ex_txt.json().get("content")
        stats["export_text_chars"] = len(txt) if isinstance(txt, str) else 0
        if strict and stats["export_text_chars"] < 100:
            raise RuntimeError("export text too small")
    else:
        stats["errors"].append(f"export text {ex_txt.status_code}")
        if strict:
            raise RuntimeError(stats["errors"][-1])

    stop.set()
    return stats


async def preflight(client: httpx.AsyncClient, base: str, strict: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    h = await client.get(f"{base}/health", timeout=15.0)
    out["health"] = h.status_code
    rd = await client.get(f"{base}/ready", timeout=15.0)
    out["ready"] = rd.status_code
    if strict:
        h.raise_for_status()
        rd.raise_for_status()

    g = await client.get(f"{base}/api/v1/settings", timeout=15.0)
    g.raise_for_status()
    envelope = g.json()
    out["settings_version_before"] = envelope.get("version")
    saved = envelope["settings"]
    bump = saved.copy()
    bump["context_window_turns"] = min(80, int(saved.get("context_window_turns", 12)) + 1)
    p = await client.put(f"{base}/api/v1/settings", json=bump, timeout=15.0)
    p.raise_for_status()
    out["settings_put"] = p.status_code
    g2 = await client.get(f"{base}/api/v1/settings", timeout=15.0)
    g2.raise_for_status()
    assert g2.json()["settings"]["context_window_turns"] == bump["context_window_turns"]
    restore = await client.put(f"{base}/api/v1/settings", json=saved, timeout=15.0)
    restore.raise_for_status()
    out["settings_restored"] = True
    return out


async def run_sim(base: str, refreshes: int, strict: bool, verbose: bool) -> dict[str, Any]:
    session_id = f"longrun-{uuid.uuid4().hex[:12]}"
    state = MeetingState(session_id=session_id)
    stop = asyncio.Event()
    max_voice_lines = refreshes * 4 + 30

    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            force=True,
        )
        print(f"[e2e] session_id={session_id} refreshes={refreshes} strict={strict}", flush=True)

    async with httpx.AsyncClient() as client:
        pre = await preflight(client, base, strict=strict)
        if verbose:
            print(f"[e2e] preflight={pre}", flush=True)
        t0 = time.perf_counter()
        stats = await asyncio.gather(
            user_voice(state, stop, max_voice_lines, pause_s=0.045),
            ambient_voice(state, stop, max_voice_lines, pause_s=0.05),
            coordinator(
                client, base, state, stop, refreshes, poll_s=0.035, strict=strict, verbose=verbose
            ),
        )
        elapsed = time.perf_counter() - t0
        coord_stats = stats[2]

    lat = coord_stats.get("latency_ms") or [0]
    lat_sorted = sorted(lat)
    p50 = lat_sorted[len(lat_sorted) // 2] if lat_sorted else 0
    p95 = lat_sorted[max(0, int(len(lat_sorted) * 0.95) - 1)] if lat_sorted else 0
    report = {
        "session_id": session_id,
        "elapsed_s": round(elapsed, 2),
        "preflight": pre,
        **coord_stats,
        "latency_p50_ms": p50,
        "latency_p95_ms": p95,
    }
    if strict and coord_stats.get("errors"):
        report["strict_failed"] = True
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--refreshes", type=int, default=50)
    ap.add_argument("--strict", action="store_true", help="Assert all responses; exit 1 on failure")
    ap.add_argument("--verbose", "-v", action="store_true", help="Print per-round progress to stdout")
    args = ap.parse_args()
    try:
        report = asyncio.run(
            run_sim(args.base_url.rstrip("/"), args.refreshes, args.strict, args.verbose)
        )
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        sys.exit(1)
    ok = not report.get("strict_failed") and report.get("refreshes_err", 0) == 0 and report.get("expand_err", 0) == 0
    print(json.dumps({"ok": ok, **report}, indent=2))
    if args.strict and not ok:
        sys.exit(1)
    if report.get("errors"):
        sys.exit(1)


if __name__ == "__main__":
    main()
