# Scene First Frame (FF) Prompts — Examples & Best Practices

In Wave 1, we generate the First Frame (FF) of the start of each continuation chain using Ideogram 4 (T2I). These prompts define the scene's composition, environment, camera, and generic character placement placeholders.

## Scene FF Prompt Formula
`[Shot/Camera description] + [Environment details] + [Character placeholders & actions] + [Lighting & Atmosphere] + [Art style instruction]`

## Best Examples

### Example 1: Pippin's Forest Walk (Single-character)
```
Wide establishing shot of a dense bamboo forest at golden hour. A baby panda with a red scarf walks along a mossy dirt path. Warm golden light filters through tall bamboo stalks. Soft volumetric fog in the background. 3D Pixar-style cinematic still.
```
* **Why it works**: It establishes a clear wide angle, sets the warm golden light, places the panda on the path, and requests the target Pixar art style.

### Example 2: The Waterfall Meeting (Multi-character)
```
Wide cinematic shot of a sparkling waterfall cascading into a crystal-clear pool, hidden behind parting bamboo stalks. On a mossy rock in the foreground, a baby panda with a red scarf stands next to a brown spider monkey with a green leaf hat. Both look up at the waterfall in awe. Dramatic volumetric light, 3D Pixar-style.
```
* **Why it works**: It places both characters side-by-side, establishes their spatial relationship ("stands next to..."), defines their generic look, and establishes the majestic waterfall backdrop.

### Example 3: Cozy Library (Single-character)
```
Medium shot of a warm cozy library filled with wooden bookshelves. A little owl wizard with gold glasses sits at a desk reading a giant leather book. Candlelight casts soft glowing shadows on the walls. 3D Pixar-style rendering, volumetric dust motes.
```

## Key Guidelines

1. **Describe Placement Explicitly**: Use spatial terms like `"on a mossy rock in the foreground"`, `"sits at a desk"`, `"walks along a mossy dirt path"`. This gives the model clean composition layout guidance.
2. **Keep Characters Distinct**: Even though these are placeholders that Flux Klein will edit, make sure their physical descriptions match their IDs loosely (e.g., `"baby panda with a red scarf"`) so that the initial image places them in the correct spots with correct colors.
3. **Lighting & Atmosphere**: Specify lighting styles like `"golden hour"`, `"dramatic volumetric light"`, or `"soft candlelight"` to establish mood and visual consistency.
4. **Art Style Match**: Ensure every scene prompt ends with a consistent style suffix matching `global.style` (e.g., `"3D Pixar-style"`).
