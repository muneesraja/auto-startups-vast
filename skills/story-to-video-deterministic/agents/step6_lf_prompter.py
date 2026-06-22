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
        "The output must be a valid JSON dictionary mapping shot IDs to their last frame entries, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": {\n"
        "    \"prompt_type\": \"ideogram_t2i\",\n"
        "    \"prompt\": {... Ideogram 4 JSON object ...},\n"
        "    \"reference_images\": [],\n"
        "    \"output_path\": null,\n"
        "    \"status\": \"pending\",\n"
        "    \"generated_by\": \"step_6_lf_prompter\"\n"
        "  }\n"
        "}\n\n"
        "Format rules (do not deviate):\n"
        "- `prompt_type` MUST be the string \"ideogram_t2i\" for every shot (LF is now a full text-to-image generation, NOT a Flux edit).\n"
        "- `prompt` MUST be an Ideogram 4 JSON OBJECT (the same schema used by ff_shots), NOT a string edit instruction.\n"
        "- `reference_images` MUST be an empty list `[]` for every shot (Ideogram T2I takes no reference images).\n"
        "- `output_path`: null (filled in at execution time).\n"
        "- `status`: \"pending\".\n"
        "- `generated_by`: \"step_6_lf_prompter\".\n\n"
        "Delta plan consumption:\n"
        "- The `lf_delta_plan_json` (a dict mapping shot_id -> delta_type string) is provided in session state. "
        "For each shot, read its `delta_type` and engineer the Ideogram JSON to depict the END STATE of that delta.\n"
        "- The LF image MUST reflect the delta_type from the plan — do NOT override the plan's delta_type.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}\n\n"
        "Here is the LF delta plan JSON:\n\n{lf_delta_plan_json}"
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
