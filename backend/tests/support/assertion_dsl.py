"""Subset of deep-research-test.md assertion DSL over refresh response dict."""

from __future__ import annotations

import re
from typing import Any


def _card_text_by_bucket(cards: list[dict[str, Any]], bucket: str) -> str:
    for c in cards:
        if c.get("bucket") == bucket:
            return str(c.get("text", ""))
    return ""


def evaluate(check: str, body: dict[str, Any]) -> bool:
    check = check.strip()
    scores: dict[str, float] = {k: float(v) for k, v in body.get("scores", {}).items()}
    cards = body.get("cards", [])
    omitted = body.get("omitted_bucket", "")
    signal = body.get("signal_state", "")

    m = re.match(r"^top3\[(\d)\]=='([^']+)'$", check)
    if m:
        idx = int(m.group(1))
        want = m.group(2)
        if idx >= len(cards):
            return False
        return cards[idx].get("bucket") == want

    m = re.match(r"^omitted=='([^']+)'$", check)
    if m:
        return omitted == m.group(1)

    m = re.match(r"^state=='([^']+)'$", check)
    if m:
        return signal == m.group(1)

    m = re.match(r"^scores\.(\w+)\s*([><=]+)\s*scores\.(\w+)$", check)
    if m:
        a, op, b = m.group(1), m.group(2), m.group(3)
        va, vb = scores.get(a), scores.get(b)
        if va is None or vb is None:
            return False
        return _cmp(va, op, vb)

    m = re.match(r"^scores\.(\w+)\s*([><=]+)\s*([0-9.]+)$", check)
    if m:
        a, op, num = m.group(1), m.group(2), float(m.group(3))
        va = scores.get(a)
        if va is None:
            return False
        return _cmp(va, op, num)

    m = re.match(r"^texts\.(\w+)\s*!~\s*/(.*)/$", check)
    if m:
        bucket, pat = m.group(1), m.group(2)
        text = _card_text_by_bucket(cards, bucket)
        return re.search(pat, text, re.I) is None

    m = re.match(r"^texts\.(\w+)\s*~\s*/(.*)/$", check)
    if m:
        bucket, pat = m.group(1), m.group(2)
        text = _card_text_by_bucket(cards, bucket)
        return re.search(pat, text, re.I) is not None

    raise ValueError(f"Unsupported assertion: {check}")


def _cmp(left: float, op: str, right: float) -> bool:
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == "==":
        return left == right
    raise ValueError(f"Unsupported operator: {op}")
