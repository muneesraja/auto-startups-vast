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
    if ref_slots is None and builder_type not in ["flux_t2i", "ltx_i2v", "ltx_director"]:
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
    if builder_type in ["flux_t2i", "ltx_i2v", "ltx_director"]:
        # Zero-reference T2I or simple video workflows have no references to prune or spawn
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

    if builder_type == "ltx_i2v":
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
