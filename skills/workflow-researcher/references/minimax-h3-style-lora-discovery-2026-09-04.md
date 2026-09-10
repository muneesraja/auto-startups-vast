# MiniMax H3 illustration style LoRA discovery — 2026-09-04

Scope: find every model / LoRA / node needed to give **story-maker-v4** the four
requested looks on **MiniMax H3 only** (no Flux, SDXL, Qwen-Image or LTX
substitutes):

1. 2D storybook illustration
2. Folk illustration + flat geometric shapes
3. Vintage editorial / storybook
4. Semi-realistic fantasy character concept art, painterly, anime-influenced

Artifacts produced:

- `workflows/comfyui/minimax-h3-r2v-style-lora.json`
- `workflows/setup/minimax-h3-r2v-style-lora.sh`
- `skills/story-maker-v4/assets/style-lora-presets.md`
- `skills/story-maker-v4/tests/test_style_lora_workflow.py`

## §1 The hard constraint

H3 is a single packed DiT. A LoRA is an adapter of H3's own tensors, so **only
`base_model:adapter:MiniMaxAI/MiniMax-H3` or `…:Comfy-Org/MiniMax-H3` repos
load.** Every high-quality storybook / folk / flat-vector / painterly LoRA found
on the Hub (`artificialguybr/KidsBook-Redmond-FLUXKLEIN9B`,
`alvdansen/illustration-1.0-flux-dev`, `Shakker-Labs/FLUX.1-dev-LoRA-Vector-Journey`,
`renderartist/simplevectorflux`, `Muapi/storybook-folk-art`,
`strangerzonehf/Flux-Midjourney-Painterly-LoRA`, `Yulldesign/flux-style-lora-modern-minimalist`)
is a **Flux/SDXL adapter and is unusable here**. They are listed only so a future
reader does not re-discover them and try to wire them in. If those exact styles
are ever required, they belong on the *image* side of V4 (storyboard sheets via
Replicate/fal), not on the H3 render.

Enumerate the real candidate set with the adapter filter, not free-text search:

```bash
curl -sG https://huggingface.co/api/models \
  -d 'filter=base_model:adapter:MiniMaxAI/MiniMax-H3' \
  -d sort=downloads -d direction=-1 -d limit=100 | jq -r '.[].id'
curl -sG https://huggingface.co/api/models \
  -d 'filter=base_model:adapter:Comfy-Org/MiniMax-H3' \
  -d sort=downloads -d direction=-1 -d limit=100 | jq -r '.[].id'
```

That returns ~70 repos total. Filtering out NSFW packs, turbo/acceleration
variants, prompt-rewriter LLM LoRAs and quantization mirrors leaves **fewer than
ten style LoRAs in the entire H3 ecosystem** as of this date. There is no
folk-art, flat-geometric or vintage-editorial H3 LoRA; those looks must be
assembled from the general painterly/cel LoRAs plus prompt spine.

## §2 Selected manifest (all HEAD-verified 200)

Base stack — `Comfy-Org/MiniMax-H3`, unchanged from `minimax-h3-t2v.sh`:

| File | Size |
|---|---|
| `diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 19998MB |
| `text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | 25884MB |
| `vae/minimax_h3_video_vae_fp16.safetensors` | 4966MB |
| `vae/minimax_h3_audio_vae_fp32.safetensors` | 577MB |

Style + directing LoRAs:

| Repo | File | Size | Role |
|---|---|---|---|
| `lovis93/studio-1939-old-animation-lora-minimax-h3` | `studio1939-light.safetensors` | 62MB | r16 painterly storybook — looks 1 and 3 |
| same | `studio1939-strong.safetensors` | 250MB | r64 flat cel over painted BG — look 2 |
| `Inner-Reflections/MiniMax-H3-Looping-Sketch-Anime` | `minimax_h3_looping_sketch_anime_v1.safetensors` | 568MB | rough outline + flat colour accent |
| `Comfy-Org/MiniMax-H3` | `loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | 1865MB | official **ref2v** 4-step turbo |
| `Jojocodex/minimax-h3-Camera-Motion-lora` | `camera_motion_h3_lora_v1_3000_pruned.safetensors` | 147MB | camera-move obedience, 0.8–1.0 |
| `Jojocodex/minimax-h3-spatial-physics-lora` | `wushu_spatial_physics_clean_3000_pruned.safetensors` | 147MB | contact weight / spatial coherence |

Opt-in (`STYLE_LORA_COMMUNITY=1`), `EllaPriest45/MinimaxH3_Styles` — a Civitai
backup mirror (its README states exactly that). Weights are H3-native and the
only direct hits for looks 3 and 4, but licence/provenance sit with the original
authors:

| File | Size | Role |
|---|---|---|
| `Painterly - MinimaxH3.safetensors` | 295MB | painterly rendering — look 4 |
| `Anime Flat Style - MinimaxH3.safetensors` | 147MB | flat anime shading |

Filenames in that repo contain spaces and commas, so the setup script's
`hf_lora` helper renames them to `h3_painterly.safetensors` /
`h3_anime_flat_style.safetensors` on the way into `models/loras/`.

## §3 Rejected H3-native candidates

| Repo | Why not |
|---|---|
| `DiffSynth-Studio/MiniMax-H3-LoRA-LineartAnime` | 1.2GB **lineart-video colourization** control LoRA — needs a line-art video input, not a storyboard sheet. Wrong pipeline shape for V4. |
| `TenStrip/Krea2-H3-Style-Lora` | Author states "only effective for pure T2V generations as a lora"; V4 is ref2va. |
| `fal/MiniMax-H3-Realism-People-LoRA` | Photoreal, opposite of the brief. |
| `ostris/minimax_h3_ref2va_jacked_lora` | Body-morph demo LoRA from a training tutorial. |
| `kabachuha/mh3-r2va-claymation-transformation` | Plasticine morph effect, not a persistent style. |
| `alvdansen/h3-keyframe-animation` | Gated repo — cannot be fetched unattended by a provisioning script. |
| `Hearmeman/minimax-h3-loras`, `nyxia/H3-Loras` | NSFW aggregators. |
| `larryvrh/…-Turbo-Lora`, `drbaph/…-ComfyUI`, `alibaba-pai/MiniMax-H3-Acc-LoRAs` | Acceleration only; the official Comfy-Org ref2v turbo is preferred because it matches the ref2va graph. |

`Comfy-Org/MiniMax-H3` also ships ten `embeddings/minimaxh3_*.safetensors`
motion embeddings (bullet time, spiral ascent, four seasons, …) at <2MB each.
Not wired in — they are motion effects, not styles — but they are the cheapest
future addition if a scene needs a specific camera stunt.

## §4 Graph wiring

`LoraLoaderModelOnly` is **comfy-core**; no custom pack is needed for the LoRA
chain itself. The graph is generated from `Minimax H3 R2V - Final - v2.json` by
retargeting link 291:

- before: `UNETLoader(127) → PathchSageAttentionKJ(154)`
- after: `UNETLoader(127) → Lora(159) → Lora(160) → Lora(161) → PathchSageAttentionKJ(154)`

`BasicScheduler(124)` deliberately keeps reading the **raw** UNET (link 252) —
this mirrors the shipped `Minimax_h3_4_step_lora.json`, where sigmas come from
the unpatched model.

Three slots, strength `0.0` = disabled. `tools/minimax_workflow.py` needs no
change: it converts the UI graph generically, and `_prune_unreachable` keeps the
LoRA chain because it is reachable from `SaveVideo` through the guider branch.
Selecting the style is therefore a pure workflow-JSON + `MINIMAX_H3_WORKFLOW`
concern, which keeps the renderer deterministic.

## §5 Gotchas

| Symptom | Cause / fix |
|---|---|
| `LoraLoaderModelOnly: value not in list` | The file is not in `models/loras/`, or its name still has the mirror's spaces/commas. Run the setup script; it renames on download. |
| LoRA loads but nothing changes | An `fl2v_*` turbo LoRA was installed against the **ref2va** UNet. Use `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`. |
| Storyboard sheet stops steering composition | Combined style strength above ~1.2. Keep slots 1+2 ≤ 1.2. |
| Over-sharpened, slow renders with turbo on | `BasicScheduler` still at 20+ steps. Turbo needs 4. |
| Style drifts between generations | A preset was changed mid-episode. The style LoRA is part of the continuity contract — freeze it per episode. |
