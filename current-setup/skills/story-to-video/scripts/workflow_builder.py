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
    """Load a workflow template JSON from the templates directory."""
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

    # Return raw template preserving metadata starting with _
    return template


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
    builder_type = template.get("_builder")
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
    if ref_slots is None and builder_type != "flux_t2i":
        return _build_workflow_legacy(template, shot_data, global_cfg)

    # Deep copy raw template
    workflow = copy.deepcopy(template)

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
    if builder_type == "flux_t2i":
        # Zero-reference T2I workflow has no references to prune or spawn
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
    width = global_cfg["width"]
    height = global_cfg["height"]
    filename_prefix = shot_data["filename_prefix"]

    # Replace reference placeholders — do NOT pad with duplicates
    # If a placeholder remains after pruning (shouldn't happen), it will be caught
    # by the remaining-placeholders check below
    workflow_str = json.dumps(workflow)

    # String replacements
    workflow_str = workflow_str.replace("__PROMPT__", _json_escape(prompt_text))
    workflow_str = workflow_str.replace("__NEGATIVE_PROMPT__", _json_escape(negative_prompt))
    workflow_str = workflow_str.replace("__FILENAME_PREFIX__", _json_escape(filename_prefix))

    for i in range(len(references)):
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
