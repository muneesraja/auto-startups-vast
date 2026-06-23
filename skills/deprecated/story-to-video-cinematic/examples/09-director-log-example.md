# Example 09: Director Log Specification

The `director_log.json` file is a required V3 component that captures the agent's pre-execution analysis and reasoning. Writing this file helps human operators and debugging agents understand why specific shot layout, continuity, and prompting decisions were made.

This example walks through a complete `director_log.json` for the "Pippin & Miko" story.

## Pippin & Miko: `director_log.json`

```json
{
  "created_at": "2026-06-16T10:45:00Z",
  "agent_model": "gemini-3.5-flash",
  "story_source": "discussion-and-docs/stories/pippin_and_miko.txt",
  "total_scenes": 2,
  "total_shots": 3,
  "decisions": [
    {
      "from_shot": "s01_sh01",
      "to_shot": "s01_sh02",
      "decision": "##continue",
      "reasoning": "Shot 2 follows Pippin immediately after he discovers the butterfly. Visual continuity must be preserved since he stays in the same forest clearing, but the camera pushes forward."
    },
    {
      "from_shot": "s01_sh02",
      "to_shot": "s02_sh01",
      "decision": "##cut",
      "reasoning": "Scene 2 introduces a time skip and location change (Miko's treehouse). We cut visual continuity and request a fresh establishing scene still from Ideogram."
    }
  ],
  "prompt_rationale": {
    "s01_sh01": {
      "ff_prompt_reasoning": "Wide establishing shot of a sunlit forest clearing to set the scene mood. Focus on Pippin the baby panda sitting in the grass looking up.",
      "lf_edit_reasoning": "Subtle delta: a glowing blue butterfly lands on a wildflower in front of Pippin. Limited to a single change for clean FFLF interpolation.",
      "motion_reasoning": "Gentle zoom-in on the butterfly landing, focusing the viewer's attention."
    },
    "s01_sh02": {
      "ff_prompt_reasoning": "FF is derived automatically from Shot 1's tail frame to guarantee perfect visual continuity.",
      "lf_edit_reasoning": "Pippin raises a paw toward the butterfly. Character identity and background must remain identical.",
      "motion_reasoning": "Pippin's paw moves slowly, requiring low-to-medium camera motion to avoid artifacts."
    },
    "s02_sh01": {
      "ff_prompt_reasoning": "Wide shot of a giant redwood tree with Miko's wooden treehouse built into the branches.",
      "lf_edit_reasoning": "Miko the monkey waves from the balcony of the treehouse.",
      "motion_reasoning": "Camera pans slightly upwards from the trunk to the balcony."
    }
  },
  "character_design_notes": {
    "pippin": "Pippin wears a signature red scarf which acts as a strong visual anchor for Flux Klein consistency checks.",
    "miko": "Miko wears a green leaf hat to distinguish him and provide a clear reference feature."
  }
}
```

## When is this log written?

The log MUST be written by the agent *prior* to executing `cinematic_orchestrator.py`. The orchestrator does not modify this file; it is a read-only reasoning dump used during post-run debugging.
