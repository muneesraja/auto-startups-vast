# MiniMax H3 SelfLift / Sol-Attn graph — pack + model resolution (2026-10-13)

Source workflow: `workflows/comfyui/minimax/BUNNY_SelfLift_12GB1080P_LORA__1.json`
("BUNNY H3 高动态HQ双采专属双语版 v1.3", 31 nodes, FLAT `nodes[]`, no `extra.prompt`,
4 `mode:4` LoadImage references). Script produced:
`workflows/setup/minimax-h3-bunny-selflift-12gb-1080p-lora.sh` — a superset of the
Singularity/Semantic-Bridge script, 20 downloads, ~64.4GB measured.

## The three packs the standard H3 manifest does not cover

| Class in JSON | Pack | Notes |
|---|---|---|
| `SelfLiftAvatarH3Sampler`, `SelfLiftAvatarH3TST` | `slmonker/selflift-Avatar` | clone dir **must** be `selflift-Avatar` (README + users). Registers 3 ids; coexists with facok's `comfyui-SelfLift`. Zero pip deps. |
| `SolAttnMiniMax` | `xm6018924/BSAI-ComfyUI-Sol-H3` | file `sol_attn_minimax_v2.py`. NOT `kijai/ComfyUI-SolAttn_triton` (that one only exports `SolAttnPatch`/`SolAttnBlockProbe`). |
| `H3SigmaRefiner` | `yichengup/ComfyUI-YCNodes-MiniMax-H3` | `py/h3_sigma_refiner.py`; `__init__.py` self-imports all `py/*.py`. No requirements.txt. |

`ComfyMathExpression` (comfy_extras/nodes_math.py), `ResolutionSelector`
(nodes_resolution.py), `SaveVideo`/`CreateVideo` (nodes_video.py) and
`LoraLoaderBypassModelOnly` are all comfy-core — verify by class name in
`comfy_extras/`, never by searching GitHub for a pack.

## Sol-Attn prerequisites (fail-soft — a green log hides them)

`SolAttnMiniMax` imports `comfy_api.latest` at module top level and needs
`comfy_kitchen`'s CUDA `sol_attn` with the `sink_blocks` / `sink_q` / `tail`
arguments (>= 0.2.37) plus Triton 3.6+. Missing any of them is **not** an error:
the node logs `kernel failed (...) falling back` and samples with the dense
backend. Probe it in the setup script instead of trusting the log:

```bash
$COMFY_PYTHON - <<'PYEOF'
import inspect, comfy_kitchen as ck
from comfy_kitchen.backends import cuda as c
sig = inspect.signature(c.sol_attn).parameters
print(getattr(ck, "__version__", "?"), "sink_blocks" in sig, "tail" in sig)
PYEOF
```

The pack also ships an `install.py` that pip-installs comfy_kitchen and downloads a
~300MB "FastH3" 4-step LoRA into `models/loras/`. Do not run it — the workflow
brings its own turbo LoRA. A later ComfyUI-Manager pass may run it; harmless.

## Widget filenames that do not exist upstream → alias, never edit the JSON

Two cases in one graph. The rule (same as the `.comfy` rename pitfall) is: install
the canonical upstream weights under the widget's **exact stored name**.

| Widget value in JSON | What ships upstream | Fix in the setup script |
|---|---|---|
| `minimax_h3_latent_upscaler_3d_fp16_V2.safetensors` | only `minimax_h3_latent_upscaler_3d_conv_v1/…_fp16.safetensors` (LBH-123-AI `config.json` lists `3d_conv_v2` as `in_training`) | download v1 fp16, flatten to the canonical name, then `ln` → `_V2` name |
| `Motion_Repair.safetensors` | repo ships v1 **and** `Motion_Repair_V2.safetensors` — the repo standard is V2 | download V2, `ln` → `Motion_Repair.safetensors` |

`ln "$canonical" "$alias" 2>/dev/null || cp "$canonical" "$alias"` — idempotent, no
duplicate disk. This matters because `selflift-Avatar` scans
`models/latent_upscale_models/` for any filename containing `h3` and silently falls
back to `none` when the stored value is absent, which drops the learned latent lift
the whole SelfLift stage depends on.

## Audit-tool caveats hit on this script

- `audit_model_manifest.py` reports the diffusion file as **missing** when the script
  downloads it through a variable (`hf_download "$DIFFUSION_REPO" "$DIFFUSION_FILE" …`)
  — a known false positive, not a gap.
- `audit_base_dir_bug.py` flags any `BASE_DIR="$COMFYUI_DIR/models"` assignment, even
  when every `hf_download` pairing is nesting-safe (`"vae/x.safetensors" "$BASE_DIR"`,
  or a bare name with `"$BASE_DIR/loras"`). **Verify the pairing by hand before
  "fixing" it** — rewriting the variable without rewriting all ~20 call sites breaks
  every download. The Singularity script this was derived from carries the same flag.
- 4 `mode:4` `LoadImage` nodes are the user's own reference stills (Chinese filenames,
  one `None`) — disabled, never downloads; don't add input-file handling for them.
