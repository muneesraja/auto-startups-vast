---
name: auto-startups-vast
version: 1.0.0
category: devops
description: Maintain the auto-startups-vast repo — skill symlink management, commit/push workflow, and repo structure conventions.
trigger: When adding, updating, removing, or committing skills in the auto-startups-vast repo, or when setting up symlinks between Hermes skills and the repo.
---

# auto-startups-vast Repo Maintenance

## Repo Location

```
~/repos/auto-startups-vast/
├── README.md
├── .env.example          # Template (never .env)
├── .gitignore
├── skills/                # ← Skills live here (source of truth)
│   ├── runpod-ai/
│   ├── story-to-video/
│   ├── vast-ai/
│   └── workflow-researcher/
├── workflows/
│   ├── comfyui/           # ComfyUI JSON templates
│   └── setup/             # Workflow download/setup scripts
├── discussion-and-docs/
├── scripts/               # Non-skill scripts (provision, bootstrap)
└── temp/                  # Scratch space (.gitignored except whitelisted)
```

## Architecture: Repo = Source of Truth

**All git-tracked skill files live in the repo.** Hermes skill directories are symlinks pointing into the repo, so editing from either location modifies the same files.

### Symlink Map

| Hermes Skill Path | Symlink Target (repo) |
|---|---|
| `~/.hermes/skills/creative/story-to-video` | `~/repos/auto-startups-vast/skills/story-to-video` |
| `~/.hermes/skills/runpod-ai` | `~/repos/auto-startups-vast/skills/runpod-ai` |
| `~/.hermes/skills/vast-ai` | `~/repos/auto-startups-vast/skills/vast-ai` |
| `~/.hermes/skills/workflow-researcher` | `~/repos/auto-startups-vast/skills/workflow-researcher` |

### Why This Direction?

Git does **NOT** follow directory symlinks. If the repo holds a symlink → `~/.hermes/skills/`, git only stores the symlink target path (e.g., `/root/.hermes/skills/creative/story-to-video`), not the file contents. Anyone cloning the repo gets a broken symlink.

By making the **repo the source of truth** and Hermes the symlink, we get:
- ✅ Git tracks real files (cloneable)
- ✅ Edits in Hermes skill dir instantly reflect in repo (same files via symlink)
- ✅ No sync/copy step between commits

### Special Cases

- **growthlabs-docs** references are symlinked to Syncthing vault: `~/.hermes/skills/productivity/growthlabs-docs/references → ~/Syncthing/obsidian-vault/growthlabs-docs`. This is NOT in the repo.
- **vast-ai/.venv/** is gitignored — it's a local venv, not tracked.

## Adding a New Skill to the Repo

1. Create the skill with `skill_manage(action='create')` — this puts it in `~/.hermes/skills/`
2. Move it to the repo:
   ```bash
   mv ~/.hermes/skills/<category>/<skill-name> ~/repos/auto-startups-vast/skills/<skill-name>
   ```
3. Replace the original with a symlink:
   ```bash
   ln -s ~/repos/auto-startups-vast/skills/<skill-name> ~/.hermes/skills/<category>/<skill-name>
   ```
4. Commit and push:
   ```bash
   cd ~/repos/auto-startups-vast
   git add skills/<skill-name>/
   git commit -m "feat: add <skill-name> skill"
   git push
   ```

## Removing a Skill from the Repo

1. Remove the Hermes symlink:
   ```bash
   rm ~/.hermes/skills/<category>/<skill-name>
   ```
2. Remove from repo and commit:
   ```bash
   cd ~/repos/auto-startups-vast
   git rm -r skills/<skill-name>/
   git commit -m "chore: remove <skill-name> skill"
   git push
   ```

## Commit & Push Workflow

Since repo files = real files and Hermes symlinks → repo:

```bash
cd ~/repos/auto-startups-vast

# Check what changed (edits via Hermes skill dir show up here)
git status
git diff

# Stage, commit, push
git add -A  # or selective paths
git commit -m "feat(story-to-video): describe change"
git push
```

No extra sync step needed — edits made through the Hermes symlink path modify the repo files directly.

## Pitfalls

1. **Never create a directory symlink in the repo pointing to `~/.hermes/skills/`.** Git won't track the contents. Always put real files in the repo and symlink from Hermes.

2. **`git add` on a directory symlink** stages the symlink itself, not the files inside. If you see `new file: skills/<name>` (without trailing `/`), it's a symlink — remove it and use real files instead.

3. **`.env` files are gitignored.** Never commit secrets. Use `.env.example` templates instead.

4. **`__pycache__/` and `.venv/` are gitignored.** Don't accidentally track Python bytecode or local venvs.

5. **When replacing a real directory with a symlink in Hermes**, make sure to delete the Hermes directory first, then create the symlink. `ln -sf` on an existing directory won't work — you must `rm -rf` first.

6. **Verify symlinks after setup:**
   ```bash
   ls -la ~/.hermes/skills/creative/story-to-video  # Should show arrow →
   cat ~/.hermes/skills/creative/story-to-video/SKILL.md | head -3  # Should work
   ```

## Verification Commands

```bash
# Check all skill symlinks are intact
find ~/.hermes/skills -maxdepth 3 -type l -ls

# Check repo status
cd ~/repos/auto-startups-vast && git status

# Verify a specific symlink resolves
readlink -f ~/.hermes/skills/creative/story-to-video
# Should output: /root/repos/auto-startups-vast/skills/story-to-video
```