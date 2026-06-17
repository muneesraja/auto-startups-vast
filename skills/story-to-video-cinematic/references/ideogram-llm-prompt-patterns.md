# Ideogram 4.0 LLM Prompting Patterns

This document outlines the visual structure, schemas, and coordinate constraints encoded in the Ideogram 4.0 LLM Prompt Enhancer. Use these patterns when designing prompts or evaluating generation quality.

---

## 1. Structured JSON Schema

Ideogram 4.0 supports rendering complex compositions using structured JSON schemas. Key order is strictly parsed by the model:

```json
{
  "high_level_description": "A detailed natural language overview of the entire scene composition.",
  "style_description": {
    "aesthetics": "Overall style description (e.g. '3D cartoon, soft lighting, vibrant colors')",
    "lighting": "Description of light direction, tone, intensity (e.g. 'volumetric warm sunlight')",
    "medium": "The visual format, usually 'illustration' or 'cinematic_still'",
    "art_style": "For non-photo renders. Describe the style specifically (e.g. 'Pixar character render'). Mutually exclusive with the 'photo' key.",
    "color_palette": ["#RRGGBB", "#RRGGBB"]
  },
  "compositional_deconstruction": {
    "background": "Detailed background scene description, elements, and lighting.",
    "elements": [
      {
        "type": "obj",
        "bbox": [ymin, xmin, ymax, xmax],
        "desc": "Rich visual description of this specific element (pose, textures, actions, details)",
        "color_palette": ["#RRGGBB", ...]
      }
    ]
  },
  "additional_directives": [
    "Extra composition control strings (e.g. 'rule of thirds', 'extremely detailed')"
  ]
}
```

---

## 2. Model Style Switching Rules

Ideogram 4.0 distinguishes between photographic images and illustration/artwork:

- **Illustrative Styles (Chibi, Pixar, Cartoon, Painting)**: Use the `"art_style"` key under `"style_description"`. Do not use `"photo"`.
- **Photographic Styles**: Replace `"art_style"` with `"photo"`.
- **Medium Mapping**: Choose a clear medium such as `"illustration"`, `"cinematic_still"`, or `"digital painting"`.

---

## 3. Color Palettes

Ideogram accepts hex color arrays (`#RRGGBB` in uppercase).
- **Style-level Palette**: Up to 16 hex colors under `style_description.color_palette` to define the global color tone.
- **Element-level Palette**: Up to 5 hex colors under `elements[].color_palette` to define local clothing, hair, or skin colors.

---

## 4. Bounding Box Coordinate System

Coordinates use a normalized `0` to `1000` grid:
- `bbox` format: `[ymin, xmin, ymax, xmax]`
  - `ymin`: distance from top edge (0 = top, 1000 = bottom)
  - `xmin`: distance from left edge (0 = left, 1000 = right)
  - `ymax`: bottom boundary
  - `xmax`: right boundary

### Vertical Landmark Table (Full-Body Standing)

| Body Landmark | 2:3 (Portrait) | 1:1 (Square) | 3:2 (Landscape) | 16:9 (Landscape) |
|---|---|---|---|---|
| **Top of Head** | 30 | 30 | 50 | 80 |
| **Chin** | 150 | 200 | 250 | 280 |
| **Shoulders** | 200 | 250 | 300 | 330 |
| **Chest** | 250 | 320 | 370 | 400 |
| **Waist** | 450 | 520 | 560 | 580 |
| **Hips** | 550 | 600 | 630 | 650 |
| **Knees** | 750 | 780 | 800 | 820 |
| **Ankles** | 900 | 920 | 930 | 940 |
| **Bottom Edge** | 970 | 970 | 970 | 970 |

### Crop Guidelines by Orientation

- **Full Body**: `ymin: ~30, ymax: ~950` (portrait only, avoid in 16:9).
- **Knee-Up**: `ymin: ~30, ymax: ~800`.
- **Waist-Up**: `ymin: ~30, ymax: ~600` (portrait) / `ymin: ~80, ymax: ~700` (16:9).
- **Bust-Up**: `ymin: ~30, ymax: ~450` (portrait) / `ymin: ~80, ymax: ~600` (16:9).
- **Face Close-up**: `ymin: ~30, ymax: ~300` (portrait) / `ymin: ~100, ymax: ~700` (16:9).

---

## 5. Pixel Verification

Before outputting bounding boxes, verify that the coordinate range provides sufficient raw pixels:

$$\text{Vertical Pixels} = \frac{y_{\max} - y_{\min}}{1000} \times \text{height\_px}$$
$$\text{Horizontal Pixels} = \frac{x_{\max} - x_{\min}}{1000} \times \text{width\_px}$$

- **Full Body**: requires at least `85%` of total vertical pixels.
- **Knee-Up**: requires at least `70%` of total vertical pixels.
- If dimensions are too small, coordinates will crop or distort features. Expand bounds towards the edges (`20` for min, `970` for max) to resolve.
