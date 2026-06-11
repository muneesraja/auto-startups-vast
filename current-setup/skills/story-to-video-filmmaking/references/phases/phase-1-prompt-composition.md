# Phase 1.5: Filmmaking Prompt Composition (Agent)

After character sheet approval and reference upload, the agent composes `filmmaking_prompt.json` — the **central instruction sheet** that the entire FFLF pipeline is driven from. Every subsequent phase is a mechanical execution of what the agent decides here.

## What the Agent Does

1. **Read `story_manifest.json`** — Extract scene structures, characters, expressions, settings, moods, and narrative arc.
2. **Plan the full shot list** with storytelling intent first:
   - Map each narrative beat to a shot
   - Ensure the sequence of shots tells the story visually, not just mechanically
   - Plan scene transitions in advance (what LF of scene A should look like to land smoothly into scene B)
   - **Validate coverage**: every scene+shot in the manifest MUST have a corresponding entry in `filmmaking_prompt.json`. If any are missing, emit a warning in a top-level `coverage` field.
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
   - ⚠️ The LF **MUST show visible spatial change** from the FF (see Continuation Logic Rule below)
7. **Decide `lf_references` per shot** (critical reasoning step):
   - See decision logic below — this is the most important agent decision for image quality
8. **Compose Motion Prompts** (`motion_prompt`):
   - Brief (20–60 word) motion-only description of what physically moves between FF and LF
   - Inject anti-jump-cut directives
   - ⚠️ ONLY spatial displacement and camera movement. NEVER re-describe visuals from keyframes.
9. **Set `segment_duration` per shot** based on the spatial displacement heuristic (see below)
10. **Apply Global & Shot Overrides**

---

## ⚠️ The FFLF Continuation Logic Rule (CRITICAL)

> **Source:** Fox•Fur•Essence Films (author of the FFLF Seed Hunter workflow)
> *"Your starting and ending keyframes must share a logical, sequential pathway, otherwise the pipeline will break down into erratic camera movements or jump cuts."*

### What This Means for FF → LF Composition

The LTX Video model treats the FF and LF keyframes as **endpoints of a spatial journey**. It must calculate a physically plausible motion path to bridge them. If the keyframes are too similar (expression-only change) or too different (completely new scene), the model's physics engine breaks down and produces:
- Dramatic, unnatural camera pans (usually upward toward the brightest element)
- Jump cuts / flickering
- Frozen frames with pixel distortions

### The Golden Rule

**Every FF → LF pair MUST show a clear spatial change.** At least ONE of these must differ between FF and LF:

| Spatial Signal | Example |
|---|---|
| **Character position** | Character moves from left to center of frame |
| **Camera angle** | Low angle → eye level |
| **Camera distance** | Wide shot → medium close-up (or reverse) |
| **Environment framing** | Cobweb fills frame → camera pulls back to reveal log walls |
| **Character body pose** | Standing still → leaning forward, arms extended |

### What Does NOT Count as Spatial Change

These are **insufficient** for FFLF interpolation and will cause camera drift:
- ❌ Expression-only change (eyes open → eyes closed)
- ❌ Lighting shift with no camera/character movement
- ❌ Color grading change
- ❌ Subtle texture/detail differences

If the story beat requires only an expression change (e.g., "Barnaby looks scared, then closes his eyes"), use a **very short duration** (2-3s) and describe any micro-motion in the prompt ("slight head tilt downward", "body sways gently").

---

## Prompt Length Budgets

### 1. Stills Prompts (`first_frame_prompt` & `last_frame_prompt`)
- **Model**: Flux 2 Dev Turbo
- **Budget**: 50–250 tokens
- **Goal**: Detailed visual composition. Describe character specs, facial expression (3-region: brow/eye/mouth), camera angle, backdrop, lighting mood.
- **Resolution**: Generate at the **same resolution** as the video pipeline's target. For `720p` preset: 1280×704. For `1080p` preset: 1920×1088. Do NOT generate at Flux's native 1344×768 if the video target is different — the FFLF template center-crops images to fit, and different crops of similar images create spurious motion signals.

### 2. Motion Prompts (`motion_prompt`)
- **Model**: LTX 2.3 FFLF Seed Hunter
- **Budget**: 20–60 words (Keep it brief — this is the author's most important rule)
- **Goal**: Describe spatial displacement and camera movement ONLY.

**DO NOT include any of the following in motion prompts:**
- ❌ Character appearance descriptions ("tiny wings", "golden fur", "chibi body")
- ❌ Lighting descriptions ("golden light shifts", "warm glow")
- ❌ Texture descriptions ("soft plush textures", "fuzzy fur")
- ❌ Background descriptions ("dark bark walls", "cobweb strands")
- ❌ Emotional/narrative descriptions ("his fear turns to effort")

> **Author's warning:** *"Don't feed hyper-detailed descriptions of backgrounds or textures into the prompt field if those structures are already visible in your keyframes. This creates conflicting layout calculations."*

**Good vs. Bad Motion Prompts:**
- ❌ **Bad**: `"Barnaby squirms against the sticky cobweb, his tiny wings fluttering uselessly. The camera tilts down slightly. The shaft of golden light shifts and catches the silver silk strands, making them shimmer."`
  - Problem: Re-describes character ("tiny wings"), lighting ("golden light"), textures ("sticky cobweb", "silver silk"), AND gives contradictory spatial cues ("tilts down" + "light shifts" upward).
- ✅ **Good**: `"A continuous fluid shot — the camera slowly pushes in on the central figure as it strains against the threads, body tilting forward slightly."`
  - Only describes: what moves (camera push + body tilt) and in what direction.

---

## `segment_duration` — Match Duration to Spatial Change

The amount of spatial displacement between FF and LF determines how long the video model needs to bridge them. Too much duration for too little displacement = the model invents dramatic camera motion to fill the gap.

| FF → LF Delta | Recommended `segment_duration` | Example |
|---|---|---|
| Expression only (same pose, same camera) | **2–3s** | Character's eyes close, mouth changes |
| Subtle spatial shift (slight camera push, head turn) | **4–5s** | Camera pushes in slightly, character tilts head |
| Clear spatial trajectory (character moves, camera tracks) | **5–7s** | Character walks from left to center, camera follows |
| Full scene traversal (wide to close-up, character crosses frame) | **7–8s** | Wide establishing shot → medium close-up of character |

> **Production learning (tiny-bee):** Shot 1 used 6 seconds for an expression-only change (eyes open → eyes closed, same camera, same position). The model invented a dramatic upward camera pan to fill the temporal gap, corrupting the entire continuation chain.

---

## `lf_references` — The Agent's Most Important Reasoning Step

The pipeline **always prepends the FF image or previous tail frame** as the primary structural anchor when generating the LF. The `lf_references` field controls what additional references are included.

### Decision Logic (Updated from Production Learnings 2026-06-11)

```
FOR EACH SHOT, reason about lf_references:

1. START: lf_references = []

2. CHECK: Is a character the emotional FOCUS of the LF?
   YES → ADD that character's reference sheet to lf_references
         (even if they're already visible in the structural anchor —
          Flux's ReferenceLatent chain DRIFTS character identity across
          iterations; the anchor alone is NOT enough to lock appearance)
   NO  → Leave it empty

3. CHECK: Does the LF introduce a character NOT visible in the FF / tail?
   YES → ADD that character's reference sheet to lf_references
   NO  → (already handled by step 2)

4. MAXIMUM: lf_references may contain at most 3 items
   (the structural anchor uses the first reference slot automatically)

5. ALWAYS write lf_reference_note explaining the reasoning for auditability
   The note MUST reference the story moment, not just the technical choice.
```

> **Why the old rule was wrong:** The original schema said *"Do NOT re-add character sheets for characters already present in the anchor."* Production testing showed this causes character drift — Flux loosens the character's identity features (chibi proportions get diluted, new features get added like leaf hats). Always include sheets for focus characters.

### Examples

```json
// Shot 1 — chain_start, Barnaby is the emotional focus
"references": ["barnaby_reference_sheet.png"],
"lf_references": ["barnaby_reference_sheet.png"],
"lf_reference_note": "Barnaby is the sole emotional focus. His character sheet is included to prevent identity drift across the Flux iteration — the structural anchor alone is not enough to lock chibi proportions."

// Shot 2 — continuation, new character (Spider) enters, Barnaby still focus
"references": [],
"lf_references": ["barnaby_reference_sheet.png", "spider_reference_sheet.png"],
"lf_reference_note": "Spider enters frame for the first time in the LF. Barnaby is still the emotional focus (reacting to the Spider). Both sheets needed: Spider for new-character conditioning, Barnaby to prevent identity dilution by the new ref."

// Shot 3 — continuation, same characters, both established in tail frame
"references": [],
"lf_references": [],
"lf_reference_note": "Continuation shot. Both characters already established in the structural anchor (Shot 2 tail frame). No new characters enter. lf_references stays empty."
```

---

## Scene Transition Planning

Before composing any shots, the agent must plan how scenes connect visually:

```
FOR EACH pair of adjacent scenes (Scene N, Scene N+1):
  1. Compare Scene N's final shot LF to Scene N+1's first shot FF
  2. Score the visual jump:
     - EASY: Same location, same characters, different camera angle
     - MEDIUM: Same characters, new location (e.g., interior → exterior of same building)
     - HARD: New location AND new characters (e.g., dark cave → bright meadow)
  3. For EASY jumps: use `continuation` or `bridge` shot type
  4. For MEDIUM jumps: use `bridge` with the LF "opening the door" to the new scene
     (e.g., character walks toward a doorway, camera reveals bright light beyond)
  5. For HARD jumps: use `independent` with `break_continuity: true`
     Do NOT attempt FFLF interpolation between incompatible scenes.
```

---

## `filmmaking_prompt.json` Schema

See [references/filmmaking-prompt-schema.md](../filmmaking-prompt-schema.md) for the full schema reference with all fields and examples.

---

## Storytelling Alignment Rules (Most Important)

The agent must prioritize story coherence over technical correctness:

1. **Every shot must advance the story** — motion prompts describe a narrative beat, not camera art for its own sake.

2. **Emotional arc across shots** — use `segment_duration` overrides to pace emotional beats. Match duration to spatial displacement (see table above). Do NOT default to 5-6s for every shot.

3. **Plan scene transitions in advance** — before writing any shot, ask: "What does the LF of the last shot in Scene A need to look like so the first shot of Scene B feels natural?" Write the bridge/final shot `last_frame_prompt` to "open the door" visually (character exits frame, camera reveals new location, etc.). For radical scene changes, use `break_continuity: true`.

4. **Character consistency** — character appearance must be stable shot-to-shot. The recursive pipeline (tail frame → next FF) handles this for continuation chains automatically. For `chain_start` shots after a scene gap, the `references` and `first_frame_prompt` must explicitly re-establish the character's appearance. Always include focus character sheets in `lf_references` to prevent identity drift.

5. **`lf_reference_note` is required reasoning** — every shot must have a note. No exceptions. It must reference the story moment ("Villain appears for the first time in this shot") not just describe the technical choice.

6. **Manifest coverage** — `filmmaking_prompt.json` must contain entries for ALL scenes and shots in `story_manifest.json`. If partial composition is unavoidable, add a `coverage` field documenting what's missing and why.

7. **Continuation shot `first_frame_image` must be `null`** — for `continuation` and `bridge` shots, do not set `first_frame_image` to a fabricated filename. The pipeline uses the tail frame from the preceding shot automatically. Setting a phantom filename is misleading.

