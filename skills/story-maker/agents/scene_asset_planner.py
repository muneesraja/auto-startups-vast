import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON scene assets plan. No markdown fences. Do not call tools.\n\n"
    "Story plan JSON:\n\n{story_plan_content}\n\n"
    "Audio plan JSON:\n\n{audio_plan_content}"
)

scene_asset_planner_agent = make_json_agent(
    name="scene_asset_planner_agent",
    prompt_name="scene_asset_planner",
    output_key="scene_assets_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_light_model,
)
