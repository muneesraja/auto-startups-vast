from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object. No markdown fences. Do not call tools.\n\n"
    "Story to adapt:\n\n{story_text}"
)

story_planner_agent = make_json_agent(
    name="story_planner_agent",
    prompt_name="story_planner",
    output_key="story_plan_content",
    extra_instruction=_JSON_RULE,
)
