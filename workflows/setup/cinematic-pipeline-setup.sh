#!/usr/bin/env bash
# ---
# name: Cinematic Pipeline Setup
# description: Copies the custom cinematic templates to ComfyUI workflows, and downloads all models for Ideogram 4, Flux Klein 9B Edit, and LTX 2.3 FFLF.
# size: ~93GB
# notes: |
#   Sub-scripts must agree on the custom node dir naming convention.
#   KJNodes is installed to `ComfyUI-KJNodes` (PascalCase, matches the
#   GitHub repo name) — flux-2-klein-image-edit.sh and flux-2-dev-turbo.sh
#   previously used `comfyui-kjnodes` (lowercase), which caused Phase 4
#   to re-clone over the top of Phase 2's install on case-insensitive
#   filesystems, wiping out the node and breaking workflows that depend
#   on it (e.g. INTConstant). All three sub-scripts now use PascalCase
#   and accept either casing as "already installed" for backwards compat.
# ---
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_DIR="$SCRIPT_DIR/../comfyui"
SKILL_TEMPLATES_DIR="$SCRIPT_DIR/../../skills/story-to-video-cinematic/assets/workflow-templates"

echo "==> [Phase 1] Copying workflow template JSON files..."
mkdir -p "$WORKFLOWS_DIR"
cp "$SKILL_TEMPLATES_DIR/ideogram-4-t2i.json" "$WORKFLOWS_DIR/ideogram-4-t2i.json"
cp "$SKILL_TEMPLATES_DIR/flux-2-klein-image-edit.json" "$WORKFLOWS_DIR/flux-2-klein-image-edit.json"
echo "  ✅ Workflow templates copied to $WORKFLOWS_DIR"

echo "==> [Phase 2] Provisioning Ideogram 4 T2I..."
bash "$SCRIPT_DIR/ideogram-4-t2i.sh"

echo "==> [Phase 3] Provisioning Flux Klein 9B Edit..."
bash "$SCRIPT_DIR/flux-2-klein-image-edit.sh"

echo "==> [Phase 4] Provisioning LTX 2.3 FFLF Seed Hunter..."
bash "$SCRIPT_DIR/ltx-23-fflf-seed-hunter.sh"

echo "🎉 Cinematic pipeline setup complete!"
