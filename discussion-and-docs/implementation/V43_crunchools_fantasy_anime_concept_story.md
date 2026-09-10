# V43 — The Legend of Crunchools: Story & Production Prompts (Story Maker V4)

## Overview
Authored a complete, validated story development, character/object/location specifications, spatial geography plan, scene breakdown, storyboard, and production-ready image/video prompts for **"The Legend of Crunchools"** using `skills/story-maker-v4`.

The story features two close friends in an alchemical cookhouse attempting to craft "Crunchools"—legendary crystalline noodles that crackle with orange spice sparks and maintain an explosive, crispy crunch even when boiled in broth:
1. **Rin (`char_01`)**: The nimble young spice-alchemist in charcoal leather doublet, rolled linen sleeves, and flour-dusted apron with expressive golden-amber anime eyes and messy honey-amber hair.
2. **Bram (`char_02`)**: The rugged forge-cook with braided chestnut topknot, trimmed beard, forehead brass cooking goggles, quilted olive vest, and heavy studded leather apron.
3. **Crunchools Dough & Crackling Noodles (`obj_01`)**: Translucent golden-amber crystalline ribbon noodles dusted with red chili flakes and mineral salt.
4. **Simmering Spiced Bronze Caldron (`obj_02`)**: Antique hammered bronze cooking cauldron with sculpted beast-head handles.
5. **The Hearthstone Alchemical Cookhouse (`loc_01`)**: Rustic granite stone kitchen with glowing spice vials, open embers, and warm lightbeams.

All authored assets adhere strictly to the requested **semi-realistic fantasy character concept art style with painterly, anime-influenced rendering** (MiniMax H3 Preset P4).

## Artifacts Generated & Validated
- **Story Development**: `outputs/story-maker-v4/crunchools-noodles/epi-1/developed_story.md`
- **Beat Board (60s, 8 beats)**: `outputs/story-maker-v4/crunchools-noodles/epi-1/beat_board.md` [PASSED `validate.py --schema beat_board`]
- **Scenes Specification (4 scenes, 15s each = 60s)**: `outputs/story-maker-v4/crunchools-noodles/epi-1/scenes.md` [PASSED `validate.py --schema scenes`]
- **Scene Storyboards (s1-s4, 15s each, 3x2 grid, 4 shots each)**:
  - `storyboard_s1.md`: The Dough Stretch & Crystal Snap [PASSED]
  - `storyboard_s2.md`: The Cauldron Plunge & Steam Burst [PASSED]
  - `storyboard_s3.md`: The Taste Test & Sound Wave Crunch [PASSED]
  - `storyboard_s4.md`: Plating & The Triumphant Feast [PASSED]
- **Image Prompts**:
  - `image_prompts/characters/char_01.txt` (Rin 8-panel identity plate)
  - `image_prompts/characters/char_02.txt` (Bram 8-panel identity plate)
  - `image_prompts/locations/loc_01.txt` (Hearthstone Cookhouse panoramic establishing plate)
  - `image_prompts/objects/obj_01.txt` (Crunchools Noodles & Dough asset plate)
  - `image_prompts/objects/obj_02.txt` (Simmering Bronze Caldron asset plate)
  - `image_prompts/s1/storyboard_sheet_g1.txt` (3840×2160 3x2 6-panel storyboard sheet with materialized spatial continuity block) [PASSED]
- **Video Prompts (Ref2VA Minimax H3, 4 scenes × 15s = 60s total)**:
  - `video_prompts/s1_g1.txt` (Scene 1: 0.0-15.0s) [PASSED `validate.py --schema video_prompt`]
  - `video_prompts/s2_g1.txt` (Scene 2: 0.0-15.0s) [PASSED `validate.py --schema video_prompt`]
  - `video_prompts/s3_g1.txt` (Scene 3: 0.0-15.0s) [PASSED `validate.py --schema video_prompt`]
  - `video_prompts/s4_g1.txt` (Scene 4: 0.0-15.0s) [PASSED `validate.py --schema video_prompt`]

## Verification
All 4 scene storyboards and all 4 Ref2VA video prompts pass their respective deterministic validators with 0 errors and 0 warnings.
