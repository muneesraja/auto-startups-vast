#!/usr/bin/env bash
# Relink Hermes skills to the updated repository path.
set -e

REPO_ROOT="$HOME/repos/auto-startups-vast"
HERMES_SKILLS_DIR="$HOME/.hermes/skills"

echo "==> Re-creating Hermes skill symlinks..."

# Remove old symlinks if they exist
rm -f "$HERMES_SKILLS_DIR/runpod-ai"
rm -f "$HERMES_SKILLS_DIR/vast-ai"
rm -f "$HERMES_SKILLS_DIR/workflow-researcher"
rm -f "$HERMES_SKILLS_DIR/creative/story-to-video"
rm -f "$HERMES_SKILLS_DIR/creative/story-to-video-filmmaking"
rm -f "$HERMES_SKILLS_DIR/creative/story-to-video-cinematic"
rm -f "$HERMES_SKILLS_DIR/creative/story-production-orchestrator"
rm -f "$HERMES_SKILLS_DIR/productivity/growthlabs-docs"

# Create new symlinks pointing to root-level skills/
ln -sf "$REPO_ROOT/skills/runpod-ai" "$HERMES_SKILLS_DIR/runpod-ai"
ln -sf "$REPO_ROOT/skills/vast-ai" "$HERMES_SKILLS_DIR/vast-ai"
ln -sf "$REPO_ROOT/skills/workflow-researcher" "$HERMES_SKILLS_DIR/workflow-researcher"
ln -sf "$REPO_ROOT/skills/story-to-video" "$HERMES_SKILLS_DIR/creative/story-to-video"
ln -sf "$REPO_ROOT/skills/story-to-video-filmmaking" "$HERMES_SKILLS_DIR/creative/story-to-video-filmmaking"
ln -sf "$REPO_ROOT/skills/story-to-video-cinematic" "$HERMES_SKILLS_DIR/creative/story-to-video-cinematic"
ln -sf "$REPO_ROOT/skills/story-production-orchestrator" "$HERMES_SKILLS_DIR/creative/story-production-orchestrator"
ln -sf "$REPO_ROOT/skills/growthlabs-docs" "$HERMES_SKILLS_DIR/productivity/growthlabs-docs"

echo "✅ All skill symlinks successfully updated!"
