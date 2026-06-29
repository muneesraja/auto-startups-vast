import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_reasoning_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "director_script.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    additional_instr = (
        f"\n\nCRITICAL: You MUST output the complete markdown director script directly in your text response. "
        f"Do not call any tools. "
        f"The story text to adapt is:\n\n{{story_text}}"
    )
    
    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

director_script_agent = LlmAgent(
    model=get_reasoning_model(),
    name="director_script_agent",
    instruction=instruction_provider,
    tools=[],
    output_key="director_script_content",
)
