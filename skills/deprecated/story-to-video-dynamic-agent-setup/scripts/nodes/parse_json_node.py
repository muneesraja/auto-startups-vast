"""Parse JSON FunctionNode that takes raw LLM text and writes parsed JSON to state.

Decouples JSON parsing from save logic. Each LLM agent emits raw text into a
`*_content` state key; this node parses and publishes a `*_json_pretty` state
key (string-formatted JSON, suitable for downstream template injection and
for save_artifact_nodes to write directly).

ADK 2.0 modernization notes:
- Uses the modern `@node` decorator (cleaner than `FunctionNode(func=...)`).
- Uses `return Event(state={...})` instead of `ctx.state[k] = v` mutation
  (explicit, composes with output_key pattern).
- Imports `Context` and `Event` from top-level `google.adk` (preferred ADK 2.0 path).
"""
import json
import os

from google.adk import Context, Event
from google.adk.workflow import node

from ._json_util import clean_json_str


@node
async def parse_blueprint_structure_node(ctx: Context) -> Event:
    """Parse blueprint_structure_json (which may be raw LLM text) -> parsed JSON string."""
    raw = ctx.state.get("blueprint_structure_json")
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        return None  # Already parsed; pass through.
    parsed = clean_json_str(raw)
    return Event(state={"blueprint_structure_json": json.dumps(parsed, indent=2, ensure_ascii=False)})


@node
async def parse_blueprint_node(ctx: Context) -> Event:
    """Parse blueprint_json_content (raw LLM text) -> parsed JSON string."""
    raw = ctx.state.get("blueprint_json_content")
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        return None
    parsed = clean_json_str(raw)
    return Event(state={"blueprint_json_content": json.dumps(parsed, indent=2, ensure_ascii=False)})


@node
async def parse_lf_delta_plan_node(ctx: Context) -> Event:
    """Parse lf_delta_plan_content -> Python dict (and re-serialize as pretty JSON).

    Stored back under state key 'lf_delta_plan_json' so downstream lf_shot_prompter
    can inject it as a template variable.
    """
    raw = ctx.state.get("lf_delta_plan_content")
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        parsed = raw
    else:
        parsed = clean_json_str(raw)
    return Event(state={"lf_delta_plan_json": json.dumps(parsed, indent=2, ensure_ascii=False)})


@node
async def parse_character_spatial_map_node(ctx: Context) -> Event:
    """Parse character_spatial_map_content -> Python dict (re-serialize as pretty JSON).

    Stored back under state key 'character_spatial_map_json' so downstream
    ff/lf prompters can inject it as a template variable.
    """
    raw = ctx.state.get("character_spatial_map_content")
    if not raw:
        return None
    if isinstance(raw, (dict, list)):
        parsed = raw
    else:
        parsed = clean_json_str(raw)
    return Event(state={"character_spatial_map_json": json.dumps(parsed, indent=2, ensure_ascii=False)})
