# Ideogram 4 Prompting, JSON Prompting, and Layout Control Guide

Last researched: 2026-06-17

This guide is written as source material for an agent skill. It focuses on practical prompt construction for Ideogram 4.0, especially JSON prompting, readable text, object placement, and bounding-box layout control.

## Executive Summary

Ideogram 4.0 is not just another natural-language text-to-image model. Its strongest mode is structured JSON prompting. Official Ideogram materials say the open-weight model was trained exclusively on structured JSON captions, and both the official open repo and developer API expose JSON-oriented workflows. Plain text can work, but JSON gives better controllability, spatial layout, typography, and color fidelity.

The most important skill behavior is:

1. Convert user intent into a structured scene plan.
2. Choose aspect ratio and resolution before placing anything.
3. Build a JSON prompt with:
   - high-level image summary
   - optional style block
   - background/environment shell
   - foreground elements with optional normalized bounding boxes
   - text elements for every literal readable string
4. Use bounding boxes only for placeable, important elements.
5. Treat floors, skies, crowds, horizons, weather, and ambient scene shell as background, not foreground objects.
6. For exact text, use `type: "text"` elements and preserve the literal string exactly.
7. For agents, generate boxes programmatically rather than expecting humans to write them by hand.

Sources used include Ideogram's official API docs, Ideogram's open-weight GitHub repository and prompting docs, Ideogram's technical blog, the cloned `EvoLinkAI/awesome-ideogram-4.0-prompts` repo, and recent Reddit user reports from `r/StableDiffusion`.

## Source Map

- Official Ideogram docs: https://docs.ideogram.ai/
- Ideogram Developer API overview: https://developer.ideogram.ai/ideogram-api/api-overview
- Ideogram 4.0 Generate API: https://developer.ideogram.ai/api-reference/api-reference/generate-v4
- Ideogram 4.0 Magic Prompt API: https://developer.ideogram.ai/api-reference/api-reference/magic-prompt-v4
- Ideogram 4.0 technical blog: https://ideogram.ai/blog/ideogram-4.0/
- Open-weight repo: https://github.com/ideogram-oss/ideogram4
- Open repo prompting guide: https://raw.githubusercontent.com/ideogram-oss/ideogram4/main/docs/prompting.md
- Open repo magic prompt system prompt: https://raw.githubusercontent.com/ideogram-oss/ideogram4/main/src/ideogram4/magic_prompt_system_prompts/v1.txt
- Cloned prompt corpus in this workspace: `repo-awesome-ideogram-4-prompts/`
- EvoLink prompt repo source: https://github.com/EvoLinkAI/awesome-ideogram-4.0-prompts
- Reddit JSON workflow discussion: https://www.reddit.com/r/StableDiffusion/comments/1twqyrf/ideogram_4_is_pretty_good_you_just_really_have/
- Reddit split-opinion workflow discussion: https://www.reddit.com/r/StableDiffusion/comments/1txm3tc/why_do_half_of_people_hate_ideogram_40_and_half/
- Reddit open-source launch discussion: https://www.reddit.com/r/StableDiffusion/comments/1tvtu2u/ideogram_40_just_open_sourced/
- Reddit negative launch/UX discussion: https://www.reddit.com/r/StableDiffusion/comments/1txnqha/ideogram_4_is_sd3_allover_again_but_worse/

## What Changed With Ideogram 4.0

Ideogram 4.0 launched on June 3, 2026 as Ideogram's first open-weight foundation model. Official materials describe it as a 9.3B parameter text-to-image model with:

- structured JSON prompting
- explicit bounding-box layout control
- color palette conditioning via hex colors
- strong multilingual text rendering
- native 2K generation
- flexible aspect ratios
- open weights in NF4 and FP8 variants
- a Qwen3-VL-8B-Instruct text encoder

The official technical blog says each training caption describes image elements with style, optional boxes, and color palettes, and that the reference pipeline validates JSON against the schema before generation. The official API exposes `/v1/ideogram-v4/generate`, where `text_prompt` and `json_prompt` are mutually exclusive. If `text_prompt` is supplied, Magic Prompt is enabled automatically. If `json_prompt` is supplied, Magic Prompt is disabled and the structured prompt is consumed directly by the diffusion model.

The open repo is even more explicit: plain text can work, but the best results come from JSON because the model's training distribution is JSON captions.

## Practical Model Mentality

Treat Ideogram 4.0 as a visual layout engine that likes structured captions, not as a casual chat prompt model.

Good agent behavior:

- Think like an art director creating a structured production brief.
- Name every important object once.
- Put background shell content in `background`.
- Put individually placeable things in `elements`.
- Put literal readable strings in `text` fields.
- Commit to exact choices instead of hedging.
- Use `bbox` for objects and text where placement matters.
- Minify JSON for direct generation when possible.

Weak agent behavior:

- Sending vague prose and hoping the model invents a coherent layout.
- Mixing mutually exclusive style options.
- Asking for exact text only in prose.
- Splitting one subject into body-part elements.
- Treating the floor or sky as a foreground object.
- Using huge overlapping boxes for many subjects.
- Omitting aspect ratio before calculating boxes.

## API-Level Notes

For Ideogram's hosted API:

- Generate endpoint: `POST https://api.ideogram.ai/v1/ideogram-v4/generate`
- It accepts multipart form data.
- `text_prompt` is a natural-language prompt. When used, Magic Prompt is enabled automatically.
- `json_prompt` is a structured prompt conforming to the Ideogram 4 JSON contract. When used, Magic Prompt is disabled.
- `text_prompt` and `json_prompt` are mutually exclusive.
- `resolution` supports Ideogram 4 2K resolutions.
- `rendering_speed` supports `TURBO`, `DEFAULT`, `QUALITY`; the docs list `FLASH` but note that `FLASH` currently returns a `400` for V4.

Magic Prompt endpoint:

- `POST https://api.ideogram.ai/v1/ideogram-v4/magic-prompt`
- Input: `text_prompt`, optional `aspect_ratio`
- Output: `json_prompt` and resolved `aspect_ratio`
- If `aspect_ratio` is `AUTO`, the model chooses a concrete ratio.
- The returned `json_prompt` can be passed directly into V4 generation.

## JSON Prompt Schema

There are several closely related JSON surfaces in the official materials:

- The hosted Magic Prompt API example returns `high_level_description`, `compositional_deconstruction`, and `style_description`.
- The open repo `docs/prompting.md` describes a schema with `high_level_description`, optional `style_description`, and required `compositional_deconstruction`.
- The open-source magic prompt system prompt emits `aspect_ratio`, `high_level_description`, and `compositional_deconstruction` in one minified JSON line.

For a general-purpose skill, use this robust schema:

```json
{
  "high_level_description": "One or two sentences summarizing the subject, medium, and whole composition.",
  "style_description": {
    "aesthetics": "Specific aesthetic terms, not a long word salad.",
    "lighting": "Specific lighting and ambience.",
    "photo": "Camera/lens/photographic treatment, if photographic.",
    "medium": "photograph",
    "color_palette": ["#1B1B2F", "#E43F5A", "#F5F5F5"]
  },
  "compositional_deconstruction": {
    "background": "The environmental shell: sky, room, walls, floor, horizon, weather, ambient lighting.",
    "elements": [
      {
        "type": "obj",
        "bbox": [120, 350, 860, 680],
        "desc": "A standalone description of one subject or object, with identity first and important visible attributes."
      },
      {
        "type": "text",
        "bbox": [60, 100, 180, 900],
        "text": "OPEN 7AM",
        "desc": "Large bold upright sans-serif headline centered across the top third, black lettering on cream paper."
      }
    ]
  }
}
```

For non-photographic outputs, use `art_style` instead of `photo`:

```json
{
  "style_description": {
    "aesthetics": "minimal, editorial, geometric",
    "lighting": "even diffuse studio lighting",
    "medium": "graphic_design",
    "art_style": "flat vector design with generous whitespace and bold sans-serif typography",
    "color_palette": ["#FFFFFF", "#111111", "#0066FF", "#00CC88"]
  }
}
```

Important schema rules:

- `compositional_deconstruction` should always exist.
- `background` comes before `elements`.
- `type: "obj"` element order: `type`, `bbox`, `desc`, `color_palette`.
- `type: "text"` element order: `type`, `bbox`, `text`, `desc`, `color_palette`.
- `bbox` and `color_palette` are optional.
- `bbox` format is `[y_min, x_min, y_max, x_max]`, normalized to `0-1000`.
- `color_palette` uses uppercase `#RRGGBB`.
- Overall palette supports up to 16 colors; per-element palette supports up to 5.
- Serialize with `ensure_ascii=false` so non-ASCII text remains literal.

## Bounding Boxes: Coordinate System

Bounding boxes use a normalized 0-1000 grid:

- `x=0` is the left edge.
- `x=1000` is the right edge.
- `y=0` is the top edge.
- `y=1000` is the bottom edge.
- Format is `[y1, x1, y2, x2]`.
- `y1 < y2`, `x1 < x2`.

Example:

```json
{
  "type": "obj",
  "bbox": [200, 350, 850, 650],
  "desc": "Golden retriever sitting upright, centered in the frame, red collar, front paws visible."
}
```

This places the dog from 20% to 85% down the image, and 35% to 65% across the image.

## How Agents Should Create Boxes

An agent should not guess boxes late. Box planning should be a separate stage.

Recommended box workflow:

1. Parse the user's requested output medium: photo, poster, product mockup, illustration, logo, UI, packaging, etc.
2. Choose aspect ratio and resolution.
3. Decide whether the scene is:
   - single subject
   - multi-subject
   - text-heavy design
   - product-centered
   - environment-heavy
4. Reserve background first.
5. Create boxes for primary subjects.
6. Create boxes for secondary objects.
7. Create boxes for exact text.
8. Verify pixel space from normalized boxes.
9. Check overlap and visual hierarchy.
10. Emit JSON.

### Pixel-Space Verification

Because the `0-1000` grid maps to the actual output resolution, box size must be checked in pixels:

```text
box_width_px = (xmax - xmin) / 1000 * width_px
box_height_px = (ymax - ymin) / 1000 * height_px
```

For a 1024x1536 portrait image:

- bbox `[30, 250, 950, 750]`
- height = `(950 - 30) / 1000 * 1536 = 1413 px`
- width = `(750 - 250) / 1000 * 1024 = 512 px`

This is sufficient for a full-body person.

For a 1680x944 landscape image:

- bbox `[80, 350, 700, 650]`
- height = `(700 - 80) / 1000 * 944 = 585 px`
- width = `(650 - 350) / 1000 * 1680 = 504 px`

This is better for waist-up or bust-up framing than full body.

### Box Presets

Use these as starting points, then adjust for aspect ratio.

Single centered subject:

```json
"bbox": [80, 280, 900, 720]
```

Full-body portrait figure:

```json
"bbox": [30, 250, 960, 750]
```

Waist-up portrait:

```json
"bbox": [60, 260, 680, 740]
```

Bust-up portrait:

```json
"bbox": [80, 300, 560, 700]
```

Left hero, right text:

```json
[
  {"type": "obj", "bbox": [120, 80, 900, 480], "desc": "Primary subject on the left."},
  {"type": "text", "bbox": [120, 540, 360, 930], "text": "HEADLINE", "desc": "Large headline on the right."}
]
```

Three subjects in a wide frame:

```json
[
  {"type": "obj", "bbox": [180, 80, 860, 330], "desc": "Left subject."},
  {"type": "obj", "bbox": [160, 375, 880, 625], "desc": "Center subject."},
  {"type": "obj", "bbox": [180, 670, 860, 920], "desc": "Right subject."}
]
```

Poster with headline, central product, bottom strip:

```json
[
  {"type": "text", "bbox": [60, 100, 190, 900], "text": "OPEN 7AM", "desc": "Bold top-third headline."},
  {"type": "obj", "bbox": [260, 300, 700, 700], "desc": "Centered product hero."},
  {"type": "obj", "bbox": [800, 80, 940, 920], "desc": "Bottom information strip."},
  {"type": "text", "bbox": [820, 120, 910, 880], "text": "123 MAIN ST\nMON-FRI", "desc": "Small footer details inside the bottom strip."}
]
```

### Shape Compensation by Aspect Ratio

The 0-1000 grid is normalized on both axes, but the actual image may be wide or tall. A bbox with equal x-span and y-span is only square in a square image.

For roughly square or round objects:

```text
(xmax - xmin) / (ymax - ymin) should roughly equal width_px / height_px
```

Examples:

- On 1:1, a square box can use equal spans: `[300, 300, 700, 700]`.
- On 16:9, a visually square object needs narrower x-span than y-span.
- On 9:16, a visually square object needs wider x-span than y-span.

### When to Use Boxes

Use boxes for:

- people
- animals
- products
- logos
- packaging panels
- readable text blocks
- signs
- speech bubbles
- foreground props
- distinct furniture
- vehicles
- UI/card regions
- key compositional anchors

Omit boxes for:

- sky
- clouds
- horizon
- fog/mist/haze
- generic distant crowds
- ground/floor/road/snow/water surface
- dense fields of small particles
- uncountable foliage
- overall paper texture or film grain

## Background vs Elements

The open-source magic prompt instructions are strict about separating scene shell from placeable elements. This is one of the most useful rules to preserve in a skill.

Background should contain:

- sky, clouds, weather, atmosphere
- horizon
- distant mountains or cityscape
- walls, floor, ceiling, windows as architecture
- ground, pavement, grass, road, water surface, snow surface
- ambient lighting
- distant blurred crowds
- room shell and architectural context

Elements should contain:

- people
- animals
- vehicles
- furniture
- plants in pots
- signs
- foreground objects
- products
- text blocks
- props
- discrete debris or objects resting on the floor

Important rule: floor and ground are background, not foreground elements. The official magic prompt system prompt notes that treating floor as an object can cause a standing subject's legs to get clipped or buried.

Shell-affixed prominent objects can be dual-mentioned:

- Mention a large fixed object in `background` to anchor it to the wall.
- Emit it as an early `obj` element to detail it.
- Put it first in `elements` so it renders behind foreground objects.

Examples:

- chalkboard covering a classroom wall
- built-in fireplace
- fixed stage proscenium
- large mounted TV
- wall-sized sign or banner

## Text Rendering Best Practices

Ideogram is historically strong at text rendering, and Ideogram 4.0 is specifically optimized for typography and design. Still, exact text should be handled deliberately.

Rules:

- Every literal readable string gets a `type: "text"` element.
- Preserve exact capitalization, punctuation, spelling, and diacritics.
- Use `\n` for natural line breaks inside one visual text block.
- Use separate text elements for visually separate blocks.
- For long titles, stack at word breaks to reduce typos.
- Do not describe exact letters only in `desc`; put them in `text`.
- If the prompt says "only one readable text element", enforce that in `additional_directives` or in the element descriptions.

Good:

```json
{
  "type": "text",
  "bbox": [90, 120, 260, 880],
  "text": "GREEN GASTRONOMY",
  "desc": "Large elegant upright serif restaurant name across the upper third, dark green lettering on cream watercolor paper."
}
```

Weak:

```json
{
  "type": "obj",
  "desc": "A poster that says Green Gastronomy somewhere."
}
```

For built environments, add realistic text unless the user asks for minimalism:

- shop signs
- menu boards
- price tags
- labels
- badges
- license plates
- jersey numbers
- product packaging text
- small posters
- address numbers

For posters and brand systems, define hierarchy:

- headline
- subheadline
- brand name
- tagline
- date/time
- CTA
- footer/legal/small print

## Prompt Style Rules

### Be Concrete

Avoid hedges:

- "things like"
- "such as"
- "for example"
- "or similar"
- "maybe"
- "could be"
- "various"
- "some kind of"

Pick concrete values:

- one material
- one color
- one font category
- one lighting condition
- one location
- one camera/framing style

### Do Not Split One Subject Into Parts

One coherent subject should usually be one `obj`.

Good:

```json
{
  "type": "obj",
  "bbox": [80, 280, 900, 720],
  "desc": "Adult golden retriever sitting upright, fluffy golden coat, red collar, tongue out, front paws aligned on the concrete step."
}
```

Bad:

```json
[
  {"type": "obj", "desc": "Dog head"},
  {"type": "obj", "desc": "Dog torso"},
  {"type": "obj", "desc": "Dog paws"},
  {"type": "obj", "desc": "Dog tail"}
]
```

Split only if objects are truly separate:

- a person and a dog
- a bottle and a glass
- a speech bubble and its text
- a poster strip and its headline

### Use Natural Photographic Defaults

The open-source magic prompt system prompt specifically warns against overusing "warm" photographic grading because it can create an obvious AI amber look. For realistic photos, prefer:

- neutral daylight
- overcast daylight
- cool-neutral white balance
- ordinary phone snapshot framing
- natural skin tone
- off-center composition

Use cinematic, bokeh, dramatic rim light, long lens, and motion blur only when the user asks for them.

### Designed Artifact vs Captured Moment

Choose the medium explicitly:

- `graphic_design`: poster, flyer, logo, packaging, book cover, menu, app icon, infographic
- `photograph`: portrait, product photo, street photo, food photo, fashion editorial
- `illustration`: watercolor, anime, comic, children's book, vector, painting
- `3D render`: CGI, isometric, product render, architectural visualization

If the user says "create a poster", use graphic design. If the user says "photo of a poster on a wall", use photograph with a poster object.

## Lessons From the EvoLink Prompt Corpus

The cloned `EvoLinkAI/awesome-ideogram-4.0-prompts` repo is a curated prompt/result corpus. It includes 32 cases sourced mostly from X/Twitter, creator communities, and public demos. Its strongest signals:

- Ideogram 4.0 is especially strong for typography, posters, design layouts, logos, packaging, and dense readable text.
- Layout-first prompts are effective even in plain text.
- The most reusable community pattern is structured blocks like:

```text
#subject: minimal coffee shop poster
#layout: headline top third, product centered, hours + #address in a bottom strip
#text: headline reads "OPEN 7AM" - exact, no typos
#style: warm film photo, lots of negative space
```

- Product packaging examples emphasize nutrition labels and readable packaging text.
- Community JSON examples use `bbox` heavily for poster composition and exact text placement.
- The repo preserves a useful "JSON caption generator" prompt that teaches an LLM to calculate bboxes on a 0-1000 scale from aspect ratio and pixel dimensions.

Most useful local files:

- `repo-awesome-ideogram-4-prompts/README.md`
- `repo-awesome-ideogram-4-prompts/data/ingested_tweets.json`

The README has particularly useful sections:

- Coffee Shop Layout Prompt
- Ideogram 4 JSON Caption Generator
- FIFA World Cup 2026 Stadium Poster JSON example
- Typography stress tests
- Product packaging/nutrition label examples

## Lessons From Reddit

Reddit feedback is unusually important here because it reflects real workflow friction.

Main user-experience findings:

- Many users report that JSON prompting is not optional in practice if you want the best results.
- Users find manual bbox creation painful.
- Prompt-builder tools are emerging because the JSON/box format is powerful but tedious.
- Kijai's ComfyUI prompt builder node is repeatedly mentioned as important in local workflows.
- Users praise Ideogram 4.0 for prompt adherence and control when using proper JSON.
- Users criticize the local launch UX because plain natural-language prompts can produce poor output or safety false positives.
- Some users report false safety blocks more often with non-JSON prompts.

Representative findings from Reddit:

- One user said Ideogram 4's JSON format felt like a must and that bounding-box coordinates were hard enough that they built a web editor for boxes.
- Another thread said the model was an "adherence machine" when paired with Kijai's prompt builder.
- A negative thread argued that the spatial layout engine is powerful when fed compiled JSON, but the out-of-box local UX is poor if users must install prompt-builder or LLM conversion nodes first.
- Another comment framed JSON as a good target for a programmatic prompt builder, because characters and objects can be defined as modular nested structures.

Skill implication: do not ask users to write Ideogram JSON manually. The skill should own the conversion from intent to JSON and should offer reusable layout presets.

## Agent Prompting Pipeline

Use this pipeline inside an agent skill:

### Step 1: Classify the Task

Classify:

- `photograph`
- `graphic_design`
- `illustration`
- `3d_render`
- `product_packaging`
- `logo`
- `poster`
- `scene_with_characters`
- `text_heavy_design`

### Step 2: Choose Aspect Ratio

Defaults:

- square social image: `1:1`
- portrait poster: `2:3` or `3:4`
- phone wallpaper / vertical story: `9:16`
- cinematic scene: `16:9`
- wide banner: `3:1`
- product packaging mockup: `4:5` or `1:1`
- book cover: `2:3`
- app icon/logo: `1:1`

If using hosted API `magic-prompt-v4`, `AUTO` can choose for you, but a skill should usually choose explicitly when layout matters.

### Step 3: Build Composition Plan

Create a brief internal plan:

```text
medium: graphic_design
ratio: 2:3
primary subject: coffee cup product hero
text: OPEN 7AM, 123 MAIN ST, MON-FRI
layout: headline top, product center, footer strip bottom
palette: cream, espresso, black, muted green
boxes:
  headline [60, 100, 190, 900]
  cup [280, 300, 690, 700]
  footer strip [800, 80, 940, 920]
  footer text [820, 120, 910, 880]
```

### Step 4: Emit JSON

Include:

- one high-level summary
- style block if useful
- background shell
- all objects/text blocks
- exact boxes where needed

### Step 5: Verify

Before returning:

- Is every user-requested object present?
- Is every quoted string a `text` element?
- Are all boxes within 0-1000?
- Are y/x coordinate orders correct?
- Are ground/floor/sky in background, not elements?
- Is one subject split into parts accidentally?
- Is aspect ratio reflected in box shapes?
- Is text large enough for the actual pixel resolution?
- Are there contradictory style instructions?

## Ready-to-Use Templates

### Minimal Photo

```json
{
  "high_level_description": "A realistic iPhone-style photograph of a ceramic espresso cup on a small cafe table, framed off-center with a quiet street behind it.",
  "style_description": {
    "aesthetics": "natural, understated, realistic",
    "lighting": "overcast daylight through a cafe window, cool-neutral white balance",
    "photo": "iPhone photo, eye-level, ordinary depth of field",
    "medium": "photograph",
    "color_palette": ["#F4F1EA", "#3B2A1E", "#1F1F1F", "#6F7D67"]
  },
  "compositional_deconstruction": {
    "background": "A small cafe interior beside a window, with a simple wooden table surface in the foreground and a softly visible street outside. Neutral daylight fills the space.",
    "elements": [
      {
        "type": "obj",
        "bbox": [360, 320, 720, 620],
        "desc": "White ceramic espresso cup on a matching saucer, small handle facing right, dark espresso visible inside, positioned slightly left of center on the table."
      }
    ]
  }
}
```

### Poster With Exact Text

```json
{
  "high_level_description": "A clean specialty coffee poster with a centered iced coffee product hero, exact opening-hour headline, and restrained editorial layout.",
  "style_description": {
    "aesthetics": "minimal, editorial, refined, generous negative space",
    "lighting": "even soft studio lighting",
    "medium": "graphic_design",
    "art_style": "premium poster layout, upright sans-serif typography, realistic paper texture",
    "color_palette": ["#F6F1E8", "#2A1B12", "#111111", "#7B8C68", "#D6B17A"]
  },
  "compositional_deconstruction": {
    "background": "A warm off-white poster surface with subtle paper grain and large negative space around the central product.",
    "elements": [
      {
        "type": "text",
        "bbox": [70, 120, 190, 880],
        "text": "OPEN 7AM",
        "desc": "Large bold upright sans-serif headline across the top third, dark espresso-brown lettering, perfectly centered."
      },
      {
        "type": "obj",
        "bbox": [285, 310, 690, 690],
        "desc": "Clear plastic cup of iced latte with visible ice cubes, cream swirling into espresso, flat transparent lid, centered as the product hero."
      },
      {
        "type": "obj",
        "bbox": [805, 90, 940, 910],
        "desc": "Muted olive footer strip spanning the bottom of the poster with clean rectangular edges."
      },
      {
        "type": "text",
        "bbox": [830, 150, 910, 850],
        "text": "MON-FRI\n123 MAIN ST",
        "desc": "Small medium-weight upright sans-serif footer text centered inside the bottom strip, cream lettering."
      }
    ]
  }
}
```

### Character/Animal Placement With Boxes

```json
{
  "high_level_description": "A storybook illustration of a fox and a rabbit sharing a lantern-lit path in a pine forest at dusk.",
  "style_description": {
    "aesthetics": "gentle, charming, narrative",
    "lighting": "cool dusk ambience with a small amber lantern glow",
    "medium": "illustration",
    "art_style": "children's book watercolor illustration with soft outlines",
    "color_palette": ["#1F3A34", "#D9822B", "#F2D8A7", "#6A8D73", "#2A2520"]
  },
  "compositional_deconstruction": {
    "background": "A pine forest path at dusk, with dark green tree trunks rising on both sides, mossy ground, and a cool blue-grey sky visible between branches.",
    "elements": [
      {
        "type": "obj",
        "bbox": [330, 180, 820, 430],
        "desc": "Orange fox standing on the left side of the path, slim body, white chest, black-tipped ears, friendly expression, head turned toward the rabbit."
      },
      {
        "type": "obj",
        "bbox": [420, 560, 820, 760],
        "desc": "Small cream rabbit standing on the right side of the path, upright ears, soft round body, blue scarf, looking up toward the fox."
      },
      {
        "type": "obj",
        "bbox": [520, 440, 690, 555],
        "desc": "Small brass lantern placed between the fox and rabbit on the forest path, amber light glowing through glass panels."
      }
    ]
  }
}
```

## Common Failure Modes and Fixes

Problem: output ignores placement.

Fix: use `bbox` on the key elements, tighten boxes, and avoid one giant all-covering subject box.

Problem: text has typos.

Fix: create `type: "text"` elements, put literal text in `text`, split long text with `\n`, enlarge the bbox.

Problem: subject is cropped.

Fix: expand vertical bbox; for full-body portrait use y about `30-950`, and explicitly say "full body visible from head to feet, no cropping."

Problem: extra text appears.

Fix: add directive language in high-level description or an `additional_directives` array if your runtime tolerates extra keys. Safer schema-only alternative: write in `background`/`desc` that no other readable signage or labels are present.

Problem: figure legs are buried in the ground.

Fix: move floor/ground into `background`, not a foreground `obj`; make the figure bbox end above the bottom edge with visible feet.

Problem: model returns poor or safety-blocked output in local workflow.

Fix: use proper JSON or Magic Prompt conversion. Reddit users report more failures with unstructured natural language, and the open repo notes higher false-positive safety rates for non-JSON prompts.

Problem: prompt feels too rigid and loses creativity.

Fix: use JSON for spatial/layout constraints but leave aesthetic interpretation in high-level and background prose. For ideation, generate 3-5 JSON variants with different layout plans.

## Skill Design Recommendations

For a future Ideogram 4 skill, implement these features:

- A `natural_language_to_ideogram_json` workflow.
- Aspect-ratio selector with defaults by medium.
- Box presets for portraits, products, posters, text-heavy graphics, and multi-character scenes.
- Pixel verification for bboxes.
- Text extraction that turns every quoted string into a `text` element.
- Background/element classifier.
- Color palette normalization to uppercase `#RRGGBB`.
- Optional minified JSON output mode.
- Optional "explain layout boxes" debug mode.
- A warning when user asks for complex full-body figures in 16:9.
- A warning when exact text is too long for the requested box.
- Support for generating both hosted API `json_prompt` and local open-weight JSON strings.

## Final Rules for Agents

When in doubt:

- Choose JSON over plain text.
- Choose explicit boxes over vague spatial prose.
- Choose fewer, well-described elements over many body-part fragments.
- Choose literal `text` fields for readable copy.
- Choose concrete nouns and colors over hedged style language.
- Choose background for scene shell and elements for placeable objects.
- Choose aspect ratio before boxes.
- Verify box sizes in pixels.
- Make the prompt easy for the model to parse, not poetic.
