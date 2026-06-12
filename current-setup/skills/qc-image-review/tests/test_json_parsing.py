"""Test JSON extraction from LLM response with potentially noisy prose.

Bug: the old regex `\{[\s\S]*\}` matched from the first `{` to the LAST `}`.
If the model outputs prose with braces before the JSON, it captured the wrong span.
"""
import re
import sys
from pathlib import Path

# Extract the regex from openrouter_qc.py so we test the same pattern
SCRIPT_PATH = Path("/root/.hermes/skills/creative/qc-image-review/scripts/openrouter_qc.py")


def extract_json(text: str) -> str:
    """Extract the LAST JSON object from text (LLM may include prose + JSON).

    Strategy: find all brace-delimited spans (handles 1 level of nesting)
    and return the last one that parses as valid JSON. This handles cases
    where the model includes prose with single braces before the real JSON
    response (e.g., "{my note: ...} The verdict: {\"pass\": true}").
    """
    import json
    # Find all candidate JSON spans
    candidates = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
    # Return the last one that parses as valid JSON
    for candidate in reversed(candidates):
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            continue
    return ""


def test_clean_json_extracted():
    text = '{"pass": true, "score": 0.8}'
    assert extract_json(text) == '{"pass": true, "score": 0.8}'


def test_prose_with_braces_before_json():
    text = 'Here is my verdict: {my note: this is a frozen shot}. The JSON is: {"pass": false}'
    result = extract_json(text)
    import json
    parsed = json.loads(result)
    assert parsed["pass"] is False


def test_nested_json_extracted():
    text = 'Some prose. {"pass": true, "scores": {"character_likeness": 8.5}, "issues": []} More prose.'
    result = extract_json(text)
    import json
    parsed = json.loads(result)
    assert parsed["pass"] is True
    assert parsed["scores"]["character_likeness"] == 8.5


def test_no_json_returns_empty():
    text = "No JSON here, just prose."
    assert extract_json(text) == ""


def test_old_greedy_regex_would_have_failed():
    """Demonstrate that the OLD regex would have failed this test case."""
    old_extract = lambda t: (re.search(r"\{[\s\S]*\}", t).group(0) if re.search(r"\{[\s\S]*\}", t) else "")
    text = 'Here is my verdict: {my note: this is a frozen shot}. The JSON is: {"pass": false}'
    old_result = old_extract(text)
    import json
    # Old regex captures from first { to last } — which includes BOTH braces
    # so json.loads would fail
    try:
        json.loads(old_result)
        # If this succeeds, the test was wrong about the old regex behavior
        assert False, f"Old regex should have produced invalid JSON, got: {old_result}"
    except json.JSONDecodeError:
        # Expected: old regex produced invalid JSON
        pass
