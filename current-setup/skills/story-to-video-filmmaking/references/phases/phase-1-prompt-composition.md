# Phase 1.5: Filmmaking Prompt Composition (Agent)

After character sheet approval and reference upload, the agent composes `filmmaking_prompt.json` — the central instruction sheet that coordinates dual-keyframe generation and continuation-aware shot chaining.

## What the Agent Does

1. **Read `story_manifest.json`** — Extract scene structures, characters, expressions, settings, and moods.
2. **Auto-Build Continuation Chains**:
   - The first shot in any scene is marked as `chain_start`.
   - Subsequent shots within the same scene are marked as `continuation`, with `continues_from` pointing to the previous shot's prefix.
   - If a shot has `break_continuity: true`, it is forced to `independent` (no continuation).
3. **Determine Shot-Level Character Presence**:
   - Filter character reference sheets per shot based on active presence in the action/descriptions. Avoid adding background characters.
4. **Compose Stills Prompts (First & Last Frames)**:
   - For `chain_start` and `independent` shots, compose both `first_frame_prompt` and `last_frame_prompt`.
   - For `continuation` and `bridge` shots, compose only the `last_frame_prompt`. The first frame is extracted automatically from the previous shot's video tail.
   - Stills prompts use the detailed composition style (e.g. Flux/Qwen) with character specs, 3-region facial expressions, lighting, and camera angles.
5. **Compose Motion Prompts**:
   - Compose a brief, motion-only prompt (20–60 words) describing the camera movement and physical trajectory between the first and last frame.
   - Inject anti-jump-cut directives (e.g. `"A continuous fluid shot — camera slowly zooms in..."`).
6. **Apply Global & Shot-Specific Overrides**:
   - Select the default resolution preset (`1080p` or `720p`), segment duration (default `5`s), and guide strengths.
7. **Write `filmmaking_prompt.json`** to the story working directory.

---

## Prompt Length Budgets

### 1. Stills Prompts (`first_frame_prompt` & `last_frame_prompt`)
- **Model**: Flux 2 Dev Turbo or Qwen
- **Budget**: 50–250 tokens
- **Goal**: Detailed visual composition. Describe character sheets, facial expression, and backdrop.

### 2. Motion Prompts (`motion_prompt`)
- **Model**: LTX 2.3 FFLF
- **Budget**: 20–60 words (Keep it brief!)
- **Goal**: Describe spatial displacement and camera movement only. DO NOT describe details already present in the stills (e.g. character features, color of clothing, scenery details). Doing so is completely counter-productive.

**Good vs. Bad Motion Prompts:**
- ❌ **Bad (Too Descriptive)**: `"A cute orange tiger cub with blue eyes and no stripes stands in a sunny jungle clearing and slowly turns his head to laugh, with beautiful trees behind him"`
- ✅ **Good (Motion-Focused)**: `"A continuous fluid shot — the camera slowly pushes in on the tiger cub as he turns his head toward us, his expression shifting to a laugh"`

---

## filmmaking_prompt.json Schema

See [references/filmmaking-prompt-schema.md](../filmmaking-prompt-schema.md) for the full schema reference.

