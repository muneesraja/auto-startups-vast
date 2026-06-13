# Character Sheet Prompts — Examples & Best Practices

When generating character sheets using Ideogram 4 T2I in Wave 0, the goal is to produce a high-quality, neutral, and consistent reference that the consistency editor (Flux Klein 9B) can easily latch onto.

## Character Sheet Prompt Formula
`[Subject/Display Name] + [Standard Multiview Layout] + [Physical Description & Clothing] + [Technical constraints (clean background, studio lighting)] + [Art style / engine instructions]`

## Best Examples

### Example 1: Pippin the Panda
```
Professional character reference sheet for Pippin the Panda. Front view, 3/4 view, and side profile. A cheerful baby panda with round face, large dark circular eye patches, fluffy white-and-black fur, wearing a small red knitted scarf around his neck. Clean white background, studio lighting, 3D Pixar-style rendering, high detail.
```

### Example 2: Miko the Monkey
```
Professional character reference sheet for Miko the Monkey. Front view, 3/4 view, and side profile. A playful brown spider monkey with long curled tail, bright amber eyes, wiry brown fur, wearing a tiny green leaf hat tilted to one side. Clean white background, studio lighting, 3D Pixar-style rendering, high detail.
```

### Example 3: Luna the Wizard
```
Professional character reference sheet for Luna the Wizard. Front view, 3/4 view, and side profile. A young girl wizard with silver braided hair, wearing a dark blue robe embroidered with small yellow stars and a matching pointed wizard hat. Clean plain grey background, studio lighting, 3D animated movie style, detailed textures.
```

## Key Guidelines

1. **Standard Layout Descriptors**: Always request multiple angles like `"Front view, 3/4 view, and side profile"`. This ensures the reference sheet contains enough visual angles of the character.
2. **Neutral/Clean Background**: Always ask for `"Clean white background"` or `"Clean plain grey background"`. This prevents ComfyUI from mixing the character's reference background into the edited scene.
3. **Avoid Action / Pose description**: Keep the characters in simple standing or neutral poses. Action descriptions belong in the shot plan, not the character reference sheet.
4. **Distinctive Props/Clothing**: Mention defining garments (e.g., `"small red knitted scarf"`, `"tiny green leaf hat"`) explicitly. These act as strong anchors for both the generation and the editing passes.
