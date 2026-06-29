import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object mapping shot_id to shot image spec. "
    "No markdown fences. Do not call tools.\n\n"
    "Story plan JSON:\n\n{story_plan_content}\n\n"
    "Scene assets JSON:\n\n{scene_assets_content}\n\n"
    "Audio plan JSON:\n\n{audio_plan_content}"
)

shot_reference_strategist_agent = make_json_agent(
    name="shot_reference_strategist_agent",
    prompt_name="shot_reference_strategist",
    output_key="shot_image_specs_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_light_model,
)
