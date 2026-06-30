from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object. No markdown fences. Do not call tools.\n\n"
    "Target duration: {target_duration_seconds} seconds "
    "(tolerance ±{duration_tolerance_percent}%).\n\n"
    "Story to expand:\n\n{story_text}"
)

narrative_expander_agent = make_json_agent(
    name="narrative_expander_agent",
    prompt_name="narrative_expander",
    output_key="narrative_outline_content",
    extra_instruction=_JSON_RULE,
)
