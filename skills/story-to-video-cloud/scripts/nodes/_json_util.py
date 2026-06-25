"""Reusable JSON parsing helper.

Wraps the legacy clean_json_str logic as a pure function. Calling sites use
parse_json_node to normalize LLM text outputs into python objects in state.
"""
import json
import re


_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)
_THOUGHT_PATTERN = re.compile(r"<thought>.*?</thought>", re.DOTALL)
# ponytail: trailing comma before } or ] is the #1 LLM JSON error
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _repair_json(s: str) -> dict:
    """Try progressively harder fixes on malformed JSON.

    Strategies (cheapest first):
    1. Strip trailing commas  (e.g.  {"a":1,} )
    2. Close unclosed braces/brackets at the end (truncated output)
    3. Truncate from the error position back to the last valid close

    Raises json.JSONDecodeError only if ALL strategies fail.
    """
    # --- Strategy 1: trailing commas ---
    fixed = _TRAILING_COMMA.sub(r"\1", s)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # --- Strategy 2: close unclosed braces/brackets (truncated output) ---
    # Count unmatched openers
    open_braces = fixed.count("{") - fixed.count("}")
    open_brackets = fixed.count("[") - fixed.count("]")
    if open_braces > 0 or open_brackets > 0:
        # Strip any trailing partial key/value (back to last , or { or [)
        trimmed = re.sub(r'[^,\[\]{}]*$', '', fixed).rstrip().rstrip(",")
        closers = "]" * max(open_brackets, 0) + "}" * max(open_braces, 0)
        try:
            return json.loads(trimmed + closers)
        except json.JSONDecodeError:
            pass

    # --- Strategy 3: truncate to last valid close ---
    # Walk backwards from the end to find a valid JSON prefix
    for i in range(len(fixed) - 1, max(len(fixed) - 500, 0), -1):
        if fixed[i] == '}':
            try:
                return json.loads(fixed[:i + 1])
            except json.JSONDecodeError:
                continue

    # Nothing worked — raise the original error for diagnostics
    return json.loads(s)


def clean_json_str(s):
    """Parse a possibly-malformed JSON string emitted by an LLM.

    - Strips leading/trailing whitespace.
    - Removes <think>...</think> and <thought>...</thought> blocks.
    - Strips ```json and ``` markdown code fences.
    - Extracts the substring between the first '{' and the last '}'.
    - Attempts repair for trailing commas, truncated output, etc.

    Raises:
        json.JSONDecodeError: if the cleaned string is not valid JSON
            even after repair attempts.

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

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        print("⚠️ [_json_util] json.loads failed, attempting repair…")
        return _repair_json(s)


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
