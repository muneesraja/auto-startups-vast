# MiniMax H3 Operational Modes & Prompting Guide

Comprehensive guide for authoring MiniMax H3 prompts across all operational modes, distilled from official MiniMax specifications and production benchmarks.

---

## 1. Operating Modes Overview

MiniMax H3 operates in five distinct modes depending on conditioning assets:

| Mode | Conditioning Assets | Prompt Sections | Mandatory Line 1 Alignment Syntax | Primary Use Case |
|---|---|---|---|---|
| **Ref2VA** (Full-Reference) | Storyboard sheet + optional character/location/object images, tail video, audio | 6 sections (`subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`) | Embedded in `subject_definitions` & `retention_analysis` | Multi-shot story production, storyboard-directed scenes, complex staging |
| **FL2VA** (First & Last Frame) | 2 keyframe images (first & last) | Mandatory alignment line + 3 core fields | `How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot N) aligns with the S.SS-second mark of the target video.` | Continuous single-shot morphing, precise scene-to-scene landing, driftless action |
| **I2VA** (Image-to-Video) | 1 starting frame image | Mandatory alignment line + 3 core fields | `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.` | Single keyframe development forward, opening shots |
| **L2VA** (Last-to-Video) | 1 ending frame image | Mandatory alignment line + 3 core fields | `How the reference pictures align with the target video — <Picture 1> (from [Shot N]) aligns with the S.SS-second mark of the target video.` | Precise convergence onto an ending pose, reveal, or cliffhanger |
| **T2VA** (Text-to-Video) | None (pure text) | 3 core fields directly | None (starts directly with `integrated_multimodal_description:`) | Establishing cutaways, environment shots without prior assets |

---

## 2. The "One Job" Rule for Multi-Reference Assets

When passing multiple reference files to MiniMax H3 (up to 9 images, 3 videos, 3 audio tracks — max 12 total), assign **one clear primary responsibility** to each asset:

1. **Identity Reference**: An image defining facial structure, hairstyle, and skin tone.
2. **Wardrobe/Prop Reference**: An image defining specific clothing, gear, or hand-held items.
3. **Staging/Storyboard Reference**: `<Picture 1>` defines camera viewpoint, panel blocking, and composition progression across the grid.
4. **Motion/Continuation Reference**: `<Video 1>` defines the preceding clip's tail motion, physical momentum, and starting pose.
5. **Vocal Timbre Reference**: `<Audio 1>` provides timbre and pitch cadence for a specific speaker `(Sx)`.

> **Rule:** Never assign conflicting visual jobs to two different image references. If `<Subject 1>` derives appearance from `<Picture 2>`, `<Picture 1>` must be strictly restricted to storyboard framing/staging.

---

## 3. Base Modes Contract (I2VA / FL2VA / L2VA / T2VA)

Base modes use a two-part structure:
- **Part 1**: The mandatory image-alignment instruction (absent in T2VA). Followed by exactly one blank line.
- **Part 2**: The three core fields:
  ```text
  integrated_multimodal_description: [Shot 1] ...

  overall_soundscape: ...

  non_diegetic_music: ...
  ```

### 3.1 I2VA Template
```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, the young woman shown in <Picture 1> remains beside the rain-covered train window, preserving her appearance, clothing, seat position, and the carriage layout. The camera trucks right with small amplitude at slow speed as she lifts her gaze toward passing city lights. Her reflection glides across the glass while she (S1) softly says: <d>[English] I get off at the next station.</d> She folds the letter along its crease.

overall_soundscape: The train wheels produce a steady metallic rhythm beneath a low ventilation hum. Rain ticks against the window while paper rustles softly in her hands.

non_diegetic_music: Sustained cello notes at a slow tempo with widely spaced piano tones, gradually decreasing in volume.
```

### 3.2 FL2VA Template (Keyframe Interpolation)
```text
How the reference pictures align with the target video — Picture 1 (from Shot 1) aligns with the 0.00-second mark of the target video; Picture 2 (from Shot 1) aligns with the 8.00-second mark of the target video.

integrated_multimodal_description: [Shot 1] Live-action, cinematic, a rain-soaked cyclist begins in the position and framing established by Picture 1, holding a closed black umbrella beside a silver bicycle. The camera pulls out with small amplitude at slow speed as she releases the handlebar, raises the umbrella above her shoulder, and presses the runner upward until the canopy opens. Water rolls from the expanding fabric while she steps beneath it, rotates the handle into the final angle, and settles into the pose, spacing, and composition established by Picture 2 at the end of the shot.

overall_soundscape: Rain falls steadily on the pavement, followed by the metallic click of the umbrella runner and the soft snap of the canopy opening. Water drips from the bicycle frame as distant traffic passes.

non_diegetic_music: N/A
```

---

## 4. Full-Reference Mode (Ref2VA) Contract

This is the canonical format for `story-maker-v5` generations conditioned on storyboard sheets.

### Section Order (Strict)
1. `subject_definitions:`
2. `summary:`
3. `retention_analysis:`
4. `detailed_description:`
5. `overall_soundscape:`
6. `non_diegetic_music:`

### 4.1 Optimal Depth & Information Density
- **Sweet Spot**: **350–500 English words** in `detailed_description`.
- **Structure**:
  - 1–2 sentence style and cinematography statement *before* `[Shot 1]`.
  - `[Shot 1]` with **no timestamp**.
  - Subsequent shots: `[Shot N] At MM:SS.mmm, ...` with strictly increasing generation-local timestamps.
  - One dominant action beat per shot.
- **No Tag Stuffing**: Never include tags like `"4k"`, `"8k"`, `"masterpiece"`, `"trending on artstation"`, or `"unreal engine"`. MiniMax H3 is trained on natural narrative language; tag stuffing causes stiff, synthetic results.

### 4.2 Camera Motion 3D Formula
Always specify camera movements along three dimensions:
$$\text{Motion Type} + \text{with [small|large] amplitude} + \text{at [slow|fast] speed}$$

Examples:
- `The camera pushes in with small amplitude at slow speed toward the folded letter in her hands.`
- `The camera pans right with large amplitude at fast speed, revealing the open doorway.`
- `The camera holds a static shot as the character exits frame left.`

### 4.3 Facial Scale & Framing Strategy
- **Community Finding**: Heads and faces that occupy less than 15% of frame height (e.g. extreme wide or distant shots) suffer detail degradation and facial drift in H3.
- **Directing Mitigation**:
  - Reserve extreme wide shots for environment orientation or rapid physical locomotion.
  - Motivate quick cuts to Medium Close-Up (`MCU`) or Close-Up (`CU`) for spoken dialogue, emotional reactions, or decisive character decisions.
  - Explicitly describe facial features (eyebrows, gaze direction, mouth state) in close shots.

### 4.4 Seamless Continuation for Generations 2+
When generating `g(K+1)` conditioned on `g(K)`'s rendered tail (`tail_sN_gK.mp4` attached as `<Video 1>`):
1. In `summary`: Use `[video continuation + reference generation]`.
2. In `subject_definitions`: `<Video 1> is the previous generation's rendered tail and continuation starting point.`
3. In `retention_analysis`: `<Video 1> (continuation starting point): fully_preserved - ending pose, staging, lighting, and motion state.`
4. In `detailed_description`: Begin the opening shot with:
   `"The target video is a seamless continuation from <Video 1>. [Shot 1] begins directly from the ending pose, camera angle, and lighting of <Video 1>..."`

### 4.5 Audio & Dialogue Separation
MiniMax H3 generates synchronized 32kHz stereo audio directly. To guarantee pristine audio:
- **Spoken Dialogue**: Attribute with stable speaker IDs `(S1)`, `(S2)`. The delivery description sits outside `<d>`; exact verbatim words sit inside:
  `<Subject 1> (S1) turns sharply and says with hushed urgency: <d>[English] We need to move now!</d>`
- **Voiceover**: Must use exact syntax:
  `says in an off-screen voiceover: <d>[English] ...</d> while his lips remain completely closed.`
- **Cuts Across Dialogue**: Use `<scenetrans>` at connecting points in both shots and specify that audio continues seamlessly across the cut.
- **`overall_soundscape`**: 1–4 continuous sentences of diegetic ambience, Foley (footsteps, fabric, props), impacts, and non-verbal human sounds (breaths, grunts, laughter). NEVER include score or musical instruments here.
- **`non_diegetic_music`**: 1–3 sentences specifying non-diegetic score: instrumentation, tempo/BPM, rhythm, and dynamics. Synced to the action curve (`anticipation → movement → impact → sound → reaction → music hit`). Use `N/A` if no score.
