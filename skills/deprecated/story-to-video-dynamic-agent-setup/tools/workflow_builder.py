#!/usr/bin/env python3
"""
Workflow Builder System for ComfyUI templates
"""

import copy
import json
import os
import re

# Workflow templates directory (relative to this script's parent)
TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "workflow-templates"
)


def load_workflow_template(template_name, templates_dir=None):
    """Load a workflow template JSON from the templates directory.

    Auto-converts ComfyUI UI-format exports to API format if needed. UI
    exports have top-level keys like `id`, `nodes` (with `type`/`widgets_values`),
    `links` (list of lists), `definitions.subgraphs`, etc. The `/prompt` API
    expects a flat `{ "<node_id>": {"class_type": ..., "inputs": ...} }` dict.
    """
    if templates_dir is None:
        templates_dir = TEMPLATES_DIR

    template_path = os.path.join(templates_dir, f"{template_name}.json")
    if not os.path.exists(template_path):
        available = [f.replace(".json", "") for f in os.listdir(templates_dir)
                     if f.endswith(".json")]
        raise FileNotFoundError(
            f"Workflow template not found: {template_path}\n"
            f"Available templates: {', '.join(available) or 'none'}"
        )

    with open(template_path) as f:
        template = json.load(f)

    # Auto-convert UI format -> API format if needed.
    if _is_ui_format(template):
        template = _ui_to_api(template, template_name)

    # Return raw template preserving metadata starting with _
    return template


def _is_ui_format(template):
    """Detect ComfyUI UI-export format (vs API format).

    UI format has top-level `nodes` (list) and no `class_type` keys at the
    top level. API format has numeric string keys whose values contain
    `class_type`.
    """
    if not isinstance(template, dict):
        return False
    if "nodes" in template and isinstance(template["nodes"], list):
        return True
    return False


# Per-node-type WIDGET order (only the fields that come from `widgets_values`,
# NOT the connected inputs). The connected inputs are wired separately via
# the link map. We derive this from ComfyUI's documented input_order by
# filtering out the fields that have a non-None `link` in the node's
# `inputs` list (those are the connected ones, not widgets).
# For simplicity, we hard-code the widget-only ordering per type.
_NODE_WIDGET_ORDER = {
    "VAEDecode": [],  # samples + vae are connected, not widgets
    "EmptyFlux2LatentImage": ["width", "height", "batch_size"],
    "CLIPTextEncode": ["text"],  # text is widget; clip is connected
    "PrimitiveInt": ["value"],
    "RandomNoise": ["noise_seed"],
    "VAELoader": ["vae_name"],
    "CFGGuider": ["cfg"],  # model/positive/negative are connected
    "KSamplerSelect": ["sampler_name"],
    "UNETLoader": ["unet_name", "weight_dtype"],
    "CLIPLoader": ["clip_name", "type", "device"],
    "Flux2Scheduler": ["steps", "width", "height"],
    "SamplerCustomAdvanced": [],  # all connected
    "SaveImage": ["filename_prefix"],  # images is connected
    "ConditioningZeroOut": [],
    "LoadImage": ["image"],
    "ReferenceLatent": [],
    "ImageScaleToTotalPixels": ["upscale_method", "megapixels", "resolution_steps"],
    "VAEEncode": [],  # pixels + vae are connected
    "Flux2ProImageNode": [],
}


def _ui_to_api(ui_workflow, template_name="<unknown>"):
    """Convert a ComfyUI UI-format export to API format.

    Handles:
    - Flattening subgraphs in `definitions.subgraphs` (only the first level;
      nested subgraphs are not supported).
    - Mapping each `widgets_values` entry to the corresponding input key
      using a per-node-type input-order table.
    - Mapping each connected input (link ID) to `[origin_node_id, origin_slot]`.
    - Inserting `__PROMPT__`, `__WIDTH__`, `__HEIGHT__`, `__SEED__`,
      `__FILENAME_PREFIX__` placeholders so the standard substitution logic
      in `build_dynamic_workflow` can fill them in per-shot.
    - Skipping decorative nodes (e.g. `MarkdownNote`) that have no API
      effect but are referenced by the top-level link list.

    Returns a dict suitable for POST /prompt.
    """
    # 1. Collect subgraphs (if any) — but the conversion logic only inlines
    #    the first subgraph as the main graph. Top-level nodes (e.g. SaveImage)
    #    are kept and wired to the subgraph's output node (-20).
    subgraphs = ui_workflow.get("definitions", {}).get("subgraphs", []) or []

    # 2. Determine which nodes to convert.
    if subgraphs:
        sub = subgraphs[0]
        inner_nodes = sub.get("nodes", [])
        inner_links = sub.get("links", []) or []
        inner_node_ids = {n["id"] for n in inner_nodes}
        external_nodes = [n for n in ui_workflow.get("nodes", []) if n["id"] not in inner_node_ids]
    else:
        inner_nodes = ui_workflow.get("nodes", [])
        inner_links = []
        external_nodes = []

    # 3. Build a map: link_id -> (origin_id, origin_slot)
    link_map = {}
    # Track which inner node is wired to the subgraph's external text input
    # (-10, slot 0). Only that node should get the __PROMPT__ placeholder.
    text_consumer_node = None
    for link in inner_links:
        if isinstance(link, dict):
            link_map[link["id"]] = (link["origin_id"], link["origin_slot"])
            if link.get("origin_id") == -10 and link.get("origin_slot") == 0:
                text_consumer_node = link.get("target_id")
        elif isinstance(link, (list, tuple)) and len(link) >= 3:
            link_map[link[0]] = (link[1], link[2])
            if link[1] == -10 and link[2] == 0:
                text_consumer_node = link[3]

    # Node types that are purely decorative / informational and have no
    # server-side effect. Skip them entirely during conversion.
    _DECORATIVE_TYPES = {"MarkdownNote", "Note", "Comment"}

    # 4. Convert each inner node to API format.
    api = {}
    for n in inner_nodes:
        nid = n["id"]
        ntype = n["type"]
        if ntype in _DECORATIVE_TYPES:
            continue
        if nid < 0:
            continue  # subgraph input/output placeholders

        inputs = {}
        widget_order = _NODE_WIDGET_ORDER.get(ntype, [])
        widgets = n.get("widgets_values", []) or []
        for i, wv in enumerate(widgets):
            if i < len(widget_order):
                key = widget_order[i]
                if isinstance(wv, str) and wv in ("fixed", "randomize", "increment", "decrement"):
                    continue
                # Insert substitution placeholders for the standard keys
                # that the rest of workflow_builder knows how to fill in.
                if ntype == "CLIPTextEncode" and key == "text":
                    # Only mark the text as __PROMPT__ if this CLIPTextEncode
                    # is the one wired to the subgraph's external text input
                    # (-10). Other CLIPTextEncode nodes (e.g. the negative-
                    # prompt encoder) keep their original widget value.
                    if text_consumer_node is not None and nid == text_consumer_node:
                        inputs[key] = "__PROMPT__"
                    else:
                        inputs[key] = wv
                elif ntype == "PrimitiveInt" and key == "value":
                    if nid == 68:
                        inputs[key] = "__WIDTH__"
                    elif nid == 69:
                        inputs[key] = "__HEIGHT__"
                    else:
                        inputs[key] = wv
                elif ntype == "RandomNoise" and key == "noise_seed":
                    inputs[key] = "__SEED__"
                elif ntype == "VAELoader" and key == "vae_name":
                    inputs[key] = "__VAE_NAME__"
                elif ntype == "UNETLoader" and key == "unet_name":
                    inputs[key] = "__UNET_NAME__"
                elif ntype == "CLIPLoader" and key == "clip_name":
                    inputs[key] = "__CLIP_NAME__"
                else:
                    inputs[key] = wv
        # Then, map connected inputs (link IDs to [origin_id, slot]).
        for inp in n.get("inputs", []) or []:
            iname = inp.get("name")
            ilink = inp.get("link")
            if ilink is None:
                continue
            if ilink in link_map:
                origin_id, origin_slot = link_map[ilink]
                if origin_id == -10:
                    continue
                inputs[iname] = [str(origin_id), origin_slot]
        api[str(nid)] = {"class_type": ntype, "inputs": inputs}

    # 5. Wire external nodes (e.g. SaveImage) to the subgraph's IMAGE output.
    # Find the inner node connected to the subgraph's output node (-20).
    output_producer = None
    output_slot = 0
    for link in inner_links:
        if isinstance(link, dict) and link.get("target_id") == -20:
            output_producer = link["origin_id"]
            output_slot = link.get("origin_slot", 0)
            break
        if isinstance(link, (list, tuple)) and len(link) >= 5 and link[3] == -20:
            output_producer = link[1]
            output_slot = link[2]
            break

    for n in external_nodes:
        nid = n["id"]
        ntype = n["type"]
        if ntype in _DECORATIVE_TYPES:
            continue
        if ntype not in _NODE_WIDGET_ORDER:
            continue
        widget_order = _NODE_WIDGET_ORDER[ntype]
        widgets = n.get("widgets_values", []) or []
        inputs = {}
        for i, wv in enumerate(widgets):
            if i < len(widget_order):
                key = widget_order[i]
                if isinstance(wv, str) and wv in ("fixed", "randomize", "increment", "decrement"):
                    continue
                if ntype == "SaveImage" and key == "filename_prefix":
                    inputs[key] = "__FILENAME_PREFIX__"
                else:
                    inputs[key] = wv
        # Connected inputs (from external links)
        for inp in n.get("inputs", []) or []:
            iname = inp.get("name")
            ilink = inp.get("link")
            if ilink is None:
                continue
            if output_producer is not None:
                inputs[iname] = [str(output_producer), output_slot]
        api[str(nid)] = {"class_type": ntype, "inputs": inputs}

    return api


def _apply_overrides(workflow, overrides, overrides_map):
    """Apply agent-specified parameter overrides to workflow nodes."""
    if not overrides or not overrides_map:
        return workflow

    applied = []
    for name, value in overrides.items():
        mapping = overrides_map.get(name)
        if mapping is None:
            print(f"   ⚠️ Unknown override '{name}' — skipping")
            continue

        node_id = mapping["node"]
        input_key = mapping["key"]

        if node_id not in workflow:
            print(f"   ⚠️ Override '{name}' targets node {node_id} which doesn't exist — skipping")
            continue

        workflow[node_id]["inputs"][input_key] = value
        applied.append(f"{name}={value}")

    if applied:
        print(f"   🎛️  Overrides applied: {', '.join(applied)}")

    return workflow


def _prune_unused_refs(workflow, num_refs, ref_slots, conditioning_node, conditioning_input_pattern):
    """Prune unused LoadImage nodes and their connections on the conditioning node."""
    sorted_slots = sorted(ref_slots.items(), key=lambda x: int(x[0]))

    for slot_str, info in sorted_slots:
        slot_num = int(slot_str)
        if slot_num > num_refs:
            if info.get("required", False):
                continue

            node_id = info["load_image_node"]
            if node_id in workflow:
                del workflow[node_id]

            if conditioning_node in workflow:
                input_key = conditioning_input_pattern.format(N=slot_num)
                if input_key in workflow[conditioning_node]["inputs"]:
                    del workflow[conditioning_node]["inputs"][input_key]


def _spawn_extra_refs(workflow, num_refs, template_refs, spawn_node_id_start, conditioning_node, conditioning_input_pattern):
    """Spawn new LoadImage nodes for reference slots beyond the template count."""
    if num_refs <= template_refs:
        return workflow

    for slot_num in range(template_refs + 1, num_refs + 1):
        spawn_id = str(spawn_node_id_start + (slot_num - template_refs - 1))

        # 1. Create LoadImage node
        workflow[spawn_id] = {
            "inputs": {
                "image": f"__REFERENCE_{slot_num}__"
            },
            "class_type": "LoadImage",
            "_meta": {"title": f"Load Image (ref {slot_num})"}
        }

        # 2. Connect to conditioning node
        if conditioning_node in workflow:
            input_key = conditioning_input_pattern.format(N=slot_num)
            workflow[conditioning_node]["inputs"][input_key] = [spawn_id, 0]

    return workflow


def _prune_flux_refs(workflow, num_refs, ref_slots, chain_endpoints):
    """Prune unused ReferenceLatent chains and their sub-pipelines for Flux."""
    last_slot_num = max(1, num_refs)
    sorted_slots = sorted(ref_slots.items(), key=lambda x: int(x[0]))

    for slot_str, info in sorted_slots:
        slot_num = int(slot_str)
        if slot_num > last_slot_num:
            # Delete all 5 nodes of this slot
            for key in ["load_image_node", "scale_node", "vae_encode_node", "positive_ref_node", "negative_ref_node"]:
                node_id = info.get(key)
                if node_id and node_id in workflow:
                    del workflow[node_id]

    # Connect the consumer nodes to the final nodes of the last remaining slot
    last_slot_str = str(last_slot_num)
    if last_slot_str in ref_slots:
        last_slot_info = ref_slots[last_slot_str]
        pos_final = last_slot_info["positive_ref_node"]
        neg_final = last_slot_info["negative_ref_node"]

        # Wire positive chain
        pos_endpoint = chain_endpoints["positive"]
        pos_consumer = pos_endpoint["consumer_node"]
        pos_input = pos_endpoint["consumer_input"]
        if pos_consumer in workflow:
            workflow[pos_consumer]["inputs"][pos_input] = [pos_final, 0]

        # Wire negative chain
        neg_endpoint = chain_endpoints["negative"]
        neg_consumer = neg_endpoint["consumer_node"]
        neg_input = neg_endpoint["consumer_input"]
        if neg_consumer in workflow:
            workflow[neg_consumer]["inputs"][neg_input] = [neg_final, 0]


def _spawn_flux_refs(workflow, num_refs, template_refs, spawn_node_id_start, ref_slots, chain_endpoints):
    """Spawn new ReferenceLatent chains and their sub-pipelines for Flux."""
    if num_refs <= template_refs:
        return workflow

    vae_node_id = chain_endpoints["vae_node"]
    tail_pos = chain_endpoints["positive"]["final_node"]
    tail_neg = chain_endpoints["negative"]["final_node"]

    for slot_num in range(template_refs + 1, num_refs + 1):
        offset = (slot_num - template_refs - 1) * 5
        load_id = str(spawn_node_id_start + offset + 0)
        scale_id = str(spawn_node_id_start + offset + 1)
        vae_id = str(spawn_node_id_start + offset + 2)
        pos_ref_id = str(spawn_node_id_start + offset + 3)
        neg_ref_id = str(spawn_node_id_start + offset + 4)

        # 1. Spawn LoadImage
        workflow[load_id] = {
            "inputs": {
                "image": f"__REFERENCE_{slot_num}__"
            },
            "class_type": "LoadImage",
            "_meta": {"title": f"Load Image (ref {slot_num})"}
        }

        # 2. Spawn ImageScaleToTotalPixels
        workflow[scale_id] = {
            "inputs": {
                "upscale_method": "lanczos",
                "megapixels": 1,
                "resolution_steps": 1,
                "image": [load_id, 0]
            },
            "class_type": "ImageScaleToTotalPixels",
            "_meta": {"title": f"Scale Image (ref {slot_num})"}
        }

        # 3. Spawn VAEEncode
        workflow[vae_id] = {
            "inputs": {
                "pixels": [scale_id, 0],
                "vae": [vae_node_id, 0]
            },
            "class_type": "VAEEncode",
            "_meta": {"title": f"VAE Encode (ref {slot_num})"}
        }

        # 4. Spawn ReferenceLatent (positive)
        workflow[pos_ref_id] = {
            "inputs": {
                "conditioning": [tail_pos, 0],
                "latent": [vae_id, 0]
            },
            "class_type": "ReferenceLatent",
            "_meta": {"title": f"ReferenceLatent Positive (ref {slot_num})"}
        }

        # 5. Spawn ReferenceLatent (negative)
        workflow[neg_ref_id] = {
            "inputs": {
                "conditioning": [tail_neg, 0],
                "latent": [vae_id, 0]
            },
            "class_type": "ReferenceLatent",
            "_meta": {"title": f"ReferenceLatent Negative (ref {slot_num})"}
        }

        tail_pos = pos_ref_id
        tail_neg = neg_ref_id

    # Connect the consumer nodes to the final tails of the chain
    pos_endpoint = chain_endpoints["positive"]
    pos_consumer = pos_endpoint["consumer_node"]
    pos_input = pos_endpoint["consumer_input"]
    if pos_consumer in workflow:
        workflow[pos_consumer]["inputs"][pos_input] = [tail_pos, 0]

    neg_endpoint = chain_endpoints["negative"]
    neg_consumer = neg_endpoint["consumer_node"]
    neg_input = neg_endpoint["consumer_input"]
    if neg_consumer in workflow:
        workflow[neg_consumer]["inputs"][neg_input] = [tail_neg, 0]


def _prune_dev_turbo_refs(workflow, num_refs, ref_slots, chain_endpoints):
    """Prune unused ReferenceLatent chains and their sub-pipelines for Flux Dev Turbo."""
    last_slot_num = max(1, num_refs)
    sorted_slots = sorted(ref_slots.items(), key=lambda x: int(x[0]))

    for slot_str, info in sorted_slots:
        slot_num = int(slot_str)
        if slot_num > last_slot_num:
            # Delete all 4 nodes of this slot
            for key in ["load_image_node", "resize_node", "vae_encode_node", "ref_node"]:
                node_id = info.get(key)
                if node_id and node_id in workflow:
                    del workflow[node_id]

    # Connect the consumer node to the final node of the last remaining slot
    last_slot_str = str(last_slot_num)
    if last_slot_str in ref_slots:
        last_slot_info = ref_slots[last_slot_str]
        ref_final = last_slot_info["ref_node"]

        # Wire conditioning chain
        cond_endpoint = chain_endpoints["conditioning"]
        cond_consumer = cond_endpoint["consumer_node"]
        cond_input = cond_endpoint["consumer_input"]
        if cond_consumer in workflow:
            workflow[cond_consumer]["inputs"][cond_input] = [ref_final, 0]


def _spawn_dev_turbo_refs(workflow, num_refs, template_refs, spawn_node_id_start, ref_slots, chain_endpoints):
    """Spawn new ReferenceLatent chains and their sub-pipelines for Flux Dev Turbo."""
    if num_refs <= template_refs:
        return workflow

    vae_node_id = chain_endpoints["vae_node"]
    tail_ref = chain_endpoints["conditioning"]["final_node"]

    for slot_num in range(template_refs + 1, num_refs + 1):
        offset = (slot_num - template_refs - 1) * 4
        load_id = str(spawn_node_id_start + offset + 0)
        resize_id = str(spawn_node_id_start + offset + 1)
        vae_id = str(spawn_node_id_start + offset + 2)
        ref_id = str(spawn_node_id_start + offset + 3)

        # 1. Spawn LoadImage
        workflow[load_id] = {
            "inputs": {
                "image": f"__REFERENCE_{slot_num}__"
            },
            "class_type": "LoadImage",
            "_meta": {"title": f"Load Image (ref {slot_num})"}
        }

        # 2. Spawn ImageResizeKJv2
        workflow[resize_id] = {
            "inputs": {
                "width": 1000,
                "height": 1000,
                "upscale_method": "lanczos",
                "keep_proportion": "total_pixels",
                "pad_color": "0, 0, 0",
                "crop_position": "center",
                "divisible_by": 16,
                "device": "cpu",
                "image": [load_id, 0],
                "mask": [load_id, 1]
            },
            "class_type": "ImageResizeKJv2",
            "_meta": {"title": f"Resize Image v2 (ref {slot_num})"}
        }

        # 3. Spawn VAEEncode
        workflow[vae_id] = {
            "inputs": {
                "pixels": [resize_id, 0],
                "vae": [vae_node_id, 0]
            },
            "class_type": "VAEEncode",
            "_meta": {"title": f"VAE Encode (ref {slot_num})"}
        }

        # 4. Spawn ReferenceLatent
        workflow[ref_id] = {
            "inputs": {
                "conditioning": [tail_ref, 0],
                "latent": [vae_id, 0]
            },
            "class_type": "ReferenceLatent",
            "_meta": {"title": f"ReferenceLatent (ref {slot_num})"}
        }

        tail_ref = ref_id

    # Connect the consumer node to the final tail of the chain
    cond_endpoint = chain_endpoints["conditioning"]
    cond_consumer = cond_endpoint["consumer_node"]
    cond_input = cond_endpoint["consumer_input"]
    if cond_consumer in workflow:
        workflow[cond_consumer]["inputs"][cond_input] = [tail_ref, 0]


def _build_workflow_legacy(template, shot_data, global_cfg):
    """Build a ComfyUI API workflow by replacing template placeholders (legacy fallback)."""
    workflow = copy.deepcopy(template)

    # Build replacement map
    prompt_text = shot_data["prompt"]
    negative_prompt = shot_data.get("negative_prompt", global_cfg.get("negative_prompt", ""))
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))
    width = global_cfg["width"]
    height = global_cfg["height"]
    filename_prefix = shot_data["filename_prefix"]
    references = list(shot_data.get("references", []))

    # Pad references to ensure we have enough for the template's slots
    while len(references) < 10:
        references.append(references[0] if references else "example.png")

    # Walk the workflow dict and replace placeholder strings
    workflow_str = json.dumps(workflow)

    # String replacements
    workflow_str = workflow_str.replace("__PROMPT__", _json_escape(prompt_text))
    workflow_str = workflow_str.replace("__NEGATIVE_PROMPT__", _json_escape(negative_prompt))
    workflow_str = workflow_str.replace("__FILENAME_PREFIX__", _json_escape(filename_prefix))
    # Model loader name placeholders (set by the UI->API converter)
    workflow_str = workflow_str.replace("__UNET_NAME__", _json_escape(global_cfg.get("unet_name", "flux-2-klein-9b-fp8.safetensors")))
    workflow_str = workflow_str.replace("__CLIP_NAME__", _json_escape(global_cfg.get("clip_name", "qwen_3_8b_fp8mixed.safetensors")))
    workflow_str = workflow_str.replace("__VAE_NAME__", _json_escape(global_cfg.get("vae_name", "full_encoder_small_decoder.safetensors")))

    # Reference image replacements (up to 10 slots)
    for i in range(10):
        placeholder = f"__REFERENCE_{i+1}__"
        if placeholder in workflow_str:
            workflow_str = workflow_str.replace(placeholder, _json_escape(references[i]))

    # Numeric replacements
    workflow_str = workflow_str.replace('"__SEED__"', str(seed))
    workflow_str = workflow_str.replace('"__WIDTH__"', str(width))
    workflow_str = workflow_str.replace('"__HEIGHT__"', str(height))
    workflow_str = workflow_str.replace('__SEED__', str(seed))
    workflow_str = workflow_str.replace('__WIDTH__', str(width))
    workflow_str = workflow_str.replace('__HEIGHT__', str(height))

    result = json.loads(workflow_str)

    # Verify no remaining placeholders
    remaining = re.findall(r'__[A-Z_]+__', workflow_str)
    if remaining:
        print(f"   ⚠️ Unreplaced placeholders in workflow: {set(remaining)}")

    # Strip metadata keys starting with _
    return {k: v for k, v in result.items() if not k.startswith("_")}


def build_dynamic_workflow(template, shot_data, global_cfg):
    """Build a ComfyUI API workflow dynamically supporting pruning, spawning, and overrides.

    Falls back to legacy builder if template does not have _reference_slots metadata.
    """
    builder_type = shot_data.get("_builder_mode") or template.get("_builder")
    references = list(shot_data.get("references", []))

    # Deduplicate references — same image in multiple slots causes
    # the model to hallucinate duplicate characters
    seen = set()
    deduped_refs = []
    for ref in references:
        if ref not in seen:
            deduped_refs.append(ref)
            seen.add(ref)
    if len(deduped_refs) < len(references):
        removed = len(references) - len(deduped_refs)
        print(f"   ⚠️ Deduplicated references: removed {removed} duplicate ref(s) ({references} → {deduped_refs})")
    references = deduped_refs
    num_refs = len(references)

    if builder_type == "flux_reference_chain" and num_refs == 0:
        # Auto-switch to T2I template (no references)
        print("   🔄 Zero references — auto-switching to flux-2-klein-t2i template")
        t2i_template = load_workflow_template("flux-2-klein-t2i")
        return build_dynamic_workflow(t2i_template, shot_data, global_cfg)

    ref_slots = template.get("_reference_slots")
    if ref_slots is None and builder_type not in ["flux_t2i", "ltx_i2v", "ltx_director", "ltx_fflf_seed_hunter", "ltx_flf2v", "ideogram_t2i", "flux_klein_edit", "flux_klein_edit_dynamic"]:
        return _build_workflow_legacy(template, shot_data, global_cfg)

    # Deep copy raw template
    workflow = copy.deepcopy(template)

    if builder_type == "flux_klein_edit_dynamic":
        character_refs = shot_data.get("character_refs", [])
        num_refs = len(character_refs)

        # 1. Update first character ref placeholder if any
        if num_refs >= 1:
            workflow["121"]["inputs"]["image"] = character_refs[0]
        else:
            # Flux-only arch: all images are reference latents, no scene-image concept.
            # If a scene_image is supplied (e.g. LF using FF as the primary ref),
            # use it; otherwise fall back to the first character ref slot.
            # Last-resort: example.png is a ComfyUI-shipped sample to keep graph valid.
            workflow["121"]["inputs"]["image"] = (
                shot_data.get("scene_image")
                or (character_refs[0] if character_refs else None)
                or "example.png"
            )
            
        # 2. Clone reference chain for additional characters
        for i in range(2, num_refs + 1):
            ref_filename = character_refs[i - 1]
            suffix = f"_{i}"
            prev_suffix = f"_{i-1}" if i > 2 else ""
            
            prev_pos_node = f"92:131{prev_suffix}"
            prev_neg_node = f"92:129{prev_suffix}"
            
            # LoadImage clone
            workflow[f"121{suffix}"] = {
                "inputs": {"image": ref_filename},
                "class_type": "LoadImage",
                "_meta": {"title": f"Load Image (Ref {i})"}
            }
            
            # ImageScaleToTotalPixels clone
            workflow[f"92:85{suffix}"] = {
                "inputs": {
                    "upscale_method": "lanczos",
                    "megapixels": 1,
                    "resolution_steps": 1,
                    "image": [f"121{suffix}", 0]
                },
                "class_type": "ImageScaleToTotalPixels",
                "_meta": {"title": f"Scale Image to Total Pixels (Ref {i})"}
            }
            
            # VAEEncode clone
            workflow[f"92:130{suffix}"] = {
                "inputs": {
                    "pixels": [f"92:85{suffix}", 0],
                    "vae": ["92:110", 0]
                },
                "class_type": "VAEEncode",
                "_meta": {"title": f"VAE Encode (Ref {i})"}
            }
            
            # ReferenceLatent positive clone — chains from previous positive
            workflow[f"92:131{suffix}"] = {
                "inputs": {
                    "conditioning": [prev_pos_node, 0],
                    "latent": [f"92:130{suffix}", 0]
                },
                "class_type": "ReferenceLatent",
                "_meta": {"title": f"ReferenceLatent Positive (Ref {i})"}
            }
            
            # ReferenceLatent negative clone — chains from previous negative
            workflow[f"92:129{suffix}"] = {
                "inputs": {
                    "conditioning": [prev_neg_node, 0],
                    "latent": [f"92:130{suffix}", 0]
                },
                "class_type": "ReferenceLatent",
                "_meta": {"title": f"ReferenceLatent Negative (Ref {i})"}
            }
            
            # Rewire CFGGuider to use the new last-in-chain ReferenceLatent
            workflow["92:103"]["inputs"]["positive"] = [f"92:131{suffix}", 0]
            workflow["92:103"]["inputs"]["negative"] = [f"92:129{suffix}", 0]

    # Limit number of references to max_references
    max_refs = template.get("_max_references", 12)
    if num_refs > max_refs:
        print(f"   ⚠️ Too many references ({num_refs}) for model max ({max_refs}). Truncating to {max_refs}.")
        references = references[:max_refs]
        num_refs = max_refs

    # For flux_dev_turbo_chain, handle 0 references by disabling references switch
    if builder_type == "flux_dev_turbo_chain":
        use_refs_node = template.get("_switch_nodes", {}).get("use_references")
        if num_refs == 0:
            print("   🔄 Zero references — disabling ReferenceLatent chain via ComfySwitchNode")
            if use_refs_node and use_refs_node in workflow:
                workflow[use_refs_node]["inputs"]["value"] = False
            references = ["example.png"]
            num_refs = 1
        else:
            print("   🔄 References present — enabling ReferenceLatent chain via ComfySwitchNode")
            if use_refs_node and use_refs_node in workflow:
                workflow[use_refs_node]["inputs"]["value"] = True

    template_refs = template.get("_template_references", 4)
    spawn_node_id_start = template.get("_spawn_node_id_start", 1001)
    conditioning_node = template.get("_conditioning_node", "104")
    conditioning_input_pattern = template.get("_conditioning_input_pattern", "images.image_{N}")

    # Apply reference modifications
    if builder_type in ["flux_t2i", "ltx_i2v", "ltx_director", "ltx_flf2v", "ideogram_t2i", "flux_klein_edit", "flux_klein_edit_dynamic"]:
        # Zero-reference T2I or simple video/edit workflows have no references to prune or spawn
        pass
    elif builder_type == "flux_reference_chain":
        chain_endpoints = template.get("_chain_endpoints", {})
        if num_refs < template_refs:
            _prune_flux_refs(
                workflow,
                num_refs,
                ref_slots,
                chain_endpoints
            )
        elif num_refs > template_refs:
            _spawn_flux_refs(
                workflow,
                num_refs,
                template_refs,
                spawn_node_id_start,
                ref_slots,
                chain_endpoints
            )
    elif builder_type == "flux_dev_turbo_chain":
        chain_endpoints = template.get("_chain_endpoints", {})
        if num_refs < template_refs:
            _prune_dev_turbo_refs(
                workflow,
                num_refs,
                ref_slots,
                chain_endpoints
            )
        elif num_refs > template_refs:
            _spawn_dev_turbo_refs(
                workflow,
                num_refs,
                template_refs,
                spawn_node_id_start,
                ref_slots,
                chain_endpoints
            )
    else:
        if num_refs < template_refs:
            _prune_unused_refs(
                workflow,
                num_refs,
                ref_slots,
                conditioning_node,
                conditioning_input_pattern
            )
        elif num_refs > template_refs:
            _spawn_extra_refs(
                workflow,
                num_refs,
                template_refs,
                spawn_node_id_start,
                conditioning_node,
                conditioning_input_pattern
            )

    # Apply parameter overrides
    overrides = shot_data.get("overrides", {})
    overrides_map = template.get("_overrides_map", {})
    workflow = _apply_overrides(workflow, overrides, overrides_map)

    # Apply text substitutions
    prompt_text = shot_data["prompt"]
    negative_prompt = shot_data.get("negative_prompt", global_cfg.get("negative_prompt", ""))
    seed = shot_data.get("seed", global_cfg.get("seed_base", 42))
    width = global_cfg.get("width", 1280)
    height = global_cfg.get("height", 720)
    filename_prefix = shot_data["filename_prefix"]

    # Replace reference placeholders — do NOT pad with duplicates
    # If a placeholder remains after pruning (shouldn't happen), it will be caught
    # by the remaining-placeholders check below
    workflow_str = json.dumps(workflow)

    # String replacements
    workflow_str = workflow_str.replace("__PROMPT__", _json_escape(prompt_text))
    workflow_str = workflow_str.replace("__NEGATIVE_PROMPT__", _json_escape(negative_prompt))
    workflow_str = workflow_str.replace("__FILENAME_PREFIX__", _json_escape(filename_prefix))
    # Model loader name placeholders (set by the UI->API converter)
    workflow_str = workflow_str.replace("__UNET_NAME__", _json_escape(global_cfg.get("unet_name", "flux-2-klein-9b-fp8.safetensors")))
    workflow_str = workflow_str.replace("__CLIP_NAME__", _json_escape(global_cfg.get("clip_name", "qwen_3_8b_fp8mixed.safetensors")))
    workflow_str = workflow_str.replace("__VAE_NAME__", _json_escape(global_cfg.get("vae_name", "full_encoder_small_decoder.safetensors")))

    for i in range(len(references)):
        placeholder = f"__REFERENCE_{i+1}__"
        if placeholder in workflow_str:
            workflow_str = workflow_str.replace(placeholder, _json_escape(references[i]))

    if builder_type == "flux_klein_edit":
        scene_image = shot_data.get("scene_image", "")
        character_ref = shot_data.get("character_ref", "")
        edit_prompt = shot_data.get("prompt", "")
        
        workflow_str = workflow_str.replace("__SCENE_IMAGE__", _json_escape(scene_image))
        workflow_str = workflow_str.replace("__CHARACTER_REF__", _json_escape(character_ref))
        workflow_str = workflow_str.replace("__EDIT_PROMPT__", _json_escape(edit_prompt))
    elif builder_type == "flux_klein_edit_dynamic":
        scene_image = shot_data.get("scene_image", "")
        edit_prompt = shot_data.get("prompt", "")
        character_refs = shot_data.get("character_refs", [])
        char_ref = character_refs[0] if character_refs else ""
        
        workflow_str = workflow_str.replace("__SCENE_IMAGE__", _json_escape(scene_image))
        workflow_str = workflow_str.replace("__EDIT_PROMPT__", _json_escape(edit_prompt))
        workflow_str = workflow_str.replace("__CHARACTER_REF__", _json_escape(char_ref))
    elif builder_type == "ltx_i2v":
        motion_image = shot_data.get("motion_image", "")
        if not motion_image and references:
            motion_image = references[0]
        if not motion_image:
            motion_image = "example.png"
        
        duration = shot_data.get("duration", global_cfg.get("duration", 5))
        fps = shot_data.get("fps", global_cfg.get("fps", 25))

        workflow_str = workflow_str.replace("__MOTION_IMAGE__", _json_escape(motion_image))
        workflow_str = workflow_str.replace('"__DURATION__"', str(duration))
        workflow_str = workflow_str.replace('__DURATION__', str(duration))
        workflow_str = workflow_str.replace('"__FPS__"', str(fps))
        workflow_str = workflow_str.replace('__FPS__', str(fps))
    elif builder_type == "ltx_fflf_seed_hunter":
        # Resolve resolution preset
        resolution_preset = global_cfg.get("resolution_preset", "1080p")
        presets = template.get("_resolution_presets", {})
        if resolution_preset in presets:
            width = presets[resolution_preset]["width"]
            height = presets[resolution_preset]["height"]
        else:
            width = global_cfg.get("custom_width", 1920)
            height = global_cfg.get("custom_height", 1088)

        # FFLF-specific parameter injection
        first_frame = shot_data.get("first_frame_image", "")
        last_frame = shot_data.get("last_frame_image", "")
        input_strength = shot_data.get("input_ref_strength", global_cfg.get("input_ref_strength", 0.8))
        end_strength = shot_data.get("end_ref_strength", global_cfg.get("end_ref_strength", 0.8))
        duration_seconds = shot_data.get("segment_duration", global_cfg.get("segment_duration", 5))
        fps = shot_data.get("fps", global_cfg.get("fps", 25))
        
        # Seeds
        seed_base = shot_data.get("seed_base", global_cfg.get("seed_base", 42))
        seed_stage2 = shot_data.get("seed_stage2", global_cfg.get("seed_stage2", 4242))
        seed_stage3 = shot_data.get("seed_stage3", global_cfg.get("seed_stage3", 424242))
        
        selected_index = shot_data.get("_selected_gen_index", 0)
        finish_mode = shot_data.get("_finish_mode", False)

        # Apply substitutions to the serialized workflow string
        workflow_str = workflow_str.replace("__FIRST_FRAME__", _json_escape(first_frame))
        workflow_str = workflow_str.replace("__LAST_FRAME__", _json_escape(last_frame))
        workflow_str = workflow_str.replace('"__INPUT_REF_STRENGTH__"', str(input_strength))
        workflow_str = workflow_str.replace('"__END_REF_STRENGTH__"', str(end_strength))
        workflow_str = workflow_str.replace('"__DURATION_SECONDS__"', str(duration_seconds))
        workflow_str = workflow_str.replace('"__FPS__"', str(fps))
        workflow_str = workflow_str.replace('"__SELECTED_GEN_INDEX__"', str(selected_index))
        
        # Replace seed tokens
        workflow_str = workflow_str.replace('"__SEED__"', str(seed_base))
        workflow_str = workflow_str.replace('"__SEED_STAGE2__"', str(seed_stage2))
        workflow_str = workflow_str.replace('"__SEED_STAGE3__"', str(seed_stage3))

        workflow_str = workflow_str.replace('__INPUT_REF_STRENGTH__', str(input_strength))
        workflow_str = workflow_str.replace('__END_REF_STRENGTH__', str(end_strength))
        workflow_str = workflow_str.replace('__DURATION_SECONDS__', str(duration_seconds))
        workflow_str = workflow_str.replace('__FPS__', str(fps))
        workflow_str = workflow_str.replace('__SELECTED_GEN_INDEX__', str(selected_index))
        workflow_str = workflow_str.replace('__SEED__', str(seed_base))
        workflow_str = workflow_str.replace('__SEED_STAGE2__', str(seed_stage2))
        workflow_str = workflow_str.replace('__SEED_STAGE3__', str(seed_stage3))
        
        # Embed width and height
        workflow_str = workflow_str.replace('"__WIDTH__"', str(width))
        workflow_str = workflow_str.replace('"__HEIGHT__"', str(height))
        workflow_str = workflow_str.replace('__WIDTH__', str(width))
        workflow_str = workflow_str.replace('__HEIGHT__', str(height))

        # Re-parse JSON to dict
        workflow_dict = json.loads(workflow_str)

        # Handle finish_mode toggle programmatically:
        if not finish_mode:
            print("   🔍 Finish mode is OFF — outputting Stage 1 previews only.")
            # Remove final output + Stage 2 previews that depend on Stage 2
            for nid in ["5033", "5178", "5179"]:
                workflow_dict.pop(nid, None)
            # Remove Stage 2/3 subgraphs entirely
            stage23_prefixes = ("5012:", "5219:", "5027:")
            for nid in list(workflow_dict.keys()):
                if nid.startswith(stage23_prefixes):
                    del workflow_dict[nid]
            # Remove bridging nodes
            for nid in ["5207", "5177", "5173"]:
                workflow_dict.pop(nid, None)
        else:
            print(f"   🎬 Finish mode is ON — rendering final video at {width}x{height} using selected gen index {selected_index}.")
            # Delete Stage 1 preview nodes and their decoder feeders to clean up graph
            for preview_node_id in ["5062", "5186", "5202", "5063", "5187", "5203"]:
                workflow_dict.pop(preview_node_id, None)

        return {k: v for k, v in workflow_dict.items() if not k.startswith("_")}
    elif builder_type == "ltx_director":
        duration = shot_data.get("duration", global_cfg.get("duration", 5))
        fps = shot_data.get("fps", global_cfg.get("fps", 24))
        duration_frames = int(duration * fps)

        # 16:9 resolution guard. The LTXVLatentUpsampler + spatial-upscaler-x2
        # models are hardcoded to expect a 16:9 base latent (multiples of
        # 32×18). Non-16:9 pairs blow up the upscaler's tile geometry:
        # "RuntimeError: The size of tensor a (2560) must match the size of
        # tensor b (128) at non-singleton dimension 2". Force the user to
        # either pick a 16:9 valid resolution or set 0/0 to auto-derive from
        # the first keyframe's native dims.
        width = global_cfg.get("width")
        height = global_cfg.get("height")
        div = global_cfg.get("divisible_by", 32)
        if width and height:
            if width % div or height % div:
                raise ValueError(
                    f"Width ({width}) and height ({height}) must both be "
                    f"divisible by {div}. Suggested 16:9 pairs: "
                    f"768x432, 1024x576, 1536x864, 2048x1152."
                )
            # 16:9 check with float tolerance
            ratio = width / height
            if abs(ratio - 16/9) > 0.005:
                # Suggest nearest valid 16:9 at the same width
                suggested_h = round(width * 9 / 16 / div) * div
                raise ValueError(
                    f"Aspect ratio {width}x{height} ({ratio:.3f}:1) is not 16:9. "
                    f"The LTX 2.3 spatial upscaler requires 16:9 (1.778:1). "
                    f"Suggested fix: {width}x{suggested_h} (or 1024x576, "
                    f"1536x864). Set custom_width=0, custom_height=0 in the "
                    f"LTXDirector node to auto-derive from the first keyframe."
                )

        timeline_data = shot_data.get("timeline_data", {"segments": [], "audioSegments": []})
        if isinstance(timeline_data, (dict, list)):
            timeline_data_str = json.dumps(timeline_data)
        else:
            timeline_data_str = str(timeline_data)

        # Derive local_prompts / segment_lengths / guide_strength from the
        # timeline segments so the LTXDirector node has them populated when
        # the API call is made (the timeline editor auto-sync is normally a
        # frontend-only path).
        #
        # The LTXDirector node expects:
        #   - local_prompts: NEWLINE-separated string of segment prompts
        #   - segment_lengths: COMMA-separated string of frame counts
        #   - guide_strength: COMMA-separated string of guide strengths (one per
        #     image-anchored segment; can be left empty for pure text)
        #
        # The script's build_director_timeline() may emit overlapping segments
        # (e.g. a 0.5s keyframe + 0-2.5s text + 2.5-5.0s text). The node
        # schedules them sequentially with non-overlapping frame budgets, so
        # we collapse the timeline to a single ordered, non-overlapping walk
        # that sums exactly to duration_frames. Each text segment keeps its
        # prompt; keyframe-only segments get a placeholder prompt; guide
        # strength from the original keyframe is preserved on the corresponding
        # frames.
        raw_segments = timeline_data.get("segments", []) if isinstance(timeline_data, dict) else []

        # Build (start, end, prompt, guide_strength) tuples, clipped to duration
        duration_s = float(duration)
        clipped = []
        for seg in raw_segments:
            try:
                start = max(0.0, float(seg.get("start", 0.0)))
                end = min(duration_s, float(seg.get("end", start + 0.5)))
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue
            text = (seg.get("text", "") or seg.get("prompt", "") or "").strip()
            guide = float(seg.get("guideStrength", seg.get("guide_strength", 1.0)))
            has_image = bool(seg.get("imageFile"))
            clipped.append((start, end, text, guide, has_image))

        # Assign frame budgets to cover [0, duration_frames] contiguously.
        # Each timeline segment that has a non-empty prompt contributes its
        # frame range; image-only keyframes are merged into the surrounding
        # text segment so we don't get an empty prompt on a non-zero frame
        # range.
        n_frames_total = duration_frames
        local_prompts_list = []
        segment_lengths_list = []
        guide_strength_list = []

        if not clipped:
            # Fall back to a single text segment covering the whole duration
            local_prompts_list = [prompt_text]
            segment_lengths_list = [n_frames_total]
            guide_strength_list = [1.0]
        else:
            # Walk timeline, splitting frame ranges at segment boundaries
            boundaries = sorted({0.0, duration_s, *[s for s, *_ in clipped], *[e for _, e, *_ in clipped]})
            for b_start, b_end in zip(boundaries[:-1], boundaries[1:]):
                if b_end <= b_start:
                    continue
                # Find any clipped segment that overlaps this boundary
                seg_text = ""
                seg_guide = 1.0
                for s, e, t, g, _ in clipped:
                    if s <= b_start < e or s < b_end <= e or (b_start >= s and b_end <= e):
                        if t:
                            seg_text = seg_text or t
                        seg_guide = max(seg_guide, g)
                # If this slice still has no text, borrow from the top-level
                # prompt so the node never sees an empty-prompt segment.
                if not seg_text:
                    seg_text = prompt_text
                seg_frames = max(1, int(round((b_end - b_start) * fps)))
                local_prompts_list.append(seg_text)
                segment_lengths_list.append(seg_frames)
                guide_strength_list.append(seg_guide)

            # Normalize so the frame counts sum exactly to duration_frames
            drift = n_frames_total - sum(segment_lengths_list)
            if segment_lengths_list and drift != 0:
                segment_lengths_list[-1] = max(1, segment_lengths_list[-1] + drift)

        # Format as pipe-separated / CSV strings.
        # Per the PromptRelay source code (ComfyUI-PromptRelay/nodes.py):
        #   - local_prompts: "Ordered prompts for each temporal segment,
        #     separated by |"
        #   - segment_lengths: "Comma-separated pixel space frame counts per
        #     segment. Leave empty to auto-distribute evenly."
        #   - guide_strength: comma-separated, one per image-anchored segment
        # JSON-lists or newline-separated strings are rejected as a single
        # entry, so pipe/CSV is the only format the API path can rely on.
        local_prompts_str = "|".join(local_prompts_list)
        segment_lengths_str = ",".join(str(x) for x in segment_lengths_list)
        guide_strength_str = ",".join(f"{g:.3f}" for g in guide_strength_list)

        workflow_str = workflow_str.replace('"__DURATION__"', str(duration))
        workflow_str = workflow_str.replace('__DURATION__', str(duration))
        workflow_str = workflow_str.replace('"__FPS__"', str(fps))
        workflow_str = workflow_str.replace('__FPS__', str(fps))
        workflow_str = workflow_str.replace('"__DURATION_FRAMES__"', str(duration_frames))
        workflow_str = workflow_str.replace('__DURATION_FRAMES__', str(duration_frames))
        workflow_str = workflow_str.replace("__TIMELINE_DATA__", _json_escape(timeline_data_str))
        workflow_str = workflow_str.replace("__LOCAL_PROMPTS__", _json_escape(local_prompts_str))
        workflow_str = workflow_str.replace("__SEGMENT_LENGTHS__", _json_escape(segment_lengths_str))
        workflow_str = workflow_str.replace("__GUIDE_STRENGTH__", _json_escape(guide_strength_str))

    elif builder_type == "ltx_flf2v":
        # LTX-2.3 First-Last-Frame (FLF2V) workflow. All parameter nodes in the
        # API JSON are hardcoded INTConstant / PrimitiveFloat / PrimitiveBoolean /
        # PrimitiveStringMultiline / LoadImage nodes — no `__PLACEHOLDER__` strings.
        # We mutate them directly by node id (verified from the API JSON):
        #   45  = LoadImage FIRST FRAME     → shot_data["first_frame_image"]
        #   47  = LoadImage LAST FRAME      → shot_data["last_frame_image"]
        #   2076 = PrimitiveFloat FPS       → fps (default 24)
        #   2078 = INTConstant LENGTH secs  → duration_seconds
        #   2079 = INTConstant HEIGHT       → height
        #   2080 = INTConstant WIDTH        → width
        #   2082 = PrimitiveBoolean ENHANCER→ use_builtin_enhancer
        #   2103 = PrimitiveStringMultiline PROMPT → prompt
        #   2108 = PrimitiveFloat LAST FRAME STRENGTH (1.0)
        #   2110 = PrimitiveFloat FIRST FRAME STRENGTH (0.5)
        #   14   = RandomNoise seed (stage 1)
        #   15   = RandomNoise seed (stage 2)
        first_frame = shot_data.get("first_frame_image", "")
        last_frame = shot_data.get("last_frame_image", "")
        if not first_frame or not last_frame:
            raise ValueError(
                "ltx_flf2v: both first_frame_image and last_frame_image are required."
            )
        duration_seconds = int(shot_data.get("duration_seconds", global_cfg.get("duration_seconds", 3)))
        fps = int(shot_data.get("fps", global_cfg.get("fps", 24)))
        width = int(shot_data.get("width", global_cfg.get("width", 1280)))
        height = int(shot_data.get("height", global_cfg.get("height", 720)))
        use_builtin_enhancer = bool(shot_data.get("use_builtin_enhancer", False))
        seed = int(shot_data.get("seed", global_cfg.get("seed_base", 42)))

        # Direct node mutation — the FLF2V API JSON keeps all parameters in
        # first-class typed nodes (not string placeholders).
        try:
            workflow["45"]["inputs"]["image"] = first_frame
            workflow["47"]["inputs"]["image"] = last_frame
            workflow["2076"]["inputs"]["value"] = fps
            workflow["2078"]["inputs"]["value"] = duration_seconds
            workflow["2079"]["inputs"]["value"] = height
            workflow["2080"]["inputs"]["value"] = width
            workflow["2082"]["inputs"]["value"] = use_builtin_enhancer
            workflow["2103"]["inputs"]["value"] = prompt_text
            workflow["2108"]["inputs"]["value"] = float(shot_data.get("last_frame_strength", 1.0))
            workflow["2110"]["inputs"]["value"] = float(shot_data.get("first_frame_strength", 0.5))
            workflow["14"]["inputs"]["noise_seed"] = seed
            workflow["15"]["inputs"]["noise_seed"] = seed + 1
        except KeyError as e:
            raise KeyError(
                f"ltx_flf2v builder expected a node id that wasn't found in the "
                f"workflow template: {e}. Template may be the wrong file."
            ) from e

        # Skip the workflow_str serialization path — we've mutated the dict in place.
        result = workflow
        remaining = re.findall(r'__[A-Z_]+__', json.dumps(workflow))
        if remaining:
            print(f"   ⚠️ Unreplaced placeholders in ltx_flf2v workflow: {remaining}")
        return {k: v for k, v in result.items() if not k.startswith("_")}

    # Numeric replacements
    workflow_str = workflow_str.replace('"__SEED__"', str(seed))
    workflow_str = workflow_str.replace('"__WIDTH__"', str(width))
    workflow_str = workflow_str.replace('"__HEIGHT__"', str(height))
    workflow_str = workflow_str.replace('__SEED__', str(seed))
    workflow_str = workflow_str.replace('__WIDTH__', str(width))
    workflow_str = workflow_str.replace('__HEIGHT__', str(height))

    result = json.loads(workflow_str)

    # Verify no remaining placeholders
    remaining = re.findall(r'__[A-Z_]+__', workflow_str)
    if remaining:
        print(f"   ⚠️ Unreplaced placeholders in workflow: {remaining}")

    # Strip metadata keys starting with _
    return {k: v for k, v in result.items() if not k.startswith("_")}


def _json_escape(text):
    """Escape text for safe embedding in JSON string values.

    Handles newlines, quotes, backslashes, and other special characters
    that could break the JSON structure when replacing placeholder tokens.
    """
    # json.dumps adds surrounding quotes — strip them
    return json.dumps(text)[1:-1]
