# Story Manifest Format & Prompt Composition Rules

## Story Manifest JSON Schema

```json
{
  "title": "story-slug",
  "display_title": "Human-Readable Title",
  "style": "Style descriptor used across all prompts",
  "characters": [
    {
      "id": "character_id",
      "name": "Character Name",
      "identity_spec": "Full visual description for reference sheets and scene prompts"
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "title": "Scene Title",
      "characters_present": ["character_id", "..."],
      "setting": "Environment description",
      "action": "What happens in this scene",
      "emotion": "Emotional tone",
      "camera": "Camera angle/framing"
    }
  ]
}
```

## Prompt Composition Rules

### Full Prompt (1-2 characters)

Use the full `identity_spec` for each character:

```text
Characters in this scene must match the provided reference images exactly:
- {name}: {identity_spec}

Scene setting: {setting}.
Action: {action}.
Mood: {emotion}.
Camera: {camera}.
Style: {style}.
```

### Abbreviated Prompt (3+ characters)

Use shortened identity specs (key distinguishing features only) to keep prompt length manageable:

```text
Characters in this scene must match the provided reference images exactly:
- {name}: {abbreviated_key_features}
...

Scene setting: {setting}.
Action: {action}.
Mood: {emotion}.
Camera: {camera}.
Style: {style}.
```

### Anchor Phrase

Always include `"Characters in this scene must match the provided reference images exactly"` — this anchors the Qwen Image Edit model to the reference sheets and produces more consistent character depictions.

### Style Consistency

The `style` field from the manifest should match across:
1. **Character reference sheets** — the style used to generate them
2. **Scene prompts** — included verbatim in every scene prompt
3. **I2V motion prompts** — implied by the animation model

If reference sheets were generated with a different style, note the mismatch may cause inconsistency.

## Motion Prompt Format (for I2V)

Motion prompts describe **movement**, not the still image. They should:
- Start with what the main character does (verb-first)
- Include secondary motions (crowd reactions, environmental movement)
- Note camera motion (dolly, track, hold)
- NOT re-describe the scene appearance (the I2V model sees the input image)

```text
{character_1} {primary_action} while {character_2} {secondary_action}. 
{environmental_motion}. The camera {camera_motion}.
```

## Character-to-Image Mapping

| Characters in Scene | Ref Image Assignment | Notes |
|---|---|---|
| 1 character | [char_ref, char_ref, char_ref] | Duplicate to fill 3 slots |
| 2 characters | [char1_ref, char2_ref, char1_ref] | Fill 3rd slot with most important char |
| 3 characters | [char1_ref, char2_ref, char3_ref] | Perfect fit |
| 4+ characters | [char1_ref, char2_ref, char3_ref] | Pick top 3 by visual importance |

## Tested Story: Hare and Tortoise Race

- 5 characters, 6 scenes
- 4/5 reference sheets on ComfyUI instance (fox missing)
- All 6 scenes generated successfully in ~3 minutes on RTX 3090
- Fox fallback: used tortoise reference sheet (similar size woodland character)