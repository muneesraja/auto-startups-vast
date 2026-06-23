"""Motion Prompter — ADK 2.0 dynamic reflexion workflow (max 3 cycles).

Replaces the legacy `LoopAgent(sub_agents=[generator, critic], max_iterations=3)`
pattern with an ADK 2.0 dynamic `@node` workflow that drives the generator +
critic via `ctx.run_node()` and exits early when the critic's response contains
the `MOTION_PROMPTS_OK` phrase.

The output of the loop is the `motion_prompts` JSON namespace (via the
generator's `output_key="motion_prompts_content"`). The wave executor reads it
to generate videos via LTX-2.3 FLF2V with the FF + LF images and the motion
prompt.
"""
import os

from google.adk import Agent, Context, Event
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from google.adk.workflow import node

from config import get_reasoning_model, get_light_model
from ._safe_inject import safe_inject_session_state


def get_motion_generator_instruction() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "motion_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


async def motion_generator_instruction_provider(context: ReadonlyContext) -> str:
    base = get_motion_generator_instruction()
    additional = (
        "\n\n=== YOU ARE THE MOTION PROMPT GENERATOR ===\n"
        "Produce the `motion_prompts` JSON. On iteration 1, write a fresh draft. "
        "On iteration 2+, refine using the critic's feedback in `motion_criticism`.\n\n"
        "CRITICAL OUTPUT FORMAT:\n"
        "- Return ONLY the JSON object representing the 'motion_prompts' namespace.\n"
        "- Do NOT wrap in markdown code fences.\n"
        "- Do NOT call any tools.\n"
        "- `prompt` MUST be a single natural-language string (30-100 words ideal).\n"
        "- `duration_seconds` MUST equal the shot's `duration_seconds` from the blueprint.\n"
        "- `ff_image` MUST be `\"ff_shots.SHOT.output_path\"`.\n"
        "- `lf_image` MUST be `\"lf_shots.SHOT.output_path\"`.\n"
        "- One entry per shot in the blueprint.\n\n"
        "Apply the LTX-2 rules:\n"
        "1. Core Actions — describe events/actions over time.\n"
        "2. Audio — add Audio: line when the scene calls for it.\n"
        "3. Reference Image — do NOT repeat static FF/LF details.\n"
        "4. Consistency — no instructions that contradict FF or LF.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}\n\n"
        "Here is the FF prompt for this shot:\n\n{ff_prompts_content}\n\n"
        "Here is the LF prompt for this shot:\n\n{lf_prompts_content}\n\n"
        "If iteration > 1, here is the critic's previous feedback (apply it):\n\n"
        "{motion_criticism}"
    )
    full = base + additional
    return await safe_inject_session_state(full, context)


async def motion_critic_instruction_provider(context: ReadonlyContext) -> str:
    base = get_motion_generator_instruction()
    additional = (
        "\n\n=== YOU ARE THE MOTION PROMPT CRITIC ===\n"
        "Validate the motion prompt draft (under `motion_prompts_content`) "
        "against the 8-point checklist in your system prompt. If all checks pass, "
        "respond EXACTLY with the phrase `MOTION_PROMPTS_OK` and nothing else. "
        "Otherwise, list the failing checks using the "
        "`[FAIL] check_id: issue` / `[SUGGEST] concrete fix` format.\n\n"
        "Do NOT modify the motion prompt yourself.\n"
        "Do NOT call any tools.\n"
        "Do NOT wrap your response in markdown.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}\n\n"
        "Here is the FF prompt for this shot:\n\n{ff_prompts_content}\n\n"
        "Here is the LF prompt for this shot:\n\n{lf_prompts_content}\n\n"
        "Here is the current motion prompt draft (under review):\n\n{motion_prompts_content}"
    )
    full = base + additional
    return await safe_inject_session_state(full, context)


motion_generator_agent = Agent(
    model=get_light_model(),
    name="motion_generator",
    instruction=motion_generator_instruction_provider,
    tools=[],
    output_key="motion_prompts_content",
)

motion_critic_agent = Agent(
    model=get_reasoning_model(),
    name="motion_critic",
    instruction=motion_critic_instruction_provider,
    tools=[],
    output_key="motion_criticism",
    include_contents="none",
)


@node(name="motion_prompter_loop", rerun_on_resume=True)
async def motion_prompter_loop(ctx: Context, node_input: "str | None" = ""):
    """Motion reflexion loop: Generator + Critic, max 3 cycles.

    Runs the generator then the critic via `ctx.run_node()`. Exits early when
    the critic's response contains `MOTION_PROMPTS_OK` (all 8 checklist checks
    pass). The generator's output_key `motion_prompts_content` and the critic's
    output_key `motion_criticism` propagate state between iterations.

    `node_input` defaults to `""` so the upstream save node (which yields no
    `Event(output=...)` and therefore sends `None`) can be coerced without
    Pydantic ValidationError. The actual prompt data is read from session
    state via `{blueprint_json_content}`, `{ff_prompts_content}`, etc. — the
    node_input value is unused by the agents' instruction_providers.
    """
    starter = node_input if isinstance(node_input, str) else ""
    draft = ""
    # Seed `motion_criticism` and `motion_prompts_content` to empty strings so the
    # generator's and critic's instruction_providers can safely reference
    # `{motion_criticism}` and `{{motion_prompts_content}}` (parsed by
    # `inject_session_state` as a state-template variable) on iteration 1,
    # before either has run. Without this, `inject_session_state` raises
    # `KeyError: 'Context variable not found: ...'` on the very first LLM call.
    yield Event(state={"motion_criticism": "", "motion_prompts_content": "", "motion_iteration": 0})
    for iteration in range(1, 4):  # max_iterations=3
        draft = await ctx.run_node(motion_generator_agent, starter)
        critique = await ctx.run_node(motion_critic_agent, draft)
        critique_text = critique if isinstance(critique, str) else str(critique or "")
        if "MOTION_PROMPTS_OK" in critique_text:
            # Exit early on PASS — yield the generator's final draft as output.
            yield Event(output=draft)
            return
        yield Event(state={"motion_criticism": critique_text, "motion_iteration": iteration})
    # Max iterations exhausted without PASS — yield last draft as output.
    yield Event(output=draft)
