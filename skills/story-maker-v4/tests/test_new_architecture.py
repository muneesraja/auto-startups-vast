"""Tests for new architectural features in story-maker-v4:
- Critique severity tiers (BLOCKER, MAJOR with disposition, NOT_APPLICABLE)
- Hard constraint validation (co_presence_exclusion, visibility_exclusion)
- Render manifest generation and sha256 checksum verification
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools.critique_validator import validate_critique_report
from tools.validators import validate_constraints, validate_render_manifest
from scripts.build_manifest import build_manifest, sha256_file


class TestCritiqueSeverityTiers(unittest.TestCase):
    def test_blocker_fails_gate(self):
        report = """# Critique Report — Test
## Summary
- Pass: 1
- Blocker: 1

### Q1.1 — Visible goal?
- Status: PASS
- Notes: Clear goal.

### Q1.2 — Character co-presence check?
- Status: BLOCKER
- Notes: Girl and wild dogs appeared together in Scene 5!
- Fix: Remove dogs from scene 5.
"""
        res = validate_critique_report(report)
        self.assertFalse(res.ok)
        self.assertTrue(any("BLOCKER" in e for e in res.errors))

    def test_major_with_disposition_passes(self):
        report = """# Critique Report — Test
## Summary
- Pass: 1
- Major: 1

### Q1.1 — Visible goal?
- Status: PASS
- Notes: Clear goal.

### Q1.2 — Early conflict present?
- Status: MAJOR
- Severity: MAJOR
- Disposition: ACCEPTED_AS_INTENDED
- Notes: Scene 1 is a quiet meditative setup; conflict begins in Scene 2.
"""
        res = validate_critique_report(report)
        self.assertTrue(res.ok)
        self.assertTrue(any("ACCEPTED_AS_INTENDED" in w for w in res.warnings))

    def test_major_without_disposition_fails(self):
        report = """# Critique Report — Test
## Summary
- Major: 1

### Q1.2 — Early conflict present?
- Status: MAJOR
- Notes: Scene 1 lacks conflict.
"""
        res = validate_critique_report(report)
        self.assertFalse(res.ok)
        self.assertTrue(any("requires Disposition" in e for e in res.errors))

    def test_not_applicable_skips_cleanly(self):
        report = """# Critique Report — Test
## Summary
- Pass: 1
- Not_applicable: 1

### Q1.1 — Visible goal?
- Status: PASS
- Notes: Clear goal.

### Q7.10 — Lip sync match?
- Status: NOT_APPLICABLE
- Notes: Silent film.
"""
        res = validate_critique_report(report)
        self.assertTrue(res.ok)


class TestConstraintValidation(unittest.TestCase):
    def test_co_presence_exclusion_violated(self):
        story_json = json.dumps({
            "constraints": [
                {
                    "id": "H1",
                    "type": "co_presence_exclusion",
                    "subjects": ["char_01", "char_04"],
                    "valid_until_scene": "s7",
                    "severity": "BLOCKER"
                }
            ]
        })
        # Mock scenes where s3 has both char_01 and char_04
        scenes_md = """# Scenes
target_seconds: 40

## Scene s1 — Departure
scene_id: s1
target_seconds: 15
cast: [char_01]

## Scene s3 — Danger Ahead
scene_id: s3
target_seconds: 25
cast: [char_01, char_04]
"""
        res = validate_constraints(story_json, scenes_md)
        self.assertFalse(res.ok)
        self.assertTrue(any("Co-presence exclusion violated in scene s3" in e for e in res.errors))

    def test_co_presence_exclusion_respected(self):
        story_json = json.dumps({
            "constraints": [
                {
                    "id": "H1",
                    "type": "co_presence_exclusion",
                    "subjects": ["char_01", "char_04"],
                    "valid_until_scene": "s7",
                    "severity": "BLOCKER"
                }
            ]
        })
        # char_01 in s3, char_04 in s5, first together in s8
        scenes_md = """# Scenes
target_seconds: 60

## Scene s3 — Walking
scene_id: s3
target_seconds: 20
cast: [char_01]

## Scene s5 — Threat in Darkness
scene_id: s5
target_seconds: 20
cast: [char_04]

## Scene s8 — First Meeting
scene_id: s8
target_seconds: 20
cast: [char_01, char_04]
"""
        res = validate_constraints(story_json, scenes_md)
        self.assertTrue(res.ok)

    def test_visibility_exclusion(self):
        story_json = json.dumps({
            "constraints": [
                {
                    "id": "H2",
                    "type": "visibility_exclusion",
                    "subjects": ["char_01"],
                    "scene": "s5",
                    "severity": "BLOCKER"
                }
            ]
        })
        scenes_md = """# Scenes
target_seconds: 25

## Scene s5 — Wide Road
scene_id: s5
target_seconds: 25
cast: [char_01, char_02]
"""
        res = validate_constraints(story_json, scenes_md)
        self.assertFalse(res.ok)
        self.assertTrue(any("Visibility exclusion violated: char_01 present in scene s5" in e for e in res.errors))


class TestRenderManifest(unittest.TestCase):
    def test_manifest_generation_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            # Create minimal scenes.md
            (run_dir / "scenes.md").write_text("""# Scenes
## Scene s1 — Opening
- scene_id: s1
- target_seconds: 12
- cast: [char_01]
- location_id: loc_01
""", encoding="utf-8")

            # Create storyboard_s1.md
            (run_dir / "storyboard_s1.md").write_text("""# Scene s1 — Opening
## Generation g1 — 0.0s - 12.0s
### Shot 1 — 0.0s - 12.0s
- characters_present: [char_01]
- action: Walking slowly
""", encoding="utf-8")

            # Create sheet and video prompt
            sheet = run_dir / "storyboard_sheet_s1_g1.webp"
            sheet.write_bytes(b"fake_webp_data_12345")

            os.makedirs(run_dir / "video_prompts", exist_ok=True)
            prompt = run_dir / "video_prompts" / "s1_g1.txt"
            prompt.write_text("Detailed prompt for s1_g1", encoding="utf-8")

            # Build manifest
            manifest = build_manifest(str(run_dir), approve=True, approved_by="director")
            manifest_file = run_dir / "render_manifest.json"
            self.assertTrue(manifest_file.is_file())
            self.assertEqual(len(manifest["generations"]), 1)
            self.assertEqual(manifest["generations"][0]["sheet_sha256"], sha256_file(str(sheet)))

            # Validate manifest: should pass initially
            res = validate_render_manifest(str(manifest_file), run_dir=str(run_dir))
            self.assertTrue(res.ok, f"Validation errors: {res.errors}")

            # Tamper with the sheet
            sheet.write_bytes(b"tampered_webp_data_99999")

            # Validate again: should detect sha256 mismatch
            res_tampered = validate_render_manifest(str(manifest_file), run_dir=str(run_dir))
            self.assertFalse(res_tampered.ok)
            self.assertTrue(any("sha256 mismatch" in e for e in res_tampered.errors))


if __name__ == "__main__":
    unittest.main()
