# Cinematic Prompt Schema v3.1

The `cinematic_prompt.json` configuration file is the single source of truth for the cinematic animation pipeline. Every scene, shot, prompt, character reference sheet, and continuity choice is explicitly declared in this schema.

## Top-Level structure

```json
{
  "version": "3.0",
  "pipeline": "cinematic-v2",
  "models": { ... },
  "global": { ... },
  "characters": [ ... ],
  "director_plan": { ... }
}
```

## Schema Field Reference

### 1. Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string | ✅ | Must be `"3.0"` |
| `pipeline` | string | ✅ | Must be `"cinematic-v2"` |
| `models` | object | ✅ | Mapping of model family names to their identifiers |
| `global` | object | ✅ | Global pipeline parameters, including the quality gate config |
| `characters` | array | ✅ | Registry of characters with sheet descriptions and prompts |
| `director_plan` | object | ✅ | Story summary and list of scenes |

### 1.1 `global.quality_gate` — Quality Gate Configuration

The `quality_gate` object in global settings configures the automated evaluation of images and videos:

```json
"quality_gate": {
  "enabled": true,
  "provider": "openrouter",
  "model_image": "google/gemini-3.1-flash-lite",
  "model_video": "google/gemini-3.5-flash",
  "min_score": 6,
  "gates": {
    "character_sheet": true,
    "scene_composition": true,
    "klein_consistency": true,
    "lf_delta": true,
    "final_video": true
  }
}
```

- `enabled` (bool): Toggle all quality gates on/off.
- `provider` (string): API provider, e.g., `"openrouter"` or `"gemini"`.
- `model_image` (string): Model to use for image evaluation gates (Gates 1–4).
- `model_video` (string): Model to use for video coherence check (Gate 5).
- `min_score` (number): Pass/fail threshold (default: 6).
- `gates` (object): Toggles for individual gates.

**Recommended model IDs:**

| Provider | Gate | Recommended Model |
|----------|------|-------------------|
| `openrouter` | Image (Gates 1–4) | `google/gemini-flash-1.5-8b` |
| `openrouter` | Video (Gate 5) | `google/gemini-2.0-flash-exp` |
| `gemini` | Image (Gates 1–4) | `gemini-2.5-flash` |
| `gemini` | Video (Gate 5) | `gemini-2.5-flash` |

> [!NOTE]
> Model availability on OpenRouter can change. If `google/gemini-flash-1.5-8b` is unavailable, substitute `google/gemini-flash-1.5` or check [openrouter.ai/models](https://openrouter.ai/models) for current free-tier vision models.

### 2. `characters[]` — Character Registry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique character identifier matching references in shots |
| `display_name` | string | ✅ | Human-readable name for logging |
| `description` | string | ✅ | Detailed visual description used for T2I prompts |
| `style_notes` | string | ❌ | Style instructions (e.g., " Pixar-style, chibi ratios") |
| `edit_prompt_descriptor` | string | ✅ | Short descriptor representing the character in Flux Klein edit prompts |
| `character_sheet_path` | string\|null | ❌ | Local file path if pre-existing, `null` if it should be generated |
| `character_sheet_prompt` | string | ✅ | Ideogram T2I prompt used to generate the character sheet |

### 3. `director_plan.scenes[].shots[]` — Shot Definition

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `shot_id` | int | ✅ | Sequential shot ID within this scene |
| `shot_type` | enum | ✅ | `"chain_start"` \| `"continuation"` \| `"independent"` |
| `continuity` | enum | ✅ | `"start"` \| `"##continue"` \| `"##cut"` |
| `continues_from` | string\|null | ❌ | Prefix of predecessor shot, e.g. `"s01_sh01"`. Null for `chain_start` |
| `narrative` | string | ✅ | Text narration of what happens in the shot |
| `cinematography_notes` | string | ❌ | Camera angles, framing, or lighting instructions |
| `characters_present` | string[] | ✅ | Array of character IDs present in the shot. Order dictates reference mapping index! |
| `ff_source` | enum | ✅ | `"ideogram"` \| `"extracted_tail"` |
| `ff_prompt` | string\|null | ❌ | Ideogram T2I prompt for FF. Must be non-empty if `ff_source: "ideogram"` |
| `ff_edit_instructions` | object\|null | ❌ | Dict mapping character IDs to custom Flux Klein edit prompts |
| `lf_source` | enum | ✅ | `"ideogram_fresh"` \| `"klein_from_ff"` \| `"klein_from_extracted_tail"` |
| `lf_prompt` | string\|null | ❌ | Ideogram prompt for LF. Used if `lf_source` is `"ideogram_fresh"` |
| `lf_edit_instruction` | string | ✅ | Delta prompt for Flux Klein describing change from FF to LF |
| `lf_edit_references` | string[] | ✅ | Character IDs whose sheets should be mapped as refs for LF generation |
| `motion_prompt` | string | ✅ | Brief motion description for LTX FFLF (20-60 words) |
| `overrides` | object | ❌ | Overrides for global parameters (`segment_duration`, etc.) |

---

## Design Choices & Key Benefits

1. **Explicit Source Enums**: The fields `ff_source` and `lf_source` leave no ambiguity. The orchestrator maps inputs directly to ComfyUI based on these enums.
2. **Order-based Character Mapping**: The array order of `characters_present` determines which reference sheet maps to which reference input in the dynamic workflow (Index 0 → Ref 1, Index 1 → Ref 2, etc.).
3. **Continuation Chains**: A shot marked `##continue` is linked via `continues_from` to its predecessor. This forces the orchestrator to extract the tail frame from the predecessor's video and use it as the starting frame (FF) for the current shot, preventing visual jumps.
