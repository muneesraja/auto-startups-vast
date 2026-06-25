import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_reasoning_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "lf_shot_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

import json
from scripts.blueprint_projections import project_for_lf_prompter

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()

    raw_bp = context.state.get("blueprint_json_content")
    if raw_bp:
        bp_dict = json.loads(raw_bp) if isinstance(raw_bp, str) else raw_bp
        projected = project_for_lf_prompter(bp_dict)
        print(f"📉 [lf_shot_prompter] Projected blueprint: {len(projected)} chars (from {len(raw_bp) if isinstance(raw_bp, str) else 0} chars)")
    else:
        projected = "{}"

    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'lf_shots' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping shot IDs to their last frame entries, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": {\n"
        "    \"prompt_type\": \"grok_edit\",\n"
        "    \"prompt\": \"...\",\n"
        "    \"reference_images\": [\n"
        "      \"{{ff_shots.scene_01_shot_01.fal_image_url}}\",\n"
        "      \"{{character_sheets.char_01.fal_image_url}}\"\n"
        "    ],\n"
        "    \"output_path\": null,\n"
        "    \"fal_image_url\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_5_lf_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Format rules (do not deviate):\n"
        "- `prompt_type` MUST be the string \"grok_edit\" for every shot.\n"
        "- `prompt` MUST be a natural language Grok Edit prompt string describing the ending state and changes from the first frame.\n"
        "- `reference_images` MUST contain the FF image placeholder (always first) and character sheet placeholders (if any characters are present) e.g., '{{ff_shots.shot_id.fal_image_url}}' and '{{character_sheets.char_id.fal_image_url}}'.\n"
        "- `output_path`: null (filled in at execution time).\n"
        "- `fal_image_url`: null.\n"
        "- `status`: \"pending\".\n"
        "- `generated_by`: \"step_5_lf_prompter\".\n\n"
        "Delta plan consumption:\n"
        "- The `lf_delta_plan_json` is provided in session state. "
        "For each shot, read its `delta_type` and engineer the Grok Edit prompt to depict the END STATE of that delta.\n"
        "- The LF image MUST reflect the delta_type from the plan — do NOT override the plan's delta_type.\n\n"
        "Here is the visual blueprint JSON context:\n\n{projected-blueprint}\n\n"
        "Here is the LF delta plan JSON:\n\n{lf_delta_plan_json}"
    )

    full_prompt = system_prompt + additional_instr
    injected = await instructions_utils.inject_session_state(full_prompt, context)
    return injected.replace("{projected-blueprint}", projected)

lf_shot_prompter = LlmAgent(
    model=get_reasoning_model(),
    name="lf_shot_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="lf_prompts_content",
)
