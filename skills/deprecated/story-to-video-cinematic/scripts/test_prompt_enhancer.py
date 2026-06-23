#!/usr/bin/env python3
"""
Unit test for llm_prompt_enhancer.py
"""

import os
import sys
import json
import urllib.error
import unittest
from unittest.mock import patch, MagicMock

# Resolve paths
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

from llm_prompt_enhancer import (
    get_resolution_string,
    validate_ideogram_json,
    enhance_character_sheet_prompt,
    enhance_scene_prompt,
)

class TestLLMPromptEnhancer(unittest.TestCase):

    def setUp(self):
        self.global_cfg = {
            "width": 1344,
            "height": 768,
            "prompt_enhancer": {
                "enabled": True,
                "provider": "openrouter",
                "model": "google/gemini-3.1-flash-lite",
                "fallback_model": "openai/gpt-4o-mini",
                "cache_prompts": False
            }
        }
        self.output_dir = os.path.join(script_dir, "temp_test_output")
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        import shutil
        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)

    def test_get_resolution_string(self):
        # 1. Direct width/height
        cfg = {"width": 1024, "height": 1024}
        self.assertEqual(get_resolution_string(cfg), "1024x1024")
        
        # 2. Resolution preset
        cfg = {"resolution_preset": "1080p"}
        self.assertEqual(get_resolution_string(cfg), "1920x1080")
        
        # 3. Default fallback
        cfg = {}
        self.assertEqual(get_resolution_string(cfg), "1920x1080")

    def test_validate_ideogram_json(self):
        # 1. Valid JSON
        valid_json = json.dumps({
            "high_level_description": "A test scene description",
            "style_description": {
                "aesthetics": "3D style",
                "lighting": "cinematic",
                "medium": "illustration",
                "art_style": "pixar style",
                "color_palette": ["#FF0000", "#00FF00"]
            },
            "compositional_deconstruction": {
                "background": "white background",
                "elements": [
                    {
                        "type": "obj",
                        "bbox": [100, 100, 900, 900],
                        "desc": "Object desc",
                        "color_palette": ["#FFFFFF"]
                    }
                ]
            }
        })
        self.assertTrue(validate_ideogram_json(valid_json))

        # 2. Invalid JSON (missing key)
        invalid_json = json.dumps({
            "high_level_description": "A test scene description",
            "style_description": {}
        })
        self.assertFalse(validate_ideogram_json(invalid_json))

        # 3. Invalid bbox bounds
        invalid_bbox = json.dumps({
            "high_level_description": "A test",
            "style_description": {},
            "compositional_deconstruction": {
                "background": "bg",
                "elements": [{"type": "obj", "bbox": [100, 100, 1200, 900], "desc": "obj"}]
            }
        })
        self.assertFalse(validate_ideogram_json(invalid_bbox))

    @patch("urllib.request.urlopen")
    def test_enhance_character_sheet_success(self, mock_urlopen):
        # Setup mock response
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "high_level_description": "Mocked front, 3/4, side character sheets for Pippin",
                        "style_description": {
                            "aesthetics": "model sheet",
                            "lighting": "flat studio",
                            "medium": "illustration",
                            "art_style": "Pixar chibi",
                            "color_palette": ["#FFFFFF"]
                        },
                        "compositional_deconstruction": {
                            "background": "white background",
                            "elements": [
                                {"type": "obj", "bbox": [50, 50, 950, 350], "desc": "front view"},
                                {"type": "obj", "bbox": [50, 380, 950, 650], "desc": "3/4 view"},
                                {"type": "obj", "bbox": [50, 680, 950, 950], "desc": "side view"}
                            ]
                        }
                    })
                }
            }]
        }
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # Set environment key to bypass check
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
            enhanced = enhance_character_sheet_prompt(
                character_name="Pippin",
                character_desc="A baby panda",
                style_notes="chibi style",
                global_style="3D Pixar",
                global_cfg=self.global_cfg,
                output_dir=self.output_dir,
                filename_prefix="pippin_test"
            )
            
            self.assertIsNotNone(enhanced)
            data = json.loads(enhanced)
            self.assertEqual(data["high_level_description"], "Mocked front, 3/4, side character sheets for Pippin")
            self.assertEqual(len(data["compositional_deconstruction"]["elements"]), 3)

    @patch("urllib.request.urlopen")
    def test_enhance_scene_still_success(self, mock_urlopen):
        # Setup mock response
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "high_level_description": "Pippin playing in the forest",
                        "style_description": {
                            "aesthetics": "3D forest style",
                            "lighting": "warm shafts of sunlight",
                            "medium": "cinematic_still",
                            "art_style": "Pixar render",
                            "color_palette": ["#00FF00"]
                        },
                        "compositional_deconstruction": {
                            "background": "detailed forest background",
                            "elements": [
                                {"type": "obj", "bbox": [150, 250, 950, 750], "desc": "Pippin playing"}
                            ]
                        },
                        "additional_directives": ["vibrant colors"]
                    })
                }
            }]
        }
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # Set environment key to bypass check
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
            characters_cfg = {
                "pippin": {"display_name": "Pippin", "description": "Baby panda"}
            }
            enhanced = enhance_scene_prompt(
                prompt_text="Pippin playing in the forest",
                global_style="3D Pixar",
                characters_present=["pippin"],
                characters_cfg=characters_cfg,
                global_cfg=self.global_cfg,
                output_dir=self.output_dir,
                filename_prefix="scene_test"
            )
            
            self.assertIsNotNone(enhanced)
            data = json.loads(enhanced)
            self.assertEqual(data["high_level_description"], "Pippin playing in the forest")
            self.assertEqual(data["compositional_deconstruction"]["background"], "detailed forest background")

    @patch("urllib.request.urlopen")
    def test_prompt_enhancer_caching(self, mock_urlopen):
        # Enable caching in config
        self.global_cfg["prompt_enhancer"]["cache_prompts"] = True
        
        mock_response_data = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "high_level_description": "Cached scene",
                        "style_description": {
                            "aesthetics": "style", "lighting": "light", "medium": "med", "art_style": "art",
                            "color_palette": []
                        },
                        "compositional_deconstruction": {
                            "background": "bg",
                            "elements": [{"type": "obj", "bbox": [0,0,10,10], "desc": "el"}]
                        }
                    })
                }
            }]
        }
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
            # First call should invoke the API
            enhanced_first = enhance_scene_prompt(
                prompt_text="Forest",
                global_style="Style",
                characters_present=[],
                characters_cfg={},
                global_cfg=self.global_cfg,
                output_dir=self.output_dir,
                filename_prefix="cache_test"
            )
            self.assertIsNotNone(enhanced_first)
            self.assertEqual(mock_urlopen.call_count, 1)

            # Second call should read from cache and NOT call the API
            enhanced_second = enhance_scene_prompt(
                prompt_text="Forest",
                global_style="Style",
                characters_present=[],
                characters_cfg={},
                global_cfg=self.global_cfg,
                output_dir=self.output_dir,
                filename_prefix="cache_test"
            )
            self.assertEqual(enhanced_first, enhanced_second)
            self.assertEqual(mock_urlopen.call_count, 1) # Still 1 because it loaded from cache

    @patch("urllib.request.urlopen")
    def test_prompt_enhancer_fallback_on_api_error(self, mock_urlopen):
        # Setup mock to raise HTTPError (rate limit or similar)
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://mock", code=429, msg="Too Many Requests", hdrs={}, fp=None
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test_key"}):
            enhanced = enhance_scene_prompt(
                prompt_text="Forest",
                global_style="Style",
                characters_present=[],
                characters_cfg={},
                global_cfg=self.global_cfg,
                output_dir=self.output_dir,
                filename_prefix="fallback_test"
            )
            # Should return None, triggering template fallback in ideogram_generator.py
            self.assertIsNone(enhanced)

if __name__ == "__main__":
    unittest.main()
