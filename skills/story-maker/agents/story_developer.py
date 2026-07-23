import config
from agents._base import make_text_agent

_EXTRA = (
    "\n\nCRITICAL: Return ONLY the developed story markdown document. "
    "No JSON. Do not wrap the entire document in markdown code fences.\n"
    "If the raw story is thin vs the target duration, expand into distinct "
    "non-alike scenes using obstacles, contrast cuts, hubris, reversal, and "
    "payoff — do not pad with repeated walk/run beats on the same backdrop. "
    "Include a Purpose line under every scene title.\n\n"
    "Raw story input:\n\n{story_text}\n\n"
    "Target duration: {target_duration_seconds} seconds (±{duration_tolerance_percent}%).\n"
    "Style profile: {style_id}\n"
)

story_developer_agent = make_text_agent(
    name="story_developer_agent",
    prompt_name="story_developer",
    output_key="developed_story_content",
    extra_instruction=_EXTRA,
    model_factory=config.get_story_developer_model,
)
