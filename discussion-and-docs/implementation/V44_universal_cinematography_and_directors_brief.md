# V44 Universal Cinematography & Director's Brief Prompt Overhaul

## Overview

Overhauled the `story-maker-v4` video prompting system to be universal across all animation and video styles. Replaced the rigid 6-section Ref2VA format with the proven **Director's Brief** format, created a comprehensive visual vocabulary reference, updated skill guidelines, enhanced validation tools with automatic format detection, and converted all 8 video prompts for the Secret Easter Garden story.

---

## 1. Deliverable 1: `assets/cinematography-bible.md`

Authored a single, exhaustive reference document covering the visual language of AI animation directing:
- **Section A — Shot Sizes**: 7 canonical sizes (`extreme_wide`, `wide`, `full`, `medium`, `medium_closeup`, `closeup`, `extreme_closeup`) plus combination setups (Two-Shot, OTS, Insert, Cutaway).
- **Section B — Camera Angles**: 12 complete camera angles (`eye_level`, `low_angle`, `high_angle`, `birds_eye`, `worms_eye`, `dutch_angle`, `over_the_shoulder`, `pov`, `three_quarter_front`, `three_quarter_back`, `profile`, `top_down`) with psychological and emotional functions.
- **Section C — Camera Positions**: 8 positions across the 360° horizontal spatial circle.
- **Section D — Camera Movements**: 22 MiniMax H3 native camera moves (Push In, Pull Out, Pan, Tilt, Truck, Pedestal, Arc, Tracking, Static, Handheld/Shake, Roll, etc.), composite moves (Dolly Zoom, Crane, Orbit, Whip Pan, Steadicam), and the mandatory 3D formula (`[Motion Type] with [small|large] amplitude at [slow|fast] speed`).
- **Section E — Transitions & Cut Mechanics**: 8 core H3 validated canonical phrases (`Hard cinematic cut.`, `Cut on the action.`, `Cut to the reaction.`, `Match cut on <element>.`, `Whip pan transition.`, `Audio leads the cut.`, etc.) plus extended editorial forms.
- **Section F — Facial Reactions & Character Acting**: Anatomical sequence taxonomy:
  - 18 Eye Reactions
  - 10 Brow Reactions
  - 16 Mouth & Jaw Reactions
  - 12 Head Reactions
  - 18 Body Postures & Gestures
- **Section G — Animation Micro-Beats**: Step-by-step cause-and-effect acting sequences (`Stimulus → Freeze → Eyes → Brows → Mouth → Head → Body → Secondary Motion`) and secondary motion physics (overlapping action, follow-through, weight).
- **Section H — Composition Rules**: 12 fundamental composition principles.
- **Section I — Director's Brief Prompt Construction**: Master template and guidelines.

---

## 2. Deliverable 2: Skill Documentation Updates

- **`prompts/video_prompter.md`**: Replaced Ref2VA instructions with Director's Brief format, mandating per-shot camera angle, position, movement (3D formula), micro-beat facial acting, audio direction, and continuation blocks for g2+.
- **`assets/minimax-h3-prompt-bible.md`**: Documented both formats (Director's Brief default vs Ref2VA legacy), pointed vocabulary tables to `cinematography-bible.md`, and retained canonical transitions, dialogue tags, and continuation rules.
- **`assets/directors-guide.md`**: Refactored shot design, camera movement, composition, and animation direction sections to reference `cinematography-bible.md` for exhaustive taxonomy while maintaining high-level directing principles.

---

## 3. Deliverable 3: Validator Updates (`tools/validators.py`)

- Implemented `is_directors_brief()` to auto-detect prompt format.
- Added `validate_video_prompt_brief()`:
  - Validates `subject_definitions:Reference` header and visual guide reference to storyboard
  - Checks character identity descriptions and preamble style declarations
  - Rejects internal `char_NN` tokens and prohibited studio brands (`pixar`, `disney`, `dreamworks`, `ghibli`)
  - Validates `Timeline` header and per-shot header format (`SHOT N — start–ends (Continuous Shot)`)
  - Ensures contiguous, generation-local timestamps that match storyboard shot timings
  - Validates presence of dedicated `Audio:` line in every shot block
  - Checks dialogue tagging syntax and speaker attribution
  - Checks seamless continuation statement for g2+ generations
  - Checks word count density (350–500 target) and warns on prompt-stuffing keywords
- Integrated seamless auto-detection into both `validate_video_prompt()` and `validate()` dispatch.
- Added comprehensive unit tests in `tests/test_phase2.py` covering passes, missing timeline, prohibited brand names, missing audio, shot range mismatches, and g2 continuation requirements. All 176 unit tests pass.

---

## 4. Deliverable 4: All 8 Video Prompts Rewritten & Validated

Rewrote all 8 video prompts in `outputs/story-maker-v4/secret-easter-garden/epi-1/video_prompts/`:
1. `s1_g1.txt`: Low-angle kick → high-angle ball drop into hedge → side-profile hedge parting. (PASS)
2. `s1_g2.txt`: Seamless continuation → OTS latch discovery → Dutch angle three knocks → 3/4 arc doorway burst. (PASS)
3. `s2_g1.txt`: Low-angle rabbit bow → high-angle stream distress → side-profile rescue planning. (PASS)
4. `s2_g2.txt`: Seamless continuation → OTS log crawl → worm's-eye duckling rescue → 3/4 arc Care egg illumination. (PASS)
5. `s3_g1.txt`: Low-angle gale ascent → Dutch angle trapped nest → high-angle flagstone climb. (PASS)
6. `s3_g2.txt`: Seamless continuation → OTS cardigan shield → side-profile ribbon untangling → 3/4 arc Courage egg illumination. (PASS)
7. `s4_g1.txt`: Low-angle somber canopy tilt → 3/4 arc mushroom ring marching song → side-profile Cheer egg awakening. (PASS)
8. `s4_g2.txt`: Seamless continuation → bird's-eye canopy illumination → OTS Golden Egg presentation → Dutch angle lawn sprint return to Grandma May. (PASS)

All 8 prompts validated with 0 errors.
