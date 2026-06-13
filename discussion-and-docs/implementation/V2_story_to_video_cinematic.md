# Story-to-Video Cinematic Pipeline (V2) — Implementation Documentation

This document records the architectural details and code structure of the second version (V2) of the **`story-to-video-cinematic`** pipeline, implemented on **June 13, 2026**.

---

## 1. Pipeline Overview & Upgrades

The V2 release upgrades the cinematic pipeline from a sequential shot-by-shot execution model to a highly optimized **Batch-Wave Execution Model** and introduces **Dynamic Multi-Character Flux Klein Editing**:

| Aspect | V1 (Old) | V2 (Current V2/V3) |
|--------|---------|---------------------|
| **Execution model** | Sequential per shot | **Batch-wave** (fixed GPU swapping waves) |
| **GPU model swaps** | `N * 3` swaps | **Max 7 swaps** total, independent of shot count |
| **Character references** | 1 per shot (`primary_character`) | **1–4 per shot** (cloned ReferenceLatent chains) |
| **Schema version** | 2.0 | **3.0** |
| **Continuity bounds** | Hardcoded logic | **Explicit `##continue` / `##cut`** |
| **Quality Gates** | None | **Gemini-powered likeness / neutrality reviews** |

---

## 2. The Batch-Wave Model & GPU Swaps

Loading large models (Ideogram: ~30GB, Flux Klein: ~18GB, LTX: ~45GB) on cloud GPUs introduces huge swap overheads (~1 min per load). The V2 orchestrator resolves this by grouping tasks into waves, swapping the active GPU model only 7 times total:

```
Wave 0 (GPU: Ideogram) ── Generate all character sheet references.
Wave 1 (GPU: Ideogram) ── Generate all raw FFs for chain start/##cut shots.
Wave 2 (GPU: Flux Klein) ─ Edit FFs for character likeness + Derive all LFs.
Wave 3 (GPU: LTX-Video) ── Render depth-0 (chain start) videos + extract tails.
Wave 4 (GPU: Flux Klein) ─ Edit tail frames into derived LFs (Continuation Depth 1).
Wave 5 (GPU: LTX-Video) ── Render continuation videos + extract tails (Depth 1).
Wave 6 (GPU: Flux Klein) ─ Edit tail frames into derived LFs (Continuation Depth 2).
Wave 7 (GPU: LTX-Video) ── Render continuation videos (Depth 2).
```

---

## 3. Dynamic Multi-Character reference Injection

The Flux Klein template `flux-2-klein-image-edit.json` is dynamically manipulated at runtime by the `flux_klein_edit_dynamic` builder.

If a shot contains $N$ characters (up to 4):
1. **Node 121** (Ref 1 LoadImage) is mapped to character reference sheet 1.
2. For each extra character, the builder clones:
   - `LoadImage` node (`121_N`)
   - `ImageScaleToTotalPixels` node (`92:85_N`)
   - `VAEEncode` node (`92:130_N`)
   - `ReferenceLatent` positive node (`92:131_N`)
   - `ReferenceLatent` negative node (`92:129_N`)
3. The ReferenceLatent nodes are chained sequentially (`prev_ref → current_ref`).
4. **CFGGuider** (`92:103`) is rewired to consume the positive and negative endpoints of the last ReferenceLatent in the chain.

---

## 4. V3 JSON Schema Specification (`cinematic_prompt.json`)

The prompt schema version is upgraded to `3.0` to support scenes containing arrays of characters, explicit scene folders, and enums:

```json
{
  "version": "3.0",
  "pipeline": "cinematic-v2",
  "models": { ... },
  "global": {
    "max_continuous_shots": 3,
    "quality_gate": { "enabled": true, "provider": "openrouter" }
  },
  "characters": [
    {
      "id": "pippin",
      "display_name": "Pippin the Panda",
      "description": "fluffy baby panda wearing a small red knitted scarf",
      "edit_prompt_descriptor": "the baby panda with the red scarf",
      "character_sheet_prompt": "Professional character reference sheet for Pippin..."
    }
  ],
  "director_plan": {
    "scenes": [
      {
        "scene_id": 1,
        "shots": [
          {
            "shot_id": 1,
            "shot_type": "chain_start",
            "continuity": "start",
            "characters_present": ["pippin"],
            "ff_source": "ideogram",
            "ff_prompt": "Pippin walking in bamboo forest...",
            "ff_edit_instructions": { "pippin": "Replace the panda..." },
            "lf_source": "klein_from_ff",
            "lf_edit_instruction": "The panda turns its head...",
            "lf_edit_references": ["pippin"],
            "motion_prompt": "Camera pushes forward..."
          }
        ]
      }
    ]
  }
}
```

---

## 5. Verification & Testing

We verified all V2 components using our test suite:
1. **Schema Validation (`scripts/validate_schema.py`)**: Validated the 12 semantic checks against the Pippin example.
2. **Prompts Composition (`flux_edit_pass.py`)**: Verified that multi-character prompt descriptions concatenate in `characters_present` order.
3. **Dynamic Builder Compilation (`workflow_builder.py`)**: Asserted that multi-character slots clone and chain ReferenceLatents correctly and rewire `CFGGuider` output.
4. **Orchestrator Depth Calculations (`cinematic_orchestrator.py`)**: Confirmed visual depths are recursively computed and visual boundaries break at `##cut` or `ff_source: "ideogram"`.
