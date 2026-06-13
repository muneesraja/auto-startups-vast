#!/usr/bin/env bash
# ---
# name: Cinematic Pipeline Setup
# description: Copies the custom cinematic templates to ComfyUI workflows, and downloads all models for Ideogram 4, Flux Klein 9B Edit, and LTX 2.3 FFLF.
# size: ~93GB
# ---
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOWS_DIR="$SCRIPT_DIR/../../current-setup/comfyui-workflows"
SKILL_TEMPLATES_DIR="$SCRIPT_DIR/../../current-setup/skills/story-to-video-cinematic/assets/workflow-templates"

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
