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
    end_idx = s.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        s = s[start_idx : end_idx + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        fixed = _TRAILING_COMMA.sub(r"\1", s)
        return json.loads(fixed)


def get_namespace_dict(data, key):
    if not isinstance(data, dict):
        return {}
    if key in data:
        return data[key]
    return data
