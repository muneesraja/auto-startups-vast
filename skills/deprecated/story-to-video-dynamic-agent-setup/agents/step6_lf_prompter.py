"""LF Prompter — ADK 2.0 dynamic reflexion workflow (max 3 cycles).

Replaces the legacy `LoopAgent(sub_agents=[generator, critic], max_iterations=3)`
pattern. Per ADK 2.0 docs: "Starting in ADK 2.0, templated workflows have been
superseded by more flexible workflow structures, including graph-based workflows
and dynamic workflows." The loop is now implemented as a `@node`-decorated
dynamic workflow that drives the generator + critic via `ctx.run_node()` and
exits early when the critic's response contains the `LF_PROMPTS_OK` phrase.

Benefits over LoopAgent:
- Automatic checkpointing for resume (each `ctx.run_node` call is tracked and
  skipped on resume if it already completed).
- No need for the `exit_loop` tool / `actions.escalate = True` side-channel;
  the loop simply returns when the critic passes the checklist.
- Native Python control flow (more readable, easier to test).

The output of the loop is the `lf_prompts` JSON namespace (via the generator's
`output_key="lf_prompts_content"`). The wave executor reads this JSON to
generate the LF images via Flux Klein 9B with char sheets + FF as references.
"""
import os

from google.adk import Agent, Context, Event
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from google.adk.workflow import node

from config import get_reasoning_model, get_light_model
from ._safe_inject import safe_inject_session_state


def get_lf_generator_instruction() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "lf_shot_prompter.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


async def lf_generator_instruction_provider(context: ReadonlyContext) -> str:
    base = get_lf_generator_instruction()
    additional = (
        "\n\n=== YOU ARE THE LF PROMPT GENERATOR ===\n"
        "Produce the `lf_shots` JSON. On iteration 1, write a fresh draft. On "
        "iteration 2+, refine using the critic's feedback in `lf_criticism`.\n\n"
        "CRITICAL OUTPUT FORMAT:\n"
        "- Return ONLY the JSON object representing the 'lf_shots' namespace.\n"
        "- Do NOT wrap in markdown code fences.\n"
        "- Do NOT call any tools.\n"
        "- `prompt_type` MUST be `\"flux_klein_t2i\"` for every generated shot.\n"
        "- `prompt` MUST be a single natural-language string (NOT dict, NOT list).\n"
        "- `reference_images` order: char sheets first (in `character_spatial_map_json` "
        "`reference_index` order), then `ff_shots.SHOT.output_path` as the LAST entry.\n\n"
        "For continuation shots (continuation_from_previous == true): emit a "
        "placeholder entry with `prompt_type: \"extracted_frame\"`, `prompt: null`, "
        "`reference_images: []`, `status: \"pending_wave_1\"`, `generated_by: \"system\"`.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}\n\n"
        "Here is the character spatial map JSON:\n\n{character_spatial_map_json}\n\n"
        "Here is the LF delta plan JSON:\n\n{lf_delta_plan_json}\n\n"
        "Here is the FF prompt for this shot:\n\n{ff_prompts_content}\n\n"
        "If iteration > 1, here is the critic's previous feedback (apply it):\n\n"
        "{lf_criticism}"
    )
    full = base + additional
    return await safe_inject_session_state(full, context)


async def lf_critic_instruction_provider(context: ReadonlyContext) -> str:
    base = get_lf_generator_instruction()
    additional = (
        "\n\n=== YOU ARE THE LF PROMPT CRITIC ===\n"
        "Validate the LF prompt draft (under `lf_prompts_content`) against "
        "the 8-point checklist in your system prompt. If all checks pass, "
        "respond EXACTLY with the phrase `LF_PROMPTS_OK` and nothing else. "
        "Otherwise, list the failing checks using the "
        "`[FAIL] check_id: issue` / `[SUGGEST] concrete fix` format.\n\n"
        "Do NOT modify the LF prompt yourself.\n"
        "Do NOT call any tools.\n"
        "Do NOT wrap your response in markdown.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}\n\n"
        "Here is the character spatial map JSON:\n\n{character_spatial_map_json}\n\n"
        "Here is the LF delta plan JSON:\n\n{lf_delta_plan_json}\n\n"
        "Here is the FF prompt for this shot:\n\n{ff_prompts_content}\n\n"
        "Here is the current LF prompt draft (under review):\n\n{lf_prompts_content}"
    )
    full = base + additional
    return await safe_inject_session_state(full, context)


lf_generator_agent = Agent(
    model=get_light_model(),
    name="lf_generator",
    instruction=lf_generator_instruction_provider,
    tools=[],
    output_key="lf_prompts_content",
)

lf_critic_agent = Agent(
    model=get_reasoning_model(),
    name="lf_critic",
    instruction=lf_critic_instruction_provider,
    tools=[],
    output_key="lf_criticism",
    include_contents="none",
)


@node(name="lf_prompter_loop", rerun_on_resume=True)
async def lf_prompter_loop(ctx: Context, node_input: "str | None" = ""):
    """LF reflexion loop: Generator + Critic, max 3 cycles.

    Runs the generator then the critic via `ctx.run_node()`. Exits early when
    the critic's response contains `LF_PROMPTS_OK` (all 8 checklist checks pass).
    The generator's output_key `lf_prompts_content` and the critic's output_key
    `lf_criticism` propagate state between iterations — the generator's
    instruction_provider reads `{lf_criticism}` on iteration 2+ to refine.

    The final generator draft is yielded as an `Event(output=...)` so the
    parent workflow can use it as the loop node's output if needed (state is
    also already populated via the generator's output_key).

    `node_input` defaults to `""` so the upstream save node (which yields no
    `Event(output=...)` and therefore sends `None`) can be coerced without
    Pydantic ValidationError. The actual prompt data is read from session
    state via `{blueprint_json_content}`, `{ff_prompts_content}`, etc. — the
    node_input value is unused by the agents' instruction_providers.
    """
    starter = node_input if isinstance(node_input, str) else ""
    draft = ""
    # Seed `lf_criticism` and `lf_prompts_content` to empty strings so the
    # generator's and critic's instruction_providers can safely reference
    # `{lf_criticism}` and `{{lf_prompts_content}}` (parsed by
    # `inject_session_state` as a state-template variable) on iteration 1,
    # before either has run. Without this, `inject_session_state` raises
    # `KeyError: 'Context variable not found: ...'` on the very first LLM call.
    yield Event(state={"lf_criticism": "", "lf_prompts_content": "", "lf_iteration": 0})
    for iteration in range(1, 4):  # max_iterations=3
        # Generator writes draft into state['lf_prompts_content'] via output_key.
        draft = await ctx.run_node(lf_generator_agent, starter)
        # Critic reads draft from state, writes critique to state['lf_criticism'].
        critique = await ctx.run_node(lf_critic_agent, draft)
        critique_text = critique if isinstance(critique, str) else str(critique or "")
        if "LF_PROMPTS_OK" in critique_text:
            # Exit early on PASS — yield the generator's final draft as output.
            yield Event(output=draft)
            return
        # Yield state-update so parent workflow + any resume checkpoint records
        # the iteration boundary. Generator's instruction_provider reads
        # `{lf_criticism}` on the next iteration automatically.
        yield Event(state={"lf_criticism": critique_text, "lf_iteration": iteration})
    # Max iterations exhausted without PASS — yield last draft as output.
    yield Event(output=draft)
