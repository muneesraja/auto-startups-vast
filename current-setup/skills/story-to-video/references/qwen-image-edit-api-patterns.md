# Qwen Image Edit API Patterns — Multi-Reference & Batch Generation

Session: 2026-05-18, tested against Qwen Image Edit 2511 4-step on mandi-qwen.muneesraja.com (RTX 3090)

## API Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/prompt` | POST | Queue a generation prompt |
| `/history/{id}` | GET | Check prompt status + get outputs |
| `/view` | GET | Download output image (`?filename=X&type=output`) |
| `/upload/image` | POST | Upload image to instance input dir |
| `/object_info/{node_type}` | GET | Get node's input/output spec + valid values |
| `/system_stats` | GET | GPU/device info |

## Multi-Reference Image Selection Pattern

The workflow has 3 LoadImage slots (nodes 213, 175, 182) each feeding into ImageResizeKJv2 → VAEEncode → ReferenceLatent chain.

```python
AVAILABLE_ON_INSTANCE = {"hare_reference_sheet.png", "tortoise_reference_sheet.png", ...}
REF_IMAGES = {"hare": "hare_reference_sheet.png", "tortoise": "tortoise_reference_sheet.png", ...}
FALLBACKS = {"fox": "tortoise_reference_sheet.png"}  # missing chars → closest available

def pick_images(characters):
    images = []
    for c in characters:
        ref = REF_IMAGES.get(c)
        if ref and ref in AVAILABLE_ON_INSTANCE:
            images.append(ref)
        else:
            images.append(FALLBACKS.get(c, "example.png"))
    unique = list(dict.fromkeys(images))  # dedupe preserving order
    while len(unique) < 3:
        unique.append(unique[0] or "example.png")
    return unique[:3]
```

## Checking Available Images

```bash
curl -s "$COMFY_URL/object_info/LoadImage" | python3 -c "
import json, sys
data = json.load(sys.stdin)
images = data['LoadImage']['input']['required']['image'][0]
for img in images: print(f'  - {img}')
"
```

## Upload Pattern

```bash
curl -s -X POST "$COMFY_URL/upload/image" \
  -F "image=@local_image.png" \
  -F "overwrite=true"
```

## Queue → Poll → Download Pattern

```python
import json, subprocess, time, os

def curl_json(method, endpoint, base_url, data=None):
    cmd = ["curl", "-s", "-X", method, f"{base_url}{endpoint}"]
    if data:
        cmd.extend(["-H", "Content-Type: application/json", "-d", json.dumps(data)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return json.loads(result.stdout) if result.stdout.strip() else {}

def wait_for_prompt(prompt_id, base_url, poll_interval=5, max_wait=180):
    start = time.time()
    while time.time() - start < max_wait:
        data = curl_json("GET", f"/history/{prompt_id}", base_url)
        if prompt_id in data:
            info = data[prompt_id]
            status = info.get("status", {}).get("status_str", "unknown")
            if status == "success":
                return info.get("outputs", {})
            elif status == "error":
                msgs = info.get("status", {}).get("messages", [])
                raise RuntimeError(f"Execution error: {json.dumps(msgs)[:500]}")
        time.sleep(poll_interval)
    raise TimeoutError(f"Prompt {prompt_id} timed out after {max_wait}s")

def download_output(filename, output_path, base_url, subfolder=""):
    url = f"{base_url}/view?filename={filename}&subfolder={subfolder}&type=output"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    subprocess.run(["curl", "-s", "-o", output_path, url], timeout=60)
    return os.path.exists(output_path)
```

## Error Handling Patterns

### Validation Errors (pre-execution)

```python
result = curl_json("POST", "/prompt", base_url, data={"prompt": workflow})
if "error" in result:
    err = result["error"]
    node_errors = result.get("node_errors", {})
    for nid, errs in node_errors.items():
        for e in errs.get("errors", []):
            print(f"Node {nid}: {e.get('details', e.get('message', ''))}")
```

Common validation errors:
- `value_not_in_list` — model/image filename not found on instance → check `/object_info`
- `required_input_missing` — missing widget that exists in `/object_info` but not in API format
- `prompt_no_outputs` — add SaveImage node
- `exception_during_inner_validation` — missing node referenced by link → include all functional nodes

### Execution Errors (during generation)

Check `/history/{prompt_id}` for `status.status_str == "error"` and parse `status.messages`.

Common execution error:
- `'int' object has no attribute 'movedim'` — wrong output index (used [1]=width instead of [0]=image)

## Timing

- **Per scene**: ~20-30 seconds on RTX 3090 (4-step Lightning)
- **6 scenes**: ~3 minutes total (sequential)
- **Prompt queue**: instant
- **Polling**: 5-second intervals recommended

## Manifest-Driven Usage

```bash
# Generate all scenes from a story manifest
python3 generate_scene.py \
  --manifest /path/to/story_manifest.json \
  --all \
  --url https://mandi-qwen.muneesraja.com \
  --output-dir /root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/hare-and-tortoise/scenes

# Generate a single scene
python3 generate_scene.py --manifest story_manifest.json --scene 1 --seed 42
```

The script auto-loads `story_manifest.json`, builds prompts from character identity_specs and scene descriptions, checks available images on the instance, and handles fallbacks for missing reference sheets.