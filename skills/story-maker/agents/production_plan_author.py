import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON production plan. No markdown fences. Do not call tools.\n\n"
    "Target duration seconds: {target_duration_seconds}\n"
    "Duration tolerance percent: {duration_tolerance_percent}\n"
    "Min shot seconds: {min_shot_seconds}\n"
    "Max shot seconds: {max_shot_seconds}\n"
    "Default pace: {default_pace}\n"
    "Pipeline mode: {pipeline_mode}\n"
    "Panels per sheet: {panels_per_sheet}\n"
    "Min panels per sheet: {min_panels_per_sheet}\n\n"
    "Scene paper (source of truth):\n\n{scene_paper_text}\n\n"
    "Deterministic sheet map context (storyboard mode only; may be empty):\n\n"
    "{sheet_map_context}"
)

production_plan_author_agent = make_json_agent(
    name="production_plan_author_agent",
    prompt_name="production_plan_author",
    output_key="plan_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_story_plan_model,
)
