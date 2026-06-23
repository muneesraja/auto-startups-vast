import os
from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_light_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "character_sheet_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()

    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'character_sheets' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping character IDs to their character sheet entries, e.g.:\n"
        "{\n"
        "  \"char_01\": {\n"
        "    \"prompt_type\": \"flux_klein_t2i\",\n"
        "    \"prompt\": \"A professional 16:9 character reference sheet for Pippin the chubby baby panda...\",\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_3_character_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Hard rules:\n"
        "- `prompt_type` MUST be exactly the string \"flux_klein_t2i\" for every character.\n"
        "- `prompt` MUST be a single natural-language string (NOT a dict, NOT a list, NOT a JSON object).\n"
        "- `output_path` is null until the image is generated.\n"
        "- `status` is \"pending\" until generation completes.\n"
        "- `generated_by` is \"step_3_character_prompter\".\n"
        "- The dictionary MUST be keyed by character IDs (e.g. \"char_01\").\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}"
    )

    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

character_sheet_prompter = Agent(
    model=get_light_model(),
    name="character_sheet_prompter",
    instruction=instruction_provider,
    tools=[],
    output_key="character_prompts_content",
)
