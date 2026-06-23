import os
from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_light_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "ff_shot_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()

    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'ff_shots' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping shot IDs to their first frame entries, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": {\n"
        "    \"prompt_type\": \"flux_klein_t2i\",\n"
        "    \"prompt\": \"Use image 1 as the character reference for Pippin. A medium-wide eye-level shot of a forest path in late morning with warm dappled sunlight...\",\n"
        "    \"reference_images\": [\n"
        "      \"{{character_sheets.char_01.output_path}}\"\n"
        "    ],\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_4_ff_prompter\"\n"
        "  },\n"
        "  \"scene_01_shot_02\": {\n"
        "    \"prompt_type\": \"extracted_frame\",\n"
        "    \"prompt\": null,\n"
        "    \"reference_images\": [],\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending_wave_1\",\n"
        "    \"generated_by\": \"system\"\n"
        "  }\n"
        "}\n\n"
        "Hard rules:\n"
        "- For every shot where `continuation_from_previous == false`:\n"
        "  `prompt_type`: 'flux_klein_t2i', `prompt`: [Generated Flux natural-language paragraph], `status`: 'pending', `generated_by`: 'step_4_ff_prompter'.\n"
        "- For every shot where `continuation_from_previous == true`:\n"
        "  `prompt_type`: 'extracted_frame', `prompt`: null, `reference_images`: [], `status`: 'pending_wave_1', `generated_by`: 'system'.\n"
        "- `reference_images` MUST list one `{{character_sheets.X.output_path}}` per character in `characters_present`, in `character_spatial_map_json` `reference_index` order.\n"
        "- `prompt` MUST be a single natural-language string (NOT a dict, NOT a list).\n"
        "- Reference images in the prompt using the 'image N' anchor form (N = 1-based position in the `reference_images` list).\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}\n\n"
        "Here is the character spatial map JSON:\n\n{character_spatial_map_json}"
    )

    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

ff_shot_prompter = Agent(
    model=get_light_model(),
    name="ff_shot_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="ff_prompts_content",
)
