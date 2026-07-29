"""Trimmed config for story-maker-v3.

story-maker-v3 has NO agent framework and NO LiteLLM: Claude Code is the brain
(authors all markdown/JSON, runs validators, does the vision step), Python is the
hands (deterministic media execution). This module therefore carries ONLY the
image-generation + ComfyUI render configuration the Python "hands" need. There
are no model tiers, no LLM factories, no OpenRouter routing here.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - test fallback without python-dotenv
    def load_dotenv(*_args, **_kwargs):
        return False


# ---------------------------------------------------------------------------
# Env loading — same two-layer pattern as skills/story-maker/config.py
# ---------------------------------------------------------------------------

config_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(os.path.dirname(config_dir))  # repo root
# Shared credentials live in the repo root .env. Load first WITHOUT override so
# values exported into the shell by the user win.
_shared_dotenv = os.path.join(workspace_root, ".env")
load_dotenv(_shared_dotenv, override=False)


def _load_project_dotenv() -> str | None:
    """Walk up from CWD looking for a project .env to layer on top.

    The project .env is loaded with override=True so values like COMFYUI_URL in
    the repo take precedence over the shared root .env.
    """
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / ".env"
        if candidate.is_file() and str(candidate) != _shared_dotenv:
            load_dotenv(candidate, override=True)
            return str(candidate)
    return None


_loaded_project_dotenv = _load_project_dotenv()

# ---------------------------------------------------------------------------
# Credentials + ComfyUI
# ---------------------------------------------------------------------------

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
COMFYUI_AUTH = os.getenv("COMFYUI_AUTH")
FAL_KEY = os.getenv("FAL_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

DEFAULT_OUTPUT_BASE_DIR = os.getenv(
    "STORY_MAKER_OUTPUT_DIR",
    os.path.join(workspace_root, "outputs", "story-maker-v3"),
)

# LTX output resolution (must be divisible by 32 for latent math)
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1088"))
# LTX Director Hotfix working resolution (1280x720 is invalid under ÷32)
DIRECTOR_VIDEO_WIDTH = int(os.getenv("DIRECTOR_VIDEO_WIDTH", "1280"))
DIRECTOR_VIDEO_HEIGHT = int(os.getenv("DIRECTOR_VIDEO_HEIGHT", "704"))

# ---------------------------------------------------------------------------
# Image generation config
# ---------------------------------------------------------------------------

DEFAULT_IMAGE_PROVIDER = "replicate"
GROK_REPLICATE_MODEL = os.getenv("GROK_REPLICATE_MODEL", "openai/gpt-image-2")
# Fallback quality when a call does not pass quality= explicitly
REPLICATE_IMAGE_QUALITY = os.getenv("REPLICATE_IMAGE_QUALITY", "low")
# Sheet assets (character + storyboard): medium quality, 2K pixel enums from Replicate
REPLICATE_SHEET_QUALITY = os.getenv("REPLICATE_SHEET_QUALITY", "medium")
# Panel regen / shot stills from storyboard crops: low quality, still 2K landscape
REPLICATE_PANEL_QUALITY = os.getenv("REPLICATE_PANEL_QUALITY", "low")
# Replicate gpt-image-2 `aspect_ratio` accepts ratios OR pixel enums
# (e.g. 2048x1152, 1152x2048). Prefer pixel enums to lock resolution.
CHARACTER_SHEET_SIZE = os.getenv("CHARACTER_SHEET_SIZE", "2048x1152")
BACKGROUND_IMAGE_SIZE = os.getenv("BACKGROUND_IMAGE_SIZE", "3840x2160")
# v3 storyboard sheet = 4 rows x 2 cols, generated on Replicate as a 2160x3840
# album page. Each LTX session still contains 4 panels, laid out as a 2x2 sub-block
# (session 1 = rows 1-2, session 2 = rows 3-4). Each cell is 1080x1920; the per-panel
# upscale step then recomposes each cell to a true 16:9 2048x1152 panel. The portrait
# orientation gives every panel a little more horizontal width than the old 2x4 layout.
STORYBOARD_SHEET_SIZE = os.getenv("STORYBOARD_SHEET_SIZE", "2160x3840")
# Panel crop: python (white-gutter detect → uniform grid) | vision | auto
STORYBOARD_CROP_MODE = os.getenv("STORYBOARD_CROP_MODE", "python")
PANEL_IMAGE_SIZE = os.getenv("PANEL_IMAGE_SIZE", "2048x1152")
COST_REPLICATE_IMAGE = float(os.getenv("COST_REPLICATE_IMAGE", "0.01"))
COST_FAL_IMAGE = float(os.getenv("COST_FAL_IMAGE", "0.04"))
COST_LTX_VIDEO = float(os.getenv("COST_LTX_VIDEO", "0.0"))

# Provider/model reference-image caps (shot still edit / composite)
FAL_GROK_REF_LIMIT = 3
REPLICATE_SEEDREAM_REF_LIMIT = 10
REPLICATE_GPT_IMAGE_REF_LIMIT = 13  # safe cap for Replicate openai/gpt-image-2
REPLICATE_LEGACY_GROK_REF_LIMIT = 1


# ---------------------------------------------------------------------------
# Provider resolvers (image backends only — no LLM routing)
# ---------------------------------------------------------------------------

def get_image_provider() -> str:
    """Default still-image backend for locations / shot stills / panel regen.

    Character sheets use :func:`get_character_sheet_image_provider`.
    Storyboard album sheets use :func:`get_storyboard_image_provider`.
    """
    provider = (os.getenv("PROVIDER") or DEFAULT_IMAGE_PROVIDER).strip().lower()
    if provider not in ("fal", "replicate"):
        raise ValueError(f"Invalid PROVIDER={provider!r}; use 'fal' or 'replicate'")
    if provider == "fal" and not (FAL_KEY or os.environ.get("FAL_KEY")):
        raise ValueError("PROVIDER=fal requires FAL_KEY in .env")
    if provider == "replicate" and not (
        REPLICATE_API_TOKEN or os.environ.get("REPLICATE_API_TOKEN")
    ):
        raise ValueError("PROVIDER=replicate requires REPLICATE_API_TOKEN in .env")
    return provider


def get_storyboard_image_provider() -> str:
    """Backend for storyboard sheet generation only.

    Defaults to ``replicate`` (GPT Image 2) at 2160x3840. Replicate supports this
    portrait pixel enum and keeps storyboard sheets on the same backend as panels.
    """
    raw = (os.getenv("STORYBOARD_IMAGE_PROVIDER") or "replicate").strip().lower()
    if raw not in ("fal", "replicate"):
        raise ValueError(
            f"Invalid STORYBOARD_IMAGE_PROVIDER={raw!r}; use 'fal' or 'replicate'"
        )
    if raw == "fal" and not (FAL_KEY or os.environ.get("FAL_KEY")):
        raise ValueError("STORYBOARD_IMAGE_PROVIDER=fal requires FAL_KEY in .env")
    if raw == "replicate" and not (
        REPLICATE_API_TOKEN or os.environ.get("REPLICATE_API_TOKEN")
    ):
        raise ValueError(
            "STORYBOARD_IMAGE_PROVIDER=replicate requires REPLICATE_API_TOKEN in .env"
        )
    return raw


def get_character_sheet_image_provider() -> str:
    """Backend for character sheet generation.

    Defaults to ``replicate`` (GPT Image 2) at 2048x1152. The 16:9 layout gives
    zoomed-out characters more horizontal space than the old 9:16 portrait sheet.
    Override with ``CHARACTER_SHEET_IMAGE_PROVIDER``. Location plates and panel/shot
    stills stay on :func:`get_image_provider` (Replicate).
    """
    raw = (os.getenv("CHARACTER_SHEET_IMAGE_PROVIDER") or "replicate").strip().lower()
    return _validate_image_backend(raw, label="CHARACTER_SHEET_IMAGE_PROVIDER")


def _validate_image_backend(provider: str, *, label: str) -> str:
    resolved = (provider or "").strip().lower()
    if resolved not in ("fal", "replicate"):
        raise ValueError(f"Invalid {label}={provider!r}; use 'fal' or 'replicate'")
    if resolved == "fal" and not (FAL_KEY or os.environ.get("FAL_KEY")):
        raise ValueError(f"{label}=fal requires FAL_KEY in .env")
    if resolved == "replicate" and not (
        REPLICATE_API_TOKEN or os.environ.get("REPLICATE_API_TOKEN")
    ):
        raise ValueError(f"{label}=replicate requires REPLICATE_API_TOKEN in .env")
    return resolved


def get_panel_image_provider() -> str:
    """Primary backend for panel / shot still regen.

    ``PANEL_IMAGE_PROVIDER`` overrides ``PROVIDER`` (default replicate).
    """
    raw = (os.getenv("PANEL_IMAGE_PROVIDER") or "").strip().lower()
    if raw:
        return _validate_image_backend(raw, label="PANEL_IMAGE_PROVIDER")
    return get_image_provider()


def get_panel_image_fallback_provider() -> str | None:
    """Optional secondary backend after primary panel regen fails.

    Defaults to **off** — fal GPT Image 2 edit+refs for panel volume is
    typically ~3–4× Replicate ``quality=low``. Opt in with
    ``PANEL_IMAGE_FALLBACK_PROVIDER=fal``.
    """
    raw = os.getenv("PANEL_IMAGE_FALLBACK_PROVIDER")
    if raw is None:
        return None
    cleaned = raw.strip().lower()
    if cleaned in ("", "none", "off", "0", "false"):
        return None
    fallback = _validate_image_backend(cleaned, label="PANEL_IMAGE_FALLBACK_PROVIDER")
    primary = get_panel_image_provider()
    if fallback == primary:
        return None
    return fallback


def get_image_ref_limit(provider: str | None = None) -> int:
    """Max reference image URLs per edit call for a provider/model.

    When ``provider`` is omitted, uses :func:`get_image_provider`.
    """
    override = os.getenv("IMAGE_REF_LIMIT")
    if override is not None and str(override).strip():
        limit = int(override)
        if limit < 1:
            raise ValueError(f"IMAGE_REF_LIMIT must be >= 1, got {limit}")
        return limit

    resolved = (provider or get_image_provider()).strip().lower()
    if resolved == "fal":
        # fal openai/gpt-image-2 shares the GPT Image ref budget; legacy Grok stays at 3.
        model = (
            os.getenv("GROK_FAL_MODEL")
            or os.getenv("GROK_REPLICATE_MODEL")
            or GROK_REPLICATE_MODEL
            or ""
        ).lower()
        if "gpt-image" in model:
            return REPLICATE_GPT_IMAGE_REF_LIMIT
        return FAL_GROK_REF_LIMIT

    model = (os.getenv("GROK_REPLICATE_MODEL") or GROK_REPLICATE_MODEL or "").lower()
    if "seedream" in model:
        return REPLICATE_SEEDREAM_REF_LIMIT
    if "gpt-image" in model:
        return REPLICATE_GPT_IMAGE_REF_LIMIT
    if "grok-imagine" in model or model.startswith("xai/"):
        return REPLICATE_LEGACY_GROK_REF_LIMIT
    return REPLICATE_GPT_IMAGE_REF_LIMIT