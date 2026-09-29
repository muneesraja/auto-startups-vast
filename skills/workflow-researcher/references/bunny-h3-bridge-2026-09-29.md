# BUNNY H3 Conditioning Bridge (JOKER141 / FourBunny) — 2026-09-29

A MiniMax-H3 `CONDITIONING`-path residual adapter that plugs inline between the H3
text conditioning and the downstream node (in: CONDITIONING, out: CONDITIONING).
Targets what motion-repair LoRAs cannot fix: character/action ownership,
attacker-target confusion, object/weapon ownership, spatial continuity after a
position exchange, identity+state after occlusion, prompt/environment continuity.

Used by `minimax-h3-i2v-2stage-latent-upscale-Singularity-Semantic_Bridge.sh`.

## The two-orgs trap (check both independently, never assume)

| Thing | Location |
|---|---|
| **Node** (custom_nodes pack) | GitHub `aa335615543-ux/BUNNY_H3_Conditioning_Bridge` |
| **Adapters** (weights) | HF `JOKER141/BUNNY_H3_Conditioning_Bridge` |

A request phrased as "update the script with `JOKER141/BUNNY_H3_Conditioning_Bridge`"
names the **HF weights repo only**. The upstream README's install step names the
**GitHub** org instead. `JOKER141/...` 404s on GitHub; a GitHub repo does not exist
for the HF-style name. Neither org is a typo — check both:

```bash
curl -s   "https://huggingface.co/api/models/<org>/<repo>"   # siblings list + gated flag
curl -s -o /dev/null -w '%{http_code}\n' "https://api.github.com/repos/<org>/<repo>"
```

## Where the weights go (lookup order is in the node source, not the doc)

`nodes.py` resolves an adapter as: **bundled `<node_dir>/models/` FIRST**, then
external `folder_paths.models_dir/semantic_bridge/` (which the node registers
itself via `add_model_folder_path("semantic_bridge", ...)`). Both appear in the
`adapter` dropdown, deduped case-insensitively.

- Put the adapter in the **bundled** dir: it wins the lookup and it is what the
  README documents. The external dir still works (v0.1/0.2 backward compat).
- `_list_adapters()` force-moves `BUNNY_H3_ActionLogic_Bridge_V1.safetensors` to
  the top of the dropdown when present — treat V1 as the default.

## Node install: the folder name is not fixed

`pyproject.toml` sets `[tool.comfy] DisplayName = "BUNNY_H3_Conditioning_Bridge"`,
but registry installs (comfy-cli / Manager / Marketplace) use the project name
`bunny-h3-semantic-bridge`. A manual `git clone` lands as the canonical name.
**Resolve whichever exists** (test for `nodes.py`) — never hardcode the path, or
the models dir will not follow the actual folder:

```bash
for CAND in "$CUSTOM_NODES_DIR/bunny-h3-semantic-bridge" "$CUSTOM_NODES_DIR/BUNNY_H3_Conditioning_Bridge"; do
    [ -f "$CAND/nodes.py" ] && BUNNY_DIR="$CAND" && break
done
```

`[ -f x ] && A=y && break` inside a `for` is safe under `set -e` (commands in an
`&&` list are exempt) — verified by running the block under `set -e`; do not
"fix" it into an if-block for that reason.

## Adapter manifest

| File | Size | Notes |
|---|---|---|
| `BUNNY_H3_ActionLogic_Bridge_V1.safetensors` | 22.0M | Documented default; README install + Recommended settings + repo Example Workflow + the node's dropdown all pin V1 |
| `BUNNY_H3_ActionLogic_Bridge_V2.safetensors` | 22.0M | Rebuilt-pipeline adapter (V2 notes). Same arch/dims, drop-in |

Both are 5120 -> hidden -> hidden -> 5120 MLPs validated at load time, public and
ungated. Download **both** — 44MB is noise next to the ~71GB base set, and it
avoids a re-provision just to fetch the other one.

## Do not remove the older Semantic Bridge

`MiniMax_H3_Semantic_Bridge` (speach1sdef178, HF zip) registers
`SenseNovaH3DistilledBridge`, which the `*_fl2v.json` workflow variant still uses.
BUNNY registers only `BunnyH3ConditioningBridge`. **Different class names — they
coexist.** Add BUNNY; do not replace.

## Probe before wiring a bridge into a JSON

Grep the workflow for a bridge-shaped class before assuming it needs one: a JSON
whose filename says "Semantic_Bridge" may contain no bridge node at all (a
`cnr_id` tally by `comfy-core`/pack is the fast tell). A downloaded node that no
node in the graph references is inert — flag that to the user instead of implying
the graph is wired.
