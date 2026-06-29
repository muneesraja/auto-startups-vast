import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object mapping shot_id to motion spec. "
    "No markdown fences. Do not call tools.\n\n"
    "Story plan JSON:\n\n{story_plan_content}\n\n"
    "Audio plan JSON:\n\n{audio_plan_content}"
)

motion_prompter_agent = make_json_agent(
    name="motion_prompter_agent",
    prompt_name="motion_prompter_i2v",
    output_key="motion_prompts_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_light_model,
)
