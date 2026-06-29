import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object mapping character_id to sheet spec. "
    "No markdown fences. Do not call tools.\n\n"
    "Story plan JSON:\n\n{story_plan_content}"
)

character_sheet_prompter_agent = make_json_agent(
    name="character_sheet_prompter_agent",
    prompt_name="character_sheet_prompter",
    output_key="character_sheet_prompts_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_light_model,
)
