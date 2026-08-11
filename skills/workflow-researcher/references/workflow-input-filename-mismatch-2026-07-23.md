# ComfyUI Workflow Author-Time Filename Mismatch — Bug Class & Fix

**Date discovered:** 2026-07-23 (SCAIL2-WORKFLOW.json, pod 194.14.47.19, user: Lingesh)
**Affects:** Any third-party ComfyUI workflow with hardcoded filenames in `LoadImage` / `VHS_LoadVideo` widgets.

## The bug class

A workflow JSON authored on one user's machine gets shared with the world. The author drags their local files into the ComfyUI web UI; the editor saves the filenames verbatim into the workflow JSON:

```json
{ "type": "LoadImage",      "widgets_values": ["gg.png", "image"] }
{ "type": "VHS_LoadVideo",  "widgets_values": { "video": "less1.mp4", ... } }
```

`gg.png` and `less1.mp4` are whatever files happened to be on the author's desktop. They are NOT part of the model set, NOT auto-downloaded, NOT user-portable. When a new user loads the workflow, the loaders reference files that don't exist on their pod, and ComfyUI shows:

- "1 required model is missing" (in the workflow's red badge)
- "Some nodes are missing required inputs" (per-node)
- "Some nodes are missing" (the broader "Missing Node Type" banner — confusingly similar to the KJNodes GetNode/SetNode symptom but a different bug)

**The user reports the symptom as if models or nodes are missing, but actually their input file just has a different name.** This wastes diagnostic cycles chasing model-download issues when the real fix is one widget-value edit.

## Detection recipe (run on the user's pod, before assuming a node-pack or model-download issue)

```bash
# 1. What does the workflow's loaders want?
python3 << 'EOF'
import json
wf = json.load(open('/path/to/workflow.json'))
for n in wf['nodes']:
    if n['type'] == 'LoadImage':
        print(f"LoadImage id={n['id']} wants: {n['widgets_values'][0]!r}")
    elif n['type'] == 'VHS_LoadVideo':
        wv = n['widgets_values']
        if isinstance(wv, dict):
            print(f"VHS_LoadVideo id={n['id']} wants: {wv.get('video')!r}")
        else:
            print(f"VHS_LoadVideo id={n['id']} wants: {wv!r}")
EOF

# 2. What's actually in input/?
ssh -p $PORT -i ~/.ssh/id_ed25519 root@$HOST 'ls -la /workspace/runpod-slim/ComfyUI/input/ 2>/dev/null'

# 3. Cross-check: do the wanted files exist on disk?
```

If the wanted filename isn't in `ls input/` output, this is the bug. The user just uploaded a file with a different name.

## Symptom ladder (don't trust the error text at face value)

| User sees | Likely cause | Real fix |
|---|---|---|
| "Some nodes are missing" | KJNodes GetNode/SetNode bus pattern | Rewire with `scripts/fix_get_set_nodes.py` |
| "Some nodes are missing" | `Note` or `Reroute` class removed in comfy-core master | Delete `Note`; rewire `Reroute` to direct links |
| "1 required model is missing" | Workflow's `LoadImage` / `VHS_LoadVideo` references filenames the user didn't upload | Patch the workflow JSON's `widgets_values` |
| "Some nodes are missing required inputs" | Same as above — the loader has no source file, so the downstream node has no input | Same — patch the JSON |

The "Some nodes are missing" and "Some nodes are missing required inputs" banners look similar but are different. The first means the node class isn't registered; the second means a specific input on a registered node has no source wire/file.

## Fix: patch the workflow JSON

**Option 1 (one-off, fine for a single test):** Rename the user's uploaded file to match the workflow's hardcoded name. Use `ssh` to move the file inside `ComfyUI/input/`.

**Option 2 (preferred for shared workflows):** Edit the workflow JSON's `widgets_values` to point at the user's actual file. For `LoadImage`, change `widgets_values[0]`. For `VHS_LoadVideo`, change `widgets_values.video` AND `widgets_values.videopreview.params.filename` (VHS embeds preview metadata that the UI also reads).

```python
import json
with open('/path/to/workflow.json') as f:
    wf = json.load(f)
for n in wf['nodes']:
    if n['type'] == 'LoadImage' and n['widgets_values'][0] == 'gg.png':
        n['widgets_values'][0] = 'ChatGPT Image Jul 23, 2026, 12_51_57 PM.png'
    elif n['type'] == 'VHS_LoadVideo':
        wv = n['widgets_values']
        if wv.get('video') == 'less1.mp4':
            wv['video'] = 'ronaldo raw.mp4'
            if 'videopreview' in wv:
                wv['videopreview']['params']['filename'] = 'ronaldo raw.mp4'
with open('/path/to/workflow.json', 'w') as f:
    json.dump(wf, f, indent=2)
```

Commit the patched JSON to the workflow repo so future runs are clean.

## Why this is a class-level bug

This will hit every user who tries to run a shared workflow on a fresh pod. The fix is small (one or two widget values) but the symptom is misleading (looks like a node-pack or model issue), so it burns diagnostic time on the first encounter per workflow. Documenting the pattern saves future cycles.

## When authoring new workflows

- **Don't hardcode filenames in `LoadImage` / `VHS_LoadVideo` widgets** that aren't part of the bundled assets. If the user must provide their own input, leave the field empty so ComfyUI shows the file picker in the UI — or document the expected filename in a `MarkdownNote` next to the loader.
- **If the workflow needs a specific input file as part of the asset bundle** (e.g. a default reference image), include it in the setup script's `mkdir -p .../input && cp` step. Don't assume the file exists by default.
- **Test on a fresh pod** before publishing. The most common feedback on shared workflows is "your workflow doesn't work" — usually one of: missing input filename, KJNodes GetNode/SetNode, or removed `Note`/`Reroute` class. All three are detectable in 30 seconds with the right probes.

## Related

- `references/comfyui-bus-node-bug-2026-07-23.md` — the KJNodes GetNode/SetNode companion bug, which produces similar "Some nodes are missing" text but is a different class
- `references/scail-2-wan-discovery-2026-07-23.md` — the specific workflow that hit all three bugs (GetNode/SetNode + Note + input filename) on 2026-07-23
- `comfyui-remote-mgmt` skill — has a "Pitfall — workflow author-time filenames" section that links here
