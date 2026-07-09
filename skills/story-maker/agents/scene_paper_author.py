import config
from agents._base import make_text_agent

_EXTRA = (
    "\n\nCRITICAL: Return ONLY the scene paper markdown document. "
    "No JSON. Do not wrap the entire document in markdown code fences.\n\n"
    "Raw story input:\n\n{story_text}\n\n"
    "Target duration: {target_duration_seconds} seconds (±{duration_tolerance_percent}%).\n"
    "Style profile: {style_id}\n"
    "Pipeline mode: {pipeline_mode}\n"
    "Panels per storyboard sheet (max): {panels_per_sheet}\n"
    "Minimum panels per storyboard sheet: {min_panels_per_sheet}\n"
)

scene_paper_author_agent = make_text_agent(
    name="scene_paper_author_agent",
    prompt_name="scene_paper_author",
    output_key="scene_paper_content",
    extra_instruction=_EXTRA,
    model_factory=config.get_narrative_expander_model,
)
