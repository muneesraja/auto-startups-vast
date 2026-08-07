# GPT Image 2 Prompting Research

> Synthesized from two community prompt repositories:
> - [awesome-gpt-image](https://github.com/ZeroLu/awesome-gpt-image) (~70KB README, 1077 lines)
> - [awesome-gpt-image-2](https://github.com/YouMind-OpenLab/awesome-gpt-image-2) (~390KB README, 14,393+ prompts in web gallery, 120+ featured in README)

---

## 1. GPT Image 2 Core Capabilities

GPT Image 2 (codename "duct-tape") is positioned around six pillars:

| Capability | What it means for prompting |
|---|---|
| **Pixel-Perfect Text Rendering** | You can specify exact text (Chinese, English, Japanese) verbatim and expect it rendered accurately — no typos, no warped glyphs |
| **Cross-Image Consistency** | The same character/style/IP stays identical across a series, down to the pixel — enables storyboards, IP sheets, multi-panel product visuals |
| **Commercial-Grade Illustration** | Output is production-ready without manual polish — prompts can target "ship-ready" quality |
| **True Art Style Induction** | Evokes the *feeling* of a style rather than copying a reference literally — style keywords matter more than reference mimicry |
| **Storyboard & Product Series** | Optimized for multi-panel generation — you can specify grid layouts, panel sequences, per-panel content |
| **Multi-Language Design** | Mixed-language designs (e.g. Chinese + English + Japanese) in a single image, accurately |

### Key differences from GPT Image 1 / earlier models
- Text accuracy is native, not approximate — specify exact strings
- Cross-image consistency is a first-class feature — reference images maintain identity across panels
- Style induction is creative, not literal — style keywords evoke rather than copy
- Multi-panel is supported natively — no need for external compositing
- Prompts are more structured (JSON, goal/layout/constraints) rather than free-form

---

## 2. Prompt Structure Patterns

### Pattern A: Descriptive Narrative (most common)
```
[Subject Description] + [Pose/Action] + [Environment/Setting] + [Lighting] + [Style/Aesthetic] + [Technical Specs] + [Aspect Ratio]
```

### Pattern B: Camera/Format + Lighting + Subject + Environment + Quality
```
35mm film photography, warm vintage Japanese onsen ryokan aesthetic, soft ambient wooden lantern lighting mixed with gentle natural window light, subtle film grain, gentle color shift, high atmosphere editorial style, intimate medium shot, [subject], [pose], [lighting], authentic vintage film color grading with warm tones, extremely sharp yet soft skin rendering, [negative constraints]
```

### Pattern C: Task + Exact Requirements + Structural Layout (posters, infographics)
```
Design a 3:4 vertical poster for [purpose]. Use [style]. The palette should be [colors], with [texture]. Main subject: [description]. The poster must accurately display the following exact [language] copy: [text elements]. Fine print: [disclaimer]. Maintain [design hierarchy]. Pay special attention to [specific elements].
```

### Pattern D: Grid/Panel + Count + Subject + Labels (storyboards, grids)
```
Create a [N] x [N] grid of [N] different [topic]. Use [style]. Each [item] should appear in its own [container] with a short clear label underneath. Keep the grid [layout requirements]. Use these [row/column themes]: [specs]. Show each tile as [visual description]. Keep the overall style [style attributes].
```

### Pattern E: Goal-Oriented with Constraints (concept art, storyboards)
```
Goal: [objective]
Canvas: [dimensions/format]
Layout: [composition details]
Subject details: [character/object specifics]
Visual style: [aesthetic]
Constraints: [negative constraints]
```

### Pattern F: Structured JSON (complex diagrams, exploded views)
```json
{
  "type": "exploded view product diagram poster",
  "subject": "VR headset",
  "style": "clean high-tech 3D render, studio lighting, glowing accents",
  "background": "soft purple and blue gradient",
  "header": { "logo": "...", "subtitle": "..." },
  "layout": { "centerpiece": "...", "callout_labels": { "count": 8, "left_side": [...], "right_side": [...] } },
  "footer": { "left_text_block": { "headline": "...", "body": "..." }, "right_logo": "..." }
}
```

### Pattern G: Reference-Based + Task + Constraints
```
Using this portrait, create [output type]. Show [what to display]. Keep text [length constraint] and avoid [format issues].
```

### Common Elements in Effective Prompts
1. **Subject** — detailed physical descriptions (age, ethnicity, features, expression)
2. **Outfit/Clothing** — specific colors, materials, styles
3. **Pose/Action** — precise body positioning, gestures
4. **Environment** — background, setting, props
5. **Lighting** — type, direction, quality ("soft natural window light", "dramatic rim lighting")
6. **Camera/Technical** — lens type, aperture, angle, depth of field
7. **Style Keywords** — "photorealistic", "editorial", "cinematic", "anime", "watercolor"
8. **Aspect Ratio** — explicitly specified ("9:16 vertical", "3:4", "16:9")
9. **Quality Tags** — "8K", "HDR", "masterpiece", "ultra-realistic"
10. **Negative Constraints** — what to avoid

---

## 3. Verbatim Prompt Examples

### 3.1 Photography / Photorealism

**Ultra-Realistic Urban Street Photo:**
```
Create an ultra-realistic urban street group photo at a convenience store entrance at 10 PM summer night. 3-4 young people briefly chatting at the entrance, someone holding drinks, someone sitting on plastic outdoor chairs, someone standing looking at their phone. Bright white light streaming through the glass doors and windows, warm yellow street lights and distant car headlights outside. Characters wearing everyday clothes: T-shirts, shirts, shorts, jeans, sneakers. No internet celebrity styling. Faces and postures must look like real pedestrians, not overly polished. Environment must include real convenience store elements: freezer stickers, promotional posters, trash cans, entrance mats, glass reflections, shared bikes on roadside, water droplets from drink bottles on ground. The image should look like a very authentic life slice captured by a photographer in the city.
```

**RAW iPhone Quality:**
```
Create a completely RAW quality, unprocessed, unedited image with full iPhone camera quality. A subway station in USA, a momentary blur. The subway is in motion. In front of the subway, there is an elderly woman and man.
```

**Amateur iPhone Photo:**
```
Amateur iPhone photo at Apple Park during the iPhone 20 keynote, Tim Cook presenting on stage. Shot from the crowd at a distance
```

**35mm Film Portrait:**
```
9:16 vertical - editorial portrait, single subject soft black mist filter, subtle haze, gentle highlight bloom, muted tones minimal indoor space, clean background, slight texture young Korean woman, minimal makeup, natural skin texture outfit: [details] hair: [details] pose: [details] composition: subject slightly off-center, negative space present expression: [details] lighting: soft side light, gentle shadow falloff mood: understated, quiet, subtly sensual through natural body lines, relaxed and unposed quality: fine grain, slight softness, realistic look
```

**Handwritten Notebook:**
```
Amateur photo of an open notebook lying flat, filled with handwritten notes in black ballpoint pen. The handwriting is casual and slightly messy, like personal notes, natural imperfections, crossed out words, underlined headings. Shot from slightly above, natural daylight from a window, no flash. Casual desk setting, shot on iPhone
```

### 3.2 Character / Portrait

**Elf Cosplayer Mirror Selfie:**
```
Create a realistic vertical smartphone mirror selfie of an adult fantasy elf cosplayer sitting on a soft white sheet on a gray carpet in a minimal beige room. The subject is an elf princess cosplayer, wearing a delicate white draped fantasy outfit with gold chain details, thin arm jewelry, gold leg bands, and pale blue flower accessories. She has long silver-gray hair styled in twin ponytails, pointed elf ears, and a blue-and-white floral crown. Pose her seated with one knee bent close to the body and the other leg extended toward the mirror, creating strong foreground perspective with the bare sole and toes large in the lower left foreground; the other foot is visible near the bottom edge. She holds a light gray smartphone in front of her face, obscuring facial features, with her other hand touching her hair near the ear. Use soft natural window light, muted neutral tones, shallow casual indoor realism, visible mirror edge at the far left, baseboard along the back wall, and a slightly candid cosplay photography aesthetic. Keep the composition intimate but non-explicit, with realistic skin texture, fabric folds, carpet detail, and no added text or watermark.
```

**3D Pixar-Style Caricature Portrait:**
```
Create an ultra-premium, hyper-detailed 3D caricature portrait of an irresistibly cheerful young woman with an oversized head and a tiny, perfectly proportioned body. She has a stylish short tousled dark-brown pixie haircut with soft textured layers, huge sparkling dark brown eyes looking playfully upward, long curled eyelashes, naturally thick eyebrows, glowing porcelain skin, rosy cheeks, and a dazzling open smile with perfectly aligned white teeth that instantly radiates happiness. She wears elegant pearl stud earrings, a shimmering rose-pink satin button-up blouse with subtle glitter highlights and rolled sleeves, a luxurious flowing black midi skirt with realistic fabric movement, and glossy mustard-yellow designer heels. She playfully holds the sides of her blouse while standing in a lively, confident pose with one knee slightly bent, creating an energetic and charming silhouette. Behind her is an enormous semi-transparent monochrome portrait of the same joyful face, softly blended into a breathtaking background of fiery orange, golden yellow, and warm amber watercolor textures with glowing particles, paint splashes, dreamy bokeh lights, and subtle light rays that create depth and visual drama. Elegant hand-lettered white calligraphy reading "You Look Beautiful" appears in the lower-right corner, surrounded by delicate butterflies, tiny hearts, sparkling stars, floral flourishes, and graceful ornamental swirls, seamlessly integrated into the composition. Style: Pixar-quality 3D caricature, Disney-inspired charm, premium digital illustration, cinematic lighting, volumetric glow, HDR color grading, glossy rendering, ultra-realistic textures, expressive facial features, vibrant warm palette, luxury poster design, immaculate composition, crisp focus, magazine-cover aesthetics, social-media optimized, highly shareable, emotionally uplifting, masterpiece, award-winning artwork, 8K ultra-HD, razor-sharp details, vertical 3:4 aspect ratio.
```

**Refined Watercolor Portrait (with reference):**
```
A refined watercolor-style portrait of a confident, mature man with short salt-and-pepper hair, well groomed beard, and black rectangular eyeglasses. He is dressed in a charcoal blazer over a black button-up shirt, looking thoughtfully into the distance with a calm, professional expression. The artwork features realistic facial details blended with elegant watercolor splashes in warm beige, gray, and sepia tones on a clean off-white background, creating a sophisticated, modern editorial aesthetic. Use uploaded reference images for facial features and expression alignment and spectacles if. Aspect ratio 10:21.
```

### 3.3 Multi-Panel / Storyboard / Grid

**16-Panel Anime Expression Grid:**
```
Create a 16-panel expression grid of a silver-haired, blue-eyed anime girl. Her face shape, hairstyle, and clothing must remain highly consistent across all panels. The 16 expressions should include: happy, sad, angry, surprised, shy, speechless, evil grin, contemplative, curious, proud, wronged, disdainful, confused, scared, crying, and a heart expression.
```

**10x10 Technology Topics Grid:**
```
Create a 10 x 10 grid of 100 different topics representing recent technological progress. Use a realistic, polished editorial illustration style. Each topic should appear in its own square with a short clear label underneath. Keep the grid neat on a white background. Make every topic visually different and every label correctly spelled. Use these row themes: Row 1: AI models and agents Row 2: robotics Row 3: semiconductors and compute Row 4: networks and smart devices Row 5: biotech and health technology Row 6: energy and power systems Row 7: transport and autonomy Row 8: space and aerospace Row 9: manufacturing and materials Row 10: climate and environmental technology. Show each tile as a realistic mini-scene, product-class object, lab instrument, robot, chip, vehicle, or device that clearly conveys the topic. Keep the overall style consistent, modern, realistic, and visually impressive.
```

**16-Panel Y2K Dance Tutorial Contact Sheet:**
```
Using the provided reference image as the subject, outfit, rooftop party setting, and Y2K flash-photo style base, transform it into a wide 16-panel dance tutorial contact sheet titled "SATURDAY NIGHT.". Keep the same person identity, sparkly Y2K outfit, rooftop skyline at night, direct-flash digital camera look, and party energy, but generate distinct dance poses across the panels rather than one pose.

Canvas and layout: Create a horizontal black poster/contact-sheet layout with exactly 16 rectangular frames arranged in a 4 columns x 4 rows grid. Each frame should look like a flash snapshot from the same rooftop session, separated by thin black borders. Add bold white italic all-caps typography.

Panel sequence: Include exactly these 16 numbered dance-step panels, each with a small title at the top-left, a timestamp at the top-right, and a short instruction caption along the bottom: [detailed 16-panel sequence...]

Style constraints: Make it feel like an early-2000s digital-camera party dance breakdown, with motion blur in hair and limbs where appropriate, harsh flash highlights, dark skyline backgrounds, and consistent subject identity in every frame. Do not add extra panels, extra steps, logos, watermarks, or unrelated text.
```

**Tiny Dragon Rainbow Flame Storyboard:**
```
Goal: Create a polished cinematic storyboard sheet for a short animated fantasy scene about a tiny dragon discovering an unexpected magical ability.

Canvas: Wide 16:9 storyboard board, [continues with detailed panel descriptions...]
```

### 3.4 Infographic / Educational

**English Vocabulary Study Card:**
```
Create an exquisite 4:5 vertical English vocabulary study card for A2-B1 level learners.

Card Type: Comprehensive Vocabulary Card
Theme: vibrant editorial illustration
Palette: Sunshine Classroom
Colors: Primary Cobalt Blue #2563EB, Secondary Coral Red #FF6B5C, Secondary Lemon Yellow #FFD84D, Secondary Sky Blue #7DD3FC, Dark Text #17324D, Warm Cream Background #FFF9E8.

Accurately display the following text:
library
/laI.brer.i/
noun
[Chinese text]
Places where people can read or borrow books and other materials.
We borrowed two books from the library.

COMMON COLLOCATIONS
Go to the library
Borrow from the library
Public library
Library card

GRAMMAR
Countable noun
Plural form: libraries

RELATED WORDS
Librarian - Shelf - Catalogue

Create a warm, modern library flat vector cross-section illustration. Show a learner borrowing two books from a librarian, naturally including bookshelves and a library card. Keep character figures friendly but editorial rather than childish. Arrange information like a professionally published learner's dictionary page: prominent headword, compact pronunciation line, clear definitions, highlighted example sentences, and neatly grouped learning modules. Use generous white space. Use pure flat colors and clean line art. No gradients, shadows, 3D, gloss effects, photorealism, visual clutter, logos, or watermarks. Keep all body text dark and legible. Accurately replicate provided English, IPA, and Simplified Chinese without adding extra text.
```

**Minimalist Editorial Graphic Design:**
```
Generate a minimalist, editorial-style graphic image centered around any subject. It features large areas of clean white space for "breathing," with the core subject rendered as a high-contrast black-and-white icon at the visual center with sharp edges. Part of the subject overlaps a solid color rectangular field, creating a stage-like layering effect. The information layer uses a heavy dark text block at the bottom, creating a visual impact where the image is truncated by text, which in turn supports the image. The main sentence uses bold, sans-serif light-colored characters in a tight multi-line layout with clean spacing and strong leading. An enlarged quotation mark or theme symbol serves as a rhythmic anchor at the top, while thin, lightweight credits at the bottom provide contrast, finishing with a tiny logo. Colors are extracted from the theme's material and mood: a high-brightness, clean background, black and white for the main subject's structure, and a mid-to-high saturation emotional color for the color field. The overall tone is bright, direct, and modern, with the energy of a public statement and the order of a publication. Avoid complex scenes, decorative textures, vintage filters, and loose layouts.
```

### 3.5 Game / Entertainment

**GTA 6 In-Game Footage:**
```
GTA 6 in-game footage, very detailed, very realistic. Close-up shot taken from a stationary 4k monitor. (There's a slight blurriness in the image, as it feels like it was taken handheld). A wide, bright environment. Realistic details. The character is walking on the beach with a dog.
```

**100 Pixel Art Grid:**
```
Create a single image containing a grid of 100 completely unique pixel art items, each with a meaningful label
```

### 3.6 Image Editing / Style Transfer

**Photo Enhancement:**
```
Enhance this iPhone photo with ChatGPT so it looks like a professional photographer and designer worked on it.
```

**Comic Page Coloring & Translation:**
```
Colorize this comic page and translate it into Chinese, placing the text in the original positions while maintaining composition and image details consistently
```

**Cosmetic Beauty Campaign (dual reference):**
```
Use the uploaded model photo as an exact personality reference. Preserve appearance 1:1: face, features, proportions, skin, hair, and overall look. Do not change the personality. The skin must be maximally natural and alive: real pores, natural texture, soft natural glow, no plastic retouching, no beautify, no excessive smoothing. Use the uploaded product photo as an exact product reference. Preserve the product 1:1: shape, size, proportions, packaging, cap, label, logo, text, material, color, coating, reflections, and all design details. The product must look maximally natural and realistic, like a real physical object in hand, not CGI, without distortions and without reinterpretation. Close-up beauty shot in the style of a modern luxury cosmetic campaign. The model from the photo reference holds the product from the uploaded photo near one eye, slightly covering it, and makes a playful facial expression with soft lips in a kissy face style. Gaze is directed at the camera. Hair is smoothly combed back. On the ears - gold hoop earrings. Background - clean minimalist white, without extra objects. Lighting is soft studio, clean beauty lighting, with delicate highlights on skin and product. Makeup is natural and fresh: glowing skin, slightly shiny lips, neat eyebrows, softly emphasized eyes, no heavy makeup. Overall aesthetic - fresh skincare / beauty editorial, glossy, expensive, modern, but at the same time natural and realistic. Frame focus - on the model's face, natural skin, and product. Avoid: changing the face, plastic skin, heavy retouching, CGI product look, unreadable logo, extra objects, bad hand anatomy, cartoonishness.
```

### 3.7 Concept Art / Character Sheet

**Dark Ghost Spirit Turnaround:**
```
Goal: Create a dark fantasy character concept sheet for a ghostly faceless spirit, shown as a full-body costume/creature design turnaround.

Canvas: Wide horizontal studio concept-art canvas, approximately 16:9, grayscale monochrome, neutral light-gray background, soft even lighting, no environment, no props, no text.

Layout: Show exactly 3 full-body views of the same character, evenly spaced from left to right: 1 front view, 1 left side profile view, and 1 rear view. All three figures stand upright with arms hanging slightly away from the body, feet hidden under long trailing robes, centered vertically with their hems nearly touching the bottom edge.

Subject details: The character is a No-Face-like dark ghost spirit, tall and slender, fully covered in layered black tattered robes. The garment is made of many ragged, shredded strips of cloth, with torn triangular edges, frayed holes, draping folds, and long trailing hems that pool and taper near the floor. The silhouette is hooded, cloaked, and ominous, with no visible skin except pale claw-like fingers. The front and side views show a smooth white oval mask under the hood, featuring two narrow horizontal black eye slits, two short cheek marks, and a wide dark grinning mouth. The back view shows only the black hood and layered ragged cloak with no mask visible.

Hands and claws: Each visible hand has exactly 5 long curved white claws, thin and talon-like, extending from ragged black sleeves. In the front view, both hands are visible with 10 total claws; in the side view, the nearer hand is visible with 5 claws and a few partially obscured claws from the far hand; in the rear view, both hands hang at the sides with 10 total claws visible.

Material and texture: Emphasize rough cloth texture, torn gauze, distressed fabric, heavy folds, matte black layers, subtle gray highlights, and worn edges. The mask is smooth, porcelain-like, stark white, and contrasts strongly with the dark robes.

Visual style: cinematic grayscale creature concept art, realistic costume design, high-detail horror character sheet, symmetrical studio presentation, soft shadows under the figures, sharp silhouette, eerie but elegant mood.

Constraints: Use exactly 3 views and no extra characters. Keep the image monochrome except for tonal gray shading. Do not add scenery, weapons, typography, logos, or watermarks. Maintain a clean neutral background and a professional production-design reference sheet look.
```

### 3.8 Product / Exploded View (JSON)

**VR Headset Exploded View Poster:**
```json
{
  "type": "exploded view product diagram poster",
  "subject": "VR headset",
  "style": "clean high-tech 3D render, studio lighting, glowing accents",
  "background": "soft purple and blue gradient",
  "header": {
    "logo": "Meta Quest 3",
    "subtitle": "A completely new reality, from a completely new structure."
  },
  "layout": {
    "centerpiece": "vertically stacked exploded view of a VR headset showing 9 distinct layers of internal components: outer shell, camera sensors, motherboard with chip, pancake lenses, internal frame, battery packs, side straps, top strap, and facial interface cushion.",
    "callout_labels": {
      "count": 8,
      "left_side": ["Snapdragon XR2 Gen 2", "Adjustable IPD mechanism", "Precision head strap"],
      "right_side": ["Face plate", "Tracking cameras", "Pancake lenses", "High-performance battery", "Soft face interface"]
    },
    "footer": {
      "left_text_block": {
        "headline": "Experience evolves from structure.",
        "body": "Each part supports immersive experience with cutting-edge technology and thoughtful design."
      },
      "right_logo": "Meta"
    }
  }
}
```

### 3.9 Micro Typography

**Text on a Single Grain of Rice:**
```
A massive pile of rice, and on one single grain of rice there is tiny text that reads "wOw"
```

### 3.10 360 Panorama

```
360 equirectangular image of [place]
```

---

## 4. Negative / Avoid Guidance

### Anatomy
```
extra fingers, extra limbs, distorted faces, asymmetrical eyes, fused hair, repeating hair bundles, melted knits, broken chairs, doll-like skin, excessive beautification, overly strong HDR, illustration styles
```

### Style violations
```
no plastic skin, no digital over-sharpening, no airbrushing, no blemishes, no moles, no oily skin, no watermark, no text
```
```
doll-like face, excessive skin smoothing, plastic skin, random facial light spots, perfect commercial ad, modern HD cinema look
```

### Composition
```
Avoid: poster feel, studio portrait feel, e-commerce feel, anime feel, cosplay feel, random annotations, incorrect structures, blurry text, fake materials, excessive decoration.
```
```
Avoid generic backgrounds, hard cut-and-paste compositions, templated fantasy assets, video-game promo art vibes, excessive cartooning, or realism that kills the artistic mood.
```
```
Avoid complex scenes, decorative textures, vintage filters, and loose layouts.
```

### Content
```
Do not add logos, watermarks, QR codes, or social media handles. Keep all text integrated into the design.
```
```
No grid, collage, contact sheet, split screen, multiple panels, text, logos, watermark, duplicate person, anime or CGI appearance.
```

### Common negative patterns
1. **Anatomical issues** — extra fingers, extra limbs, distorted faces, asymmetrical eyes, fused hair
2. **Unwanted elements** — logos, watermarks, text (unless specified), extra people, modern objects
3. **Style violations** — doll-like skin, excessive beautification, overly strong HDR, plastic appearance
4. **Composition issues** — horizontal flipping, distortion, incorrect reflections
5. **Technical artifacts** — clipping, deformation, unnatural shadows

---

## 5. Tips by Task

### 5.1 Character Consistency
- Use explicit consistency requirements: "Her face shape, hairstyle, and clothing must remain highly consistent across all panels"
- Create character reference sheets: "Based on this character and background, please create a character reference sheet similar to official setting materials. Includes three-view drawings: front view, side view, and back view. Add variations of the character's facial expressions. Break down and display detailed parts of the clothing and equipment. Add a color palette."
- For brand collaboration: "featuring the same pet (absolutely consistent in appearance and coloring)"
- Use uploaded reference images as strict visual references
- Specify "preserve exact facial features, face shape, eye shape, nose, lips, skin tone, hairstyle, proportions"
- Use "maintain identity across all views without excessive beautification or aging"
- For multi-panel: "consistent subject identity in every frame"

### 5.2 Multi-Panel / Storyboard Generation
- Specify exact panel counts: "Create a 16-panel expression grid", "Create an eight-panel manga"
- Use grid structures: "Create a 10 x 10 grid of 100 different topics"
- Specify content per panel: "The 16 expressions should include: happy, sad, angry, surprised, shy, speechless, evil grin, contemplative, curious, proud, wronged, disdainful, confused, scared, crying, and a heart expression"
- For storyboards: "A 48-panel grid is no longer enough for me. I need a 100-panel image, 8K"
- Use the Goal/Canvas/Layout/Constraints pattern for complex storyboards
- Maintain consistent subject identity across all frames
- Use reference images for base style/subject
- Specify panel-specific content (title, timestamp, caption)
- Include style constraints for the entire sheet

### 5.3 Style Transfer
- Use reference images: "Using this portrait, create a diagram-first personal color analysis"
- Specify output style clearly: "Colorize this comic page and translate it into Chinese, placing the text in the original positions while maintaining composition and image details consistently"
- For UI systems: "Generate a UI design system for me in xx style, including web pages, mobile, cards, controls, buttons"
- Use style keywords that evoke feelings rather than literal copying
- Specify medium: "cel-shaded", "digital illustration", "oil painting"
- Reference art movements: "constructivist", "surrealist", "minimalist"

### 5.4 Image Editing
- Enhancement: "Enhance this iPhone photo with ChatGPT so it looks like a professional photographer and designer worked on it"
- Specific editing tasks: "Colorize this comic page and translate it into Chinese"
- Maintain constraints: "placing the text in the original positions while maintaining composition and image details consistently"
- Use "uploaded reference image as exact reference"
- Specify "preserve 1:1" for exact fidelity
- List specific features to preserve (face shape, hairstyle, skin tone, etc.)
- For editing: specify what to change vs. what to keep

### 5.5 Text Rendering
- Use "exact" specifications: "Use the exact slogan '...'"
- Provide full text lists: "The poster must accurately display the following exact Chinese copy: [list of all text elements]"
- Specify typography requirements: "Pay special attention to small text, numbers, prices, info modules, and Chinese typography aesthetics"
- For reference-based text: "If you have a reference image for the exact calligraphy style, upload it as an image reference for stronger fidelity"
- Quality constraints: "All Chinese text must be clear and readable with realistic fonts"
- Use "accurately display" or "accurately replicate" for precise text
- Specify multilingual text with exact characters
- Include layout instructions for text placement

### 5.6 Multi-Image Reference Blending
- Specify which reference applies to which element: "Apply the reference image only to the Princess, not to the General"
- List exactly what to inherit vs. what not to inherit: "Inherit the Princess's facial features, eyes, face shape... Do not inherit outfit, color scheme, or background from the reference"
- Use "sole subject reference" for single-image consistency
- For multi-reference: specify "Image 1 (face) + Image 2 (materials)"
- Use "maintain identity across all views"
- For product + model: "Use the uploaded model photo as an exact personality reference... Use the uploaded product photo as an exact product reference. Preserve the product 1:1"

---

## 6. Reference Image Usage Patterns

### Pattern 1: Single Reference for Identity
```
Use uploaded reference images for facial features and expression alignment...
Use the uploaded reference image as the only identity reference. Preserve the subject's exact facial features...
create a premium studio portrait using my uploaded face as the exact facial reference...
```

### Pattern 2: Selective Inheritance
```
Apply the reference image only to the Princess, not to the General.
Inherit the Princess's facial features, eyes, face shape, nose/mouth, hairstyle, color, bangs, parting, length, age, skin, height, proportions, and body type from the reference image.
Do not inherit outfit, color scheme, or background from the reference.
```

### Pattern 3: Multi-Reference for Different Elements
```
multi-reference image writing for Image 1 (face) + Image 2 (materials) are all included
```

### Pattern 4: Reference for Style/Base
```
Using the provided reference image as the subject, outfit, rooftop party setting, and Y2K flash-photo style base, transform it into a wide 16-panel dance tutorial contact sheet...
```

### Pattern 5: Reference for Product + Model
```
Use the uploaded model photo as an exact personality reference... Use the uploaded product photo as an exact product reference. Preserve the product 1:1: shape, size, proportions, packaging, cap, label, logo, text, material, color, coating, reflections, and all design details.
```

### Pattern 6: Character Sheet Reference
```
Use the attached full-body reference image as the sole subject reference to create a simple 1:1 square character sheet... maintain all figure displays as the same individual from the reference image.
```

### Key insights
- GPT Image 2 supports selective reference application (inherit specific features only)
- Can use multiple reference images for different purposes (face, materials, style)
- Reference images can be used for identity preservation without inheriting outfit/background
- Multi-reference workflow requires models that support multiple image inputs
- "You must choose an image generation model that supports multiple reference images, otherwise facial consistency cannot be guaranteed"

---

## 7. Prompt Type Categories

### By Use Case
| Category | Examples |
|---|---|
| Profile / Avatar | Personal portraits, cosplay, character portraits |
| Social Media Post | Fashion shots, lifestyle imagery, influencer content |
| Infographic / Edu Visual | Educational cards, diagrams, maps, explainer slides |
| YouTube Thumbnail | Video thumbnails, promotional graphics |
| Comic / Storyboard | Storyboard sheets, comic panels, character sheets |
| Product Marketing | Fashion posters, commercial advertisements |
| E-commerce Main Image | Product photography, packaging mockups |
| Game Asset | Character turnarounds, concept art, game assets |
| Poster / Flyer | Event posters, promotional materials |
| App / Web Design | UI mockups, web design concepts |

### By Style
| Style | Notes |
|---|---|
| Photography | Realistic photos, portraits, lifestyle |
| Cinematic / Film Still | Movie-like imagery, dramatic lighting |
| Anime / Manga | Japanese animation style, manga illustrations |
| Illustration | Editorial illustrations, vector art |
| Sketch / Line Art | Hand-drawn sketches, line drawings |
| Comic / Graphic Novel | Comic book style, graphic novel art |
| 3D Render | 3D rendered imagery, product visualization |
| Chibi / Q-Style | Cute stylized characters |
| Isometric | Isometric perspective illustrations |
| Pixel Art | Retro pixel-based art |
| Oil Painting | Traditional oil painting style |
| Watercolor | Watercolor painting technique |
| Ink / Chinese Style | Traditional ink wash, Chinese art |
| Retro / Vintage | Vintage aesthetics, retro styles |
| Cyberpunk / Sci-Fi | Futuristic, sci-fi themes |
| Minimalism | Clean, minimalist design |

### By Subject
Portrait/Selfie, Influencer/Model, Character, Group/Couple, Product, Food/Drink, Fashion Item, Animal/Creature, Vehicle, Architecture/Interior, Landscape/Nature, Cityscape/Street, Diagram/Chart, Text/Typography, Abstract/Background

---

## 8. Key Takeaways for Our Storyboard Pipeline

1. **Use the Goal/Canvas/Layout/Constraints pattern** for storyboard sheets — it gives the model clear structure for multi-panel work
2. **Specify exact panel counts and grid layout** (e.g., "3x3 grid", "4 columns x 4 rows")
3. **Demand consistency explicitly**: "consistent subject identity in every frame", "face shape, hairstyle, and clothing must remain highly consistent across all panels"
4. **Use reference images with selective inheritance**: inherit character identity from char sheets, inherit layout/geography from 360 panoramas, but do NOT inherit their 3D/photoreal style
5. **Add negative constraints for style lock**: "no 3D rendering, no photorealism, no plastic skin" to keep the children's book illustration look
6. **Specify text rendering explicitly** if any labels are needed: "accurately display the following text"
7. **Use quality tags**: "8K", "masterpiece", "ultra-realistic" — but pair with style keywords to avoid drifting to photorealism
8. **Aspect ratio is explicit**: always declare "16:9", "3:4", etc.
9. **For character sheets**: use the three-view pattern (front, side, back) with "no environment, no props, no text"
10. **For multi-reference**: specify which reference applies to which element, and what to inherit vs. not inherit
