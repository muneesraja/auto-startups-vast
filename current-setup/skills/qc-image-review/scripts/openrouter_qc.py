#!/usr/bin/env python3
"""
openrouter_qc.py — Binary pass/fail QC for AI-generated stills via OpenRouter.

Uses Gemini 3.1 Flash Lite for cheap, fast, validated likeness scoring.
Per-gate image budget enforcement. Strict JSON output.

Usage:
    python3 openrouter_qc.py \
        --images shot05_ff.png chomp_neutral_sheet.png \
        --gate ff_gate \
        --shot-id shot05 \
        --characters chomp \
        --ff-prompt "A gray wolf cub..." \
        --reference-description "Chomp: gray wolf cub, amber eyes, white chest patch" \
        --output qc_result.json

Environment:
    OPENROUTER_API_KEY must be set in ~/.hermes/.env
"""
import argparse
import base64
import io
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. pip install requests")
    sys.exit(1)

# Per-gate image budget enforcement
GATE_BUDGET = {
    "ff_gate": 2,
    "lf_gate": 3,
    "motion_eval": 5,  # v2.1, deferred
}

# OpenRouter config
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3.1-flash-lite"

# Pass thresholds
PASS_THRESHOLDS = {
    "character_likeness": 7.0,
    "style_match": 7.0,
}

# Frozen-shot threshold: if FF and LF are this similar, the I2I edit had no effect
FROZEN_THRESHOLD = 0.02


def compute_continuity_delta(ff_path: str, lf_path: str) -> float:
    """
    Compute visual difference between FF and LF.
    Returns a value in [0, 1]:
    - 0.0 = identical (frozen shot — FAIL)
    - 1.0 = very different (good — pass)

    Uses SSIM (structural similarity) if scikit-image is available,
    else falls back to normalized L1 pixel difference. Both implementations
    are bounded to [0, 1].
    """
    try:
        from skimage.metrics import structural_similarity as ssim
        from PIL import Image
        import numpy as np

        ff = np.array(Image.open(ff_path).convert("L").resize((256, 256)))
        lf = np.array(Image.open(lf_path).convert("L").resize((256, 256)))

        similarity = ssim(ff, lf)
        delta = 1.0 - similarity  # 0 = identical, 1 = different
        return max(0.0, min(1.0, float(delta)))
    except ImportError:
        # Fallback: normalized L1 pixel difference
        from PIL import Image
        import numpy as np

        ff = np.array(Image.open(ff_path).convert("L").resize((256, 256)))
        lf = np.array(Image.open(lf_path).convert("L").resize((256, 256)))

        l1_diff = np.abs(ff.astype(float) - lf.astype(float)).mean() / 255.0
        return max(0.0, min(1.0, float(l1_diff)))

REVIEW_PROMPT_TEMPLATE = """You are a quality control reviewer for AI-generated film stills.

Compare the generated image (Image 1) against the provided character reference sheet(s) and determine if the character matches.

For each image, evaluate:
1. CHARACTER_LIKENESS (0-10): Does the character's appearance match the reference sheet? Check proportions, colors, features.
2. STYLE_MATCH (0-10): Does the visual style match? (3D Pixar, chibi, realistic, etc.)
3. EXPRESSION_NEUTRALITY (0-10, reference sheets only): Is the expression neutral/calm? (Not applicable for scene stills - use N/A)

Reference sheets:
{reference_descriptions}

Generated image context:
- Shot: {shot_id}
- First Frame prompt: {ff_prompt}
- Last Frame prompt: {lf_prompt}
- Characters expected: {characters}
- Gate: {gate}

Respond in JSON:
{{
  "character_likeness": <0-10>,
  "style_match": <0-10>,
  "expression_neutrality": <0-10 or "N/A">,
  "overall_score": <0-10>,
  "pass": <true/false>,
  "rejection_reason": "<string, only if pass=false>",
  "specific_issues": ["<issue1>", "<issue2>"]
}}"""


def load_env():
    """Load OPENROUTER_API_KEY from ~/.hermes/.env if not already set."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return
    env_file = Path.home() / ".hermes" / ".env"
    if not env_file.exists():
        print(f"ERROR: {env_file} not found")
        sys.exit(1)
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("\"").strip("'")
            if key == "OPENROUTER_API_KEY" and not os.environ.get(key):
                os.environ[key] = val


def encode_image_jpeg(path: str) -> str:
    """Read image, compress to JPEG q=85, return base64 data URL."""
    try:
        from PIL import Image
        img = Image.open(path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except ImportError:
        # No PIL, fall back to raw file as-is
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:image/png;base64,{b64}"


def review_image(
    image_paths: list,
    shot_id: str,
    gate: str,
    characters: list,
    ff_prompt: str = "",
    lf_prompt: str = "",
    reference_description: str = "",
    api_key: str = None,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
) -> dict:
    """
    Run binary pass/fail QC on an image set.

    Returns:
        JSON dict with pass/fail verdict
    """
    # Enforce per-gate image budget
    budget = GATE_BUDGET.get(gate, 2)
    if len(image_paths) > budget:
        print(f"WARN: {gate} budget is {budget}, using first {budget} of {len(image_paths)} images")
        image_paths = image_paths[:budget]

    # Build the prompt
    prompt = REVIEW_PROMPT_TEMPLATE.format(
        reference_descriptions=reference_description or "No reference description provided",
        shot_id=shot_id,
        ff_prompt=ff_prompt or "(not provided)",
        lf_prompt=lf_prompt or "(not provided)",
        characters=", ".join(characters) if characters else "(none)",
        gate=gate,
    )

    # Build the message content
    content = [{"type": "text", "text": prompt}]
    for path in image_paths:
        data_url = encode_image_jpeg(path)
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url}
        })

    # Dry-run mode: print payload, don't call API
    if dry_run:
        return {
            "dry_run": True,
            "gate": gate,
            "shot_id": shot_id,
            "image_count": len(image_paths),
            "model": model,
            "pass": None,
            "message": "Dry run - no API call made",
        }

    # Call OpenRouter
    api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "gate": gate,
            "shot_id": shot_id,
            "pass": False,
            "rejection_reason": "OPENROUTER_API_KEY not set",
            "specific_issues": ["API key missing"],
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    try:
        resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()
        # Extract the assistant message
        assistant_msg = result["choices"][0]["message"]["content"]
        # Try to parse as JSON
        try:
            verdict = json.loads(assistant_msg)
        except json.JSONDecodeError:
            # Try to extract JSON from prose
            #
            # Old (greedy) regex matched from first `{` to LAST `}` — broken
            # when the model outputs prose with braces before the JSON.
            #
            # New strategy: find all brace-delimited spans (1 level of nesting),
            # try parsing each as JSON, return the LAST one that succeeds.
            # This handles "{my note} The verdict: {\"pass\": true}" correctly.
            import re
            candidates = re.findall(
                r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
                assistant_msg,
            )
            verdict = None
            for candidate in reversed(candidates):
                try:
                    verdict = json.loads(candidate)
                    break
                except (json.JSONDecodeError, ValueError):
                    continue
            if verdict is None:
                return {
                    "gate": gate,
                    "shot_id": shot_id,
                    "pass": False,
                    "rejection_reason": "Could not parse QC verdict as JSON",
                    "raw_response": assistant_msg,
                }

        # Apply gate-specific pass/fail logic
        char_likeness = verdict.get("character_likeness", 0)
        style_match = verdict.get("style_match", 0)
        base_pass = (
            char_likeness >= PASS_THRESHOLDS["character_likeness"]
            and style_match >= PASS_THRESHOLDS["style_match"]
        )

        if gate == "ff_gate":
            verdict["pass"] = base_pass
            if not base_pass and not verdict.get("rejection_reason"):
                verdict["rejection_reason"] = (
                    f"FF gate failed: character_likeness {char_likeness} < "
                    f"{PASS_THRESHOLDS['character_likeness']} or style_match {style_match} < "
                    f"{PASS_THRESHOLDS['style_match']}"
                )

        elif gate == "lf_gate":
            # LF gate: also check that LF is different from FF (not a frozen shot)
            # Image order: [LF, FF, ...optional ref]
            is_frozen = False
            continuity_delta = None
            if len(image_paths) >= 2:
                lf_path, ff_path = image_paths[0], image_paths[1]
                try:
                    continuity_delta = compute_continuity_delta(ff_path, lf_path)
                    verdict["continuity_delta"] = continuity_delta
                    is_frozen = continuity_delta < FROZEN_THRESHOLD
                except Exception as e:
                    verdict["continuity_delta_error"] = str(e)
                    # If we can't compute delta, fall back to a "fail open" stance
                    # (don't fail the LF gate just because we can't compute delta)
                    is_frozen = False

            verdict["pass"] = base_pass and not is_frozen
            if is_frozen:
                verdict["rejection_reason"] = (
                    f"FROZEN SHOT: continuity_delta {continuity_delta:.4f} < "
                    f"{FROZEN_THRESHOLD} — LF is visually identical to FF. "
                    f"The I2I edit had no visible effect. Director should redesign "
                    f"the LF to have a visible pose delta (head turn, expression "
                    f"change, body lean, etc.)."
                )
            elif not base_pass and not verdict.get("rejection_reason"):
                verdict["rejection_reason"] = (
                    f"LF gate failed: character_likeness {char_likeness} < "
                    f"{PASS_THRESHOLDS['character_likeness']} or style_match {style_match} < "
                    f"{PASS_THRESHOLDS['style_match']}"
                )

        elif gate == "motion_eval":
            # v2.1, not fully implemented in v0.1
            verdict["pass"] = base_pass
            if not base_pass and not verdict.get("rejection_reason"):
                verdict["rejection_reason"] = (
                    f"Motion eval gate failed: character_likeness {char_likeness} < "
                    f"{PASS_THRESHOLDS['character_likeness']} or style_match {style_match} < "
                    f"{PASS_THRESHOLDS['style_match']}"
                )

        else:
            # Unknown gate — fall back to base check
            verdict["pass"] = base_pass

        verdict["gate"] = gate
        verdict["shot_id"] = shot_id
        verdict["image_budget_used"] = len(image_paths)
        return verdict

    except requests.exceptions.RequestException as e:
        return {
            "gate": gate,
            "shot_id": shot_id,
            "pass": False,
            "rejection_reason": f"OpenRouter API error: {e}",
            "specific_issues": ["API call failed"],
        }


def main():
    parser = argparse.ArgumentParser(description="Binary QC via OpenRouter Gemini Flash Lite")
    parser.add_argument("--images", nargs="+", required=True, help="Image paths")
    parser.add_argument("--gate", choices=["ff_gate", "lf_gate", "motion_eval"], required=True)
    parser.add_argument("--shot-id", required=True)
    parser.add_argument("--characters", nargs="+", default=[])
    parser.add_argument("--ff-prompt", default="")
    parser.add_argument("--lf-prompt", default="")
    parser.add_argument("--reference-description", default="")
    parser.add_argument("--output", help="Write result to JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Don't call API, just print payload")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    load_env()

    result = review_image(
        image_paths=args.images,
        shot_id=args.shot_id,
        gate=args.gate,
        characters=args.characters,
        ff_prompt=args.ff_prompt,
        lf_prompt=args.lf_prompt,
        reference_description=args.reference_description,
        model=args.model,
        dry_run=args.dry_run,
    )

    result_json = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w") as f:
            f.write(result_json)
        print(f"Wrote {args.output}")
    else:
        print(result_json)

    # Exit code: 0 if pass, 1 if fail, 2 if dry-run
    if args.dry_run:
        sys.exit(2)
    sys.exit(0 if result.get("pass") else 1)


if __name__ == "__main__":
    main()
