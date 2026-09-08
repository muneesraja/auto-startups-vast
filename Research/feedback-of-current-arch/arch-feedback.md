The architecture is strong in separation of concerns, staged validation, and explicit artifact flow. The main improvements I would focus on are **state management, contract enforcement, reproducibility, failure recovery, and reducing LLM self-approval bias**.

**High-priority architectural feedback**

1. **Introduce a machine-readable canonical model underneath the Markdown**
   Markdown is useful for human review, but it is currently both the authoring format and the integration contract. That creates parsing fragility and makes cross-artifact consistency expensive.

   Add canonical JSON models for:
   - story metadata
   - entities/assets
   - beats
   - scenes
   - spatial plans
   - generations
   - shots
   - prompts
   - render metadata

   Keep Markdown as a generated or human-facing projection where possible.

   Example:

   ```text
   story.yaml
   story.json
   scenes.json
   spatial_plan_s1.json
   storyboard_s1.json
   render_manifest.json
   ```

   The validators should validate the JSON schema first. Markdown validators can then check presentation-level requirements.

2. **Create an explicit immutable run manifest**
   The current pipeline appears resume-safe, but the architecture does not define a complete run identity. You need to know exactly which source, prompts, models, settings, and code version produced each artifact.

   Add a `run_manifest.json` containing:

   ```json
   {
     "run_id": "2026-09-08T120000Z-abc123",
     "story_id": "story-name",
     "episode_id": "epi-1",
     "source_story_sha256": "...",
     "git_commit": "...",
     "config_snapshot": {},
     "providers": {},
     "model_versions": {},
     "prompt_hashes": {},
     "input_artifact_hashes": {},
     "created_at": "2026-09-08T12:00:00Z"
   }
   ```

   This is important because image and video providers can change behavior even when your prompts do not.

3. **Replace implicit stage progression with a persistent state machine**
   Gates are described clearly, but they appear partly enforced by runbook behavior. Make them executable.

   Suggested state model:

   ```text
   PLANNED
   → PLANNING_VALIDATED
   → CRITIQUE_PASSED
   → ASSETS_BUILT
   → SHEETS_BUILT
   → SHEETS_APPROVED
   → VIDEO_PROMPTS_VALIDATED
   → VIDEO_PROMPTS_APPROVED
   → RENDERING
   → RENDERED
   → CONCATENATED
   ```

   Store state in a manifest, not only in file existence. File existence cannot distinguish:
   - a stale artifact
   - a partially written artifact
   - an artifact produced from an older prompt
   - an artifact that passed validation before its dependency changed

4. **Add dependency fingerprints to every artifact**
   Each generated artifact should record the hashes of its direct inputs.

   For example, a storyboard sheet should record:

   ```json
   {
     "artifact": "storyboard_sheet_s1_g2.webp",
     "inputs": {
       "storyboard": "sha256:...",
       "spatial_plan": "sha256:...",
       "location_lock": "sha256:...",
       "character_refs": {
         "char_01": "sha256:..."
       }
     },
     "generator": {
       "provider": "replicate",
       "model": "openai/gpt-image-2",
       "prompt_sha256": "...",
       "settings": {}
     }
   }
   ```

   Then the system can automatically detect when an artifact is stale and must be rebuilt.

5. **Separate “validation” from “approval”**
   Deterministic validation can prove structural correctness. It cannot prove that:
   - the story is compelling
   - the visual composition works
   - the sheet accurately represents the storyboard
   - the generated motion is acceptable
   - the audio is usable

   Use distinct statuses:

   ```text
   INVALID
   VALID
   NEEDS_REVIEW
   APPROVED
   REJECTED
   SUPERSEDED
   ```

   In particular, GATE 0 should not be represented as “the LLM found zero FAILs.” That risks circular approval. The critique agent can produce recommendations, but the director or user should own approval.

6. **Make the critique agent adversarial rather than self-certifying**
   The current loop is:

   ```text
   Agent 6 critiques → another agent fixes → Agent 6 re-critiques
   ```

   This can converge toward satisfying the checklist rather than improving the work. Consider:

   - a separate critic prompt from the authoring prompts
   - immutable critique snapshots
   - explicit evidence required for every PASS
   - severity levels: `BLOCKER`, `MAJOR`, `MINOR`, `ADVISORY`
   - a maximum revision count
   - user escalation after repeated failures
   - optional independent second critique pass with a different rubric

   A question bank is useful, but 200+ questions can produce false confidence. Weight questions by risk instead of treating all PASS results equally.

7. **Define atomic artifact writes and locking**
   Both Claude and Python touch the same workspace. Add protections against partial or concurrent writes:

   ```text
   write artifact.tmp
   fsync
   atomic rename to artifact
   write artifact.meta.json
   ```

   Also add:
   - a per-story lock
   - a per-episode lock
   - a render lock
   - explicit `RUNNING`, `SUCCEEDED`, and `FAILED` job records

   This matters especially for background rendering and resume behavior.

8. **Add a durable job queue for rendering**
   “Fire-and-forget” is risky for paid, long-running work. `render_all.py` should operate from a render manifest or job database rather than deriving everything from directory contents.

   Each generation should have:

   ```text
   PENDING
   RUNNING
   SUCCEEDED
   RETRYABLE_FAILURE
   PERMANENT_FAILURE
   CANCELLED
   ```

   Record:
   - attempt count
   - provider request ID
   - ComfyUI prompt ID
   - start/end timestamps
   - error details
   - output checksum
   - duration
   - cost if available

   This enables safe retries and avoids duplicate paid generations.

9. **Treat audio as a first-class artifact**
   Native stereo audio is useful, but relying on generated audio for final editorial control is fragile. Separate:

   ```text
   video_track.mp4
   dialogue_track.wav
   ambience_track.wav
   effects_track.wav
   music_track.wav
   final_mix.wav
   ```

   At minimum, extract and validate:
   - sample rate
   - channel count
   - peak level
   - integrated loudness
   - clipping
   - silence gaps
   - A/V duration alignment

   The final concat stage should explicitly define whether audio is copied, mixed, replaced, or ducked.

10. **Make timing mathematically authoritative**
    There are several timing layers:

    ```text
    beat timing
    scene target duration
    generation duration
    shot timestamps
    clip duration
    tail conditioning duration
    concat duration
    ```

    Define one authoritative timing model and derive all other timings from it. Store durations in milliseconds or integer frames instead of floating-point seconds where possible.

    Add invariants such as:

    ```text
    sum(generation durations) == scene duration
    sum(shot durations) == generation duration
    final duration == sum(scene durations)
    ```

    Use tolerances only at provider boundaries.

11. **Clarify the spatial coordinate system**
    The spatial planner is one of the most valuable parts of the design, but it needs a formal coordinate contract. Define:

    - coordinate handedness
    - origin
    - units
    - camera forward direction
    - vertical axis
    - panorama convention
    - allowed camera movement
    - treatment of occlusion
    - whether coordinates describe subject centers, feet, bounding boxes, or zones

    Without this, “2.5D continuity” can become descriptive rather than enforceable.

12. **Do not rely on a “360° location lock” as a literal spatial guarantee**
    A generated wide-angle image is not a true geometric environment representation. It can support visual consistency, but it cannot reliably provide a complete 360-degree spatial map.

    I would distinguish:

    ```text
    visual location reference
    spatial layout contract
    camera-facing reference
    ```

    The spatial plan should remain authoritative. The location image should be treated as evidence/reference, not the source of geometry.

13. **Add a real visual regression layer**
    Agent 7 should produce more than a Markdown report. Store machine-readable visual QA results per sheet:

    ```json
    {
      "sheet_id": "s1_g2",
      "checks": {
        "character_presence": "PASS",
