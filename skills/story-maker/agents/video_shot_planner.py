import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object. No markdown fences. Do not call tools.\n\n"
    "Target duration: {target_duration_seconds} seconds "
    "(tolerance ±{duration_tolerance_percent}%).\n\n"
    "Story plan JSON (authoritative panel order and per-scene budgets):\n\n{story_plan_content}\n\n"
    "Storyboard sheet map markdown (if present):\n\n{story_sheet_scene_text}\n"
)

video_shot_planner_agent = make_json_agent(
    name="video_shot_planner_agent",
    prompt_name="video_shot_planner",
    output_key="video_shot_plan_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_light_model,
)
