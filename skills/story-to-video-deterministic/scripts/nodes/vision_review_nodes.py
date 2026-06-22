"""Vision review FunctionNodes - audit-mode (non-blocking) LLM-as-judge reviewers.

These run as Wave-1 per-shot nodes AFTER both FF and LF consistency patches have
completed. Each node encodes the relevant images as data URLs, calls MiniMax M3
via the OpenAI multimodal API, extracts structured JSON, and writes:

- A standalone review JSON file in <output_dir>/ff_vision_reviews/<shot_id>.json
  (or lf_vision_reviews/...).
- A summary entry back into prompts.json under ff_vision_reviews[shot_id] (or
  lf_vision_reviews[shot_id]).

CRITICAL: These nodes NEVER raise on review failures. The Wave continues to the
video phase regardless of review verdicts. Problems are surfaced as JSON entries
so the user (or a future repair-loop) can inspect them later and decide whether
to retry. This is the audit-mode phase described in the Option B plan.
"""
import os
import json
import re
import base64
from typing import Any

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from .wave_executor_workflow import (
    _resolve_ref,
    _load_prompts,
    _save_prompts_locked,
)


# Model name for the vision reviewer. MiniMax M3 has multimodal input capability.
_VISION_MODEL = "MiniMax-M3"

# Cap on image file size we encode as data URL (avoid blowing through request size).
_MAX_IMAGE_BYTES = 6 * 1024 * 1024


def _encode_image_data_url(path: str) -> str | None:
    """Return a base64 data-URL for the image at path, or None if missing /
    oversized / unsupported extension."""
    if not path or not isinstance(path, str):
        return None
    if not os.path.exists(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(ext)
    if not mime:
        return None
    try:
        if os.path.getsize(path) > _MAX_IMAGE_BYTES:
            return None
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except OSError:
        return None


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _extract_json_from_response(content: str) -> dict | None:
    """Extract a JSON object from the LLM response. MiniMax M3 wraps chain-of-
    thought in a think tag. We strip that, then take the substring between the
    first { and the last }."""
    if not content:
        return None
    stripped = _THINK_BLOCK.sub("", content).strip()
    # Strip markdown code fence if present.
    if stripped.startswith("```"):
        stripped = stripped.lstrip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        stripped = stripped.strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(stripped[start:end + 1])
    except json.JSONDecodeError:
        return None


def _get_minimax_client():
    """Build an OpenAI-compatible client pointed at the MiniMax API.

    Lazy-imported so the wave workflow module can be imported without the
    openai package being a hard dependency.
    """
    import sys
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if here not in sys.path:
        sys.path.insert(0, here)
    from config import MINIMAX_API_KEY  # type: ignore
    if not MINIMAX_API_KEY:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(
        api_key=MINIMAX_API_KEY,
        base_url="https://api.minimax.io/v1",
        timeout=120.0,
        max_retries=1,
    )


def _call_vision_review(images_with_captions: list[tuple[str, str]], prompt_text: str) -> str | None:
    """Make a multimodal ChatCompletion call to MiniMax M3 with the given images
    (each tagged with a short caption to ground the model on what it is seeing)
    and return the raw text response. Returns None on any error."""
    client = _get_minimax_client()
    if client is None:
        return None
    content_parts: list[dict[str, Any]] = []
    for caption, data_url in images_with_captions:
        if not data_url:
            continue
        content_parts.append({"type": "text", "text": f"[IMAGE: {caption}]"})
        content_parts.append({"type": "image_url", "image_url": {"url": data_url}})
    content_parts.append({"type": "text", "text": prompt_text})
    if not any(p["type"] == "image_url" for p in content_parts):
        return None
    try:
        resp = client.chat.completions.create(
            model=_VISION_MODEL,
            messages=[{"role": "user", "content": content_parts}],
            max_tokens=600,
        )
        return resp.choices[0].message.content
    except Exception:  # noqa: BLE001
        return None


_REVIEW_RESULT_SCHEMA_HINT = (
    "Return ONLY a JSON object with this exact schema (no markdown, no prose):\n"
    "{\n"
    '  "pass": true | false,\n'
    '  "score": 0.0-1.0,\n'
    '  "frame_analyzed": "<which frame you reviewed: raw_ff | patched_ff | raw_lf | patched_lf>",\n'
    '  "characters": [\n'
    '    {\n'
    '      "character_id": "<id>",\n'
    '      "visible": true | false,\n'
    '      "identity_match": 0.0-1.0,\n'
    '      "pose_preserved": true | false,\n'
    '      "problems": ["short problem description", ...]\n'
    '    }\n'
    '  ],\n'
    '  "recommended_action": "continue" | "repair_patch" | "manual_review",\n'
    '  "notes": "brief summary"\n'
    "}\n"
)


# ----- FF Vision Review -----

async def _run_ff_vision_review(ctx: Context, shot_id: str, output_dir: str) -> None:
    """Audit-mode vision review of the FF pair: char sheets + raw FF + patched FF.

    Compares the Flux Klein-patched FF against the raw FF + each character sheet.
    Writes ff_vision_reviews/<shot_id>.json + a summary entry in prompts.json.
    Never raises; on any failure, writes a review_skipped entry and continues.
    """
    try:
        prompts = _load_prompts(output_dir)
    except Exception as e:  # noqa: BLE001
        print(f"   [ff_review:{shot_id}] Could not load prompts.json: {e}")
        return

    existing = (prompts.get("ff_vision_reviews", {}) or {}).get(shot_id) or {}
    if existing.get("status") in ("reviewed", "review_failed", "review_skipped"):
        print(f"   [ff_review:{shot_id}] Already has {existing.get('status')}; skipping.", flush=True)
        return

    cp_entry = prompts.get("consistency_patches", {}).get(shot_id) or {}
    if cp_entry.get("status") == "skipped" or not cp_entry.get("prompt"):
        # No FF consistency patch to review (establishing shot or continuation); skip.
        return
    ff_entry = prompts.get("ff_shots", {}).get(shot_id) or {}
    ff_path = ff_entry.get("output_path")
    patched_ff_path = cp_entry.get("output_path")
    if not ff_path or not patched_ff_path:
        print(f"   [ff_review:{shot_id}] FF or patch output_path empty; skipping review.")
        return

    # Resolve char_sheets included in this consistency patch.
    refs = cp_entry.get("reference_images") or []
    char_sheet_paths: list[tuple[str, str]] = []
    for i, ref in enumerate(refs, start=1):
        try:
            resolved = _resolve_ref(ref, prompts)
            char_sheet_paths.append((f"char_sheet_{i}", resolved))
        except KeyError:
            pass  # Reference not resolvable; skip silently.

    images_to_review: list[tuple[str, str]] = []
    for caption, path in char_sheet_paths:
        data_url = _encode_image_data_url(path)
        if data_url:
            images_to_review.append((caption, data_url))
    raw_ff_data = _encode_image_data_url(ff_path)
    if raw_ff_data:
        images_to_review.append(("raw_ff", raw_ff_data))
    patched_data = _encode_image_data_url(patched_ff_path)
    if patched_data:
        images_to_review.append(("patched_ff", patched_data))

    if not images_to_review or not patched_data:
        # Nothing to compare against (file missing / too large).
        review = {
            "pass_status": False,
            "score": None,
            "frame_analyzed": "patched_ff",
            "characters": [],
            "recommended_action": "skip",
            "notes": "Missing or oversized image for review (raw FF / patched FF / char sheets).",
            "status": "review_skipped",
        }
        prompts.setdefault("ff_vision_reviews", {})[shot_id] = review
        await _save_prompts_locked(output_dir, prompts)
        print(f"   [ff_review:{shot_id}] Skipped (missing image inputs).")
        return

    prompt_text = (
        "You are reviewing a character consistency patch on a first-frame image for a "
        "story-to-video pipeline. The character sheet images show the reference identity "
        "to apply (face texture, fur color, body proportions, clothing). The raw_ff image "
        "is the unedited Ideogram 4 T2I scene. The patched_ff image is the Flux Klein 9B "
        "edit that should have applied each char sheet's identity to the corresponding "
        "on-screen character.\n\n"
        "For each character sheet provided, evaluate:\n"
        "- visible: is that character visible in the patched_ff image?\n"
        "- identity_match (0.0-1.0): how closely the patched on-screen character matches "
        "  the corresponding char sheet's face texture, fur/skin color, body proportions, "
        "  and clothing. 1.0 = perfect match, 0.5 = identity partially swapped, 0.0 = no match.\n"
        "- pose_preserved: did the Flux patch preserve the original pose/expression from "
        "  raw_ff, or did it overwrite the pose with the character sheet's neutral pose?\n"
        "- problems: short strings describing specific failures.\n\n"
        "Set 'pass' to true if EVERY character has identity_match >= 0.7 and pose_preserved "
        "is true. Set 'recommended_action' to 'repair_patch' if identity_match < 0.5 for any "
        "character (Flux lost the identity), 'manual_review' if identities appear swapped "
        "between characters, or 'continue' if all good.\n\n"
        f"{_REVIEW_RESULT_SCHEMA_HINT}"
    )

    print(
        f"   [ff_review:{shot_id}] Reviewing patched FF with MiniMax M3 "
        f"({len(images_to_review)} image inputs)...",
        flush=True,
    )
    raw_response = _call_vision_review(images_to_review, prompt_text)
    review = _build_review_entry(raw_response, frame_analyzed="patched_ff")
    review.setdefault("status", "reviewed")

    # Write standalone JSON file.
    review_dir = os.path.join(output_dir, "ff_vision_reviews")
    os.makedirs(review_dir, exist_ok=True)
    with open(os.path.join(review_dir, f"{shot_id}.json"), "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)

    # Update prompts.json with the summary entry.
    prompts.setdefault("ff_vision_reviews", {})[shot_id] = review
    await _save_prompts_locked(output_dir, prompts)
    verdict = "PASS" if review.get("pass_status") else "FAIL"
    print(f"   [ff_review:{shot_id}] {verdict} (score={review.get('score')!r}).", flush=True)


# ----- LF Vision Review -----

async def _run_lf_vision_review(ctx: Context, shot_id: str, output_dir: str) -> None:
    """Audit-mode vision review of the LF pair: char sheets + raw LF + patched LF.

    Compares the Flux Klein-patched LF against the raw LF + each character sheet.
    Also checks that the LF delta (pose/expression/motion) survived the patch.
    Writes lf_vision_reviews/<shot_id>.json + a summary entry in prompts.json.
    Never raises.
    """
    try:
        prompts = _load_prompts(output_dir)
    except Exception as e:  # noqa: BLE001
        print(f"   [lf_review:{shot_id}] Could not load prompts.json: {e}")
        return

    existing = (prompts.get("lf_vision_reviews", {}) or {}).get(shot_id) or {}
    if existing.get("status") in ("reviewed", "review_failed", "review_skipped"):
        print(f"   [lf_review:{shot_id}] Already has {existing.get('status')}; skipping.", flush=True)
        return

    lf_cp_entry = prompts.get("lf_consistency_patches", {}).get(shot_id) or {}
    if lf_cp_entry.get("status") == "skipped" or not lf_cp_entry.get("prompt"):
        return  # No LF consistency patch for this shot.
    lf_entry = prompts.get("lf_shots", {}).get(shot_id) or {}
    lf_path = lf_entry.get("output_path")
    patched_lf_path = lf_cp_entry.get("output_path")
    if not lf_path or not patched_lf_path:
        print(f"   [lf_review:{shot_id}] LF or patch output_path empty; skipping review.")
        return

    refs = lf_cp_entry.get("reference_images") or []
    char_sheet_paths: list[tuple[str, str]] = []
    for i, ref in enumerate(refs, start=1):
        try:
            resolved = _resolve_ref(ref, prompts)
            char_sheet_paths.append((f"char_sheet_{i}", resolved))
        except KeyError:
            pass

    images_to_review: list[tuple[str, str]] = []
    for caption, path in char_sheet_paths:
        data_url = _encode_image_data_url(path)
        if data_url:
            images_to_review.append((caption, data_url))
    raw_lf_data = _encode_image_data_url(lf_path)
    if raw_lf_data:
        images_to_review.append(("raw_lf", raw_lf_data))
    patched_data = _encode_image_data_url(patched_lf_path)
    if patched_data:
        images_to_review.append(("patched_lf", patched_data))

    if not images_to_review or not patched_data:
        review = {
            "pass_status": False,
            "score": None,
            "frame_analyzed": "patched_lf",
            "characters": [],
            "recommended_action": "skip",
            "notes": "Missing or oversized image for LF review.",
            "status": "review_skipped",
        }
        prompts.setdefault("lf_vision_reviews", {})[shot_id] = review
        await _save_prompts_locked(output_dir, prompts)
        print(f"   [lf_review:{shot_id}] Skipped (missing image inputs).")
        return

    prompt_text = (
        "You are reviewing a character consistency patch on a LAST-frame image for a "
        "story-to-video pipeline. The LF image is the END STATE of a shot's motion (a "
        "character has moved / expression changed / camera has shifted). The character "
        "sheet images show the reference identity to apply. The raw_lf image is the "
        "unedited Ideogram 4 T2I scene. The patched_lf image is the Flux Klein 9B edit "
        "that should have applied each char sheet's identity WITHOUT erasing the LF delta.\n\n"
        "For each character sheet provided, evaluate:\n"
        "- visible: is that character visible in the patched_lf image?\n"
        "- identity_match (0.0-1.0): how closely the patched character matches the sheet's "
        "  face texture, fur/skin color, body proportions, and clothing.\n"
        "- pose_preserved: did the Flux patch PRESERVE the LF's delta pose / expression / "
        "  gaze shift, or did it revert the character back to the character sheet's neutral "
        "  pose (collapsing the video's motion)? This is the critical test for LF patches.\n"
        "- problems: short strings describing specific failures (e.g. 'pose reverted to "
        "  neutral', 'identity not applied', 'identity swapped with adjacent character').\n\n"
        "Set 'pass' to true if EVERY character has identity_match >= 0.7 AND pose_preserved "
        "is true (LF delta intact). Set 'recommended_action' to 'repair_patch' if "
        "identity_match < 0.5 for any character, 'manual_review' if pose seems reverted "
        "(LF delta lost), or 'continue' if all good.\n\n"
        f"{_REVIEW_RESULT_SCHEMA_HINT}"
    )

    print(
        f"   [lf_review:{shot_id}] Reviewing patched LF with MiniMax M3 "
        f"({len(images_to_review)} image inputs)...",
        flush=True,
    )
    raw_response = _call_vision_review(images_to_review, prompt_text)
    review = _build_review_entry(raw_response, frame_analyzed="patched_lf")
    review.setdefault("status", "reviewed")

    review_dir = os.path.join(output_dir, "lf_vision_reviews")
    os.makedirs(review_dir, exist_ok=True)
    with open(os.path.join(review_dir, f"{shot_id}.json"), "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2, ensure_ascii=False)

    prompts.setdefault("lf_vision_reviews", {})[shot_id] = review
    await _save_prompts_locked(output_dir, prompts)
    verdict = "PASS" if review.get("pass_status") else "FAIL"
    print(f"   [lf_review:{shot_id}] {verdict} (score={review.get('score')!r}).", flush=True)


def _build_review_entry(raw_response: str | None, frame_analyzed: str) -> dict[str, Any]:
    """Normalize the LLM JSON response into the VisionReviewEntry-shaped dict
    written to disk. On parse failure, return a 'review_failed' entry rather
    than raising, so the Wave continues."""
    if raw_response is None:
        return {
            "pass_status": False,
            "score": None,
            "frame_analyzed": frame_analyzed,
            "characters": [],
            "recommended_action": "skip",
            "notes": "Vision client unavailable (no api key, model call failed, etc.).",
            "status": "review_skipped",
        }
    parsed = _extract_json_from_response(raw_response)
    if not parsed:
        return {
            "pass_status": False,
            "score": None,
            "frame_analyzed": frame_analyzed,
            "characters": [],
            "recommended_action": "manual_review",
            "notes": f"Could not parse LLM JSON response. Raw text: {raw_response[:200]!r}",
            "status": "review_failed",
        }
    # Map LLM field names to schema field names (LLM emitting "pass" becomes "pass_status").
    return {
        "pass_status": bool(parsed.get("pass", False)),
        "score": parsed.get("score"),
        "frame_analyzed": parsed.get("frame_analyzed") or frame_analyzed,
        "characters": parsed.get("characters") or [],
        "recommended_action": parsed.get("recommended_action") or "continue",
        "notes": parsed.get("notes"),
        "status": "reviewed",
    }
