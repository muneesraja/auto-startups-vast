# V25 Follow-up: LF Prompt Environment Fix

## Problem

After V25 removed the FF image as a reference for LF generation, the generated LF images lost their backgrounds/environments. Grok Edit with only character sheet references (which are on white backgrounds) produced LF images with blank/white backgrounds or completely different compositions.

**Root cause**: The LF prompts only described character deltas (pose changes, expression shifts) without repeating the full environment description. Previously, the FF image carried the environment context visually. Without it, Grok Edit had no scene information.

### Example — scene_02_shot_01:
- **FF prompt**: "...Soft turquoise water blurred in the background, wet reflective sand patch, warm morning light..."
- **LF prompt**: "...Small sand grains disturbed around the shell." — No ocean, sky, or beach context.

## Fix

Updated `lf_shot_prompter.md` system prompt:

1. Added **CRITICAL** callout explaining why environment is mandatory
2. Changed prompt structure template: `[FULL environment description — setting, lighting, atmosphere, key props, carried over from FF with any delta changes applied]`
3. New Rule #3: "ALWAYS include the full environment description. Copy the environment block from the corresponding FF prompt and apply only the delta changes to it."
4. Increased word count target from 30-60 to **50-90 words** to accommodate the mandatory environment block
5. Updated all examples to include full environment descriptions
6. Added a new "Beach Scene LF" example specifically demonstrating environment carry-over

## Files Changed

- `system_prompts/lf_shot_prompter.md` — Prompt-only fix, no code changes
