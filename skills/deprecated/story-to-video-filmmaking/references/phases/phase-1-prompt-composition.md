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
   - 📝 **NEW (2026-06-11):** LF prompts are **edit instructions, not composition descriptions.** See the dedicated section below — *"The Edit-Instruction LF Pattern."* This is the single most important prompt-authoring change for FFLF quality.
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

## The Edit-Instruction LF Pattern (2026-06-11, elephant story)

> **This is the single most important prompt-authoring rule for FFLF.** A wrong LF prompt produces a still that the video model can't interpolate from, which is exactly what made 10 of 14 elephant-story shots fail quality (2 frozen, 8 radical — see `fflf-production-learnings.md` § "LF Edit-Mode Prompting").

### Why LF prompts are not composition descriptions

The pipeline's API call for the LF looks like this (paraphrased from `generate_frames.py`):

```python
shot_for_builder = {
    "prompt": last_frame_prompt,         # ← what the agent writes
    "references": [ff_image, char_sheet_a, char_sheet_b],  # FF + character refs already prepended
    "filename_prefix": "..."
}
```

**Two facts about this call that change everything:**

1. **The FF image is already in the `references` list** — Flux 2 Dev Turbo receives it as an actual image attachment, not just a text description.
2. **The workflow has a ReferenceLatent node wired in** — Flux uses the references as conditioning signals, not as style-only hints.

This means Flux is operating in **I2I edit mode** for the LF, not T2I. But the prompts we write treat it like T2I:

| ❌ Current (T2I-style) | ✅ Correct (I2I edit-style) |
|---|---|
| "Wide shot. Elly's round body is now on the shallow pebbly riverbank, having just stepped out of the deep water. Her legs are still slightly wet, water dripping from her body onto the pebbles. She is breathing a huge visible sigh of relief..." | "Edit image 1 (the previous frame). **KEEP UNCHANGED:** the dam structure, the churning water, the misty jungle canopy, the soft golden morning light, Elly's chibi proportions, soft warm gray skin, big dark-brown eyes, short stubby trunk, floppy ears, stubby legs. **CHANGE:** Elly's pose is now stepping forward onto a pebbly riverbank, one foot still in the water, her trunk released from gripping the log. Her mouth is in a small shaky relieved exhale, eyes open and looking down at her feet. The dam is now in the background, smaller. Water visibly drips from her body. **Camera:** same angle, slightly wider framing (pulled back ~10%). **Mood:** the danger is past." |

The first prompt **tells Flux to imagine a new image from a description.** Flux dutifully produces a beautiful still that satisfies the text, but the still has no enforced relationship to the FF — it just happens to share the same semantic concept ("elephant + water + dam").

The second prompt **tells Flux to edit the FF, preserving most of it.** Flux preserves the dam, the water, the lighting, the character — and only modifies the specific deltas listed. The resulting LF has SSIM ~0.7-0.85 to the FF (the healthy band for FFLF motion), instead of SSIM 0.45 (radical) or 0.96 (frozen).

### The Edit-Instruction LF Template

Use this structure for every `last_frame_prompt`:

```
[CONTEXT — 1-2 sentences]
Edit image 1 (the previous frame). [Shot context: where we are in the story,
what the camera is doing, what just happened].

[KEEP UNCHANGED — explicit preserve list, the more specific the better]
KEEP UNCHANGED: [list every visual element that should stay the same —
character identity and proportions, clothing, key props, background
environment, lighting direction, overall color palette, the visual style
("3D Pixar-style", "chibi proportions", "soft plush textures", etc.)].

[CHANGE — explicit delta list, ordered by visual prominence]
CHANGE:
- [Primary motion / pose change]
- [Secondary motion or expression change]
- [Tertiary details: water splash, dust, hair movement, etc.]

[CAMERA — what the camera does, if anything]
Camera: [same angle / slight push-in / pull-back / pan / tilt].
[Optional: "framing tightened to medium close-up" or "wider establishing shot"]

[MOOD — what the emotional read should be]
Mood: [tense / relieved / heroic / intimate / playful].
```

### LF prompt vocabulary for the CHANGE section

Use these verbs/concepts to make deltas visually concrete:

| Verb | What it produces |
|---|---|
| "stepping forward onto X" | Foot motion, body weight shift |
| "released from gripping X" | Hand/trunk opens, body relaxes |
| "turning 90° toward camera" | Profile → 3/4 view, body rotation |
| "leaning back / forward" | Posture change, weight redistribution |
| "looking up at / down at X" | Head angle change, eye direction |
| "mouth in a small [adjective] [noun] shape" | Expression change (3-region) |
| "the camera has pulled back / pushed in by ~10%" | Framing change |
| "the [prop] is now in the background, smaller" | Scale change on a known object |
| "water visibly drips from X" | Secondary motion cue |
| "a faint glow surrounds X" | Lighting change |

### What NOT to write in the LF prompt (anti-patterns)

- ❌ "is now doing X" without "edit image 1" or "KEEP UNCHANGED:" — invites full re-imagination
- ❌ Re-describing the character from scratch (color, height, clothing) — the FF already has it, and the character reference sheet is in `references[]`
- ❌ Describing the FF as if it doesn't exist ("Wide shot. Elly is on the bank...") — T2I vocabulary
- ❌ A complete scene description that's longer than the FF prompt — the LF should describe a delta, not a scene
- ❌ Vague deltas ("a little different", "slightly changed", "more of the same") — Flux interprets these as "no change"

### Calibration: shot 3.2 (elephant story) before / after

The elephant story's shot 3.2 ("The wade-out") had a T2I-style LF prompt that produced a near-identical image to the FF (frozen-keyframe problem, SSIM 0.45 — radical, not frozen, but the model had nothing to interpolate). The rewrite:

**Before (T2I-style, what was in `filmmaking_prompt.json`):**
> Wide shot. Elly's round body is now on the shallow pebbly riverbank, having just stepped out of the deep water. Her legs are still slightly wet, water dripping from her body onto the pebbles. She is breathing a huge visible sigh of relief, her whole round body deflating very slightly. The danger is past. The sturdy dam is visible behind her, the river tamer now. Soft golden morning light on the pebbles, the jungle canopy above.

**After (I2I edit-style):**
> Edit image 1 (the previous frame). Elly has just been saved from a waterfall by hitting a wooden dam, and the next story beat is her stepping out of the water onto the bank.
>
> KEEP UNCHANGED: the dam structure (now a stable background element, no longer bowing), the churning water, the misty jungle canopy, the soft golden morning light, Elly's chibi proportions, soft warm gray skin, big dark-brown eyes, short stubby trunk, floppy ears, stubby legs, the 3D Pixar style, the soft plush textures.
>
> CHANGE:
> - Elly's pose: now stepping out of the water onto a shallow pebbly riverbank, one foot still in the water, one foot on the pebbles
> - Her trunk: no longer gripping the log, hanging relaxed at her side
> - Her expression: eyes open, looking down at her feet, mouth in a small shaky relieved exhale (not the previous tight scared line)
> - Her body: slightly deflating with a visible sigh of relief
> - Water drips visibly from her body onto the pebbles
> - The dam is now behind her, smaller in the frame
>
> Camera: same medium shot angle, slightly wider framing (pulled back ~10%).
>
> Mood: relieved, the danger is past.

The "after" prompt forces Flux to **edit** the previous frame rather than re-imagine. The resulting LF has clear motion signal (foot stepping, trunk releasing, expression change, body exhale, water dripping) while preserving the shared environment (dam, water, jungle, lighting, character).

### Edge case: a real scene change

If the story genuinely requires the LF to be in a different location (the FFLF "MEDIUM" or "HARD" transition per the Scene Transition Planning rules), the edit-instruction pattern still applies — but the CHANGE list must include the location swap explicitly, and the pipeline should mark the shot as `bridge` or `independent` with `break_continuity: true`:

```
Edit image 1 (the previous frame — the dark forest interior).

KEEP UNCHANGED: [character identity, clothing, the 3D Pixar style, soft
plush textures, the soft golden rim light from the FF].

CHANGE:
- Location: from dark forest interior to bright sunlit meadow clearing
- Lighting: from cool blue backlight to warm golden morning light
- Background: tangled roots → tall soft green grass, scattered
  wildflowers (yellow buttercups, white daisies)
- The hollow log opening is now visible in the far background, dark
  mouth contrasting with the bright clearing

Camera: same medium shot angle, same character position in frame.

Mood: relieved, hopeful, the danger is past.
```

This is the "break_continuity" pattern: the LF is in a new location, the pipeline marks the next shot as a new `chain_start`, and no tail-frame chaining is attempted.

### Quick reference: T2I vs I2I vocabulary

| T2I vocabulary (for FF only) | I2I vocabulary (for LF) |
|---|---|
| "Wide shot. A [character] is doing [action] in [setting]." | "Edit image 1. KEEP UNCHANGED: [...]. CHANGE: [...]." |
| "The character has [identity spec]." | (Reference sheet is already attached — don't repeat.) |
| "Lighting is [mood]." | "KEEP UNCHANGED: [mood]" or "CHANGE: lighting from X to Y." |
| "Camera is at [angle/distance]." | "Camera: [same as FF / slight change]." |

**Rule of thumb:** if the LF prompt could be rewritten as an FF prompt (i.e. it's a complete scene description), it's wrong. An LF prompt must be a delta from the FF.

---

## Prompt Length Budgets

### 1. Stills Prompts (`first_frame_prompt` & `last_frame_prompt`)
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

