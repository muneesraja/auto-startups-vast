import config
from agents._base import make_json_agent

_JSON_RULE = (
    "\n\nCRITICAL: Return ONLY the raw JSON object. No markdown fences. Do not call tools.\n\n"
    "Target duration: {target_duration_seconds} seconds "
    "(tolerance ±{duration_tolerance_percent}%).\n\n"
    "Scene paper (source of truth — expand from this, not the raw story):\n\n{scene_paper_text}\n\n"
    "Storyboard sheet map (if non-empty, this is AUTHORITATIVE for scene/sheet boundaries: "
    "produce exactly one JSON scene per sheet listed below, in the same order, using its "
    "subtitle and duration budget — never add, remove, merge, or split beyond what this map "
    "declares):\n\n{story_sheet_scene_text}"
)

narrative_expander_agent = make_json_agent(
    name="narrative_expander_agent",
    prompt_name="narrative_expander",
    output_key="narrative_outline_content",
    extra_instruction=_JSON_RULE,
    model_factory=config.get_narrative_expander_model,
)
