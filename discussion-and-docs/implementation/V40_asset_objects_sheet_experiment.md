# V40: 4K Objects and Assets Sheet Experiment

**Status:** Completed  
**Story:** Bamboo the Little Dino  
**Episode:** Episode 2 ("Sun & Milk")  
**Output Target:** `outputs/story-maker-v3/bamboo-the-dino/assets/objects/objects_sheet_epi2.webp`

---

## 1. Objective
Establish a reusable, deterministic 4K Objects and Props Asset Sheet workflow in `story-maker-v3` to provide high-fidelity visual and material reference anchors for inanimate props, interactive objects, and set dressing across scenes and episodes.

---

## 2. Implementation Overview

### A. Template & Builder Tooling
- **`skills/story-maker-v3/prompts/object_sheet_template.md`**: Standardized prompt structure enforcing Pixar/Disney 3D animation aesthetics, 4K landscape format (3840×2160), clean studio lighting, high material fidelity, and strict negative prompting against text/clutter.
- **`skills/story-maker-v3/tools/object_sheet_builder.py`**: Python helper module to load and resolve object prompt files into full generation prompts.
- **`skills/story-maker-v3/tools/image_pipeline.py`**:
  - Extended `AssetRegistry` to track `"objects"` with `object_asset(oid)` and `object_path(oid)`.
  - Added `generate_object_sheet(...)` generating 4K landscape sheets (`3840x2160`).
- **`skills/story-maker-v3/scripts/build_images.py`**: Added `--objects` CLI flag and integrated object generation into `--assets-only` passes.

### B. Episode 2 Objects Inventory & Prompt Authoring
Extracted all key props from Episode 2 story and storyboards (`storyboard_s1.md`, `storyboard_s2.md`):
1. **Baby Milk Bottle**: Wide-neck glass baby bottle with measurement marks, silicone nipple, filled with frothy milk and gentle steam.
2. **Milk Powder Canister**: Vintage cylindrical blue tin canister with lid, star motif, and scoop with powder.
3. **Electric Kettle**: Mint-green and cream electric kettle with heat base and steam spout.
4. **Wooden Step Ladder**: 3-step sturdy pine toddler ladder with natural wood grain.
5. **Toddler Biscuits & Crackers**: Golden-brown star and square crackers on a wooden prep board.
6. **Sheer Window Curtain**: Flowing cream linen curtain on rings filtering morning sunlight.
7. **Kitchen Table & Chair**: Light honey-oak wooden dining furniture.
8. **Pantry Cereal Jars**: Glass jars with cork stoppers containing cereal loops and oats.
9. **Flashback Keepsakes**: Soft blue baby blanket with yellow stars and Mother's silver teardrop pendant.

---

## 3. Results & Verification
- **Output File**: `outputs/story-maker-v3/bamboo-the-dino/assets/objects/objects_sheet_epi2.webp`
- **Resolution**: `3840 × 2160` (4K landscape, RGB WebP, ~1.05MB)
- **Hosted URL**: `https://replicate.delivery/xezq/uZBzLD9GLcI3LRBt9H5TENgore4T2iakFA5mKqESmmzf9dCXA/tmpfkwpkgie.webp`
- **Asset Registry**: Persisted under `"objects"` in `outputs/story-maker-v3/bamboo-the-dino/epi-2/asset_registry.json`.
- **Unit Tests**: All 21 tests in `skills/story-maker-v3/tests/test_phase2.py` passing.
