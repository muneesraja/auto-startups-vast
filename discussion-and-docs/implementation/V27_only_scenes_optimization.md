# V27 — Scene Filtering and Timeout Safeguards for Fast Pipeline Execution

## Overview

To resolve recurring pipeline slowness, hangs, and resource timeouts, we implement two core architectural safeguards:

1. **Scene-based Filtering during Prompt Generation**:
   - Previously, the `--only-scenes` flag was only applied during the video generation phase (`wave_nodes.py`). The preceding 7 LLM agent phases (plan, structure, visuals, characters, spatial map, shot prompts, delta plan, motion prompts) processed all scenes (e.g., all 10 scenes, 54 shots of the story).
   - We updated `parse_json_node.py` (`parse_blueprint_structure` and `parse_blueprint`) to filter the parsed scenes list to only include those in `--only-scenes` if specified.
   - We updated `resume_router.py` to filter loaded JSON files from disk during resume mode.
   - Downstream agents and nodes now naturally only process the selected scenes, drastically reducing LLM workload, token consumption, and generation times.

2. **Timeout Safeguards in model configuration**:
   - Updated `config.py` to configure a 120-second timeout on the MiniMax client (`LiteLlm`) instances.
   - Coupled with `num_retries=3`, if a call to the MiniMax API hangs, it will time out and auto-retry instead of hanging the process indefinitely.

## Proposed Changes

### [skills/story-to-video-cloud/config.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/config.py)
- Set `timeout=120` inside `get_reasoning_model` and `get_light_model`.

### [skills/story-to-video-cloud/scripts/nodes/parse_json_node.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/parse_json_node.py)
- In `parse_blueprint_structure`, filter `parsed["scenes"]` using `ctx.state.get("only_scenes")`.
- In `parse_blueprint`, filter `parsed["scenes"]` using `ctx.state.get("only_scenes")`.

### [skills/story-to-video-cloud/scripts/nodes/resume_router.py](file:///Users/pandismart/Documents/projects/auto-startups-vast/skills/story-to-video-cloud/scripts/nodes/resume_router.py)
- In `resume_router`, filter loaded JSON configurations from disk using `ctx.state.get("only_scenes")`.
