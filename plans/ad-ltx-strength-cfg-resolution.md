# Assistant-director LTX strength, CFG, and 1920×1088

## Goal

Give the storyboard assistant director per-clip control over low-res image lock (`LTXVImgToVideoInplace` strength) and CFG, via constrained enums + code lookup. Raise default LTX output resolution to **1920×1088**.

## Design

### AD fields (per clip)

| Field | Values | Maps to |
|-------|--------|---------|
| `motion_class` | `talking`, `walking`, `horse_riding`, `forest_exploration`, `large_reveal`, `fast_action`, `general` | `i2v_strength` |
| `guidance` | `balanced`, `prompt_follow`, `strong` | `cfg` (both sampler passes) |

Resolved floats are stored on the clip (`i2v_strength`, `cfg`) at normalize time for reproducible renders.

### Strength lookup (`LTXVImgToVideoInplace`)

| motion_class | strength |
|--------------|---------:|
| talking | 0.80 |
| walking | 0.70 |
| horse_riding | 0.65 |
| forest_exploration | 0.70 |
| large_reveal | 0.60 |
| fast_action | 0.55 |
| general (default) | 0.70 |

FLF last-frame guide strength stays separate: default **0.85**, floored at `max(0.85, i2v_strength + 0.05)` so endpoints stay locked when first-frame lock is high.

### CFG lookup

| guidance | cfg |
|----------|----:|
| balanced (default) | 1.0 |
| prompt_follow | 1.2 |
| strong | 1.5 |

Ceiling **1.5** — do not expose higher values to the AD.

### Resolution

- Default `VIDEO_WIDTH=1920`, `VIDEO_HEIGHT=1088` (divisible by 32).
- Two-pass graph already uses `a/2` → low-res stage becomes **960×544**.
- Env overrides: `VIDEO_WIDTH` / `VIDEO_HEIGHT`.

## Touch points

1. `tools/ltx_render_params.py` — lookup + resolve helpers
2. `schemas/generation.py` — `DirectorClip` fields
3. `flf_storyboard_planner.py` + prompt + director bible — AD emits enums; normalize resolves floats
4. `workflow_builder.py` + templates — apply `i2v_strength` + both CFGGuiders
5. `comfyui_tools.py` + `config.py` — resolution + pass params
6. `storyboard_director_nodes.py` — pass resolved params into generators
7. Tests for lookup, normalize, and builder overrides
