"""JSON parsing helpers for LLM outputs."""
import json
import re

_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def clean_json_str(s):
    if not s:
        return {}
    s = s.strip()
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    start_idx = s.find("{")
    if start_idx == -1:
        start_idx = s.find("[")
    if start_idx == -1:
        raise json.JSONDecodeError("No JSON object found", s, 0)
    payload = s[start_idx:]
    try:
        obj, _end = json.JSONDecoder().raw_decode(payload)
        return obj
    except json.JSONDecodeError:
        fixed = _TRAILING_COMMA.sub(r"\1", payload)
        obj, _end = json.JSONDecoder().raw_decode(fixed)
        return obj


def get_namespace_dict(data, key):
    if not isinstance(data, dict):
        return {}
    if key in data:
        return data[key]
    return data
