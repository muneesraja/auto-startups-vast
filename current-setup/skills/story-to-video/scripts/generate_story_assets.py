#!/usr/bin/env python3
"""
Story-to-Video Asset Generator
===============================
Generates character reference sheets and scene illustrations using the Gemini API.
Designed to be invoked by the Hermes agent as part of the story-to-video skill.

Usage:
    python3 generate_story_assets.py \
        --manifest /root/story/<title>/story_manifest.json \
        --phase <characters|scenes|all> \
        [--max-refs 5] \
        [--force]

API Key: Read from /root/config/token.json → "gemini_api_key"
"""

import argparse
import json
import sys
import time
import io
from pathlib import Path
from typing import Optional

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai package not installed.")
    print("Install with: pip install google-genai")
    sys.exit(1)

try:
    from PIL import Image as PILImage
except ImportError:
    print("ERROR: Pillow package not installed.")
    print("Install with: pip install Pillow")
    sys.exit(1)


# ─── Configuration ────────────────────────────────────────────────────────────

TOKEN_PATH = Path("/root/config/token.json")
DEFAULT_MAX_REFS = 5
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds

# Gemini model for native image generation
IMAGE_MODEL = "gemini-2.5-flash-image"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_api_key(token_path: Optional[str] = None) -> str:
    """Load Gemini API key from token JSON file."""
    path = Path(token_path) if token_path else TOKEN_PATH
    if not path.exists():
        print(f"ERROR: Token file not found at {path}")
        sys.exit(1)
    with open(path) as f:
        config = json.load(f)
    key = config.get("gemini_api_key", "")
    if not key:
        print(f"ERROR: 'gemini_api_key' not found in {path}")
        sys.exit(1)
    return key


def load_manifest(path: str) -> dict:
    """Load and validate the story manifest JSON."""
    manifest_path = Path(path)
    if not manifest_path.exists():
        print(f"ERROR: Manifest not found at {manifest_path}")
        sys.exit(1)
    with open(manifest_path) as f:
        manifest = json.load(f)
    # Basic validation
    required = ["title", "style", "characters", "scenes"]
    for field in required:
        if field not in manifest:
            print(f"ERROR: Manifest missing required field: '{field}'")
            sys.exit(1)
    return manifest


def get_output_dir(manifest_path: str) -> Path:
    """Derive output directory from manifest location."""
    return Path(manifest_path).parent


def find_character(manifest: dict, char_id: str) -> Optional[dict]:
    """Find a character by ID in the manifest."""
    for char in manifest["characters"]:
        if char["id"] == char_id:
            return char
    return None


def load_image_as_part(image_path: Path) -> types.Part:
    """Load an image file and return it as a Gemini API Part."""
    img = PILImage.open(image_path)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return types.Part.from_bytes(data=buf.getvalue(), mime_type="image/png")


def save_image_from_response(response, output_path: Path) -> bool:
    """Extract image from Gemini response and save to disk."""
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(part.inline_data.data)
                return True
    return False


def call_gemini_with_retry(client, contents, config, max_retries=MAX_RETRIES) -> object:
    """Call Gemini API with exponential backoff retry."""
    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=contents,
                config=config,
            )
            return response
        except Exception as e:
            if attempt == max_retries:
                print(f"  ERROR: Failed after {max_retries} attempts: {e}")
                raise
            wait = RETRY_BACKOFF_BASE ** attempt
            print(f"  Attempt {attempt}/{max_retries} failed: {e}")
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)


# ─── Phase: Characters ────────────────────────────────────────────────────────

def generate_character_sheets(client, manifest: dict, output_dir: Path, force: bool = False):
    """Generate character reference sheets for all characters in the manifest."""
    characters_dir = output_dir / "characters"
    characters_dir.mkdir(parents=True, exist_ok=True)

    style = manifest["style"]
    total = len(manifest["characters"])

    print(f"\n{'='*60}")
    print(f"  Phase: Character Reference Sheets")
    print(f"  Characters: {total}")
    print(f"  Style: {style}")
    print(f"  Output: {characters_dir}")
    print(f"{'='*60}\n")

    for i, char in enumerate(manifest["characters"], 1):
        char_id = char["id"]
        output_path = characters_dir / f"{char_id}_reference_sheet.png"

        if output_path.exists() and not force:
            print(f"[{i}/{total}] {char['name']} — already exists, skipping (use --force to regenerate)")
            continue

        print(f"[{i}/{total}] Generating reference sheet for {char['name']}...")

        prompt = f"""Create a professional character reference sheet for the following character.

Character: {char['identity_spec']}

Layout:
- Top row: four full-body standing views (front, left 3/4 view, right side profile, back view)
- Bottom row: three face close-up portraits (front, left 3/4 angle, right side profile)

Requirements:
- CONSISTENT identity across ALL seven views — same face, same body, same outfit
- Clean white/neutral background
- Even studio lighting
- Style: {style}
- Each view clearly separated with space between them
- Character should be the same scale/proportion in each view"""

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        )

        try:
            response = call_gemini_with_retry(client, prompt, config)
            if save_image_from_response(response, output_path):
                print(f"  ✅ Saved: {output_path}")
            else:
                print(f"  ❌ No image in response for {char['name']}")
        except Exception as e:
            print(f"  ❌ Failed to generate {char['name']}: {e}")
            continue

    print(f"\n✅ Character sheet generation complete.")
    print(f"   Output: {characters_dir}")


# ─── Phase: Scenes ────────────────────────────────────────────────────────────

def generate_scenes(client, manifest: dict, output_dir: Path, max_refs: int = DEFAULT_MAX_REFS, force: bool = False):
    """Generate scene illustrations with smart per-scene reference selection."""
    scenes_dir = output_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    characters_dir = output_dir / "characters"

    style = manifest["style"]
    total = len(manifest["scenes"])

    print(f"\n{'='*60}")
    print(f"  Phase: Scene Illustration")
    print(f"  Scenes: {total}")
    print(f"  Max references per scene: {max_refs}")
    print(f"  Style: {style}")
    print(f"  Output: {scenes_dir}")
    print(f"{'='*60}\n")

    for scene in manifest["scenes"]:
        scene_num = scene["scene_number"]
        scene_file = scenes_dir / f"scene_{scene_num:03d}.png"

        if scene_file.exists() and not force:
            print(f"[Scene {scene_num}/{total}] \"{scene['title']}\" — already exists, skipping")
            continue

        print(f"[Scene {scene_num}/{total}] \"{scene['title']}\"")

        # ── Smart Reference Selection ──
        # Only load reference sheets for characters present in THIS scene
        # Respect the max_refs limit
        reference_parts = []
        ref_chars = []
        for char_id in scene["characters_present"]:
            if len(reference_parts) >= max_refs:
                print(f"  ⚠️  Hit max refs ({max_refs}), remaining characters text-only")
                break
            ref_path = characters_dir / f"{char_id}_reference_sheet.png"
            if ref_path.exists():
                reference_parts.append(load_image_as_part(ref_path))
                ref_chars.append(char_id)
            else:
                print(f"  ⚠️  No reference sheet for '{char_id}' — using text-only")

        print(f"  References attached: {ref_chars} ({len(reference_parts)} images)")

        # ── Build Identity Block ──
        identity_lines = []
        for char_id in scene["characters_present"]:
            char = find_character(manifest, char_id)
            if char:
                marker = "📎" if char_id in ref_chars else "📝"
                identity_lines.append(f"- {char['name']}: {char['identity_spec']} {marker}")

        # ── Build Scene Prompt ──
        prompt_text = f"""Characters in this scene (match EXACTLY to the reference images provided):
{chr(10).join(identity_lines)}

Scene setting: {scene['setting']}
Action: {scene['action']}
Mood/emotion: {scene['emotion']}
Camera framing: {scene['camera']}
Art style: {style}

IMPORTANT: Maintain exact character identity from the provided reference images.
Each character must look identical to their reference sheet — same face, same body, same outfit."""

        # ── Combine references + text prompt ──
        contents = [*reference_parts, prompt_text]

        config = types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        )

        try:
            response = call_gemini_with_retry(client, contents, config)
            if save_image_from_response(response, scene_file):
                print(f"  ✅ Saved: {scene_file}")
            else:
                print(f"  ❌ No image in response for Scene {scene_num}")
        except Exception as e:
            print(f"  ❌ Failed Scene {scene_num}: {e}")
            continue

    print(f"\n✅ Scene generation complete.")
    print(f"   Output: {scenes_dir}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate story assets (character sheets + scene images) via Gemini API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate character reference sheets
  python3 generate_story_assets.py --manifest /root/story/the-great-race/story_manifest.json --phase characters

  # Generate scene illustrations (with smart reference selection)
  python3 generate_story_assets.py --manifest /root/story/the-great-race/story_manifest.json --phase scenes

  # Generate everything
  python3 generate_story_assets.py --manifest /root/story/the-great-race/story_manifest.json --phase all

  # Force regeneration of existing files
  python3 generate_story_assets.py --manifest /root/story/the-great-race/story_manifest.json --phase all --force
        """
    )
    parser.add_argument("--manifest", required=True, help="Path to story_manifest.json")
    parser.add_argument("--phase", required=True, choices=["characters", "scenes", "all"],
                        help="Which phase to run: characters, scenes, or all")
    parser.add_argument("--max-refs", type=int, default=DEFAULT_MAX_REFS,
                        help=f"Max reference images per scene API call (default: {DEFAULT_MAX_REFS})")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate even if output files already exist")
    parser.add_argument("--token", type=str, default=None,
                        help=f"Path to token JSON file (default: {TOKEN_PATH})")
    args = parser.parse_args()

    # Load API key and initialize client
    api_key = load_api_key(args.token)
    client = genai.Client(api_key=api_key)

    # Load manifest
    manifest = load_manifest(args.manifest)
    output_dir = get_output_dir(args.manifest)

    print(f"\n📖 Story: {manifest.get('display_title', manifest['title'])}")
    print(f"🎨 Style: {manifest['style']}")
    print(f"👥 Characters: {len(manifest['characters'])}")
    print(f"🎬 Scenes: {len(manifest['scenes'])}")
    print(f"📁 Output: {output_dir}")

    # Ensure output directories exist
    (output_dir / "characters").mkdir(parents=True, exist_ok=True)
    (output_dir / "scenes").mkdir(parents=True, exist_ok=True)
    (output_dir / "videos").mkdir(parents=True, exist_ok=True)

    # Run requested phase(s)
    if args.phase in ("characters", "all"):
        generate_character_sheets(client, manifest, output_dir, force=args.force)

    if args.phase in ("scenes", "all"):
        generate_scenes(client, manifest, output_dir, max_refs=args.max_refs, force=args.force)

    print(f"\n{'='*60}")
    print(f"  ✅ All done!")
    print(f"  📁 Output: {output_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
