# Style LoRA Presets — MiniMax H3 R2V

Every LoRA here is **H3-native** (adapter of `MiniMaxAI/MiniMax-H3` or
`Comfy-Org/MiniMax-H3`). LoRAs trained for Flux / SDXL / Qwen-Image do **not**
load into the H3 DiT — do not add them to this stack.

Install everything with:

```bash
bash workflows/setup/minimax-h3-r2v-style-lora.sh
# add the Civitai-mirror styles too:
STYLE_LORA_COMMUNITY=1 bash workflows/setup/minimax-h3-r2v-style-lora.sh
```

Render with the LoRA-enabled graph:

```bash
export MINIMAX_H3_WORKFLOW="$PWD/workflows/comfyui/minimax-h3-r2v-style-lora.json"
python3 skills/story-maker-v4/scripts/render_all.py --story <story> --episode 1
```

`render_all.py` never edits LoRA slots — the workflow JSON is the single source
of truth for which style is active. Pick a preset, set the strengths in the
three `LoraLoaderModelOnly` nodes, and keep it frozen for the whole episode:
changing style mid-episode breaks continuity harder than any prompt drift.

## Installed LoRAs

| File in `models/loras/` | Source repo | Size | What it does |
|---|---|---|---|
| `studio1939-light.safetensors` | [`lovis93/studio-1939-old-animation-lora-minimax-h3`](https://huggingface.co/lovis93/studio-1939-old-animation-lora-minimax-h3) | 62MB | r16. Hand-painted golden-age animation, **painterly / illustrated storybook in motion**. Gouache backgrounds, visible brushwork, warm celluloid palette. |
| `studio1939-strong.safetensors` | same repo | 250MB | r64. Same training, full cel: **bold flat-shaded characters with clean outlines over painted backgrounds**. |
| `minimax_h3_looping_sketch_anime_v1.safetensors` | [`Inner-Reflections/MiniMax-H3-Looping-Sketch-Anime`](https://huggingface.co/Inner-Reflections/MiniMax-H3-Looping-Sketch-Anime) | 568MB | Hand-drawn 2D anime sketch: rough textured outlines, minimalist flat colour, white outline. Drop the word "anime" from the prompt for a western sketch look. |
| `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | [`Comfy-Org/MiniMax-H3`](https://huggingface.co/Comfy-Org/MiniMax-H3) | 1.9GB | Official **ref2v** 4-step turbo acceleration. Match the variant to the graph — this is the ref2v one; the `fl2v_*` files in the same repo are for the first/last-frame model. |
| `h3_camera_motion_v1_3000_pruned.safetensors` | [`Jojocodex/minimax-h3-Camera-Motion-lora`](https://huggingface.co/Jojocodex/minimax-h3-Camera-Motion-lora) | 147MB | Camera-move obedience (push in, orbit, crane, whip pan). Author's guidance: 0.8 gentle, 1.0 explicit, >1.2 unstable. |
| `h3_spatial_physics_clean_3000_pruned.safetensors` | [`Jojocodex/minimax-h3-spatial-physics-lora`](https://huggingface.co/Jojocodex/minimax-h3-spatial-physics-lora) | 147MB | Body/contact weight and spatial coherence. Pairs with the V4 spatial plan when characters interact physically. |

Opt-in (`STYLE_LORA_COMMUNITY=1`) — weights mirrored from Civitai by
[`EllaPriest45/MinimaxH3_Styles`](https://huggingface.co/EllaPriest45/MinimaxH3_Styles);
H3-native and useful, but provenance/licence belong to the original authors, so
review before any commercial use:

| File | Size | What it does |
|---|---|---|
| `h3_painterly.safetensors` | 295MB | Painterly rendering — brush texture over form. The closest match for semi-realistic fantasy concept art. |
| `h3_anime_flat_style.safetensors` | 147MB | Flat anime shading: large flat colour fields, minimal gradient. |

## Presets

Slot 1 / 2 / 3 map to the three `LoraLoaderModelOnly` nodes in
`workflows/comfyui/minimax-h3-r2v-style-lora.json`, top to bottom. Strength
`0.0` disables a slot.

### P1 — 2D storybook illustration
Warm painted picture-book pages that move.

| Slot | LoRA | Strength |
|---|---|---|
| 1 | `studio1939-light` | 0.85 |
| 2 | — | 0.0 |
| 3 | turbo (optional) | 0.0 or 0.9 |

Prompt spine: *"hand-painted 2D storybook illustration, gouache texture on paper,
soft warm palette, hand-inked contour lines, flat lighting, gentle held poses"*.

### P2 — Folk illustration + flat geometric shapes
Woodcut/folk-art feel: bold flat shapes, limited palette, decorative pattern.

| Slot | LoRA | Strength |
|---|---|---|
| 1 | `studio1939-strong` | 0.9 |
| 2 | `minimax_h3_looping_sketch_anime_v1` | 0.35 |
| 3 | turbo (optional) | 0.0 or 0.9 |

Prompt spine: *"folk-art illustration, flat geometric shapes, bold simplified
silhouettes, three-colour limited palette, decorative repeating pattern,
screen-print flatness, no gradients, no rendered volume"*.
Slot 2 at low strength supplies the visible outline; above ~0.5 it turns the
frame into a sketch and breaks the flat-shape read.

### P3 — Vintage editorial / storybook
Mid-century print look: muted inks, halftone grain, cropped editorial staging.

| Slot | LoRA | Strength |
|---|---|---|
| 1 | `studio1939-light` | 0.7 |
| 2 | `minimax_h3_looping_sketch_anime_v1` | 0.3 |
| 3 | turbo (optional) | 0.0 or 0.9 |

Prompt spine: *"vintage editorial illustration, 1950s print, muted ochre and
teal ink, visible halftone grain and misregistered plates, textured paper,
graphic cropped composition"*.

### P4 — Semi-realistic fantasy concept art (painterly, anime-influenced)
Character-design plates that hold up at close range.

| Slot | LoRA | Strength |
|---|---|---|
| 1 | `h3_painterly` (community) | 0.8 |
| 2 | `h3_anime_flat_style` (community) | 0.3 |
| 3 | turbo (optional) | 0.0 or 0.9 |

Without the community LoRAs, approximate with `studio1939-light` at 0.5 and
carry the rest in the prompt:
*"semi-realistic fantasy character concept art, painterly digital rendering,
visible brushwork, anime-influenced facial structure with large expressive eyes,
rim light and volumetric haze, muted desaturated fantasy palette,
material-accurate leather and metal"*.

Add `h3_spatial_physics_clean_3000_pruned` at 0.5–0.7 in a free slot for
combat/contact-heavy generations, and `h3_camera_motion_v1_3000_pruned` at
0.8 when the shot needs a specific camera move.

## Rules

1. **One preset per episode.** The style LoRA is part of the continuity
   contract, exactly like character sheets.
2. **Total style strength ≤ ~1.2** across slots 1+2. Beyond that H3 loses
   reference adherence and the storyboard sheet stops steering composition.
3. **Turbo changes sampling, not style.** When slot 3 is on, drop the sampler to
   4 steps in `BasicScheduler`; leaving it at 20+ steps with turbo on burns time
   and over-sharpens.
4. **Style words still matter.** These LoRAs bias rendering; the storyboard
   sheet and the prompt spine still carry composition, palette and staging.
   Repeat the style spine verbatim in every generation of the episode.
5. **Do not stack more than two style LoRAs.** The third slot is for turbo or a
   directing LoRA.
