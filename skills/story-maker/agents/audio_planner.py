import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON audio plan. No markdown fences. Do not call tools.\n\n"
    "Story plan JSON:\n\n{story_plan_content}"
)

audio_planner_agent = make_json_agent(
    name="audio_planner_agent",
    prompt_name="audio_planner",
    output_key="audio_plan_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_light_model,
)
