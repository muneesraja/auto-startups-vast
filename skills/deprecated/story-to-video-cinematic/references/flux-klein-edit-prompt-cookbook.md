# Flux Klein Edit Prompt Cookbook

Flux Klein 9B is an image-to-image **editor**, not a text-to-image generator. To get the best consistency, prompts must follow specific formulas.

## Edit Prompt Structure

`[Action/Change Instruction] + [Character Descriptor] + [Reference Directive] + [Style/Detail Preservation]`

* **Correct**: `"Replace the baby panda with the red scarf with the character from reference image 1, keeping face, fur and scarf identical. Keep background and lighting same."`
* **Incorrect**: `"A cute baby panda wearing a red scarf walks through a bamboo forest."` (This will cause Klein to ignore the reference image and hallucinate a generic panda).

---

## Cookbook Patterns

### 1. Single-Character Consistency Pass
Used to align a raw Ideogram scene to the registered character sheet.
```
Replace the [character description] with the character from reference image 1, matching their exact face, clothing, and proportions. Keep the background, lighting, and composition identical. Maintain the [global style] art style.
```

### 2. Multi-Character Consistency Pass
Used when multiple characters are in the same shot.
```
Make the [character 1 descriptor] match the character from reference image 1 exactly — same face, fur pattern, and clothing. Make the [character 2 descriptor] match the character from reference image 2 exactly — same face, colors, and clothing. Keep the background, lighting, and composition identical. Maintain the [global style] art style throughout.
```

### 3. Last Frame (LF) Derivation (`klein_from_ff`)
Used to modify the First Frame (FF) into the Last Frame (LF) describing ONLY the movement/expression delta.
```
[Describe the camera or subject delta, e.g. "Shift camera view slightly forward. The panda turns its head to the right with curious wide eyes."] Keep character identity and background identical.
```

### 4. Continuation LF Edit (`klein_from_extracted_tail`)
Used to edit an extracted tail frame to produce the LF for a continuation shot.
```
[Describe the action delta, e.g. "The panda lifts its right paw toward the butterfly. It has a delighted wide-eyed expression."] Keep character identity, background, and lighting identical.
```

---

## Critical Rules & Guidelines

1. **Reference Numbering**: References correspond 1:1 to the order of characters in the `characters_present` list. Refer to them as `"reference image 1"`, `"reference image 2"`, etc.
2. **One Delta per LF**: For best animation coherence in LTX, restrict LF edits to **one** major visual change (either a camera shift, an expression shift, or a single character action). Do not combine all three in one edit.
3. **Preserve Backgrounds**: Always append `"Keep the background, lighting, and composition identical."` to prevent Klein from drifting the environment.
