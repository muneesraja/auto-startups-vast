import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_light_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "lf_delta_planner.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

import json
from scripts.blueprint_projections import project_for_lf_delta_planner

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()

    raw_bp = context.state.get("blueprint_json_content")
    if raw_bp:
        bp_dict = json.loads(raw_bp) if isinstance(raw_bp, str) else raw_bp
        projected = project_for_lf_delta_planner(bp_dict)
        print(f"📉 [lf_delta_planner_agent] Projected blueprint: {len(projected)} chars (from {len(raw_bp) if isinstance(raw_bp, str) else 0} chars)")
    else:
        projected = "{}"

    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'lf_delta_plan' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping shot_id -> delta_type string, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_01\": \"pose-change\",\n"
        "  \"scene_01_shot_02\": \"particle-motion\",\n"
        "  \"scene_02_shot_01\": \"camera-move\"\n"
        "}\n\n"
        "Hard rules (verify each before emitting):\n"
        "1. No more than 2 consecutive shots may share the same delta_type within a scene.\n"
        "2. In any scene with >=4 shots, at least 1 shot must be pose-change.\n"
        "3. In any scene with >=4 shots, at least 1 shot must be particle-motion.\n"
        "4. camera-move may appear at most once per scene.\n"
        "5. pose-change may not appear in more than half the shots of any scene.\n"
        "6. delta_type MUST be one of the closed set: pose-change, expression-shift, camera-move, particle-motion, env-shift.\n"
        "7. Every shot in the blueprint MUST appear in the output (none may be omitted).\n\n"
        "Here is the visual blueprint JSON context:\n\n{projected-blueprint}"
    )

    full_prompt = system_prompt + additional_instr
    injected = await instructions_utils.inject_session_state(full_prompt, context)
    return injected.replace("{projected-blueprint}", projected)

lf_delta_planner_agent = LlmAgent(
    model=get_light_model(),
    name="lf_delta_planner_agent",
    instruction=instruction_provider,
    tools=[],
    output_key="lf_delta_plan_content",
)
