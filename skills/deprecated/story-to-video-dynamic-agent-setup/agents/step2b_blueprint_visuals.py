import os
from google.adk import Agent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_reasoning_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "blueprint_visuals.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the complete, enriched visual blueprint. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "Use the structural skeleton below:\n\n{blueprint_structure_json}\n\n"
        "And extract the visual details from the Director Script below:\n\n{director_script_content}"
    )
    
    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

blueprint_visuals_agent = Agent(
    model=get_reasoning_model(),
    name="blueprint_visuals_agent",
    instruction=instruction_provider,
    tools=[],
    output_key="blueprint_json_content",
)
