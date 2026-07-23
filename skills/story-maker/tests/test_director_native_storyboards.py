"""Tests for Director-native panel metadata, identity language, and AD handoff."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from schemas.plan import ProductionPlanDraft, ShotBrief  # noqa: E402
from scripts.nodes.flf_storyboard_planner import (  # noqa: E402
    _authored_chain_groups,
    _build_chain_clips,
    build_flf_planner_user_text,
)
from scripts.nodes.plan_pipeline_nodes import (  # noqa: E402
    migrate_director_panel_metadata,
    normalize_production_plan,
    validate_director_panel_metadata,
)
from scripts.nodes.reference_led_identity import (  # noqa: E402
    SCENE_09_CHILD_TEARFUL_AFTER_NAMED,
    SCENE_09_CHILD_TEARFUL_AFTER_REFERENCE_LED,
    SCENE_09_CHILD_TEARFUL_BEFORE,
    normalize_provider_identity_language,
    normalize_scene09_tearful_fixture,
)
from scripts.nodes.storyboard_nodes import build_panel_regen_prompt  # noqa: E402
from scripts.nodes.storyboard_sheet_builder import build_panel_lines  # noqa: E402


def _shot(
    n: int,
    *,
    chars: list[str] | None = None,
    cam: str = "Medium",
    group: int | None = None,
    role: str | None = None,
    after: str | None = None,
    note: str = "",
    bridge: str = "",
) -> dict:
    return {
        "shot_id": f"scene_02_shot_{n:02d}",
        "scene_id": "scene_02",
        "duration_seconds": 2,
        "characters_present": chars if chars is not None else ["naila"],
        "description": f"Naila beat {n}",
        "motion_intent": f"Naila continues beat {n}",
        "camera_intent": cam,
        "subject_position": "frame-left",
        "facing_direction": "screen-right",
        "director_chain_group": group,
        "director_guide_role": role,
        "director_transition_after": after,
        "director_continuity_note": note,
        "director_bridge_to_next": bridge,
    }


class TestDirectorPanelSchema(unittest.TestCase):
    def test_shot_brief_accepts_director_fields(self):
        shot = ShotBrief(
            shot_id="scene_01_shot_01",
            scene_id="scene_01",
            duration_seconds=2,
            description="Naila waves",
            director_transition_after="continue",
            director_chain_group=1,
            director_guide_role="start",
            director_continuity_note="Naila stays frame-left",
            director_bridge_to_next="Morph: continue. Camera tracks L→R.",
        )
        self.assertEqual(shot.director_transition_after, "continue")
        self.assertEqual(shot.director_chain_group, 1)
        self.assertEqual(shot.director_guide_role, "start")
        self.assertIn("tracks", shot.director_bridge_to_next)

    def test_legacy_migrate_derives_continue_and_groups(self):
        shots = [
            {
                "shot_id": "scene_01_shot_01",
                "characters_present": ["naila"],
                "camera_intent": "Wide",
                "description": "A",
            },
            {
                "shot_id": "scene_01_shot_02",
                "characters_present": ["naila"],
                "camera_intent": "Wide",
                "description": "B",
                "continuity_from_previous": True,
            },
            {
                "shot_id": "scene_01_shot_03",
                "characters_present": ["naila", "azhagi"],
                "camera_intent": "Close",
                "description": "C",
            },
        ]
        out = migrate_director_panel_metadata(shots)
        self.assertEqual(out[0]["director_transition_after"], "continue")
        self.assertIsNotNone(out[0]["director_chain_group"])
        self.assertIn(out[0]["director_guide_role"], ("start", "middle", "end"))
        self.assertEqual(out[-1]["director_transition_after"], "match_cut")

    def test_validate_rejects_nonconsecutive_group(self):
        shots = [
            _shot(1, group=1, role="start", after="continue", note="lock"),
            _shot(2, group=2, role="start", after="continue", note="lock"),
            _shot(3, group=1, role="end", after="match_cut", note="lock"),
        ]
        issues = validate_director_panel_metadata(shots)
        self.assertTrue(any("not consecutive" in i for i in issues))

    def test_validate_match_cut_inside_same_group(self):
        shots = [
            _shot(1, group=1, role="start", after="match_cut", note="cut"),
            _shot(2, group=1, role="end", after="match_cut", note="end"),
        ]
        issues = validate_director_panel_metadata(shots)
        self.assertTrue(any("match_cut inside same chain group" in i for i in issues))


class TestReferenceLedIdentity(unittest.TestCase):
    def test_scene09_before_after_named(self):
        named = normalize_provider_identity_language(
            SCENE_09_CHILD_TEARFUL_BEFORE,
            characters=[{"id": "naila", "name": "Naila"}],
            character_ids=["naila"],
            has_character_reference=False,
            preserve_safe_presentation=False,
        )
        self.assertIn("Naila", named)
        self.assertNotIn("child", named.lower())
        # Documented named form (apostrophe variants OK)
        self.assertTrue(
            "Naila" in named and "tearful" in named.lower(),
            named,
        )
        self.assertIn("Naila", SCENE_09_CHILD_TEARFUL_AFTER_NAMED)

    def test_scene09_reference_led_fixture(self):
        out = normalize_scene09_tearful_fixture(has_character_reference=True)
        self.assertIn("matching the attached character reference", out.lower())
        self.assertNotIn("child", out.lower())
        self.assertIn("matching the attached character reference", SCENE_09_CHILD_TEARFUL_AFTER_REFERENCE_LED)

    def test_does_not_mutate_when_no_age_labels(self):
        src = "Naila waves beside Azhagi in the meadow."
        out = normalize_provider_identity_language(
            src,
            characters=[{"id": "naila", "name": "Naila"}],
            character_ids=["naila"],
            has_character_reference=True,
            preserve_safe_presentation=False,
        )
        self.assertIn("Naila", out)
        self.assertIn("matching the attached character reference", out.lower())


class TestDirectorADHandoff(unittest.TestCase):
    def test_user_text_includes_director_metadata(self):
        scene = {
            "scene_id": "scene_02",
            "title": "Meadow",
            "environment": "meadow",
            "time_of_day": "morning",
            "lighting": "warm",
            "location_id": "loc_01",
            "staging": "path left, platform right",
            "blocking": [],
            "audio_scene": {"music_bed": "soft", "ending_state": "hold"},
            "video_shots": [
                {
                    "video_shot_id": "scene_02_vshot_01",
                    "panel_ids": ["scene_02_shot_01", "scene_02_shot_02"],
                    "anchor_panel_id": "scene_02_shot_01",
                    "duration_seconds": 12,
                }
            ],
            "shots": [
                _shot(
                    1,
                    group=1,
                    role="start",
                    after="continue",
                    note="Naila stays frame-left",
                ),
                _shot(2, group=1, role="end", after="match_cut", note="shared boundary"),
            ],
        }
        text = build_flf_planner_user_text(
            scene, ["scene_02_shot_01", "scene_02_shot_02"]
        )
        self.assertIn("Authored Director metadata", text)
        self.assertIn("group=1", text)
        self.assertIn("guide=start", text)
        self.assertIn("after=continue", text)
        self.assertIn("Naila stays frame-left", text)
        self.assertIn("soft hint only", text)
        self.assertIn("staging: path left", text)

    def test_authored_groups_to_units_with_shared_boundary(self):
        panels = [f"scene_02_shot_{i:02d}" for i in range(1, 7)]
        lookup = {
            panels[0]: _shot(1, group=1, role="start", after="continue"),
            panels[1]: _shot(2, group=1, role="middle", after="continue"),
            panels[2]: _shot(3, group=1, role="end", after="match_cut", note="face match"),
            panels[3]: _shot(4, group=2, role="start", after="continue"),
            panels[4]: _shot(5, group=2, role="middle", after="continue"),
            panels[5]: _shot(6, group=2, role="end", after="match_cut"),
        }
        units = _authored_chain_groups(panels, lookup)
        self.assertIsNotNone(units)
        assert units is not None
        self.assertEqual(units[0], [panels[0], panels[1], panels[2]])
        # Shared boundary: group2 starts with group1 end
        self.assertEqual(units[1][0], panels[2])
        self.assertIn(panels[3], units[1])

    def test_build_chain_clips_prefers_authored_groups(self):
        panels = [f"scene_02_shot_{i:02d}" for i in range(1, 5)]
        lookup = {
            panels[0]: _shot(1, group=1, role="start", after="continue", note="lock A"),
            panels[1]: _shot(2, group=1, role="end", after="match_cut", note="cut"),
            panels[2]: _shot(3, group=2, role="start", after="continue"),
            panels[3]: _shot(4, group=2, role="end", after="match_cut"),
        }
        cast_by = {pid: frozenset(["naila"]) for pid in panels}
        repairs: list[str] = []
        clips = _build_chain_clips(
            scene_id="scene_02",
            panel_ids=panels,
            normalized=[],
            cast_by=cast_by,
            shot_lookup=lookup,
            scene_global="warm meadow light",
            fps=25,
            repairs=repairs,
        )
        self.assertTrue(any("authored director groups" in r for r in repairs))
        self.assertGreaterEqual(len(clips), 2)
        # Shared boundary between units
        self.assertEqual(clips[0]["end_panel_id"], clips[1]["start_panel_id"])
        self.assertIn("continuity:", clips[0]["rationale"])


class TestDirectorPanelRegenPrompt(unittest.TestCase):
    def test_end_role_and_named_identity(self):
        shot = _shot(9, role="end", after="match_cut", note="landable end pose")
        shot["description"] = "the child’s tearful reaction close-up"
        prompt = build_panel_regen_prompt(
            shot,
            render_style="Pixar CGI",
            character_labels={"naila": "Naila"},
            story_characters=[{"id": "naila", "name": "Naila"}],
        )
        self.assertIn("END / destination", prompt)
        self.assertIn("Naila", prompt)
        self.assertNotIn("the child", prompt.lower())
        self.assertIn("landable end pose", prompt)


class TestDirectorNormalizePlan(unittest.TestCase):
    def test_normalize_fills_director_fields(self):
        plan = {
            "meta": {
                "story_title": "T",
                "style": "reel",
                "aesthetic": "warm",
                "target_duration_seconds": 30,
            },
            "characters": [
                {
                    "id": "naila",
                    "name": "Naila",
                    "appearance": "green dress",
                    "voice_profile": "soft",
                }
            ],
            "locations": [
                {
                    "id": "loc_01",
                    "name": "Meadow",
                    "description": "grass",
                    "establishing_prompt": "empty meadow",
                }
            ],
            "scenes": [
                {
                    "scene_id": "scene_02",
                    "title": "Meadow",
                    "environment": "meadow",
                    "time_of_day": "day",
                    "lighting": "sun",
                    "location_id": "loc_01",
                    "shots": [
                        {
                            "shot_id": "scene_02_shot_01",
                            "description": "Naila walks",
                            "characters_present": ["naila"],
                            "camera_intent": "Wide",
                            "duration_seconds": 2,
                        },
                        {
                            "shot_id": "scene_02_shot_02",
                            "description": "Naila stops",
                            "characters_present": ["naila"],
                            "camera_intent": "Wide",
                            "duration_seconds": 2,
                            "continuity_from_previous": True,
                        },
                    ],
                }
            ],
        }
        ctx = MagicMock()
        ctx.state = {
            "style_id": "reel_v2",
            "pipeline_mode": "storyboard",
            "storyboard_video_mode": "director",
        }
        out = normalize_production_plan(plan, ctx)
        shots = out["scenes"][0]["shots"]
        self.assertTrue(all(s.get("director_transition_after") for s in shots))
        self.assertTrue(all(s.get("director_chain_group") for s in shots))
        # Draft round-trip accepts optional director fields
        draft = ProductionPlanDraft(
            meta=out["meta"],
            characters=out["characters"],
            locations=out["locations"],
            scenes=out["scenes"],
        )
        validated = draft.to_plan()
        self.assertEqual(len(validated.scenes[0].shots), 2)


class TestPanelLinesDirector(unittest.TestCase):
    def test_panel_lines_include_director_fields(self):
        lines = build_panel_lines(
            [
                _shot(
                    1,
                    group=1,
                    role="middle",
                    after="continue",
                    note="basket in right hand",
                    bridge="Morph: continue. Naila lowers; Azhagi leans in.",
                ),
                _shot(
                    2,
                    group=1,
                    role="end",
                    after="match_cut",
                    note="shared boundary",
                ),
            ]
        )
        self.assertIn("Director guide role: middle", lines)
        self.assertIn("Continuity edge after panel: continue", lines)
        self.assertIn("Director note: basket in right hand", lines)
        self.assertIn("board beat", lines)
        self.assertIn("Motion (toward next panel):", lines)
        self.assertIn("Outgoing bridge → next panel:", lines)
        self.assertIn("Incoming bridge", lines)
        self.assertIn("Naila lowers", lines)


class TestDirectorPanelRegenAll(unittest.TestCase):
    def test_director_mode_forces_regen_all_flag_path(self):
        """Director mode should bypass anchor-only skipping (env-independent check)."""
        from scripts.nodes.storyboard_director_nodes import is_director_video_mode

        ctx = MagicMock()
        ctx.state = {"storyboard_video_mode": "director"}
        self.assertTrue(is_director_video_mode(ctx))
        ctx.state = {"storyboard_video_mode": "fallback"}
        self.assertFalse(is_director_video_mode(ctx))

    def test_panel_regen_includes_bridge_and_motion(self):
        prompt = build_panel_regen_prompt(
            {
                "shot_id": "scene_02_shot_01",
                "description": "Naila on shoulders",
                "camera_intent": "medium",
                "characters_present": ["naila", "father"],
                "director_guide_role": "start",
                "director_continuity_note": "Naila frame-left",
                "director_bridge_to_next": "Morph: continue. Camera tracks forward.",
                "motion_intent": "From wide to medium: Father walks L→R with Naila.",
            },
            render_style="Pixar CGI",
        )
        self.assertIn("Outgoing bridge toward next panel", prompt)
        self.assertIn("Connecting motion intent", prompt)
        self.assertIn("Camera tracks forward", prompt)


class TestUpstreamPromptContracts(unittest.TestCase):
    def test_story_developer_is_director_continuity(self):
        path = os.path.join(_SKILL_DIR, "prompts", "story_developer.md")
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("continuity beats", text.lower())
        self.assertNotIn("one continuous I2V clip", text)
        self.assertIn("Naila", text)
        self.assertIn("drawable evolution", text)
        self.assertIn("sub-scene architect", text.lower())
        self.assertIn("Thin-story expansion playbook", text)
        self.assertIn("must not look alike", text.lower())
        self.assertIn("Worked example", text)
        self.assertIn("scenes_target", text)
        self.assertIn("**Purpose:**", text)
        self.assertIn("Hubris pause", text)

    def test_scene_paper_has_director_keyframe_lines(self):
        path = os.path.join(_SKILL_DIR, "prompts", "reel_v2", "scene_paper_author.md")
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("Continuity", text)
        self.assertIn("Guide role", text)
        self.assertIn("Director note", text)
        self.assertIn("match_cut", text)
        self.assertIn("### Motion spine", text)
        self.assertIn("#### Bridge → Panel", text)
        self.assertIn("### Director chain sketch", text)
        self.assertIn("Prompt Relay", text)

    def test_production_plan_requires_director_fields(self):
        path = os.path.join(_SKILL_DIR, "prompts", "reel_v2", "production_plan_author.md")
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("director_transition_after", text)
        self.assertIn("director_chain_group", text)
        self.assertIn("director_motion_spine", text)
        self.assertIn("director_bridge_to_next", text)
        self.assertIn("12–15s", text)
        self.assertIn("from this still into the next still", text)


class TestMotionSpineNormalize(unittest.TestCase):
    def test_aliases_normalize_spine_and_bridge(self):
        plan = {
            "meta": {
                "story_title": "Test",
                "style": "reel",
                "aesthetic": "pixar",
                "target_duration_seconds": 30,
            },
            "characters": [
                {
                    "id": "naila",
                    "name": "Naila",
                    "appearance": "girl",
                    "voice_profile": "bright",
                }
            ],
            "locations": [
                {
                    "id": "loc_01",
                    "name": "Path",
                    "description": "path",
                    "establishing_prompt": "empty path",
                }
            ],
            "scenes": [
                {
                    "scene_id": "scene_01",
                    "title": "Walk",
                    "environment": "path",
                    "time_of_day": "day",
                    "lighting": "sun",
                    "location_id": "loc_01",
                    "motion_spine": "P01→P02: Father walks with Naila.",
                    "shots": [
                        {
                            "shot_id": "scene_01_shot_01",
                            "scene_id": "scene_01",
                            "duration_seconds": 2,
                            "characters_present": ["naila"],
                            "description": "Wide path",
                            "motion_intent": "Walk toward next panel",
                            "camera_intent": "wide",
                            "bridge_to_next": "Morph: continue. Track L→R.",
                            "director_transition_after": "continue",
                            "director_chain_group": 1,
                            "director_guide_role": "start",
                        },
                        {
                            "shot_id": "scene_01_shot_02",
                            "scene_id": "scene_01",
                            "duration_seconds": 2,
                            "characters_present": ["naila"],
                            "description": "Medium walk",
                            "motion_intent": "Match-cut handoff",
                            "camera_intent": "medium",
                            "director_transition_after": "match_cut",
                            "director_chain_group": 1,
                            "director_guide_role": "end",
                        },
                    ],
                }
            ],
        }
        ctx = MagicMock()
        ctx.state = {
            "style_id": "reel_v2",
            "pipeline_mode": "storyboard",
            "storyboard_video_mode": "director",
        }
        out = normalize_production_plan(plan, ctx)
        scene = out["scenes"][0]
        self.assertIn("Father walks", scene["director_motion_spine"])
        self.assertIn("Track L→R", scene["shots"][0]["director_bridge_to_next"])
        draft = ProductionPlanDraft(
            meta=out["meta"],
            characters=out["characters"],
            locations=out["locations"],
            scenes=out["scenes"],
        )
        validated = draft.to_plan()
        self.assertIn("Father walks", validated.scenes[0].director_motion_spine)
        self.assertIn(
            "Track",
            validated.scenes[0].shots[0].director_bridge_to_next,
        )


class TestAdPayloadSpine(unittest.TestCase):
    def test_user_text_includes_motion_spine_and_bridges(self):
        scene = {
            "scene_id": "scene_02",
            "title": "Walk",
            "environment": "path",
            "time_of_day": "day",
            "lighting": "sun",
            "location_id": "loc_01",
            "director_motion_spine": "P01→P02: Father walks with Naila on shoulders.",
            "shots": [
                _shot(
                    1,
                    group=1,
                    role="start",
                    after="continue",
                    bridge="Morph: continue. Track forward.",
                ),
                _shot(2, group=1, role="end", after="match_cut"),
            ],
        }
        text = build_flf_planner_user_text(
            scene,
            [s["shot_id"] for s in scene["shots"]],
        )
        self.assertIn("Director motion spine", text)
        self.assertIn("Father walks with Naila", text)
        self.assertIn("Panel bridges + connecting motion", text)
        self.assertIn("bridge_to_next=", text)
        self.assertIn("Track forward", text)
