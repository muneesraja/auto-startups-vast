# Example 10: Evaluation Gates Walkthrough

V3 introduces five automated quality evaluation gates that run during wave execution. If enabled, the orchestrator invokes a vision language model (via Gemini or OpenRouter) to evaluate generated images and videos against design references.

This example walks through each gate for the Pippin & Miko story.

---

## Gate 1: Character Sheet QA
* **When**: Fired in **Wave 0** after generating a character sheet.
* **Passed Args**:
  - `image_path`: generated character sheet image
  - `reference_images`: `[]` (none)
* **Goal**: Verifies the sheet contains multiple views (front, side, back) of a character on a clean, solid background.
* **Expected Response JSON**:
  ```json
  {
    "character_likeness": 9.0,
    "style_match": 8.5,
    "expression_neutrality": 9.5,
    "overall": 9.0,
    "rejected": false,
    "rejection_reason": "",
    "evidence": "Character is drawn consistently from multiple angles on a light gray background."
  }
  ```

---

## Gate 2: FF Scene Composition
* **When**: Fired in **Wave 1** after generating a raw scene still.
* **Passed Args**:
  - `image_path`: raw scene still
  - `reference_images`: character sheet(s)
  - `ff_prompt`: target text prompt
* **Goal**: Verifies the overall scene layout, characters present, and environmental descriptors match the prompt.
* **Expected Response JSON**:
  ```json
  {
    "composition_accuracy": 9.0,
    "environment_match": 8.0,
    "character_presence": 10.0,
    "style_consistency": 8.5,
    "overall": 8.8,
    "passed": true,
    "issues": []
  }
  ```

---

## Gate 3: Klein Consistency Check
* **When**: Fired in **Wave 2a** after Flux Klein character editing.
* **Passed Args**:
  - `image_path`: edited still
  - `reference_images`: `[raw_scene_still.png]` + character sheets
* **Goal**: Evaluates if the character edited into the scene matches the reference sheet, and if the background environment was preserved from the raw still.
* **Expected Response JSON**:
  ```json
  {
    "character_likeness": 8.5,
    "background_preservation": 9.5,
    "edit_quality": 8.0,
    "overall": 8.6,
    "passed": true,
    "issues": []
  }
  ```

---

## Gate 4: LF Delta Verification
* **When**: Fired in **Wave 2b** (and wave continuation LFs) after deriving the Last Frame from the First Frame.
* **Passed Args**:
  - `image_path`: First Frame (FF)
  - `reference_images`: `[Last_Frame.png]`
  - `lf_edit_instruction`: delta change description (e.g., "glowing butterfly lands in front of him")
* **Goal**: Checks if the change between FF and LF is exactly as described, subtle enough to permit smooth video interpolation, and character identity/background are preserved.
* **Expected Response JSON**:
  ```json
  {
    "delta_accuracy": 9.0,
    "identity_preserved": 9.5,
    "background_preserved": 9.5,
    "delta_magnitude": 9.0,
    "overall": 9.2,
    "passed": true,
    "issues": []
  }
  ```

---

## Gate 5: Final Video Story Coherence
* **When**: Fired at the **Final Stage** after programmatic stitching of individual video clips.
* **Passed Args**:
  - `video_path`: base64-encoded `final_stitched_video.mp4`
  - `story_summary`: Intended story narrative
  - `characters_list`: list of characters expected
* **Goal**: Evaluates overall narrative logic, consistency of characters throughout the stitched clips, and transitions.
* **Expected Response JSON**:
  ```json
  {
    "perceived_story": "A baby panda with a red scarf explores a forest clearing and discovers a blue butterfly. He reaches out to touch it, and they bond.",
    "story_matches_intent": true,
    "character_consistency": 8.5,
    "transition_smoothness": 9.0,
    "visual_quality": 8.0,
    "jump_cut_timestamps": [],
    "overall_score": 8.5,
    "passed": true,
    "issues": []
  }
  ```

---

## Failure Case Example

If a quality gate fails (e.g., Gate 3 likeness score falls below 6):

### Evaluator Response
```json
{
  "character_likeness": 4.0,
  "background_preservation": 9.5,
  "edit_quality": 6.0,
  "overall": 5.8,
  "passed": false,
  "issues": ["Panda is missing the red scarf from reference sheet 1."]
}
```

### pipeline_status.json Entry
```json
"s01_sh01_ff_edit": {
  "status": "completed",
  "output": "s01_sh01_ff_edited.png",
  "eval": {
    "gate": "klein_consistency",
    "passed": false,
    "scores": {
      "character_likeness": 4,
      "background_preservation": 9.5,
      "edit_quality": 6
    },
    "overall": 5.8,
    "issues": ["Panda is missing the red scarf from reference sheet 1."]
  }
}
```

*Note: Following the 'log and continue' decision policy, a gate failure does not halt execution, but registers as a failed gate in the run logs and `pipeline_status.json` for post-run review.*
