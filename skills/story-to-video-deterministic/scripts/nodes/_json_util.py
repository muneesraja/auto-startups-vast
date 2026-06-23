"""Reusable JSON parsing helper.

Wraps the legacy clean_json_str logic as a pure function. Calling sites use
parse_json_node to normalize LLM text outputs into python objects in state.
"""
import json
import re


_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)
_THOUGHT_PATTERN = re.compile(r"<thought>.*?</thought>", re.DOTALL)


def clean_json_str(s):
    """Parse a possibly-malformed JSON string emitted by an LLM.

    - Strips leading/trailing whitespace.
    - Removes <think>...</think> and <thought>...</thought> blocks.
    - Strips ```json and ``` markdown code fences.
    - Extracts the substring between the first '{' and the last '}'.

    Raises:
        json.JSONDecodeError: if the cleaned string is not valid JSON.

    Returns:
        dict: the parsed JSON object. Returns {} if input is falsy.
    """
    if not s:
        return {}
    s = s.strip()
    s = _THINK_PATTERN.sub("", s).strip()
    s = _THOUGHT_PATTERN.sub("", s).strip()

    # Remove potential markdown block wrappers
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()

    # Robust extract: find first '{' and last '}'
    start_idx = s.find("{")
    end_idx = s.rfind("}")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        s = s[start_idx:end_idx + 1]

    return json.loads(s)


def get_namespace_dict(data, key):
    """Extract a namespaced sub-dict, e.g. {"character_sheets": {...}} -> {...}.

    If `data` is already a flat dict (no `key` wrapper), return it as-is.
    Returns {} for non-dict input.
    """
    if not isinstance(data, dict):
        return {}
    if key in data:
        return data[key]
    return data
