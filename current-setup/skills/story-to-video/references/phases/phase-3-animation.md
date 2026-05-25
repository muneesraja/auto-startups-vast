# Phase 3: Animate Scenes (LTX 2.3 I2V) — FUTURE

> **Status: In testing.** This phase is not yet integrated into the automated pipeline.
> Requires `ltx23-video-gen` skill for RunPod provisioning.

## Motion Prompt Format

Motion prompts describe **movement**, not the still image. They should:
- Start with what the main character does (verb-first)
- Include secondary motions (crowd reactions, environmental movement)
- Note camera motion (dolly, track, hold)
- NOT re-describe the scene appearance (the I2V model sees the input image)

```text
{character_1} {primary_action} while {character_2} {secondary_action}. 
{environmental_motion}. The camera {camera_motion}.
```

Example (from hare-and-tortoise):
```text
Hare jolts upright, ears snapping high as he fumbles for the gold watch on his wrist. 
His eyes widen, his mouth falls open, and he twists toward the finish line with a sharp inhale. 
Long shadows stretch farther across the path as leaves tremble in a cooler breeze. 
The camera pushes in from a medium close-up to a tighter view as panic takes over his face.
```

## Motion Prompt Source

The `story_manifest.json` `action` field describes what happens — convert it to motion-focused text:
1. Remove all visual description (the I2V model sees the input image)
2. Convert actions to present-tense verbs with physical detail
3. Add camera motion that matches the `camera` field from the manifest
4. Keep it concise (~3-4 sentences max)
