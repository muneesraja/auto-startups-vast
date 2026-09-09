#!/usr/bin/env python3
"""Small assert-based self-check for focus depth-of-field taxonomy in validators."""

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools import validators

# 1. Verify FOCUS_TYPES constant
assert hasattr(validators, "FOCUS_TYPES"), "validators must export FOCUS_TYPES"
assert "shallow_focus" in validators.FOCUS_TYPES
assert "deep_focus" in validators.FOCUS_TYPES
assert "rack_focus" in validators.FOCUS_TYPES
assert "soft_focus" in validators.FOCUS_TYPES

# 2. Test focus parsing and validation in storyboard
shot_template = """# Scene s1 — Test
scene_id: s1
target_seconds: 15
cast: [char_01]

## Generation g1 — 0.0-15.0s
duration_seconds: 15.0
panel_grid: 3x3

### Shot 1 — 0.0-15.0s (continuous)
panels: [1, 2, 3, 4, 5, 6, 7, 8, 9]
characters_present: [char_01]
shot_size: {shot_size}
composition: rule_of_thirds
{focus_line}
acting_beat: step → turn → smile
layout: foreground character
screen_direction: held
camera_angle: eye_level
action: Test action.
camera: Static Shot with small amplitude at slow speed.
audio: Test audio.

## Handoff
- Ending frame: Test
- Spatial anchors: None
"""

scenes_text = """# Scenes
target_seconds: 15

## Scene s1 — Test
target_seconds: 15
cast: [char_01]
location_id: loc_01
style_target: Cinematic
acting_beat: Acting beat
layout_strategy: Layout
visual_motif: Motif
sound_world: Sound
"""

import tempfile

with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f_sc:
    f_sc.write(scenes_text)
    sc_path = f_sc.name

# Test A: valid focus -> no focus warnings, no errors
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f_sb:
    f_sb.write(shot_template.format(shot_size="medium", focus_line="focus: shallow_focus"))
    sb_path = f_sb.name

res = validators.validate(sb_path, "storyboard", scenes_path=sc_path)
assert res.ok, f"Expected pass, got errors: {res.errors}"
focus_warns = [w for w in res.warnings if "focus" in w]
assert len(focus_warns) == 0, f"Expected no focus warnings, got: {focus_warns}"

# Test B: missing focus -> advisory warning only, still passes
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f_sb2:
    f_sb2.write(shot_template.format(shot_size="medium", focus_line=""))
    sb_path2 = f_sb2.name

res2 = validators.validate(sb_path2, "storyboard", scenes_path=sc_path)
assert res2.ok, f"Missing focus should still pass, got errors: {res2.errors}"
assert any("missing 'focus:'" in w for w in res2.warnings), "Expected advisory warning for missing focus"

# Test C: invalid focus -> validation error
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f_sb3:
    f_sb3.write(shot_template.format(shot_size="medium", focus_line="focus: invalid_lens_blur"))
    sb_path3 = f_sb3.name

res3 = validators.validate(sb_path3, "storyboard", scenes_path=sc_path)
assert not res3.ok, "Expected failure on invalid focus"
assert any("focus 'invalid_lens_blur' not in" in e for e in res3.errors), f"Expected focus error, got: {res3.errors}"

# Test D: rack_focus on extreme_closeup -> advisory warning
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f_sb4:
    f_sb4.write(shot_template.format(shot_size="extreme_closeup", focus_line="focus: rack_focus"))
    sb_path4 = f_sb4.name

res4 = validators.validate(sb_path4, "storyboard", scenes_path=sc_path)
assert res4.ok, f"rack_focus on ECU should pass with warning, got errors: {res4.errors}"
assert any("rack_focus on an extreme_closeup has minimal focal depth" in w for w in res4.warnings)

# Clean up
Path(sc_path).unlink(missing_ok=True)
Path(sb_path).unlink(missing_ok=True)
Path(sb_path2).unlink(missing_ok=True)
Path(sb_path3).unlink(missing_ok=True)
Path(sb_path4).unlink(missing_ok=True)
Path(sb_path + ".validation.json").unlink(missing_ok=True)
Path(sb_path2 + ".validation.json").unlink(missing_ok=True)
Path(sb_path3 + ".validation.json").unlink(missing_ok=True)
Path(sb_path4 + ".validation.json").unlink(missing_ok=True)

print("All focus validator assertions passed!")
