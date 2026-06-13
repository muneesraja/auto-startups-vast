# Ideogram 4.0 Prompt Engineering Guide

Ideogram 4.0 uses **structured JSON prompts** (rather than simple natural language strings) to enforce strict composition, layout, and style fidelity. The `story-to-video-cinematic` pipeline auto-composes these structured prompts under the hood.

## JSON Prompt Structure

Every prompt sent to Ideogram 4 contains three primary keys:

```json
{
  "high_level_description": "Observational summary of the full scene",
  "style_description": {
    "medium": "illustration | cinematic_still | 3d_render | photograph",
    "aesthetics": "Global aesthetic style, colors, lighting properties",
    "lighting": "Clean studio lighting, soft volumetric shadows, etc."
  },
  "compositional_deconstruction": {
    "background": "Description of the background shell (ground, sky, walls)",
    "elements": [
      {
        "type": "obj",
        "bbox": [y1, x1, y2, x2],
        "desc": "Description of specific foreground object/character"
      }
    ]
  }
}
```

---

## Bounding Box (bbox) Coordinate System

- The coordinates `[y1, x1, y2, x2]` range from `0` to `1000`.
- **y-axis:** `0` is the top edge, `1000` is the bottom edge.
- **x-axis:** `0` is the left edge, `1000` is the right edge.
- The coordinate `y1 < y2` and `x1 < x2` define the top-left and bottom-right points of the bounding box.

### Example bounding box values:
- **Left half of the screen:** `[0, 0, 1000, 500]`
- **Right half of the screen:** `[0, 500, 1000, 1000]`
- **Centered character:** `[200, 250, 900, 750]`
- **Foreground item (bottom right):** `[700, 700, 1000, 1000]`

---

## Prompt Formula for Cinematic Assets

### 1. Character Sheets
To generate clean, consistent character sheets from front, 3/4, and side views, the pipeline sets a white backdrop and splits the bounding boxes horizontally:
- **Front view:** `[50, 50, 950, 350]`
- **3/4 view:** `[50, 380, 950, 650]`
- **Side view:** `[50, 680, 950, 950]`

### 2. Scene keyframes
To position characters and control their layout relative to environments:
- The global settings (lighting, camera direction, color grading) go in `style_description`.
- The environment shell (sky, road, architecture) goes in `background`.
- Characters are placed inside the `elements` array using explicit bounding boxes (`bbox`) and described individually to prevent the model from fusing their traits.
