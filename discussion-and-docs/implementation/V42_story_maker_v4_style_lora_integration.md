# V42 — MiniMax H3 Illustration Style-LoRA Workflow Integration

## Context & Objectives
An external update from the branch `hoplite/histiaia-oreos-a8730cdf` on `inov2027/auto-startups-vast` (commit `1d1fad1da4c5b6a164b248d0a968e1734980df51`) introduced an H3-native style-LoRA pipeline for `story-maker-v4`. This document records the verification and integration of those updates into our local repository.

## Key Capabilities Added
1. **Four Curated Illustration Looks on MiniMax H3**:
   - **P1 (2D storybook illustration)**: Warm gouache textures, soft warm palette, hand-inked contours (`studio1939-light` strength 0.85).
   - **P2 (Folk illustration + flat geometric shapes)**: Woodcut/folk-art, bold flat silhouettes, three-color limited palette (`studio1939-strong` 0.9, `minimax_h3_looping_sketch_anime_v1` 0.35).
   - **P3 (Vintage editorial / storybook)**: Mid-century print, muted ochre and teal, halftone grain (`studio1939-light` 0.7, `minimax_h3_looping_sketch_anime_v1` 0.3).
   - **P4 (Semi-realistic fantasy concept art)**: Painterly digital rendering with visible brushwork and anime-influenced facial structure (`h3_painterly` 0.8, `h3_anime_flat_style` 0.3).
2. **Directing LoRAs**:
   - Camera motion obedience (`h3_camera_motion_v1_3000_pruned` at 0.8–1.0).
   - Spatial physics / contact weight (`h3_spatial_physics_clean_3000_pruned` at 0.5–0.7).
3. **ComfyUI Graph Architecture**:
   - Three `LoraLoaderModelOnly` nodes chained sequentially between `UNETLoader` (127) and `PathchSageAttentionKJ` (154).
   - `BasicScheduler` (124) retains its direct connection to the raw unpatched `UNETLoader`, ensuring correct sigma calculation matching official Comfy-Org conventions.
4. **Provisioning Automation**:
   - `workflows/setup/minimax-h3-r2v-style-lora.sh` provisions the base Ref2VA models, 4-step turbo LoRA, style LoRAs, and directing LoRAs for Vast.ai and RunPod instances.

## Merged Artifacts
- `skills/story-maker-v4/SKILL.md`: Added section detailing illustration styles and `MINIMAX_H3_WORKFLOW` environment override.
- `skills/story-maker-v4/assets/style-lora-presets.md`: Documentation covering the 4 presets, prompt spines, slot strengths, and continuity rules.
- `skills/story-maker-v4/tests/test_style_lora_workflow.py`: Structural link and model-matching tests.
- `workflows/comfyui/minimax-h3-r2v-style-lora.json`: The ComfyUI workflow JSON.
- `workflows/setup/minimax-h3-r2v-style-lora.sh`: Provisioning script.
- `skills/workflow-researcher/SKILL.md`: Index reference update.
- `skills/workflow-researcher/references/minimax-h3-style-lora-discovery-2026-09-04.md`: Technical research notes and adapter constraints.

## Verification
- **Automated Tests**: `python3 -m pytest skills/story-maker-v4/tests/` passed 164/164 tests in 0.21s.
- **Workflow Graph Validation**: Link table completeness, LoRA chaining, and scheduler links verified.
- **Bash Syntax**: `bash -n workflows/setup/minimax-h3-r2v-style-lora.sh` passed cleanly.
