# ComfyUI API Pitfalls — Qwen Image Edit 2511

Complete list of issues discovered during testing (2026-05-18). Each caused a real failure.

## 1. Model File Paths Need Prefixes

The workflow JSON stores bare filenames, but the API requires full paths for some model types.

| Node Type | Workflow Value | API Value |
|---|---|---|
| CLIPLoader | `qwen_2.5_vl_7b_fp8_scaled.safetensors` | `split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors` |
| VAELoader | `qwen_image_vae.safetensors` | `split_files/vae/qwen_image_vae.safetensors` |
| UNETLoader | `qwen_image_edit_2511_fp8_e4m3fn.safetensors` | Same (no prefix needed) |
| LoraLoaderModelOnly | `Qwen-Image-Lightning-4steps-V2.0.safetensors` | Same (no prefix needed) |

**How to discover**: Check `/object_info/{NodeType}` — the enum values in `required` inputs show valid paths.

## 2. ImageResizeKJv2 Input Names Are Non-Obvious

The node's widget names in the saved workflow JSON differ from what the API expects.

| Workflow Key | API Key | Valid Values |
|---|---|---|
| `interpolation` | `upscale_method` | `nearest-exact, bilinear, area, bicubic, lanczos, nvidia_rtx_vsr` |
| `resize_mode` | `keep_proportion` | `stretch, resize, pad, pad_edge, pad_edge_pixel, crop, pillarbox_blur, total_pixels` |
| `fill_color` / `fill_color2` | `pad_color` | `"0, 0, 0"` (RGB string) |

**Also**: `keep_proportion` does NOT accept `True/False` — must be an enum value.

## 3. FluxKontextMultiReferenceLatentMethod Key Name

The workflow stores this as `mode`, but the API expects `reference_latents_method`.

**Error if wrong**: `required_input_missing` validation error.

Valid values: `offset, index, uxo/uno, index_timestep_zero`

## 4. SaveImage/PreviewImage Required

API returns `prompt_no_outputs` error if no output node exists. At minimum, include a SaveImage node.

```json
"214": {"class_type": "SaveImage", "inputs": {
    "images": ["8", 0], "filename_prefix": "scene_001"
}}
```

## 5. LoadImage `upload` Widget Doesn't Exist in API

The UI shows an `upload` file picker widget, but this is NOT a valid API input. Including it in the workflow causes:

**Error**: `exception_during_inner_validation` — remove `upload` from LoadImage inputs.

Correct API format:
```json
"213": {"class_type": "LoadImage", "inputs": {"image": "hare_reference_sheet.png"}}
```

## 6. Image Output Indices (CRITICAL!)

ImageResizeKJv2 has 4 outputs:
- `[0]` = IMAGE tensor ← **USE THIS** for image inputs
- `[1]` = width (INT)
- `[2]` = height (INT)
- `[3]` = mask (MASK)

**If you use `[1]` as an image input**, you pass integer `1024` instead of the image tensor. This causes:
```
'int' object has no attribute 'movedim'
```

This is the most confusing pitfall because the workflow JSON's link format uses link IDs that don't directly map to output indices.

## 7. CFGNorm Output Name

The output is called `patched_model` (not `MODEL`). However, using index `[0]` in API format works fine since that's the first output regardless of name.

## 8. Cloudflare Blocks Python urllib

ComfyUI behind Cloudflare tunnels returns `403` with `error code: 1010` for Python's urllib/requests.

**Fix**: Always use `curl` via `subprocess.run()`:
```python
def curl_json(method, endpoint, base_url, data=None):
    cmd = ["curl", "-s", "-X", method, f"{base_url}{endpoint}"]
    if data:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout) if result.stdout.strip() else {}
```

## 9. Workflow JSON ≠ API Format

ComfyUI saves workflows in "workflow format" (`nodes[]` array + `links[]` array with link IDs). The API expects "API format" (`{node_id: {class_type, inputs}}` dict with direct node references like `["197", 0]`).

**Conversion**: Must manually map each node's widgets to inputs and trace link IDs → source node + output index.

The reverse is also true — you can't POST the workflow JSON to `/prompt` directly.

## 10. Any Switch (rgthree) Required

Nodes 184 and 205 are `Any Switch (rgthree)` that select between multiple inputs based on which is connected. Even though they seem like routing convenience, they're **required** in the API format — omitting them breaks the execution graph.

Inputs use any_01, any_02, any_03 (not named inputs):
```json
"184": {"class_type": "Any Switch (rgthree)", "inputs": {
    "any_01": ["179", 0], "any_02": ["171", 0], "any_03": ["162", 0]
}}
```

## Bonus: Converting Workflow → API Format

The easiest approach is to build the API format from scratch (as in `generate_scene.py`) rather than trying to auto-convert the workflow JSON. Key steps:

1. Extract all node types and their widget values from the workflow JSON
2. Build link map: `{link_id: (source_node_id, output_index)}`
3. For each node in execution order:
   - Convert widget values to API `inputs`
   - Replace link references with `["source_node_id", output_index]`
4. Add SaveImage output node
5. Validate against `/object_info/{NodeType}` for exact input names