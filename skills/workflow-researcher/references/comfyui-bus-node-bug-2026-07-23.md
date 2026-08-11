# ComfyUI GetNode / SetNode Bus Pattern — Bug Class & Rewriter

**Date discovered:** 2026-07-23 (SCAIL2-WORKFLOW.json, pod 194.14.47.19)
**Affects:** Any ComfyUI workflow using KJNodes' "named bus" pattern for passing
data through a graph — typically authored in the ComfyUI web UI by drag-from-wire.

## The bug class

KJNodes (kijai/ComfyUI-KJNodes) advertises a SetNode / GetNode feature in its
README and adds the right-click menu entries in the frontend:

> Add Set/Get from connection menu — When dragging from a slot, "Add SetNode" and
> "Add GetNode" entries appear next to "Add Reroute" in the connection menu.

**But `SetNode` and `GetNode` are NOT exported as Python node classes** in
KJNodes' `__init__.py` or `nodes/nodes.py`. They are a **frontend-only UI
feature** — the editor serializes them to JSON when you save the workflow, but
the Python loader never registers a class for them. Loading the workflow JSON
on a fresh pod shows 17 "Missing Node Type" red boxes and every downstream
input that was wired to a GetNode silently breaks.

The community workaround recommended in the [KJNodes issue tracker](https://github.com/kijai/ComfyUI-KJNodes/issues/161)
is to rewrite the JSON to use `easy getNode` / `easy setNode` from
yolain/ComfyUI-Easy-Use — but those classes **were removed from ComfyUI-Easy-Use
in 2026**. So no currently-maintained pack provides them.

## Symptom

- Workflow JSON opens in ComfyUI UI with red "Missing Node Type" boxes for
  every GetNode / SetNode reference.
- `curl http://localhost:8188/object_info | jq 'keys[]' | grep -i 'getnode\|setnode'`
  returns nothing.
- Downstream nodes (WanSCAILToVideo, BasicScheduler, VHS_VideoCombine,
  ImageResizeKJv2) all show as having **no connected input** even though the
  workflow JSON's `links[]` array references valid node IDs.
- The graph will NOT execute — ComfyUI returns
  `prompt_validation_errors: validation_failed` on `POST /prompt`.

## Detection recipe (run before launching any workflow)

```python
import json, urllib.request

# 1. Scan the workflow for GetNode/SetNode
with open('<workflow>.json') as f:
    wf = json.load(f)
gs = [n for n in wf['nodes'] if n['type'] in ('GetNode', 'SetNode')]
if gs:
    print(f"⚠️  Workflow has {len(gs)} GetNode/SetNode references")
    # Show the names so you can confirm the bus pattern
    for n in gs[:10]:
        name = n.get('widgets_values', [''])[0]
        print(f"   {n['type']} name='{name}' id={n['id']}")

# 2. Confirm the live ComfyUI does NOT register them
oi = json.loads(urllib.request.urlopen('http://localhost:8188/object_info').read())
missing_in_api = [c for c in ('GetNode', 'SetNode', 'easy getNode', 'easy setNode')
                  if c not in oi]
print(f"Classes missing from /object_info: {missing_in_api}")
# If both queries show hits, the workflow WILL fail to execute.
```

## Fix: rewire the bus pattern to direct wires

The rewriter at `scripts/fix_get_set_nodes.py` (this skill) automates the fix.

**What it does:**
1. For each `(SetNode name, GetNode name)` pair, find the upstream source
   feeding the SetNode.
2. Replicate each GetNode output link, replacing the source (GetNode) with
   the SetNode's upstream source.
3. Delete all SetNode and GetNode nodes + their internal links.
4. Renumber link IDs sequentially + update every `inputs[].link` reference.

**Result:** identical graph semantics, no GetNode/SetNode pack required.

**Usage:**
```bash
python3 scripts/fix_get_set_nodes.py <workflow.json> -o <fixed.json>
# or overwrite in place:
python3 scripts/fix_get_set_nodes.py <workflow.json> -i
```

**Real example** (SCAIL2-WORKFLOW.json, 2026-07-23):
- Before: 63 nodes, 91 links, 17 GetNode/SetNode references
- After:  46 nodes, 86 links, 0 GetNode/SetNode references, 14 output links rewired
- Result: workflow loads cleanly, all 29/30 node classes present in
  `/object_info` (the one "missing" is `Note`, a documentation node removed
  from comfy-core master in 2026-07, doesn't affect execution)

## Permanent fix for workflow authors

**Don't use SetNode/GetNode in new workflows.** ComfyUI's editor has a
"drag from a wire" gesture (hold shift, drag, release) that creates an
instant duplicate link without a Reroute node. If you need a single source
to feed multiple consumers, just drag wires from the source output slot to
each consumer's input slot directly. Saves a pack dependency, saves a bug
class, and the workflow works on every ComfyUI install.

If you're authoring for KJNodes and want the bus pattern, KJNodes maintainer
Kijai has stated he considers the feature a frontend UI niceness, not a
public API — the absence of Python classes is by design.

## Filesystem aftermath of the bug

If you already ran the broken workflow and have orphan Set/Get nodes in
`custom_nodes/<some-pack>/`, they don't hurt anything — the dirs just sit
there. Clean up with:
```bash
# On the pod:
ls /workspace/runpod-slim/ComfyUI/custom_nodes/  # should NOT have a "bus_nodes" or similar
# If you find one you suspect was added specifically for the GetNode/SetNode classes:
rm -rf /workspace/runpod-slim/ComfyUI/custom_nodes/<pack>
# And re-clone if you still need the rest of the pack's nodes.
```

## Related issues and references

- https://github.com/kijai/ComfyUI-KJNodes/issues/161 — original report,
  community suggests `easy getNode`/`easy setNode` rewrite, no longer works
- https://github.com/Comfy-Org/ComfyUI/issues/6402 — same symptom, different
  workflow, confirmed kijai's KJNodes has no exported classes
- https://github.com/kijai/ComfyUI-KJNodes/issues/342 — "Nodes missing"
  report, same fix workflow applies
- `references/scail-2-wan-discovery-2026-07-23.md` — the SCAIL-2-specific
  workflow where this bug was hit; the SCAIL-2 reference describes
  discovery + downloads, this reference describes the rewire fix

## Companion to the rewriter

The rewriter is intentionally small (one file, no deps, `python3 fix_get_set_nodes.py
<wf.json>`). It does NOT need to be in the agent's primary toolchain — the
agent can `subprocess.run` it from any Python script that needs to fix a
workflow before launching it. It also doesn't depend on a running ComfyUI;
it's a pure JSON transform.
