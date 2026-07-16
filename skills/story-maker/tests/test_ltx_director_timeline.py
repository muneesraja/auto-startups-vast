import json
import os
import sys
import unittest

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SKILL_DIR not in sys.path:
    sys.path.insert(0, _SKILL_DIR)

from tools.ltx_director_timeline import (
    build_flf_timeline,
    build_i2v_timeline,
    build_timeline_from_director_clip,
    snap_ltx_frames,
)
from tools.ltx_director_workflow import patch_cfg_guiders, patch_director_node


class TestSnapLtxFrames(unittest.TestCase):
    def test_8n_plus_1(self):
        self.assertEqual(snap_ltx_frames(6, fps=24), 145)
        self.assertEqual(snap_ltx_frames(8, fps=24), 193)
        self.assertEqual(snap_ltx_frames(5, fps=24), 121)


class TestDirectorTimelines(unittest.TestCase):
    def test_i2v_timeline_widgets(self):
        payload = build_i2v_timeline(
            image_file="whatdreamscost/a.png",
            motion_prompt="Dog runs in and stops.",
            duration_frames=145,
            guide_strength=0.7,
            fps=24,
        )
        self.assertEqual(payload["guide_strength"], "0.70")
        self.assertEqual(payload["local_prompts"], "Dog runs in and stops.")
        lengths = [int(x) for x in payload["segment_lengths"].split(",")]
        self.assertEqual(sum(lengths), 145)
        timeline = json.loads(payload["timeline_data"])
        images = [s for s in timeline["segments"] if s["type"] == "image"]
        texts = [s for s in timeline["segments"] if s["type"] == "text"]
        self.assertEqual(len(images), 1)
        self.assertEqual(len(texts), 1)
        self.assertFalse(images[0].get("isEndFrame"))
        self.assertEqual(images[0]["imageFile"], "whatdreamscost/a.png")

    def test_flf_timeline_end_frame(self):
        payload = build_flf_timeline(
            first_image_file="whatdreamscost/a.png",
            last_image_file="whatdreamscost/b.png",
            motion_prompt="Trunk accepts fruit.",
            duration_frames=193,
            first_guide_strength=0.7,
            last_guide_strength=0.85,
            fps=24,
        )
        self.assertEqual(payload["guide_strength"], "0.70,0.85")
        lengths = [int(x) for x in payload["segment_lengths"].split(",")]
        self.assertEqual(sum(lengths), 193)
        timeline = json.loads(payload["timeline_data"])
        images = [s for s in timeline["segments"] if s["type"] == "image"]
        self.assertEqual(len(images), 2)
        self.assertFalse(images[0].get("isEndFrame"))
        self.assertTrue(images[1].get("isEndFrame"))
        self.assertEqual(images[1]["imageFile"], "whatdreamscost/b.png")
        self.assertAlmostEqual(images[0]["guideStrength"], 0.7)
        self.assertAlmostEqual(images[1]["guideStrength"], 0.85)

    def test_build_from_director_clip_i2v(self):
        clip = {
            "clip_id": "scene_07_seg_02_clip_01",
            "start_panel_id": "scene_07_shot_03",
            "end_panel_id": "scene_07_shot_03",
            "workflow": "i2v",
            "duration_seconds": 6,
            "motion_class": "walking",
            "guidance": "balanced",
            "i2v_strength": 0.7,
            "cfg": 1.0,
            "last_frame_strength": 0.85,
            "motion_prompt": "Azhagi bursts out of the forest trail.",
        }
        payload = build_timeline_from_director_clip(
            clip,
            first_image_file="whatdreamscost/scene_07_shot_03.png",
            fps=24,
        )
        self.assertEqual(payload["duration_frames"], 145)
        self.assertEqual(payload["guide_strength"], "0.70")
        self.assertIn("Azhagi bursts", payload["local_prompts"])
        timeline = json.loads(payload["timeline_data"])
        self.assertEqual(timeline.get("global_prompt"), "")

    def test_build_from_director_clip_flf(self):
        clip = {
            "clip_id": "scene_07_seg_01_clip_01",
            "start_panel_id": "scene_07_shot_01",
            "end_panel_id": "scene_07_shot_02",
            "workflow": "flf2v",
            "duration_seconds": 8,
            "motion_class": "general",
            "guidance": "balanced",
            "i2v_strength": 0.7,
            "cfg": 1.0,
            "last_frame_strength": 0.85,
            "motion_prompt": "Father feeds the elephant.",
        }
        payload = build_timeline_from_director_clip(
            clip,
            first_image_file="whatdreamscost/scene_07_shot_01.png",
            last_image_file="whatdreamscost/scene_07_shot_02.png",
            fps=24,
        )
        self.assertEqual(payload["duration_frames"], 193)
        self.assertEqual(payload["guide_strength"], "0.70,0.85")
        timeline = json.loads(payload["timeline_data"])
        images = [s for s in timeline["segments"] if s["type"] == "image"]
        self.assertTrue(images[-1]["isEndFrame"])

    def test_talking_class_stronger_start_guide(self):
        clip = {
            "clip_id": "scene_07_seg_03_clip_01",
            "start_panel_id": "scene_07_shot_04",
            "end_panel_id": "scene_07_shot_05",
            "workflow": "flf2v",
            "duration_seconds": 8,
            "motion_class": "talking",
            "guidance": "balanced",
            "i2v_strength": 0.8,
            "cfg": 1.0,
            "last_frame_strength": 0.85,
            "motion_prompt": "Urgent bark.",
        }
        payload = build_timeline_from_director_clip(
            clip,
            first_image_file="a.png",
            last_image_file="b.png",
            fps=24,
        )
        self.assertEqual(payload["guide_strength"], "0.80,0.85")

    def test_timed_motion_segments_prompt_relay(self):
        clip = {
            "clip_id": "scene_07_seg_01_clip_01",
            "start_panel_id": "scene_07_shot_01",
            "end_panel_id": "scene_07_shot_02",
            "workflow": "flf2v",
            "duration_seconds": 8,
            "motion_class": "general",
            "guidance": "balanced",
            "i2v_strength": 0.7,
            "last_frame_strength": 0.85,
            "global_prompt": "Warm meadow light, cinematic 3D.",
            "motion_segments": [
                {
                    "start_ratio": 0.0,
                    "end_ratio": 0.4,
                    "prompt": "Father lifts fruit toward the trunk.",
                },
                {
                    "start_ratio": 0.4,
                    "end_ratio": 1.0,
                    "prompt": "Trunk curls and accepts the fruit; camera settles.",
                },
            ],
            "motion_prompt": "Father lifts fruit toward the trunk. Trunk curls and accepts the fruit.",
        }
        payload = build_timeline_from_director_clip(
            clip,
            first_image_file="a.png",
            last_image_file="b.png",
            fps=24,
        )
        self.assertEqual(payload["duration_frames"], 193)
        self.assertIn(" | ", payload["local_prompts"])
        self.assertIn("Father lifts fruit", payload["local_prompts"])
        self.assertIn("Trunk curls", payload["local_prompts"])
        lengths = [int(x) for x in payload["segment_lengths"].split(",")]
        self.assertEqual(len(lengths), 2)
        self.assertEqual(sum(lengths), 193)
        timeline = json.loads(payload["timeline_data"])
        self.assertEqual(timeline["global_prompt"], "Warm meadow light, cinematic 3D.")
        texts = [s for s in timeline["segments"] if s["type"] == "text"]
        self.assertEqual(len(texts), 2)
        images = [s for s in timeline["segments"] if s["type"] == "image"]
        self.assertTrue(images[-1]["isEndFrame"])


class TestWorkflowPatches(unittest.TestCase):
    def test_patch_cfg_and_director(self):
        api = {
            "131": {"class_type": "LTXDirector", "inputs": {}},
            "17": {"class_type": "CFGGuider", "inputs": {"cfg": 1}},
            "28": {"class_type": "CFGGuider", "inputs": {"cfg": 1}},
        }
        timeline = {
            "timeline_data": "{}",
            "local_prompts": "hello",
            "segment_lengths": "145",
            "guide_strength": "0.70",
            "start_frame": 0,
            "end_frame": 145,
            "duration_frames": 145,
            "duration_seconds": 145 / 24.0,
            "frame_rate": 24,
        }
        patch_director_node(
            api,
            timeline_payload=timeline,
            global_prompt="",
            custom_width=1920,
            custom_height=1088,
        )
        patch_cfg_guiders(api, 1.2)
        self.assertEqual(api["131"]["inputs"]["local_prompts"], "hello")
        self.assertEqual(api["131"]["inputs"]["custom_width"], 1920)
        self.assertEqual(api["17"]["inputs"]["cfg"], 1.2)
        self.assertEqual(api["28"]["inputs"]["cfg"], 1.2)


if __name__ == "__main__":
    unittest.main()
