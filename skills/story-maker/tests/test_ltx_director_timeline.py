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
    build_timeline_from_beats,
    build_timeline_from_director_clip,
    snap_ltx_frames,
)
from tools.ltx_director_workflow import (
    is_aac_nan_error,
    patch_cfg_guiders,
    patch_director_node,
    patch_negative_prompt,
    patch_save_video_codec,
    patch_server_model_names,
    queue_director_timeline,
)


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

    def test_multi_guide_start_middle_end(self):
        clip = {
            "clip_id": "scene_07_unit_02",
            "start_panel_id": "scene_07_shot_03",
            "end_panel_id": "scene_07_shot_05",
            "workflow": "flf2v",
            "duration_seconds": 8,
            "motion_class": "fast_action",
            "i2v_strength": 0.55,
            "last_frame_strength": 0.85,
            "guide_frames": [
                {"panel_id": "scene_07_shot_03", "placement": "start"},
                {
                    "panel_id": "scene_07_shot_04",
                    "placement": "middle",
                    "start_ratio": 0.55,
                },
                {"panel_id": "scene_07_shot_05", "placement": "end"},
            ],
            "motion_segments": [
                {"start_ratio": 0.0, "end_ratio": 0.4, "prompt": "Dog races in."},
                {"start_ratio": 0.4, "end_ratio": 1.0, "prompt": "Settles into bark."},
            ],
            "motion_prompt": "Dog races in. Settles into bark.",
        }
        payload = build_timeline_from_director_clip(
            clip,
            first_image_file="a.png",
            last_image_file="c.png",
            guide_image_files={
                "scene_07_shot_03": "a.png",
                "scene_07_shot_04": "b.png",
                "scene_07_shot_05": "c.png",
            },
            fps=24,
        )
        timeline = json.loads(payload["timeline_data"])
        images = [s for s in timeline["segments"] if s["type"] == "image"]
        self.assertEqual(len(images), 3)
        self.assertFalse(images[0]["isEndFrame"])
        self.assertFalse(images[1]["isEndFrame"])
        self.assertTrue(images[2]["isEndFrame"])
        self.assertEqual(images[1]["imageFile"], "b.png")
        self.assertEqual(payload["guide_strength"].count(","), 2)
        lengths = [int(x) for x in payload["segment_lengths"].split(",")]
        self.assertEqual(sum(lengths), payload["duration_frames"])


class TestBeatsTimeline(unittest.TestCase):
    def test_leading_text_and_bridge_and_trailing_text(self):
        beats = [
            {"kind": "text", "duration_seconds": 1, "prompt": "empty path, girl enters from left"},
            {"kind": "guide", "panel_id": "p1", "role": "start", "anchor_seconds": 0.5},
            {"kind": "text", "duration_seconds": 2, "prompt": "walks toward camera"},
            {"kind": "text", "duration_seconds": 1, "prompt": "waves hi"},
            {"kind": "guide", "panel_id": "p2", "role": "bridge"},
            {"kind": "text", "duration_seconds": 2, "prompt": "turns, exits frame right"},
            {"kind": "guide", "panel_id": "p3", "role": "end"},
            {"kind": "text", "duration_seconds": 3, "prompt": "branch cracks, she falls"},
        ]
        payload = build_timeline_from_beats(
            beats,
            image_files={"p1": "p1.png", "p2": "p2.png", "p3": "p3.png"},
            global_prompt="sunlit meadow",
            fps=24,
        )
        # Total duration = sum of text beats only (9s), snapped to 8n+1.
        expected_frames = snap_ltx_frames(9, fps=24)
        self.assertEqual(payload["duration_frames"], expected_frames)

        timeline = json.loads(payload["timeline_data"])
        self.assertEqual(timeline["global_prompt"], "sunlit meadow")
        images = [s for s in timeline["segments"] if s["type"] == "image"]
        texts = [s for s in timeline["segments"] if s["type"] == "text"]
        self.assertEqual(len(images), 3)
        self.assertEqual(len(texts), 5)

        # Leading text pushes the start guide off frame 0.
        start_img = images[0]
        self.assertEqual(start_img["imageFile"], "p1.png")
        self.assertGreater(start_img["start"], 0)
        self.assertFalse(start_img["isEndFrame"])

        # Bridge guide lands wherever the cursor is after "waves hi", not at
        # a fixed ratio.
        bridge_img = images[1]
        self.assertEqual(bridge_img["imageFile"], "p2.png")
        self.assertFalse(bridge_img["isEndFrame"])

        # End guide is pinned to the true final frames regardless of its
        # position in the beat list (trailing text still follows it).
        end_img = images[2]
        self.assertEqual(end_img["imageFile"], "p3.png")
        self.assertTrue(end_img["isEndFrame"])
        self.assertEqual(end_img["start"] + end_img["length"], expected_frames)

        # Text segment lengths sum exactly to the total duration.
        lengths = [int(x) for x in payload["segment_lengths"].split(",")]
        self.assertEqual(sum(lengths), expected_frames)

    def test_default_guide_strengths_by_role(self):
        beats = [
            {"kind": "guide", "panel_id": "p1", "role": "start"},
            {"kind": "text", "duration_seconds": 4, "prompt": "push in"},
            {"kind": "guide", "panel_id": "p2", "role": "bridge"},
            {"kind": "text", "duration_seconds": 4, "prompt": "whip pan"},
            {"kind": "guide", "panel_id": "p3", "role": "end"},
        ]
        payload = build_timeline_from_beats(
            beats,
            image_files={"p1": "p1.png", "p2": "p2.png", "p3": "p3.png"},
            default_start_strength=0.7,
            default_bridge_strength=0.55,
            default_end_strength=0.9,
        )
        strengths = [float(x) for x in payload["guide_strength"].split(",")]
        self.assertEqual(strengths, [0.7, 0.55, 0.9])

    def test_explicit_guide_strength_overrides_default(self):
        beats = [
            {"kind": "guide", "panel_id": "p1", "role": "start", "guide_strength": 0.42},
            {"kind": "text", "duration_seconds": 5, "prompt": "hold and drift"},
            {"kind": "guide", "panel_id": "p2", "role": "end", "guide_strength": 0.99},
        ]
        payload = build_timeline_from_beats(
            beats, image_files={"p1": "p1.png", "p2": "p2.png"}
        )
        strengths = [float(x) for x in payload["guide_strength"].split(",")]
        self.assertEqual(strengths, [0.42, 0.99])

    def test_requires_at_least_one_guide(self):
        with self.assertRaises(ValueError):
            build_timeline_from_beats(
                [{"kind": "text", "duration_seconds": 4, "prompt": "nothing to anchor this"}]
            )

    def test_dispatch_from_director_clip_prefers_beats(self):
        clip = {
            "clip_id": "scene_01_unit_01",
            "start_panel_id": "scene_01_shot_01",
            "end_panel_id": "scene_01_shot_04",
            "workflow": "flf2v",
            "duration_seconds": 12,
            "global_prompt": "sunlit meadow",
            "beats": [
                {"kind": "guide", "panel_id": "scene_01_shot_01", "role": "start"},
                {"kind": "text", "duration_seconds": 4, "prompt": "push in; father lifts fruit"},
                {"kind": "guide", "panel_id": "scene_01_shot_02", "role": "bridge"},
                {
                    "kind": "text",
                    "duration_seconds": 4,
                    "prompt": "whip pan off empty ground; no new figures enter",
                },
                {"kind": "guide", "panel_id": "scene_01_shot_04", "role": "end"},
            ],
        }
        payload = build_timeline_from_director_clip(
            clip,
            first_image_file="shot01.png",
            last_image_file="shot04.png",
            guide_image_files={"scene_01_shot_02": "shot02.png"},
            render={"i2v_strength": 0.7, "last_frame_strength": 0.9},
        )
        timeline = json.loads(payload["timeline_data"])
        images = [s for s in timeline["segments"] if s["type"] == "image"]
        self.assertEqual([i["imageFile"] for i in images], ["shot01.png", "shot02.png", "shot04.png"])
        self.assertTrue(images[-1]["isEndFrame"])
        self.assertEqual(timeline["global_prompt"], "sunlit meadow")


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

    def test_patch_server_model_names_adaptive(self):
        api = {
            "12": {
                "class_type": "DualCLIPLoader",
                "inputs": {"clip_name1": "comfy_gemma_3_12B_it.safetensors"},
            }
        }
        patch_server_model_names(
            api,
            available_clip_names=[
                "gemma_3_12B_it_fp4_mixed.safetensors",
                "ltx-2.3_text_projection_bf16.safetensors",
            ],
        )
        self.assertEqual(
            api["12"]["inputs"]["clip_name1"],
            "gemma_3_12B_it_fp4_mixed.safetensors",
        )
        # Already present: leave unchanged.
        patch_server_model_names(
            api,
            available_clip_names=["gemma_3_12B_it_fp4_mixed.safetensors"],
        )
        self.assertEqual(
            api["12"]["inputs"]["clip_name1"],
            "gemma_3_12B_it_fp4_mixed.safetensors",
        )

    def test_patch_negative_prompt_rewires_zeroed_branches(self):
        api = {
            "10": {"class_type": "DualCLIPLoader", "inputs": {}},
            "131": {"class_type": "LTXDirector", "inputs": {"clip": ["10", 0]}},
            "128": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["131", 1]}},
            "129": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["131", 1]}},
            "55": {
                "class_type": "LTXDirectorCropGuides",
                "inputs": {"positive": ["131", 1], "negative": ["128", 0]},
            },
            "56": {
                "class_type": "LTXVConditioning",
                "inputs": {"positive": ["131", 1], "negative": ["129", 0]},
            },
        }
        patch_negative_prompt(api, "extra people, duplicated characters")

        new_ids = [nid for nid, n in api.items() if n["class_type"] == "CLIPTextEncode"]
        self.assertEqual(len(new_ids), 1)
        new_id = new_ids[0]
        self.assertEqual(api[new_id]["inputs"]["text"], "extra people, duplicated characters")
        self.assertEqual(api[new_id]["inputs"]["clip"], ["10", 0])
        self.assertEqual(api["55"]["inputs"]["negative"], [new_id, 0])
        self.assertEqual(api["56"]["inputs"]["negative"], [new_id, 0])

    def test_patch_negative_prompt_empty_is_noop(self):
        api = {
            "128": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["131", 1]}},
            "55": {"class_type": "LTXDirectorCropGuides", "inputs": {"negative": ["128", 0]}},
        }
        before = json.dumps(api, sort_keys=True)
        patch_negative_prompt(api, "")
        self.assertEqual(json.dumps(api, sort_keys=True), before)

    def test_patch_save_video_codec_forces_h264(self):
        api = {
            "37": {
                "class_type": "SaveVideo",
                "inputs": {
                    "filename_prefix": "video/LTX_Director",
                    "format": "auto",
                    "codec": "auto",
                },
            }
        }
        patch_save_video_codec(api)
        self.assertEqual(api["37"]["inputs"]["codec"], "h264")
        self.assertEqual(api["37"]["inputs"]["format"], "mp4")

    def test_is_aac_nan_error_matches_savevideo_message(self):
        msg = (
            "Node 37 (SaveVideo): Invalid argument: 'avcodec_send_frame()' returned 22; "
            "last error log: [aac] Input contains (near) NaN/+-Inf"
        )
        self.assertTrue(is_aac_nan_error(msg))
        self.assertTrue(is_aac_nan_error(f"LTX Director failed: {msg}"))
        self.assertFalse(is_aac_nan_error("Queue error: connection refused"))
        self.assertFalse(is_aac_nan_error("OpenEncodeSessionEx failed: unsupported device"))


class TestAacNanSeedRetry(unittest.TestCase):
    def test_queue_retries_aac_nan_with_bumped_seed(self):
        calls: list[int] = []

        def fake_once(**kwargs):
            seed = int(kwargs["seed"])
            calls.append(seed)
            if len(calls) == 1:
                return {
                    "status": "error",
                    "message": (
                        "LTX Director failed: Node 37 (SaveVideo): Invalid argument: "
                        "'avcodec_send_frame()' returned 22; last error log: "
                        "[aac] Input contains (near) NaN/+-Inf"
                    ),
                }
            return {
                "status": "success",
                "video_path": kwargs["output_path"],
                "prompt_id": "p1",
                "duration_frames": 145,
                "duration_seconds": 6.0,
                "guide_strength": "0.70",
            }

        import tools.ltx_director_workflow as wf

        original = wf._queue_director_timeline_once
        wf._queue_director_timeline_once = fake_once
        try:
            result = queue_director_timeline(
                timeline_payload={
                    "timeline_data": "{}",
                    "duration_frames": 145,
                    "duration_seconds": 6.0,
                    "guide_strength": "0.70",
                },
                output_path="/tmp/test_director_out.mp4",
                seed=42,
            )
        finally:
            wf._queue_director_timeline_once = original

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls, [42, 1042])
        self.assertEqual(result["seed"], 1042)
        self.assertEqual(result["aac_nan_retries"], 1)

    def test_queue_does_not_retry_non_nan_errors(self):
        calls: list[int] = []

        def fake_once(**kwargs):
            calls.append(int(kwargs["seed"]))
            return {"status": "error", "message": "LTX Director failed: Queue error: boom"}

        import tools.ltx_director_workflow as wf

        original = wf._queue_director_timeline_once
        wf._queue_director_timeline_once = fake_once
        try:
            result = queue_director_timeline(
                timeline_payload={"timeline_data": "{}"},
                output_path="/tmp/test_director_out.mp4",
                seed=42,
            )
        finally:
            wf._queue_director_timeline_once = original

        self.assertEqual(result["status"], "error")
        self.assertEqual(calls, [42])
        self.assertIn("Queue error", result["message"])


if __name__ == "__main__":
    unittest.main()
