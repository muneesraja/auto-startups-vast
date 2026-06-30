import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object. No markdown fences. Do not call tools.\n\n"
    "Narrative outline JSON:\n\n{narrative_outline_content}"
)

ltx_shot_director_agent = make_json_agent(
    name="ltx_shot_director_agent",
    prompt_name="ltx_shot_director",
    output_key="story_plan_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_story_plan_model,
)
