import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_light_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "consistency_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'consistency_patches' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping shot IDs to their consistency patch entries, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": {\n"
        "    \"prompt_type\": \"flux_edit\",\n"
        "    \"prompt\": \"...\",\n"
        "    \"reference_images\": [\n"
        "      \"{{character_sheets.char_01.output_path}}\",\n"
        "      \"{{ff_shots.scene_01_shot_01.output_path}}\"\n"
        "    ],\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_5_consistency_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Formatting & Reference logic:\n"
        "- For each shot where continuation_from_previous == false and characters_present is not empty, populate `consistency_patches[shot_id]`:\n"
        "  `prompt_type`: 'flux_edit'\n"
        "  `prompt`: [Generated Flux edit prompt string]\n"
        "  `reference_images`: a list of template path variables. Image 1 to N are the character sheets, and the last image is the FF shot: \n"
        "    [\"{{character_sheets.char_id_1.output_path}}\", ..., \"{{ff_shots.shot_id.output_path}}\"]\n"
        "  `status`: 'pending'\n"
        "- Edge Case: If characters_present is empty (e.g. establishing landscape shot), skip this patch (status = 'skipped') and set `prompt` = null.\n"
        "- Edge Case: If continuation_from_previous == true, skip this patch (status = 'skipped') and set `prompt` = null.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}"
    )
    
    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

consistency_prompter = LlmAgent(
    model=get_light_model(),
    name="consistency_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="consistency_prompts_content",
)
