import json
from pydantic import BaseModel, ValidationError


def parse_or_raise(raw_text: str, schema: type[BaseModel]) -> BaseModel:
    obj = json.loads(raw_text)
    return schema.model_validate(obj)


def try_parse_with_repair(raw_text: str, schema: type[BaseModel]) -> BaseModel | None:
    try:
        return parse_or_raise(raw_text, schema)
    except (json.JSONDecodeError, ValidationError):
        repaired = _repair_json_text(raw_text)
        if repaired is None:
            return None
        try:
            return parse_or_raise(repaired, schema)
        except (json.JSONDecodeError, ValidationError):
            return None


def _repair_json_text(raw_text: str) -> str | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return raw_text[start : end + 1]
