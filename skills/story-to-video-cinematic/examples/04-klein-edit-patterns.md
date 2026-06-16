# Flux Klein Edit Prompt Patterns — Complete Reference

## The Edit Prompt Formula
`[ACTION] + [SUBJECT ID] + [REFERENCE DIRECTIVE] + [PRESERVATION CONSTRAINT]`

## Pattern 1: Single-Character FF Edit (most common)
Used when: chain_start shot, 1 character present.

**Input:** Ideogram-generated scene with generic character placeholder  
**Reference:** Character sheet (1 image)

```
Replace the baby panda with the red scarf in the scene with the character 
from reference image 1, matching their exact face, fur pattern, scarf, and 
proportions. Keep the background, lighting, pose, and composition identical. 
Maintain the 3D Pixar-style art style throughout.
```

## Pattern 2: Multi-Character FF Edit (2-3 characters)
Used when: chain_start shot, 2-3 characters present.

**Input:** Ideogram-generated scene with multiple character placeholders  
**References:** Character sheet 1 + Character sheet 2 (2 images)

> [!IMPORTANT]
> **Reference ordering must match characters_present array ordering.**

```
Make the baby panda on the left match the character from reference image 1 
exactly — same face, fur pattern, and red scarf. Make the brown monkey on 
the right match the character from reference image 2 exactly — same face, 
amber eyes, and green leaf hat. Keep the background, waterfall, lighting, 
and composition identical.
```

## Pattern 3: LF Derivation from FF (`klein_from_ff`)
Used when: Deriving LF from an already-edited FF image.

**Input:** The consistent FF (output of Pattern 1 or 2)  
**References:** Character sheet(s) for identity reinforcement

> [!IMPORTANT]
> **Describe ONLY what changes. Klein already sees the FF.**

* **Good:** `"Shift camera view slightly forward. The panda turns its head to the right with curious wide eyes. Keep character identity and background identical."`
* **Bad:** `"A panda with a red scarf stands in a bamboo forest looking to the right."` *(This is a T2I generation prompt, not an edit prompt!)*

### LF Derivation Budget
Each LF edit should specify exactly **one** major change:
- Camera shift (forward, back, left, right, zoom in/out)
- Expression change (curious → surprised, happy → sad)
- Action change (walking → pausing, standing → reaching)
- **DO NOT** combine camera shift + expression + action in one prompt.

## Pattern 4: LF from Extracted Tail (`klein_from_extracted_tail`)
Used when: continuation shot, FF comes from previous video tail frame.

**Input:** Extracted tail frame from previous FFLF video  
**References:** Character sheet(s)

```
The panda lifts its right paw gently toward a glowing butterfly. The panda 
has a delighted, wide-eyed expression. Keep character identity, background, 
and lighting identical.
```

> [!NOTE]
> Tail frames may have minor LTX artifacts. Klein naturally cleans these during the edit process since it regenerates the character region.

## Anti-Patterns

* ❌ `"A beautiful panda walking in a bamboo forest at sunset"`  
  → **GENERATION prompt.** Klein ignores scene image and hallucinates.
* ❌ `"Make it look better"`  
  → **Vague.** Klein needs specific instructions.
* ❌ `"Generate a new image with the character from reference 1 in a village"`  
  → **Klein is an EDITOR**, not a generator.
* ❌ **Describing the entire background again**  
  → Klein already "sees" the scene. Redescribing causes background drift.
* ❌ `"Change the panda's expression AND move the camera AND add a butterfly"`  
  → **Too many changes.** LTX will struggle to interpolate FF→LF smoothly.
