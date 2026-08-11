# `ace-step-15-t2a-song.sh` — Worked Walkthrough (2026-07-21)

The smallest end-to-end "100% comfy-core, audio subgraph" build. Use as a template for any
workflow that matches:

- **Subgraph shape** — top-level `nodes[]` has 3-4 entries (MarkdownNote × 2, SaveAudioMP3,
  one UUID-typed container). All real loaders live in `definitions.subgraphs[0].nodes[]`.
- **`cnr_id == "comfy-core"` on every node** — zero custom node packs.
- **HF repo uses `split_files/<sub>/` prefix** — `Comfy-Org/<name>_files` style.
- **4 model downloads** — 1 × UNET + 1 × VAE + 2 × DualCLIP (clip_name1, clip_name2).

Examples of this class (so far): `ace-step-15-t2a-song.sh` (this one), `stable-audio-3-medium-base.sh`.

## Why this needs its own template (and not the canonical §3.1)

The canonical `§3.1 Canonical script template` in the global SKILL.md is aimed at LTX-Video
class workflows with 3+ custom node packs (KJNodes + LTXVideo + WhatDreamsCost + optional
`rgthree`, `VHS`, `Impact`, etc.). For the audio class, that template over-engineers:

- The custom node install block is empty (nothing to clone) but the template still prints
  the full "if comfy-cli / elif git clone" dance.
- The pip-deps loop is empty (no `requirements.txt` to install).
- The patch block is empty (no source patches needed).
- The dense `BASE_DIR` block + Python detection has one extra pitfall the canonical template
  doesn't encode: **RunPod slim venvs have no `pip` symlink** (Bug 10, 2026-07-14), so
  `COMFY_PIP` must be `"$COMFY_PYTHON -m pip"`, never the bare `pip` path.
- The ComfyUI restart block's `else` branch (no supervisor) is the one place that *must* do
  the full tmux-restart recipe, not just echo a hint. On `runpod/comfyui` images the
  entrypoint pre-starts ComfyUI, so the hint never gets acted on and the script exits 0
  with stale node code (Bug 16b, 2026-07-20).

This template encodes all of the above.

## What the script does (1-by-1)

| Phase | Lines | What | Why |
|---|---|---|---|
| Frontmatter | 1-13 | `name`, `workflow:`, `aliases:`, `description:`, `size:`, `min_vram:`, `nodes: []`, `notes:` | Stable machine ID; provisioning pipeline reads these |
| `set -e` | 15 | fail fast | Any non-zero exit halts the script (catches the `_hf_download.sh` curl failure etc.) |
| `BASE_DIR` detect | 18-33 | Platform-aware Vast/RunPod defaulting | `BASE_DIR=.../ComfyUI` (root, NOT `/models`) so the `split_files/...` HF prefix can be pre-stripped before download via a `mv` step |
| Python detect | 38-53 | `/venv/main → venv/bin → .venv-cu128 → system`, with `COMFY_PIP="$COMFY_PYTHON -m pip"` | RunPod slim has no `pip` symlink (Bug 10). The `-m pip` form is portable across all 4 paths |
| Custom node install | 56-57 | Empty (no packs) | Comment block explains why; future agents know to leave it empty if `cnr_id == comfy-core` for all nodes |
| Pip deps | 60-61 | Empty (no `requirements.txt`) | Same — preserves the structure for when packs ARE present |
| `mkdir -p` | 64 | `$BASE_DIR/models/{diffusion_models,text_encoders,vae}` | Only the subdirs the script actually writes to |
| `_hf_download.sh` auto-fetch | 67-86 | Source local, fallback to GitHub raw | Vast images don't bundle the helper; the auto-fetch keeps scripts self-contained |
| `[1/4] ... [4/4]` downloads | 92-128 | `hf_download` + `mv $BASE_DIR/split_files/<sub>/<file> $BASE_DIR/models/<sub>/<file>` | Move-rename pattern from `ltx-23-director-hotfix.sh` — needed because the HF browse-tree prefix nests one level deeper than ComfyUI's model dirs |
| `split_files/` cleanup | 131-134 | `rmdir` empty scaffolding dirs | Cosmetic — `hf_hub_download` leaves the empty `split_files/<sub>/` dirs behind |
| Restart block | 138-163 | `supervisorctl` (Vast) → `tmux new-session -d` (RunPod), with `--lowvram` | Standing rule (muneesraja, 2026-07-21). The `else` branch does the FULL tmux recipe — not a hint. |
| Final echoes | 166-170 | User-facing instruction | Uses SINGLE QUOTES for the backtick-containing lines — see `vast-ai-script-runner` pitfalls |

## Pitfalls this template specifically avoids

1. **`BASE_DIR = ComfyUI root`, not `/models`** — required so the move-rename step works.
2. **`COMFY_PIP = "$COMFY_PYTHON -m pip"`** — never bare `pip` (Bug 10, RunPod slim).
3. **`hf_download` with `local_dir=$BASE_DIR`** for `split_files/<sub>/` URLs — the helper creates `$BASE_DIR/split_files/<sub>/<file>` automatically, then the `mv` lands it in `$BASE_DIR/models/<sub>/<file>`. Passing `$BASE_DIR/models/<sub>` as `local_dir` would double-nest (Bug 15, 2026-07-17).
4. **No `git clone` / `pip install`** → restart block's `else` branch on RunPod must do the tmux-restart recipe itself, not just print a hint (Bug 16b, 2026-07-20).
5. **`--lowvram` on every main.py launch** — including the manual hint the script echoes (Bug 17, 2026-07-21).
6. **Backticks in user-facing echoes** — use single quotes for the final instruction lines (Bug 20, 2026-07-21, newly added to `vast-ai-script-runner`).

## Reusing this template for the next 100%-comfy-core audio workflow

1. Copy `ace-step-15-t2a-song.sh` to `<new-script>.sh`.
2. Update frontmatter: `name`, `workflow:` (= JSON filename), `aliases:`, `description:`, `size:`, `min_vram:`, `notes:`.
3. Update the `[i/N]` download blocks: replace `<org>/<repo>`, `split_files/<sub>/<file>`, sizes, loader type.
4. Update the `mkdir -p` line to match the loader subdirs the new workflow uses.
5. Update the cleanup `rmdir` lines to match the subdirs.
6. Update the final echo block: `<NodeName>`, `<widget1>`, `<widget2>`, output path.
7. Validate per the global `workflow-researcher` §4 checklist.
8. `bash -n <new-script>.sh` + commit + push.

## Related

- `stable-audio-3-medium-base.sh` in `auto-startups-vast/workflows/setup/` — same shape, but with a different prefix pattern (no `split_files/` → uses `$BASE_DIR/models` directly with bare filenames).
- `ltx-23-director-hotfix.sh` — canonical reference for the move-rename pattern with `split_files/` prefixes.
- `references/setup-script-bugs-2026-07-22.md` (in `vast-ai-script-runner`) — Bug 18 audit recipe: zero-node-packs workflows do need the restart (this is the Bug 16b fix), but the restart must be done correctly.
