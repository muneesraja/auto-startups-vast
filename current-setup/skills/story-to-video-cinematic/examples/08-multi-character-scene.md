# Multi-Character Scenes — Reference Ordering & Prompts

When editing a scene containing multiple characters using Flux Klein 9B, you must carefully map characters present in the shot to reference images.

## 1. Reference Image Map Ordering

Flux Klein receives reference sheets in a sequential list of ComfyUI load nodes.
* **Reference Image 1** = First character listed in `characters_present`
* **Reference Image 2** = Second character listed in `characters_present`
* **Reference Image 3** = Third character listed in `characters_present`

> [!WARNING]
> **Order consistency is critical!** If `characters_present` is `["pippin", "miko"]`, then Pippin is reference image 1, and Miko is reference image 2. If the edit prompt swap them, the characters will be visually swapped!

---

## 2. Edit Prompt Composition

The edit prompt is automatically composed by checking `characters_present` and mapping each character's `edit_prompt_descriptor` to its reference image index.

### Auto-Composition Formula:
For each character at index `i` (1-based):
`"Make [edit_prompt_descriptor] match the character from reference image [i] exactly — same face, body, clothing, and proportions."`

Plus the preservation constraint:
`"Keep the background, lighting, composition, and overall scene identical."`

### Python Auto-Composition Code:
```python
def compose_multi_character_edit_prompt(characters_present, char_lookup, global_style):
    parts = []
    for i, char_id in enumerate(characters_present, start=1):
        char = char_lookup[char_id]
        desc = char["edit_prompt_descriptor"]
        parts.append(
            f"Make {desc} match the character from reference image {i} "
            f"exactly — same face, body, clothing, and proportions."
        )
    
    preservation = (
        "Keep the background, lighting, composition, and overall scene identical. "
        f"Maintain the {global_style} art style throughout."
    )
    
    return " ".join(parts) + " " + preservation
```

---

## 3. Walkthrough Example: Pippin & Miko Meeting

### Shot data in `cinematic_prompt.json`:
```json
{
  "shot_id": 3,
  "characters_present": ["pippin", "miko"],
  "ff_edit_instructions": {
    "pippin": "Make the baby panda on the left match the character from reference image 1 exactly — same face, fur pattern, and red scarf. Keep the background, lighting, monkey, and composition identical.",
    "miko": "Make the brown monkey on the right match the character from reference image 2 exactly — same face, amber eyes, fur texture, and green leaf hat. Keep the background, lighting, panda, and composition identical."
  }
}
```

### Reference Mapping at Run-time:
1. `character_refs` list compiled by orchestrator: `["pippin_sheet.png", "miko_sheet.png"]`
2. Dynamic workflow builder clones nodes `121` (Ref 1) and `121_2` (Ref 2).
3. `pippin_sheet.png` is assigned to `121` (`__REFERENCE_1__`).
4. `miko_sheet.png` is assigned to `121_2` (`__REFERENCE_2__`).
5. **Combined Edit Prompt for FF**:
   * If `ff_edit_instructions` overrides are provided in the JSON, they are used.
   * If not, the auto-composed prompt is executed:
     `"Make the baby panda with the red scarf match the character from reference image 1 exactly — same face, body, clothing, and proportions. Make the brown monkey with the green leaf hat match the character from reference image 2 exactly — same face, body, clothing, and proportions. Keep the background, lighting, composition, and overall scene identical. Maintain the Cinematic 3D Pixar-style art style throughout."`
6. CFG Guider reads conditioning from positive chain ending at `92:131_2` and negative chain ending at `92:129_2`.
7. Output has Pippin on the left and Miko on the right, fully aligned to their sheets!
