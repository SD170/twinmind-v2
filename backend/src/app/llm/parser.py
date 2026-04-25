import json
from pydantic import BaseModel, ValidationError


def parse_or_raise(raw_text: str, schema: type[BaseModel]) -> BaseModel:
    obj = json.loads(raw_text)
    return schema.model_validate(obj)


def try_parse_with_repair(raw_text: str, schema: type[BaseModel]) -> BaseModel | None:
    normalized = _strip_markdown_fence(raw_text)
    try:
        return parse_or_raise(normalized, schema)
    except (json.JSONDecodeError, ValidationError):
        repaired = _repair_json_text(normalized)
        if repaired is None:
            return None
        try:
            return parse_or_raise(repaired, schema)
        except (json.JSONDecodeError, ValidationError):
            return None


def diagnose_parse_failure(raw_text: str, schema: type[BaseModel]) -> str:
    """Human-readable reason LLM output did not validate (for logs)."""
    parts: list[str] = [f"raw_len={len(raw_text)}"]
    normalized = _strip_markdown_fence(raw_text)
    preview = normalized if len(normalized) <= 8000 else normalized[:8000] + "...(truncated)"
    parts.append(f"raw_preview={preview!r}")

    repaired = _repair_json_text(normalized)
    if repaired is None:
        parts.append("brace_slice_failed")
        return " | ".join(parts)

    try:
        obj = json.loads(repaired)
    except json.JSONDecodeError as exc:
        parts.append(f"json_error={exc!s}")
        return " | ".join(parts)

    try:
        schema.model_validate(obj)
        parts.append("unexpected: validates_after_repair_but_try_parse_failed")
        return " | ".join(parts)
    except ValidationError as exc:
        parts.append(f"pydantic_errors={exc.errors()}")
        return " | ".join(parts)


def _strip_markdown_fence(raw_text: str) -> str:
    t = raw_text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _repair_json_text(raw_text: str) -> str | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]
