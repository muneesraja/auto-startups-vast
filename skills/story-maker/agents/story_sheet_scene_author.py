import config
from agents._base import make_text_agent

_EXTRA = (
    "\n\nCRITICAL: Return ONLY the sheet map markdown document. "
    "No JSON. Do not wrap the entire document in markdown code fences.\n\n"
    "Scene paper (source of truth — split this into sheets; never invent scenes "
    "that are not in it):\n\n{scene_paper_text}\n\n"
    "Target duration: {target_duration_seconds} seconds (±{duration_tolerance_percent}%).\n"
    "Style profile: {style_id}\n"
    "Panels per storyboard sheet (max): {panels_per_sheet}\n"
)

story_sheet_scene_author_agent = make_text_agent(
    name="story_sheet_scene_author_agent",
    prompt_name="story_sheet_scene_author",
    output_key="story_sheet_scene_content",
    extra_instruction=_EXTRA,
    model_factory=config.get_narrative_expander_model,
)
