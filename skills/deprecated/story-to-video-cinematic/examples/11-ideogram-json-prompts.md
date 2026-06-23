# Example 11: Ideogram JSON Structured Prompts

Ideogram 4 in this pipeline uses **structured JSON prompts** rather than plain text strings. The code in `ideogram_generator.py` composes this JSON automatically — the agent only needs to write natural language in `cinematic_prompt.json`. This document explains what that JSON looks like and why bounding boxes matter.

---

## The JSON Prompt Structure

Every prompt sent to Ideogram 4's CLIPTextEncode node must be a JSON string with this shape:

```json
{
  "high_level_description": "Observational summary of the full scene",
  "style_description": {
    "medium": "illustration | cinematic_still | 3d_render | photograph",
    "aesthetics": "Global aesthetic style, colors, lighting properties",
    "lighting": "Clean studio lighting, soft volumetric shadows, etc."
  },
  "compositional_deconstruction": {
    "background": "Description of background shell (ground, sky, walls, environment)",
    "elements": [
      {
        "type": "obj",
        "bbox": [y1, x1, y2, x2],
        "desc": "Description of a specific foreground object or character"
      }
    ]
  }
}
```

### Bounding Box Coordinate System

- Coordinates `[y1, x1, y2, x2]` range from **0 to 1000**.
- `y` axis: `0` = top, `1000` = bottom.
- `x` axis: `0` = left, `1000` = right.
- Rule: `y1 < y2` and `x1 < x2`.

---

## Common Bounding Box Patterns

| Layout | Usage | Bbox |
|--------|-------|------|
| Centred character | Single character, main subject | `[150, 250, 950, 750]` |
| Left half | 2-char scene — left character | `[150, 50, 950, 480]` |
| Right half | 2-char scene — right character | `[150, 520, 950, 950]` |
| Left third | 3-char scene — leftmost | `[100, 30, 950, 333]` |
| Centre third | 3-char scene — middle | `[100, 350, 950, 640]` |
| Right third | 3-char scene — rightmost | `[100, 660, 950, 970]` |
| Character sheet — front | 3-view character sheet | `[50, 50, 950, 350]` |
| Character sheet — 3/4 | 3-view character sheet | `[50, 380, 950, 650]` |
| Character sheet — side | 3-view character sheet | `[50, 680, 950, 950]` |
| Foreground item | Small object in corner | `[700, 700, 1000, 1000]` |

---

## Example 1: Character Sheet (3-View Layout)

**Agent writes in `cinematic_prompt.json`:**
```json
{
  "id": "pippin",
  "display_name": "Pippin the Panda",
  "description": "A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf",
  "style_notes": "3D animated, Pixar-style, chibi proportions",
  "character_sheet_prompt": "Professional character reference sheet for Pippin the Panda. Front view, 3/4 view, and side profile."
}
```

**Code (`compose_character_sheet_prompt`) composes and sends:**
```json
{
  "high_level_description": "Professional character reference sheet showing Pippin the Panda from front, 3/4, and side views.",
  "style_description": {
    "medium": "illustration",
    "aesthetics": "Model-sheet character design, white background. Cinematic 3D Pixar-style, soft volumetric lighting. 3D animated, Pixar-style, chibi proportions",
    "lighting": "flat studio lighting, even illumination"
  },
  "compositional_deconstruction": {
    "background": "clean white background, isolated illustration, no shadows, no distractions",
    "elements": [
      {
        "type": "obj",
        "bbox": [50, 50, 950, 350],
        "desc": "Pippin the Panda front view. A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf"
      },
      {
        "type": "obj",
        "bbox": [50, 380, 950, 650],
        "desc": "Pippin the Panda 3/4 view. A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf"
      },
      {
        "type": "obj",
        "bbox": [50, 680, 950, 950],
        "desc": "Pippin the Panda side view. A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf"
      }
    ]
  }
}
```

> [!NOTE]
> The three bboxes divide the image horizontally into thirds (left third, centre third, right third). Ideogram uses these coordinates to place each view in its designated region, ensuring a clean multi-view reference sheet.

---

## Example 2: Single-Character Scene (Centred)

**Agent writes in `cinematic_prompt.json`:**
```json
{
  "shot_id": 1,
  "ff_prompt": "Wide establishing shot of a dense bamboo forest at golden hour. A baby panda with a red scarf walks along a mossy dirt path. Warm golden light filters through tall bamboo stalks.",
  "characters_present": ["pippin"]
}
```

**Code (`compose_scene_prompt`) composes and sends:**
```json
{
  "high_level_description": "Wide establishing shot of a dense bamboo forest at golden hour. A baby panda with a red scarf walks along a mossy dirt path. Warm golden light filters through tall bamboo stalks.",
  "style_description": {
    "medium": "cinematic_still",
    "aesthetics": "Cinematic 3D Pixar-style, soft volumetric lighting, warm color palette",
    "lighting": "cinematic lighting, dramatic composition"
  },
  "compositional_deconstruction": {
    "background": "detailed cinematic background matching the scene description",
    "elements": [
      {
        "type": "obj",
        "bbox": [150, 250, 950, 750],
        "desc": "Pippin the Panda: A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf"
      }
    ]
  }
}
```

---

## Example 3: Multi-Character Scene (Left / Right Split)

**Agent writes in `cinematic_prompt.json`:**
```json
{
  "shot_id": 3,
  "ff_prompt": "Wide cinematic shot of a sparkling waterfall cascading into a crystal-clear pool. On a mossy rock in the foreground, a baby panda with a red scarf stands next to a brown spider monkey with a green leaf hat. Both look up at the waterfall in awe.",
  "characters_present": ["pippin", "miko"]
}
```

**Code (`compose_scene_prompt`) composes and sends:**
```json
{
  "high_level_description": "Wide cinematic shot of a sparkling waterfall cascading into a crystal-clear pool. On a mossy rock in the foreground, a baby panda with a red scarf stands next to a brown spider monkey with a green leaf hat. Both look up at the waterfall in awe.",
  "style_description": {
    "medium": "cinematic_still",
    "aesthetics": "Cinematic 3D Pixar-style, soft volumetric lighting, warm color palette",
    "lighting": "cinematic lighting, dramatic composition"
  },
  "compositional_deconstruction": {
    "background": "detailed cinematic background matching the scene description",
    "elements": [
      {
        "type": "obj",
        "bbox": [150, 50, 950, 480],
        "desc": "Pippin the Panda: A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf"
      },
      {
        "type": "obj",
        "bbox": [150, 520, 950, 950],
        "desc": "Miko the Monkey: A playful brown spider monkey with long curled tail, bright amber eyes, wiry brown fur, wearing a tiny green leaf hat tilted to one side"
      }
    ]
  }
}
```

> [!IMPORTANT]
> **The order of `elements` matches `characters_present` order.** `characters_present: ["pippin", "miko"]` → Pippin is placed on the **left** (bbox x=50..480) and Miko on the **right** (bbox x=520..950). This spatial consistency is critical — Flux Klein in Wave 2a will receive these same reference images in the same positional order.

---

## How This Connects to the Pipeline

```
cinematic_prompt.json (natural language)
    │
    ▼
Wave 0: compose_character_sheet_prompt() → Ideogram JSON with 3-view bboxes → Character sheet
Wave 1: compose_scene_prompt()           → Ideogram JSON with N-char bboxes  → Raw scene still
    │
    ▼
Wave 2a: Flux Klein reads the positioned scene still + character sheet references
         → Klein knows which region to edit because Ideogram placed chars in the bbox zones
```

The bbox-based composition in Wave 1 makes Klein's job easier: if Ideogram consistently places character 1 on the left and character 2 on the right, Klein can more reliably swap character identities into the correct regions.

---

## LLM-Powered Prompt Enhancement (V3.1+)

If `global.prompt_enhancer.enabled` is set to `true`, the pipeline uses an LLM (e.g. Gemini 3.1 Flash Lite) to transform the flat templates above into rich, composition-aware structured JSON prompts.

### Character Sheet Enhancement

**Natural Language Input:**
- Name: Pippin the Panda
- Description: A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf

**LLM-Enhanced JSON Output:**
```json
{
  "high_level_description": "Professional character model sheet showcasing Pippin the Panda from front, three-quarters, and side profile views.",
  "style_description": {
    "aesthetics": "Clean model-sheet presentation, stark white studio background, high visual consistency.",
    "lighting": "Even, soft studio illumination, flat lighting to minimize shadow casting.",
    "medium": "illustration",
    "art_style": "3D animated CGI style with soft plush fur rendering and cute chibi proportions.",
    "color_palette": ["#FFFFFF", "#000000", "#FF3B30", "#8E8E93"]
  },
  "compositional_deconstruction": {
    "background": "Isolated flat white background, no casting shadows, neutral backdrop.",
    "elements": [
      {
        "type": "obj",
        "bbox": [50, 50, 950, 350],
        "desc": "Pippin the Panda front view. Standing pose facing straight forward. Cute baby panda with a round face, large dark eye patches, fluffy black-and-white fur, wearing a vibrant red knitted scarf.",
        "color_palette": ["#000000", "#FFFFFF", "#FF3B30"]
      },
      {
        "type": "obj",
        "bbox": [50, 380, 950, 650],
        "desc": "Pippin the Panda 3/4 view. Turned slightly to the side. Demonstrating body depth, same cute panda features and fluffy fur texture, red scarf draped over the shoulder.",
        "color_palette": ["#000000", "#FFFFFF", "#FF3B30"]
      },
      {
        "type": "obj",
        "bbox": [50, 680, 950, 950],
        "desc": "Pippin the Panda side view profile. Standing in profile facing to the left, showing the snout shape, round back posture, and how the red scarf wraps around the neck.",
        "color_palette": ["#000000", "#FFFFFF", "#FF3B30"]
      }
    ]
  }
}
```

### Scene Still Enhancement

**Natural Language Input:**
- Prompt: Wide establishing shot of a dense bamboo forest at golden hour. A baby panda with a red scarf walks along a mossy dirt path.
- Characters: Pippin the Panda

**LLM-Enhanced JSON Output:**
```json
{
  "high_level_description": "Wide establishing cinematic shot of a baby panda walking on a mossy path within a dense, misty bamboo forest at sunset.",
  "style_description": {
    "aesthetics": "Cinematic 3D animation, soft volumetric textures, whimsical fantasy atmosphere.",
    "lighting": "Golden hour lighting, bright shafts of sunlight filtering through the bamboo leaves, creating warm volumetric glow.",
    "medium": "cinematic_still",
    "art_style": "Lush 3D Pixar-style rendering, high fidelity materials.",
    "color_palette": ["#F1C40F", "#27AE60", "#2ECC71", "#1E272C", "#FF3B30"]
  },
  "compositional_deconstruction": {
    "background": "Dense bamboo forest under a golden sky, towering bamboo stalks, soft volumetric mist rising from the damp soil, warm dappled light.",
    "elements": [
      {
        "type": "obj",
        "bbox": [200, 250, 950, 750],
        "desc": "Pippin the Panda walking forward, looking around in wonder. Chibi proportions, fluffy black-and-white fur, bright eyes, wearing a tiny red knitted scarf that flutters slightly.",
        "color_palette": ["#000000", "#FFFFFF", "#FF3B30"]
      }
    ]
  },
  "additional_directives": [
    "Volumetric fog",
    "Rule of thirds composition",
    "Shallow depth of field, soft background blur"
  ]
}
```
