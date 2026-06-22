"""Parse JSON FunctionNode that takes raw LLM text and writes parsed JSON to state.

Decouples JSON parsing from save logic. Each LLM agent emits raw text into a
`*_content` state key; this node parses and publishes a `*_json_pretty` state
key (string-formatted JSON, suitable for downstream template injection and
for save_artifact_nodes to write directly).
"""
from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str


async def parse_blueprint_structure(ctx: Context) -> None:
    """Parse blueprint_structure_json (which may be raw LLM text) -> parsed JSON string."""
    raw = ctx.state.get("blueprint_structure_json")
    if not raw:
        return
    if isinstance(raw, (dict, list)):
        # Already parsed; pass through.
        return
    parsed = clean_json_str(raw)
    import json
    ctx.state["blueprint_structure_json"] = json.dumps(parsed, indent=2, ensure_ascii=False)


async def parse_blueprint(ctx: Context) -> None:
    """Parse blueprint_json_content (raw LLM text) -> parsed JSON string."""
    raw = ctx.state.get("blueprint_json_content")
    if not raw:
        return
    if isinstance(raw, (dict, list)):
        return
    parsed = clean_json_str(raw)
    import json
    ctx.state["blueprint_json_content"] = json.dumps(parsed, indent=2, ensure_ascii=False)


async def parse_lf_delta_plan(ctx: Context) -> None:
    """Parse lf_delta_plan_content -> Python dict (and re-serialize as pretty JSON).

    Stored back under state key 'lf_delta_plan_json' so downstream lf_shot_prompter
    can inject it as a template variable.
    """
    raw = ctx.state.get("lf_delta_plan_content")
    if not raw:
        return
    if isinstance(raw, (dict, list)):
        parsed = raw
    else:
        parsed = clean_json_str(raw)
    import json
    ctx.state["lf_delta_plan_json"] = json.dumps(parsed, indent=2, ensure_ascii=False)


async def parse_character_spatial_map(ctx: Context) -> None:
    """Parse character_spatial_map_content -> Python dict (re-serialize as pretty JSON).

    Stored back under state key 'character_spatial_map_json' so downstream
    consistency_prompter + lf_consistency_prompter can inject it as a template variable.
    """
    raw = ctx.state.get("character_spatial_map_content")
    if not raw:
        return
    if isinstance(raw, (dict, list)):
        parsed = raw
    else:
        parsed = clean_json_str(raw)
    import json
    ctx.state["character_spatial_map_json"] = json.dumps(parsed, indent=2, ensure_ascii=False)


parse_blueprint_structure_node = FunctionNode(
    func=parse_blueprint_structure, name="parse_blueprint_structure_node"
)
parse_blueprint_node = FunctionNode(func=parse_blueprint, name="parse_blueprint_node")
parse_lf_delta_plan_node = FunctionNode(func=parse_lf_delta_plan, name="parse_lf_delta_plan_node")
parse_character_spatial_map_node = FunctionNode(
    func=parse_character_spatial_map, name="parse_character_spatial_map_node"
)
