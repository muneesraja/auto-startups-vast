# Phase 1.5: Filmmaking Prompt Composition (Agent)

After character sheet approval and reference upload, the agent composes `filmmaking_prompt.json` — the **central instruction sheet** that the entire FFLF pipeline is driven from. Every subsequent phase is a mechanical execution of what the agent decides here.

## What the Agent Does

1. **Read `story_manifest.json`** — Extract scene structures, characters, expressions, settings, moods, and narrative arc.
2. **Plan the full shot list** with storytelling intent first:
   - Map each narrative beat to a shot
   - Ensure the sequence of shots tells the story visually, not just mechanically
   - Plan scene transitions in advance (what LF of scene A should look like to land smoothly into scene B)
3. **Auto-Build Continuation Chains**:
   - The first shot in any scene is marked `chain_start`
   - Subsequent shots within the same scene are marked `continuation`, with `continues_from` pointing to the previous shot's prefix
   - If a shot has `break_continuity: true`, force to `independent`
   - Between-scene connector shots that need visual flow are marked `bridge`
4. **Determine Shot-Level Character Presence**:
   - Filter character reference sheets per shot based on active presence
   - Avoid adding background/irrelevant characters to `references` or `lf_references`
5. **Compose First Frame Prompts** (`first_frame_prompt`):
   - For `chain_start` and `independent` shots only
   - Detailed 50–250 token Flux prompt: character specs, 3-region facial expression, lighting, camera angle, environment
6. **Compose Last Frame Prompts** (`last_frame_prompt`):
   - For ALL shots
   - Describe the ending composition of the shot — where the action arrives, what expression the character wears, how the camera has moved
7. **Decide `lf_references` per shot** (critical reasoning step):
   - See decision logic below — this is the most important agent decision for image quality
8. **Compose Motion Prompts** (`motion_prompt`):
   - Brief (20–60 word) motion-only description of what physically moves between FF and LF
   - Inject anti-jump-cut directives
9. **Apply Global & Shot Overrides**

---

## Prompt Length Budgets

### 1. Stills Prompts (`first_frame_prompt` & `last_frame_prompt`)
- **Model**: Flux 2 Dev Turbo
- **Budget**: 50–250 tokens
- **Goal**: Detailed visual composition. Describe character specs, facial expression (3-region: brow/eye/mouth), camera angle, backdrop, lighting mood.

### 2. Motion Prompts (`motion_prompt`)
- **Model**: LTX 2.3 FFLF Seed Hunter
- **Budget**: 20–60 words (Keep it brief — this is the author's most important rule)
- **Goal**: Describe spatial displacement and camera movement ONLY.
- **Do NOT** re-describe what's already visible in the keyframes. This creates conflicting layout calculations in the video model.

**Good vs. Bad Motion Prompts:**
- ❌ **Bad**: `"A cute orange tiger cub with blue eyes stands in a sunny jungle clearing and slowly turns his head to laugh, with beautiful trees behind him"`
- ✅ **Good**: `"A continuous fluid shot — the camera slowly pushes in on the tiger cub as he turns his head toward us, his expression shifting to a laugh"`

---

## `lf_references` — The Agent's Most Important Reasoning Step

The pipeline **always prepends the FF image or previous tail frame** as the primary structural anchor when generating the LF. The `lf_references` field only adds supplementary references on top of that.

### Decision Logic

```
FOR EACH SHOT, reason about lf_references:

1. START: lf_references = []

2. The structural anchor (FF or tail frame) already carries:
   - Scene environment / backdrop
   - Characters already visible in the FF / tail
   - Lighting and color palette
   → Do NOT re-add character sheets for characters already present in the anchor

3. ADD a character sheet to lf_references IF:
   - A character appears in the LF for the FIRST TIME in this shot
   - The character is not visible in the structural anchor (FF or tail)

4. DO NOT ADD if:
   - The LF shows the same characters as the FF, just in a different pose
   - The environment changes slightly but no new characters enter

5. MAXIMUM: lf_references may contain at most 3 items
   (the structural anchor uses the first reference slot automatically)

6. ALWAYS write lf_reference_note explaining the reasoning for auditability
```

---

## `filmmaking_prompt.json` Schema

See [references/filmmaking-prompt-schema.md](../filmmaking-prompt-schema.md) for the full schema reference with all fields and examples.

---

## Storytelling Alignment Rules (Most Important)

The agent must prioritize story coherence over technical correctness:

1. **Every shot must advance the story** — motion prompts describe a narrative beat, not camera art for its own sake.

2. **Emotional arc across shots** — use `segment_duration` overrides to pace emotional beats: slow (7–8s) for tension/revelation, normal (5s) for action, short (3s) for quick cuts.

3. **Plan scene transitions in advance** — before writing any shot, ask: "What does the LF of the last shot in Scene A need to look like so the first shot of Scene B feels natural?" Write the bridge/final shot `last_frame_prompt` to "open the door" visually (character exits frame, camera reveals new location, etc.).

4. **Character consistency** — character appearance must be stable shot-to-shot. The recursive pipeline (tail frame → next FF) handles this for continuation chains automatically. For `chain_start` shots after a scene gap, the `references` and `first_frame_prompt` must explicitly re-establish the character's appearance.

5. **`lf_reference_note` is required reasoning** — every shot must have a note. No exceptions. It must reference the story moment ("Villain appears for the first time in this shot") not just describe the technical choice.
