# V37 — Review of Scene 01 Shot 02 and Motion Guards for LTX-Video

Detailed review of the prompt, director writing, FFLF plan, and generated images for **Scene 1 Shot 2** to diagnose the slow-motion generation issue, along with concrete guards for future prevention.

## 1. Case Study: Scene 01 Shot 02

### Context & Parameters
- **Shot ID**: `scene_01_shot_02`
- **Target Duration**: 8 seconds (192 frames at 24fps)
- **First Frame (FF)**: [scene_01_shot_02_ff.png](file:///Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/images/scene_01_shot_02_ff.png)
- **Last Frame (LF)**: [scene_01_shot_02_lf.png](file:///Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/images/scene_01_shot_02_lf.png)
- **Video Output**: [scene_01_shot_02.mp4](file:///Users/pandismart/Documents/Syncthing/story-to-video-cloud/baby-and-dolphin/videos/scene_01_shot_02.mp4)

---

### Comparison of Inputs and Outputs

#### A. Director's Script
- **Description**: Medium 3/4 shot of the baby squatting in knee-deep water.
- **Action**: Baby **lunges forward** with both hands to try to catch a crab, water splashes up around knees as he pumps legs and laughs.
- **End State**: Baby stops, notices something shiny in the wet sand, **leans forward to pick it up**.

#### B. FFLF Plan
- **First Frame (FF)**: Baby in shallow water, knees bent, gripping a shiny shell in his left hand.
- **Last Frame (LF)**: Baby lunges forward, hands extended and splashing water; torso bent and head turned to the right.

#### C. Generated Images
- **FF Image**: The model successfully generated the baby in a stable squatting pose.
- **LF Image (Grok Edit)**: The baby is depicted in the *exact same squatting pose* as the FF. The water ripples, splash details, and sand texture changed slightly, but the character's skeletal outline is virtually identical.
- **Video Output**: Because the start and end images have identical character poses, LTX-Video has no joint/skeletal trajectory to interpolate over the 8-second duration. The model stretches the minimal difference over the 192 frames, resulting in a frozen-like "slow-motion" effect where the character is static and only local water ripples animate.

---

## 2. Root Cause Analysis

1. **Grok Edit Structural Bias (Pose Inertia)**:
   - When performing image-to-image editing via `xai/grok-imagine-image/edit` with the FF image as the primary reference, the model prioritizes structural alignment. 
   - A dramatic skeletal change (shifting from a stable squat to a forward lunge/lean) violates the model's structural preservation bias. The edit model localizes changes to textures (splashes, water ripples) while preserving the character's layout.
   
2. **Subtle Camera Delta**:
   - The planned camera change was a "slight dolly-in (~10–15%)". Over 8 seconds, this dolly-in is too subtle to create significant optical flow across the scene.
   
3. **Duration Mismatch**:
   - Stretching a static pose over an 8-second duration amplifies the frozen look. LTX-Video needs a substantial delta to distribute over such a long timeline.

---

## 3. Recommended Guards & Prevention Strategies

To prevent these issues in future runs and on subsequent scenes, we must implement structural guards across the planning, prompting, and execution steps:

### Guard 1: Conditional Generator Selection (T2I vs. Edit)
- **Problem**: Edit models cannot alter skeleton poses significantly when constrained by a source image.
- **Guard Rule**: If a shot has a `delta_type` of `pose-change` in `lf_delta_plan.json` requiring a major skeletal shift:
  - **Do NOT** use `grok_edit` with the first frame as the structural reference.
  - **DO** use `grok_t2i` (Text-to-Image) to generate the last frame from scratch.
  - Pass the **character sheet** and the **background prompt** (or background asset) as style/IP references to ensure aesthetic and identity consistency, without locking the character into the FF pose.
  - For minor transitions (like `expression-shift` or `particle-motion`), continue using `grok_edit` to ensure pixel-perfect background alignment.

### Guard 2: Contrast-Based Prompt Directives
- **Problem**: Edit models ignore movement descriptions if they are phrased additively.
- **Guard Rule**: When generating the last frame prompt via `lf_shot_prompter`, if a pose change is requested, force the LLM to use contrast language:
  - *"Remove the stable squatting pose from the first frame. Replace it entirely with a dynamic pose where the torso is bent forward at a 45-degree angle, limbs are extended, and the posture has shifted..."*
  - Explicitly telling the model what to *remove* or *replace* encourages the edit model to ignore the structural prior of the first frame.

### Guard 3: Enforce Camera Motion as a Motion Buffer
- **Problem**: When character motion is minimal, the entire frame looks frozen.
- **Guard Rule**: For any shot longer than 6 seconds that has minimal character pose changes (e.g., `expression-shift`, `particle-motion`):
  - The FFLF planner must enforce a **continuous camera movement** (e.g., lateral tracking pan, slow crane down, or 3D dolly-out).
  - The motion of the background relative to the foreground provides necessary optical flow for LTX-Video, making the scene feel alive even if the character is static.

### Guard 4: Strict Duration-to-Motion Caps
- **Problem**: Long shots with minimal action produce slow-motion artifacts.
- **Guard Rule**: Enforce a strict relationship between duration and delta complexity in the `lf_delta_planner` and `Director Agent`:
  - **3 to 5 seconds**: Recommended for micro-movements, expression shifts, or small background actions.
  - **6 to 9 seconds**: Requires a standard pose change or continuous camera motion.
  - **10 to 12 seconds**: Requires both a major pose change and a clear environmental/camera shift.

---

## 4. Proposed Logic Modification in `step5_5_lf_prompter`

To implement **Guard 1**, we can modify `step5_5_lf_prompter.py` to allow the model to choose between `"grok_edit"` and `"grok_t2i"` depending on the `delta_type`. 

For example, when `delta_type` is `pose-change`:
1. `prompt_type` is set to `"grok_t2i"`
2. The `reference_images` array omits the `ff_image` placeholder, referencing only the `character_sheets` to maintain identity.
3. The prompt describes the scene from scratch based on the FF prompt but with the new pose, instead of relative edits.
