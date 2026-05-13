---
name: story-to-video
description: >
  Given a story, extract characters and scenes, generate consistent character
  reference sheets via Gemini API, render scene-by-scene illustrations with
  smart per-scene reference selection (max 5), and produce LTX 2.3 I2V video
  prompts. Outputs to /root/story/<title>/ and uploads to Google Drive via gws skill.
---

# Story-to-Video — Visual Story Production Pipeline

> Given a story (text or outline), produce: character reference sheets → scene illustrations → LTX 2.3 video prompts. Everything organized in `/root/story/<title>/` and uploaded to Google Drive.

## When to Use This Skill

- User says "turn this story into images", "illustrate this story", "produce visuals for this"
- User says "create character sheets for my story"
- User provides a story and mentions "scenes", "video", "LTX", or "animate"
- User asks to "generate images for each scene"

---

## Phase 1: Story Parsing (Hermes — No Script)

When the user provides a story, extract a structured **story manifest**. This is pure LLM work — no script needed.

### Rules

1. Every visually distinct character (or character group like "crowd") gets an entry
2. `identity_spec` must be **purely visual** — colors, textures, clothing, proportions, build, distinguishing features. NOT personality or backstory.
3. `characters_present` — ONLY IDs of characters who **appear visually** in the scene. If a character is mentioned but not visible, don't include them.
4. Each scene gets a `camera` angle using cinematic terminology (close-up, medium shot, wide shot, etc.)
5. **Default art style:** `"Pixar-style 3D animation, rich lighting, expressive characters"` — unless the user specifies otherwise (e.g., "anime", "watercolor", "photorealistic")
6. If user specifies a custom style, use it verbatim in the `style` field

### Output: `story_manifest.json`

Save to `/root/story/<title>/story_manifest.json`

```json
{
  "title": "the-great-race",
  "display_title": "The Great Race",
  "style": "Pixar-style 3D animation, rich lighting, expressive characters",
  "characters": [
    {
      "id": "rabbit",
      "name": "Rabbit",
      "identity_spec": "anthropomorphic rabbit, tall and lean, light brown fur, long upright ears with pink insides, bright confident blue eyes, cocky grin, athletic build, wearing a red headband and white running shorts"
    },
    {
      "id": "tortoise",
      "name": "Tortoise",
      "identity_spec": "anthropomorphic tortoise, small and round, dark green shell with hexagonal patterns, gentle brown eyes, kind wrinkled smile, short stubby legs, wearing a simple blue bandana around neck"
    },
    {
      "id": "fox",
      "name": "Fox",
      "identity_spec": "anthropomorphic fox, medium build, orange-red fur with white chest, sharp amber eyes, bushy tail, wearing a referee's black-and-white striped shirt"
    },
    {
      "id": "crowd",
      "name": "Crowd Animals",
      "identity_spec": "group of various woodland animals — squirrels, birds, deer, hedgehogs — watching from the sidelines, colorful and varied"
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "title": "The Challenge",
      "characters_present": ["rabbit", "tortoise"],
      "setting": "sunny forest clearing with wildflowers, dappled sunlight through oak trees",
      "action": "Rabbit stands tall laughing and pointing at Tortoise. Tortoise looks up with quiet determination and extends a paw to challenge him.",
      "emotion": "comedic tension — arrogance vs quiet resolve",
      "camera": "medium shot, eye level, both characters facing each other"
    }
  ]
}
```

### After Saving the Manifest

1. Create the output directory structure:
   ```bash
   mkdir -p /root/story/<title>/{characters,scenes,videos}
   ```
2. Show the manifest summary to the user for confirmation before proceeding

---

## Phase 2: Character Reference Sheet Generation

Run the script to generate character reference sheets:

```bash
python3 ~/.hermes/skills/story-to-video/scripts/generate_story_assets.py \
  --manifest /root/story/<title>/story_manifest.json \
  --phase characters
```

### What the Script Does

1. Reads Gemini API key from `/root/config/token.json` → `gemini_api_key`
2. For each character in the manifest, generates a multi-angle reference sheet:
   - Top row: full-body front view, 3/4 view, side profile, back view
   - Bottom row: face close-ups (front, 3/4, profile)
   - Clean white/neutral background, studio lighting
   - Art style from the manifest's `style` field
3. Saves to `/root/story/<title>/characters/<id>_reference_sheet.png`

### Output

```
/root/story/<title>/characters/
├── rabbit_reference_sheet.png
├── tortoise_reference_sheet.png
├── fox_reference_sheet.png
└── crowd_reference_sheet.png
```

### ⚠️ MANDATORY: User Approval Gate

**After character sheets are generated, show them to the user and ask for explicit approval.**

- If the user says "Rabbit should be white, not brown" → update the `identity_spec` in the manifest → re-run
- If the user says "looks good" / "approved" / "proceed" → move to Phase 3
- **DO NOT proceed to scene generation without approval**

---

## Phase 3: Scene Rendering with Smart Reference Selection

Run the script to generate scene images:

```bash
python3 ~/.hermes/skills/story-to-video/scripts/generate_story_assets.py \
  --manifest /root/story/<title>/story_manifest.json \
  --phase scenes
```

### 🔑 Smart Reference Image Selection

The script reads `characters_present` from each scene and attaches **ONLY** the relevant character reference sheets as context images. This is critical for quality.

**Hard limit: 5 reference images per API call.**

#### Why Only Relevant References

- **Reduces noise** — irrelevant reference images confuse the model and "bleed" unwanted characters into scenes
- **Better focus** — model dedicates full attention to the characters that matter
- **Lower cost** — fewer images per request
- **Higher quality** — beyond 5 references, identity maintenance degrades

#### How It Works

```
Scene 1 ("The Challenge"):
  characters_present: [rabbit, tortoise]
  → Attach: rabbit_ref.png, tortoise_ref.png (2 images)
  → Skip: fox, crowd

Scene 2 ("The Start"):
  characters_present: [rabbit, tortoise, fox, crowd]
  → Attach: rabbit_ref.png, tortoise_ref.png, fox_ref.png, crowd_ref.png (4 images)

Scene 3 ("The Nap"):
  characters_present: [rabbit]
  → Attach: rabbit_ref.png (1 image)
  → Skip: tortoise, fox, crowd

Scene 4 ("The Steady Climb"):
  characters_present: [tortoise, rabbit]
  → Attach: tortoise_ref.png, rabbit_ref.png (2 images)

Scene 5 ("The Finish Line"):
  characters_present: [tortoise, rabbit, crowd]
  → Attach: tortoise_ref.png, rabbit_ref.png, crowd_ref.png (3 images)
```

#### Overflow Strategy (>5 Characters in One Scene)

If a scene has more than 5 characters:
1. **Priority:** Characters with speaking/action roles first
2. **Merge groups:** Background characters share one reference
3. **Text-only fallback:** If a character can't get a reference slot, include their `identity_spec` text in the prompt but skip the image reference

### Scene Prompt Structure

The script builds prompts with a split structure:

```
[IDENTITY BLOCK — top of prompt]
Characters in this scene (match EXACTLY to the reference images):
- Rabbit: anthropomorphic rabbit, tall and lean, light brown fur...
- Tortoise: anthropomorphic tortoise, small and round...

[SCENE BLOCK — after identity block]
Scene: sunny forest clearing with wildflowers, dappled sunlight
Action: Rabbit stands tall laughing and pointing at Tortoise...
Mood: comedic tension
Camera: medium shot, eye level
Style: Pixar-style 3D animation, rich lighting, expressive characters

Maintain exact character identity from the provided reference images.
```

### Output

```
/root/story/<title>/scenes/
├── scene_001.png
├── scene_002.png
├── scene_003.png
├── scene_004.png
└── scene_005.png
```

---

## Phase 4: LTX 2.3 Video Prompt Generation (Hermes — No Script)

For each generated scene image, write a companion `.txt` file containing the LTX 2.3 I2V video prompt.

### ⚠️ MANDATORY: Read the Prompting Guide First

**Before writing ANY prompt, read `references/ltx-i2v-prompting-guide.md`** — it contains the complete ruleset, examples, and anti-patterns.

### The #1 Rule

> **Never describe what's already visible in the image.**

The image defines the visual. The prompt describes what happens NEXT — motion, camera movement, environmental change.

### Prompt Requirements

- **4-8 flowing sentences**, single paragraph, under 200 words
- **Present tense** throughout
- **Structure:** Main Action → Environmental Dynamics → Camera Movement
- **Specific verbs:** "throws", "tilts", "rustles" — NOT "moves", "goes", "does"
- **Physical cues for emotions:** "lowers gaze, shoulders slump" — NOT "looks sad"
- **Camera direction:** At least one sentence specifying camera behavior
- **One continuous shot:** No scene changes or jump cuts
- **No negative prompts**
- **No quality tags:** "cinematic", "4k", "masterpiece" do nothing

### Example (Scene 1: The Challenge)

```
Rabbit throws his head back in exaggerated laughter, ears bouncing with each
chuckle as his paw points mockingly forward. Tortoise slowly lifts his head,
expression shifting from patience to resolve, and extends one small paw in a
steady gesture of challenge. The dappled sunlight shifts through the oak
leaves above as a gentle breeze stirs the wildflowers at their feet. The
camera holds steady at eye level in a medium shot, capturing the size
contrast between the two characters.
```

### Save Location

Each prompt saved alongside its image:
```
/root/story/<title>/scenes/
├── scene_001.png
├── scene_001.txt    ← LTX video prompt
├── scene_002.png
├── scene_002.txt
├── ...
```

---

## Phase 5: Google Drive Upload (via `gws` Skill)

After all images and prompts are generated, use the **existing `gws` skill** to upload the entire story folder to Google Drive.

### Upload Structure

```
📁 Google Drive: Stories/
└── 📁 The Great Race/
    ├── 📄 story_manifest.json
    ├── 📁 characters/
    │   ├── 🖼️ rabbit_reference_sheet.png
    │   ├── 🖼️ tortoise_reference_sheet.png
    │   ├── 🖼️ fox_reference_sheet.png
    │   └── 🖼️ crowd_reference_sheet.png
    ├── 📁 scenes/
    │   ├── 🖼️ scene_001.png  +  📄 scene_001.txt
    │   ├── 🖼️ scene_002.png  +  📄 scene_002.txt
    │   ├── 🖼️ scene_003.png  +  📄 scene_003.txt
    │   ├── 🖼️ scene_004.png  +  📄 scene_004.txt
    │   └── 🖼️ scene_005.png  +  📄 scene_005.txt
    └── 📁 videos/  (empty — for LTX output later)
```

---

## Post-Pipeline (Manual by User)

After the pipeline completes:

1. User takes `scene_NNN.png` + `scene_NNN.txt` pairs from Google Drive (or `/root/story/<title>/scenes/`)
2. Loads them into ComfyUI LTX 2.3 I2V workflow on Vast.ai GPU server
3. Generates 3-5 second video clips per scene
4. Saves video output to `/root/story/<title>/videos/`

---

## Complete Flow Summary

```
User tells a story
  ↓
Phase 1: Hermes parses → story_manifest.json (saved to /root/story/<title>/)
  ↓
Phase 2: Script generates character reference sheets
  ↓
⚠️ User approves character sheets (mandatory gate)
  ↓
Phase 3: Script generates scene images (smart ref selection, max 5 per scene)
  ↓
Phase 4: Hermes writes scene_NNN.txt video prompts (reads ltx-i2v-prompting-guide.md)
  ↓
Phase 5: Hermes uses gws skill to upload to Google Drive
  ↓
Done! User runs LTX 2.3 I2V manually in ComfyUI
```

---

## Script Reference

### Full Command

```bash
python3 ~/.hermes/skills/story-to-video/scripts/generate_story_assets.py \
  --manifest /root/story/<title>/story_manifest.json \
  --phase <characters|scenes|all> \
  [--max-refs 5] \
  [--force]
```

### Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--manifest` | Yes | — | Path to `story_manifest.json` |
| `--phase` | Yes | — | `characters`, `scenes`, or `all` |
| `--max-refs` | No | `5` | Max reference images per scene API call |
| `--force` | No | `false` | Regenerate even if output files exist |

### API Key

The script reads the Gemini API key from:
```
/root/config/token.json → { "gemini_api_key": "..." }
```

---

## Available References

| File | When to use |
|------|-------------|
| `references/ltx-i2v-prompting-guide.md` | Before writing ANY `scene_NNN.txt` video prompt |
