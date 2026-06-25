import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_light_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "character_sheet_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

import json
from scripts.blueprint_projections import project_for_character_prompter

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    raw_bp = context.state.get("blueprint_json_content")
    if raw_bp:
        bp_dict = json.loads(raw_bp) if isinstance(raw_bp, str) else raw_bp
        projected = project_for_character_prompter(bp_dict)
        print(f"📉 [character_sheet_prompter] Projected blueprint: {len(projected)} chars (from {len(raw_bp) if isinstance(raw_bp, str) else 0} chars)")
    else:
        projected = "{}"
    
    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'character_sheets' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping character IDs to their character sheet entries, e.g.:\n"
        "{\n"
        "  \"char_01\": {\n"
        "    \"prompt_type\": \"grok_t2i\",\n"
        "    \"prompt\": \"...\",\n"
        "    \"reference_images\": [],\n"
        "    \"output_path\": null,\n"
        "    \"fal_image_url\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_3_character_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Here is the visual blueprint JSON context:\n\n{projected-blueprint}"
    )
    
    full_prompt = system_prompt + additional_instr
    injected = await instructions_utils.inject_session_state(full_prompt, context)
    return injected.replace("{projected-blueprint}", projected)

character_sheet_prompter = LlmAgent(
    model=get_light_model(),
    name="character_sheet_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="character_prompts_content",
)
