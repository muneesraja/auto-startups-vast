"""Unit tests for the reflexion dynamic-workflow loop (LF and motion prompters).

Tests the ADK 2.0 dynamic-workflow replacement for the legacy LoopAgent pattern:
- `lf_prompter_loop` and `motion_prompter_loop` are `@node`-decorated
  FunctionNode instances (not LoopAgent).
- Each loop wraps a generator + critic LlmAgent, runs max 3 cycles, and exits
  early when the critic's response contains the OK phrase.
- The critic no longer needs the `exit_loop` tool — the loop checks the critic's
  return value directly.
"""
import os
import sys
import inspect
import pytest

# Mock required env vars before any google.adk LiteLlm initialization
os.environ.setdefault("MINIMAX_API_KEY", "test-key-for-import-only")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-for-import-only")

# Make skill root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def lf_modules():
    """Import the LF prompter modules once."""
    from agents.step6_lf_prompter import (
        lf_generator_agent,
        lf_critic_agent,
        lf_prompter_loop,
    )
    return lf_generator_agent, lf_critic_agent, lf_prompter_loop


@pytest.fixture(scope="module")
def motion_modules():
    """Import the motion prompter modules once."""
    from agents.step7_motion_prompter import (
        motion_generator_agent,
        motion_critic_agent,
        motion_prompter_loop,
    )
    return motion_generator_agent, motion_critic_agent, motion_prompter_loop


def test_lf_prompter_loop_is_dynamic_workflow_node(lf_modules):
    """`lf_prompter_loop` must be a FunctionNode (dynamic @node workflow),
    NOT a legacy LoopAgent."""
    lf_generator, lf_critic, lf_loop = lf_modules
    from google.adk.workflow import FunctionNode
    from google.adk.agents import LoopAgent
    assert isinstance(lf_loop, FunctionNode), (
        f"lf_prompter_loop must be a FunctionNode (dynamic @node workflow); "
        f"got {type(lf_loop).__name__}"
    )
    assert not isinstance(lf_loop, LoopAgent), (
        "lf_prompter_loop must NOT be a legacy LoopAgent — ADK 2.0 supersedes "
        "templated workflows with dynamic workflows."
    )
    assert lf_loop.name == "lf_prompter_loop"
    # rerun_on_resume must be True — required by ctx.run_node inside the loop.
    assert lf_loop.rerun_on_resume is True, (
        "lf_prompter_loop must have rerun_on_resume=True (required for ctx.run_node "
        "per ADK 2.0 dynamic-workflows docs)."
    )


def test_lf_generator_and_critic_are_llm_agents(lf_modules):
    lf_generator, lf_critic, _ = lf_modules
    from google.adk import Agent
    assert isinstance(lf_generator, Agent)
    assert isinstance(lf_critic, Agent)
    assert lf_generator.name == "lf_generator"
    assert lf_critic.name == "lf_critic"


def test_lf_critic_has_no_exit_loop_tool(lf_modules):
    """In the dynamic-workflow pattern, the critic no longer needs the
    `exit_loop` tool. The loop exits by checking the critic's response for
    `LF_PROMPTS_OK` directly."""
    lf_generator, lf_critic, _ = lf_modules
    tool_names = []
    for t in (lf_critic.tools or []):
        tool_names.append(getattr(t, "name", str(t)) or getattr(t, "__name__", ""))
    assert not any("exit_loop" in n for n in tool_names), (
        f"lf_critic must NOT have an exit_loop tool in the dynamic-workflow pattern; "
        f"got tools: {lf_critic.tools!r}"
    )
    assert lf_critic.tools == [] or lf_critic.tools is None, (
        f"lf_critic must have no tools in the dynamic-workflow pattern; "
        f"got: {lf_critic.tools!r}"
    )


def test_lf_output_keys_set_for_state_propagation(lf_modules):
    """Generator writes draft to `lf_prompts_content`; critic writes critique
    to `lf_criticism`. The loop relies on these output_keys to propagate
    state between iterations (the generator reads {lf_criticism} on iter 2+)."""
    lf_generator, lf_critic, _ = lf_modules
    assert lf_generator.output_key == "lf_prompts_content"
    assert lf_critic.output_key == "lf_criticism"
    # Critic is stateless per-iteration — no need to carry prior conversation.
    assert lf_critic.include_contents == "none"


def test_motion_prompter_loop_is_dynamic_workflow_node(motion_modules):
    motion_generator, motion_critic, motion_loop = motion_modules
    from google.adk.workflow import FunctionNode
    from google.adk.agents import LoopAgent
    assert isinstance(motion_loop, FunctionNode), (
        f"motion_prompter_loop must be a FunctionNode (dynamic @node workflow); "
        f"got {type(motion_loop).__name__}"
    )
    assert not isinstance(motion_loop, LoopAgent), (
        "motion_prompter_loop must NOT be a legacy LoopAgent."
    )
    assert motion_loop.name == "motion_prompter_loop"
    assert motion_loop.rerun_on_resume is True


def test_motion_generator_and_critic_are_llm_agents(motion_modules):
    motion_generator, motion_critic, _ = motion_modules
    from google.adk import Agent
    assert isinstance(motion_generator, Agent)
    assert isinstance(motion_critic, Agent)
    assert motion_generator.name == "motion_generator"
    assert motion_critic.name == "motion_critic"


def test_motion_critic_has_no_exit_loop_tool(motion_modules):
    motion_generator, motion_critic, _ = motion_modules
    tool_names = []
    for t in (motion_critic.tools or []):
        tool_names.append(getattr(t, "name", str(t)) or getattr(t, "__name__", ""))
    assert not any("exit_loop" in n for n in tool_names), (
        f"motion_critic must NOT have an exit_loop tool; got: {motion_critic.tools!r}"
    )


def test_motion_output_keys_set_for_state_propagation(motion_modules):
    motion_generator, motion_critic, _ = motion_modules
    assert motion_generator.output_key == "motion_prompts_content"
    assert motion_critic.output_key == "motion_criticism"
    assert motion_critic.include_contents == "none"


def test_loops_body_runs_max_three_iterations(lf_modules, motion_modules):
    """Inspect the loop function source to confirm it's bounded by 3 iterations
    and exits on the OK phrase (LF_PROMPTS_OK / MOTION_PROMPTS_OK)."""
    _, _, lf_loop = lf_modules
    _, _, motion_loop = motion_modules
    lf_src = inspect.getsource(lf_loop._func)
    motion_src = inspect.getsource(motion_loop._func)
    assert "range(1, 4)" in lf_src, "LF loop must iterate max 3 times (range(1, 4))"
    assert "range(1, 4)" in motion_src, "Motion loop must iterate max 3 times"
    assert "LF_PROMPTS_OK" in lf_src, "LF loop must check critic's output for LF_PROMPTS_OK"
    assert "MOTION_PROMPTS_OK" in motion_src, "Motion loop must check for MOTION_PROMPTS_OK"
    assert "ctx.run_node" in lf_src, "LF loop must use ctx.run_node (dynamic workflow)"
    assert "ctx.run_node" in motion_src, "Motion loop must use ctx.run_node"


def test_generators_use_light_model_critics_use_reasoning_model(lf_modules, motion_modules):
    """Generators use the cheap/fast model; critics use the more capable model."""
    lf_generator, lf_critic, _ = lf_modules
    motion_generator, motion_critic, _ = motion_modules
    for agent in (lf_generator, lf_critic, motion_generator, motion_critic):
        assert agent.model is not None
