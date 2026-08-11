# MiniMax H3 — ComfyUI Setup Discovery (2026-08-03)

The H3 ("Hailuo" v3, MiniMax's general-purpose omni-modal model) workflow class
hit ComfyUI on **2026-08-03** via PR #15224. This reference documents:

1. How to detect that a workflow's "new" node is actually a comfy-core master class
   (not a separate pack)
2. The exact model set + sizes + repo
3. Workflow-class quirks (subgraph, optional frame inputs, native audio)
4. Why Phase 0 (master upgrade) is mandatory, and the version floor

## Detection recipe: "is this new node in comfy-core or a separate pack?"

Before searching GitHub for a custom-node pack, check the comfy-core source on
master. The node is in core if and only if `comfy_extras/<file>.py` defines it:

```bash
# 1. Find every non-core-looking class in the workflow JSON
python3 -c "
import json
wf = json.load(open('<workflow>.json'))
known_core = {
  'SaveVideo','SaveAudio','SaveImage','VAELoader','VAEDecode','VAEDecodeAudio',
  'KSamplerSelect','BasicScheduler','SamplerCustomAdvanced','BasicGuider',
  'UNETLoader','CLIPLoader','RandomNoise','CreateVideo','LoadImage',
  'ResolutionSelector','PrimitiveFloat','ComfyMathExpression',
  'MarkdownNote','Note','Reroute',
}
for n in wf['nodes']:
    if n.get('type') not in known_core:
        print(f\"  {n['type']} (id={n['id']})\")
for sg in wf.get('definitions', {}).get('subgraphs', []):
    for n in sg.get('nodes', []):
        if n.get('type') not in known_core:
            print(f\"  subgraph: {n['type']} (id={n['id']})\")
"

# 2. For each unknown class, check if comfy-core master has the class via raw URL
curl -sS -m 10 "https://raw.githubusercontent.com/comfyanonymous/ComfyUI/master/comfy_extras/nodes_<family>.py" | grep "^class "
```

**Faster alternative** — for each unknown class, just check the most likely
file in `comfy_extras/` directly. If the class name has a recognizable prefix
(MiniMax*, Flux*, Wan*, LTX*, Ideogram*, etc.) or the workflow's model set
matches a known family, look in the obvious file first.

**Why this matters** — searching GitHub for a "MiniMaxH3 custom node" pack
returns 404s (`kijai/ComfyUI-MiniMax-H3`, `MiniMax-AI/ComfyUI-MiniMax-H3`, etc.
— all non-existent as of 2026-08-03). The node is in
`comfy_extras/nodes_minimax_h3.py`. An agent that doesn't check master first
will waste 5-10 minutes looking for a pack that doesn't exist.

**Confirm the version floor** by checking the first commit on the file and the
first tag that contains it:

```bash
# First commit that added the file
curl -sS "https://api.github.com/repos/comfyanonymous/ComfyUI/commits?path=comfy_extras/<file>.py&per_page=1" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['commit']['author']['date'], '-', d[0]['commit']['message'].split(chr(10))[0])"

# First tag that contains it (walk tags newest-to-oldest, break on first 200)
for tag in v0.30.1 v0.30.0 v0.29.2 v0.29.0; do
  status=$(curl -sS -o /dev/null -w "%{http_code}" "https://raw.githubusercontent.com/comfyanonymous/ComfyUI/$tag/comfy_extras/<file>.py")
  echo "  $tag: HTTP $status"
done
```

H3 → added 2026-08-03, first released in **v0.30.0**. Vast base image ships
v0.23.0, so Phase 0 is mandatory.

## H3 model set (single repo: `Comfy-Org/MiniMax-H3`)

| Loader | File | Size | Subdir |
|---|---|---|---|
| `UNETLoader` (default) | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | ~20 GB | `diffusion_models/` |
| `CLIPLoader` (type=minimax) | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | ~15 GB | `text_encoders/` |
| `VAELoader` (video) | `minimax_h3_video_vae_fp16.safetensors` | ~5 GB | `vae/` |
| `VAELoader` (audio, `audio_vae`) | `minimax_h3_audio_vae_fp32.safetensors` | ~0.6 GB | `vae/` |

**Total: ~40.5 GB** on disk. Repo is public, ungated — no auth needed.

The `fl2va` in the diffusion filename stands for "first/last frame to
video+audio" — H3's first-frame, last-frame, and reference-to-video nodes
all share the same packed-DiT weights, just with different task-conditioning
flags. So a single download covers the whole H3 family.

## H3 workflow-class quirks (what trips agents up)

1. **Subgraph wrapper.** The official H3 workflow wraps the actual model graph
   in a `definitions.subgraphs[0]` entry. The parent graph's loader/sampler
   nodes are mostly placeholders (MarkdownNotes + a single SaveVideo). The
   real model loading happens inside the subgraph.

2. **`first_frame` and `last_frame` inputs are OPTIONAL** (`shape: 7` =
   optional in ComfyUI's IO system). The JSON filename "i2v" is misleading —
   this is a pure text-to-video workflow if you don't connect image inputs.
   Don't pre-flight "missing input file" bugs for H3 — there are none.

3. **Hardcoded sample prompt inside the subgraph.** The
   `MiniMaxH3ImageToVideo` node's `widgets_values[0]` is a Vaporwave title
   sequence example. The user-facing prompt is the **parent** node's
   `widgets_values[0]` (e.g. the action movie trailer prompt in the
   `video_minimax_h3_t2v.json` test case). When auditing the workflow, both
   need to be checked.

4. **Native audio output.** H3 is an **omni-modal** packed-DiT — the audio
   VAE output is real stereo audio (voice, SFX, music modeled jointly), not
   "video + audio tacked on". `CreateVideo` in the subgraph takes both
   `images` AND `audio` inputs. Both VAEs (video and audio) are required —
   skipping the audio VAE means a silent stream.

5. **Frame count = 17k+5 grid.** H3 samples at 24fps with a 17-frame-per-block
   structure. The ComfyUI node uses a `ComfyMathExpression` to snap the
   user's duration to `max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17`.
   Max output ≈ 15 seconds on the highest-VRAM cards.

6. **Canvas: 768-short-edge, 768×1344 max area.** The subgraph's
   `ResolutionSelector` already constrains this. Going above triggers the
   `MAX_PIXELS = 768*1344` check in `comfy_extras/nodes_minimax_h3.py`.

## Required Phase 0 floor for H3

```bash
# In Phase 0 of any H3 setup script:
NEEDS_UPGRADE=false
if [ "$CURRENT_VERSION" = "unknown" ] || ! ver_ge "$CURRENT_VERSION" "v0.30.0"; then
  NEEDS_UPGRADE=true
fi
```

`ver_ge` is defined in `vast-workflow-script-standards` § "Phase 0". Plain
`git stash` (not `--include-untracked` — pitfall 19, would clobber
`.venv-cu128/`).

## Required custom node pack count for H3

**Zero.** H3 is 100% comfy-core master. No `git clone` of any pack needed.
The Phase 1 block should be empty (or just a comment) — same as
`ideogram-4-t2i.sh` and `ace-step-15-t2a-song.sh`.

## Reference script

`workflows/setup/minimax-h3-t2v.sh` (commit `db32afe`, 2026-08-03) in
`muneesraja/auto-startups-vast` is the canonical 4-model download + Phase 0
master upgrade script for H3. Use it as the template for any future H3-family
workflow (H3 t2v, i2v, ref2v all share the same model set).

## Pre-built verification probes

These are the exact probes used to confirm the H3 model set + version floor.
Future agents can copy them into a session:

```bash
# Verify all 4 model URLs are live, ungated, and report sizes
python3 -c "
import urllib.request, json
models = [
  ('diffusion_models', 'minimax_h3_fl2va_pruned_int8_convrot.safetensors'),
  ('text_encoders',     'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'),
  ('vae',               'minimax_h3_video_vae_fp16.safetensors'),
  ('vae',               'minimax_h3_audio_vae_fp32.safetensors'),
]
for sub, fname in models:
    req = urllib.request.Request(
        f'https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/{sub}/{fname}',
        method='HEAD')
    r = urllib.request.urlopen(req, timeout=10)
    size_mb = int(r.headers.get('Content-Length', 0)) / 1024 / 1024
    print(f'  {size_mb:>8.2f} MB  {sub}/{fname}')

# Repo-level check
body = json.loads(urllib.request.urlopen(
    'https://huggingface.co/api/models/Comfy-Org/MiniMax-H3', timeout=10).read())
print(f'  gated={body.get(\"gated\", False)}  private={body.get(\"private\", False)}')
"
```

```bash
# Verify which ComfyUI tag first includes the H3 file
for tag in v0.30.1 v0.30.0 v0.29.2 v0.29.0; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' \
    "https://raw.githubusercontent.com/comfyanonymous/ComfyUI/$tag/comfy_extras/nodes_minimax_h3.py")
  echo "  $tag: HTTP $code"
done
```

```bash
# Confirm the node classes are in the file
curl -sS "https://raw.githubusercontent.com/comfyanonymous/ComfyUI/v0.30.1/comfy_extras/nodes_minimax_h3.py" | grep "^class "
# → EmptyMiniMaxH3LatentAV, MiniMaxH3ImageToVideo, MiniMaxH3ReferenceToVideo,
#   MiniMaxH3SigmaShift, MiniMaxH3Extension
```

## Future-work flag

If ComfyUI ships a v0.30.0+ official Docker image before the next H3 workflow
script needs provisioning, the Phase 0 block becomes a no-op. Watch
`comfyui-remote-mgmt` for that release and consider downgrading the Phase 0
to a version check only (not a checkout).
