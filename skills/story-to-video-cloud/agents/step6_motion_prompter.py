import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_light_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "motion_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

import json
from scripts.blueprint_projections import project_for_motion_prompter

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    raw_bp = context.state.get("blueprint_json_content")
    if raw_bp:
        bp_dict = json.loads(raw_bp) if isinstance(raw_bp, str) else raw_bp
        projected = project_for_motion_prompter(bp_dict)
        print(f"📉 [motion_prompter] Projected blueprint: {len(projected)} chars (from {len(raw_bp) if isinstance(raw_bp, str) else 0} chars)")
    else:
        projected = "{}"
    
    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'motion_prompts' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping shot IDs to their motion prompt entries, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": {\n"
        "    \"prompt\": \"...\",\n"
        "    \"duration_seconds\": 3,\n"
        "    \"ff_image\": \"{{ff_shots.scene_01_shot_01.output_path}}\",\n"
        "    \"lf_image\": \"{{lf_shots.scene_01_shot_01.output_path}}\",\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_6_motion_prompter\",\n"
        "    \"character_sounds\": {\n"
        "      \"char_01\": [\"hu\", \"ahhh\", \"mama\"]\n"
        "    }\n"
        "  }\n"
        "}\n\n"
        "Formatting & Reference image logic:\n"
        "- For each shot in the blueprint, populate `motion_prompts[shot_id]`:\n"
        "  `prompt`: [Generated brief LTX motion prompt string]\n"
        "  `duration_seconds`: [shot duration_seconds]\n"
        "  `ff_image`: \"{{ff_shots.shot_id.output_path}}\"\n"
        "  `lf_image`: \"{{lf_shots.shot_id.output_path}}\"\n"
        "  `status`: 'pending'\n"
        "  `character_sounds`: [JSON object mapping character ID (e.g. \"char_01\") from the shot's `characters_present` to a list of simple planned sound/noise strings (e.g., [\"hu\", \"ahhh\", \"mama\"] or [\"huhu\", \"doin\"]). These must be non-dialogue basic sounds. If no sounds are made, map to an empty list `[]` or omit. Only characters present in the shot may have sounds listed.]\n\n"
        "Here is the visual blueprint JSON context:\n\n{projected-blueprint}"
    )
    
    full_prompt = system_prompt + additional_instr
    injected = await instructions_utils.inject_session_state(full_prompt, context)
    return injected.replace("{projected-blueprint}", projected)

motion_prompter = LlmAgent(
    model=get_light_model(),
    name="motion_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="motion_prompts_content",
)
