# Story Manifest Format & Prompt Composition Rules

## Story Manifest JSON Schema (v2)

The v2 manifest adds **shots** (sub-divisions of scenes), **facial_expression** per shot, and a **total_shots_budget**. This enables fine-grained control over character emotions at the per-shot level.

### Breaking Changes from v1
- `scenes[].shots` is now **required** (replaces single-scene generation)
- `scenes[].emotion` renamed to `scenes[].mood` (shots have their own `facial_expression`)
- `total_shots_budget` is required at the top level

### Full Schema

```json
{
  "title": "story-slug",
  "display_title": "Human-Readable Title",
  "style": "Style descriptor used across all prompts",
  "total_shots_budget": 50,
  "total_duration_seconds": 300,
  "characters": [
    {
      "id": "character_id",
      "name": "Character Name",
      "identity_spec": "Full visual description for reference sheets and scene prompts",
      "personality_traits": "Optional: key traits that influence expressions (e.g., 'proud, boastful, easily flustered')"
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "title": "Scene Title",
      "characters_present": ["character_id", "..."],
      "setting": "Environment description",
      "mood": "Overall emotional tone of the scene",
      "camera": "Default camera angle/framing for this scene",
      "shots": [
        {
          "shot_number": 1,
          "description": "What happens in this specific shot",
          "facial_expression": {
            "character_id": "expression descriptor (e.g., 'beaming smile, eyes bright')"
          },
          "camera_override": "Optional: different camera for this shot (overrides scene camera)",
          "duration_seconds": 6
        }
      ]
    }
  ]
}
```

### Key Fields Explained

| Field | Level | Required | Description |
|---|---|---|---|
| `total_shots_budget` | Root | ✅ | Target total shots (e.g., 50). The agent distributes these across scenes. |
| `total_duration_seconds` | Root | ✅ | Target total duration (e.g., 300 = 5 min). Default 6 sec/shot. |
| `shots[]` | Scene | ✅ | Array of shots within a scene. Each shot = 1 generated image. |
| `facial_expression` | Shot | ✅ | Per-character expression mapping for this shot. At least one character must have an expression. |
| `camera_override` | Shot | Optional | Per-shot camera that overrides the scene-level camera. |
| `personality_traits` | Character | Optional | Helps the agent choose appropriate expressions when expanding story → shots. |

### Shot Budget Guidelines

- **Default**: 6 seconds per shot → ~50 shots for 300 seconds (5 minutes)
- **Scene shots**: 3-7 shots per scene; action scenes may need more, dialogue/emotional beats fewer
- **Nothing is fixed**: The agent decides scene/shot distribution based on story pacing. A sad scene might have 3 slow shots; an action scene might have 7 rapid ones
- Each shot generates exactly **1 image**

### Facial Expression Design

`facial_expression` is a per-character map within each shot. It describes the **visible facial reaction** the character should show.

**Why this matters**: Qwen Image Edit responds well to specific facial descriptions. Instead of simply "sad", write "downcast eyes, slight frown, teary". This gives the model a concrete visual target.

**Expression sources**: The agent reads the shot description + scene mood + character personality to determine appropriate expressions. See `references/facial-expression-vocabulary.md` for the approved vocabulary.

```json
"facial_expression": {
  "hare": "nervous wide eyes, forced smile, sweat drop on forehead",
  "tortoise": "calm gentle smile, eyes half-closed, content"
}
```

### Emotion vs Facial Expression

- **Scene-level `mood`**: Sets the overall emotional tone (e.g., "tense", "joyful", "melancholic"). This influences lighting, color palette, composition.
- **Shot-level `facial_expression`**: The specific face each character makes. A "joyful" scene can still have a shot where one character looks "surprised" or "nervous".

## Prompt Composition Rules

### Shot Prompt (v2)

Each shot combines: **Characters (with expressions) + Setting + Action + Mood + Camera + Style**

```text
Characters in this scene must match the provided reference images exactly:
- {name}: {identity_spec}. Expression: {facial_expression[character_id]}

Scene setting: {setting}.
Action: {shot.description}.
Mood: {scene.mood}.
Camera: {shot.camera_override or scene.camera}.
Style: {style}.
```

### Abbreviated Prompt (3+ characters)

Use shortened identity specs (key distinguishing features only) to keep prompt length manageable, but **always include the facial expression** — this is critical for emotional consistency:

```text
Characters in this scene must match the provided reference images exactly:
- {name}: {abbreviated_key_features}. Expression: {facial_expression[character_id]}
...

Scene setting: {setting}.
Action: {shot.description}.
Mood: {scene.mood}.
Camera: {shot.camera_override or scene.camera}.
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
- **Include facial reaction transitions** (e.g., "smile fades to worried frown")
- Note camera motion (dolly, track, hold)
- NOT re-describe the scene appearance (the I2V model sees the input image)

```text
{character_1} {primary_action} while {character_2} {secondary_action}. 
{character_1}'s expression shifts from {start_expression} to {end_expression}.
{environmental_motion}. The camera {camera_motion}.
```

## Character-to-Image Mapping

| Characters in Scene | Ref Image Assignment | Notes |
|---|---|---|
| 1 character | [char_ref, char_ref, char_ref] | Duplicate to fill 3 slots |
| 2 characters | [char1_ref, char2_ref, char1_ref] | Fill 3rd slot with most important char |
| 3 characters | [char1_ref, char2_ref, char3_ref] | Perfect fit |
| 4+ characters | [char1_ref, char2_ref, char3_ref] | Pick top 3 by visual importance |

## Migration from v1 to v2

To convert a v1 manifest:

1. Add `total_shots_budget` and `total_duration_seconds` at root level
2. Rename `scenes[].emotion` to `scenes[].mood`
3. Add `personality_traits` to each character (optional but recommended)
4. Break each scene into `shots[]` — one shot per 6-second beat
5. Add `facial_expression` to each shot with per-character expression descriptions
6. Add `duration_seconds` per shot (default: 6)

Example migration — v1 scene:
```json
{
  "scene_number": 3,
  "title": "The Race Begins",
  "characters_present": ["hare", "tortoise"],
  "setting": "A dusty forest path through dappled sunlight",
  "action": "Hare sprints ahead while Tortoise plods steadily",
  "emotion": "excited",
  "camera": "wide shot"
}
```

Becomes v2:
```json
{
  "scene_number": 3,
  "title": "The Race Begins",
  "characters_present": ["hare", "tortoise"],
  "setting": "A dusty forest path through dappled sunlight",
  "mood": "excited, energetic",
  "camera": "wide shot",
  "shots": [
    {
      "shot_number": 1,
      "description": "Hare bursts forward from the starting line, legs stretched wide, dust kicking up behind",
      "facial_expression": {
        "hare": "confident grin, eyes determined, brows raised high",
        "tortoise": "serene focus, eyes forward, slight determined smile"
      },
      "duration_seconds": 6
    },
    {
      "shot_number": 2,
      "description": "Hare glances back over his shoulder at Tortoise with a mocking smirk",
      "facial_expression": {
        "hare": "mocking smirk, one eyebrow raised, corner of mouth curled",
        "tortoise": "calm plodding expression, no reaction to the taunt"
      },
      "camera_override": "medium shot, over-the-shoulder from hare's perspective",
      "duration_seconds": 6
    },
    {
      "shot_number": 3,
      "description": "Tortoise walks steadily past a milestone marker, unfazed by the distance ahead",
      "facial_expression": {
        "tortoise": "peaceful determination, eyes half-lidded, steady pace"
      },
      "duration_seconds": 6
    }
  ]
}
```

## Tested Story: Hare and Tortoise Race

- 5 characters, 6 scenes
- 4/5 reference sheets on ComfyUI instance (fox missing)
- All 6 scenes generated successfully in ~3 minutes on RTX 3090
- Fox fallback: used tortoise reference sheet (similar size woodland character)