import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object. No markdown fences. Do not call tools.\n\n"
    "Scene paper (source of truth):\n\n{scene_paper_text}\n\n"
    "Storyboard sheet map (if non-empty, this is AUTHORITATIVE for scene/sheet boundaries: "
    "the narrative outline scenes already mirror it 1:1 — keep that same scene count and "
    "order, and give each scene exactly its mapped panel count of shots; never add extra "
    "scenes/sheets beyond this map):\n\n{story_sheet_scene_text}\n\n"
    "Narrative outline JSON:\n\n{narrative_outline_content}"
)

ltx_shot_director_agent = make_json_agent(
    name="ltx_shot_director_agent",
    prompt_name="ltx_shot_director",
    output_key="story_plan_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_story_plan_model,
)
