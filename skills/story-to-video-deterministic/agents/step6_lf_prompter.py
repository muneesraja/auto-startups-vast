import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_reasoning_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "lf_shot_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'lf_shots' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "You MUST output the list of reference image paths under the key \"reference_images\" (do NOT use the key \"references\"). "
        "The output must be a valid JSON dictionary mapping shot IDs to their last frame entries, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": {\n"
        "    \"prompt_type\": \"flux_edit\",\n"
        "    \"prompt\": \"...\",\n"
        "    \"reference_images\": [\n"
        "      \"{{consistency_patches.scene_01_shot_01.output_path}}\",\n"
        "      \"{{character_sheets.char_01.output_path}}\"\n"
        "    ],\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_6_lf_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Formatting & Reference image logic:\n"
        "- Reference Image 1 MUST always represent the starting frame for the edit (the FF image after character consistency patching or video extraction):\n"
        "  - If continuation_from_previous == false:\n"
        "    - If characters_present is not empty: `\"{{consistency_patches.shot_id.output_path}}\"`\n"
        "    - If characters_present is empty: `\"{{ff_shots.shot_id.output_path}}\"`\n"
        "  - If continuation_from_previous == true: `\"{{ff_shots.shot_id.output_path}}\"`\n"
        "- Reference Images 2 to N represent character sheets in `characters_present` list:\n"
        "  `\"{{character_sheets.char_id.output_path}}\"`\n"
        "- Generate the edit prompt string in `lf_shots[shot_id].prompt` according to the rules and few-shot examples.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}"
    )
    
    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

lf_shot_prompter = LlmAgent(
    model=get_reasoning_model(),
    name="lf_shot_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="lf_prompts_content",
)
