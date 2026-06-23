import os
from google.adk.agents import LlmAgent
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
        "    \"prompt_type\": \"ideogram_json\",\n"
        "    \"prompt\": { ... },\n"
        "    \"reference_images\": [],\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_4_ff_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Edge Cases for 'ff_shots':\n"
        "- For shots where continuation_from_previous == true: skip generating Ideogram JSON, and set:\n"
        "  `prompt_type`: 'extracted_frame', `prompt`: null, `status`: 'pending_wave_1', `generated_by`: 'system'\n"
        "- For shots where continuation_from_previous == false: generate the Ideogram 4 JSON prompt, and set:\n"
        "  `prompt_type`: 'ideogram_json', `prompt`: [Generated JSON prompt dict], `status`: 'pending', `generated_by`: 'step_4_ff_prompter'\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}"
    )
    
    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

ff_shot_prompter = LlmAgent(
    model=get_light_model(),
    name="ff_shot_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="ff_prompts_content",
)
