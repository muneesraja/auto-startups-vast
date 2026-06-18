import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_reasoning_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "motion_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'motion_prompts' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping shot IDs to their motion prompt entries, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": {\n"
        "    \"prompt\": \"...\",\n"
        "    \"duration_seconds\": 3,\n"
        "    \"ff_image\": \"{{consistency_patches.scene_01_shot_01.output_path}}\",\n"
        "    \"lf_image\": \"{{lf_shots.scene_01_shot_01.output_path}}\",\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_7_motion_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Formatting & Reference image logic:\n"
        "- For each shot in the blueprint, populate `motion_prompts[shot_id]`:\n"
        "  `prompt`: [Generated brief LTX motion prompt string]\n"
        "  `duration_seconds`: [shot duration_seconds]\n"
        "  `ff_image`: \n"
        "    - If continuation_from_previous == false:\n"
        "      - If characters_present is not empty: `\"{{consistency_patches.shot_id.output_path}}\"`\n"
        "      - If characters_present is empty: `\"{{ff_shots.shot_id.output_path}}\"`\n"
        "    - If continuation_from_previous == true: `\"{{ff_shots.shot_id.output_path}}\"`\n"
        "  `lf_image`: `\"{{lf_shots.shot_id.output_path}}\"`\n"
        "  `status`: 'pending'\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}"
    )
    
    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

motion_prompter = LlmAgent(
    model=get_reasoning_model(),
    name="motion_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="motion_prompts_content",
)
