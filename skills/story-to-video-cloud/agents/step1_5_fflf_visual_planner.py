import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_reasoning_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "fflf_visual_planner.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()
    
    additional_instr = (
        f"\n\nCRITICAL: You MUST output the JSON composition plan mapping shot IDs to ff/lf details directly in your response. "
        f"Do not call any tools, and do not wrap in markdown code blocks or add explanatory text. "
        f"The Director's Script to plan visual framing for is:\n\n{{director_script_content}}"
    )
    
    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

fflf_visual_planner_agent = LlmAgent(
    model=get_reasoning_model(),
    name="fflf_visual_planner_agent",
    instruction=instruction_provider,
    tools=[],
    output_key="fflf_plan_content",
)
