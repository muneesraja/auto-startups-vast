import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - test fallback without python-dotenv
    def load_dotenv(*_args, **_kwargs):
        return False

config_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(os.path.dirname(config_dir))
# Shared credentials live in the home root (~/.hermes/.env). Load first
# WITHOUT override so values exported into the shell by the user win.
_shared_dotenv = os.path.join(workspace_root, ".env")
load_dotenv(_shared_dotenv, override=False)


def _load_project_dotenv() -> str | None:
    """Walk up from CWD looking for a project .env to layer on top.

    This lets a project repo (e.g. /root/repos/auto-startups-vast/.env)
    override shared defaults from ~/.hermes/.env without forcing the
    user to keep credentials in two places.

    The project .env is loaded with override=True so values like
    COMFYUI_URL in the repo take precedence over the shared root .env.
    Returns the loaded path, or None if no project .env was found.
    """
    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        candidate = parent / ".env"
        if candidate.is_file() and str(candidate) != _shared_dotenv:
            load_dotenv(candidate, override=True)
            return str(candidate)
    return None


_loaded_project_dotenv = _load_project_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
COMFYUI_AUTH = os.getenv("COMFYUI_AUTH")
FAL_KEY = os.getenv("FAL_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")

DEFAULT_OUTPUT_BASE_DIR = os.getenv(
    "STORY_MAKER_OUTPUT_DIR",
    os.path.join(workspace_root, "outputs", "story-maker"),
)
WORKFLOWS_DIR = os.path.join(config_dir, "assets", "workflow-templates")
I2V_TEMPLATE_NAME = "ltx-i2v"
FLF2V_TEMPLATE_NAME = os.getenv("FLF2V_TEMPLATE_NAME", "ltx-flf2v")
# storyboard video path: "fallback" = existing video_shots I2V; "director" = assistant-director I2V/FLF
STORYBOARD_VIDEO_MODE = os.getenv("STORYBOARD_VIDEO_MODE", "fallback").strip().lower()
# Render backend when STORYBOARD_VIDEO_MODE=director:
#   templates = legacy ltx-i2v / ltx-flf2v templates (default)
#   director_v2 = LTX Director Hotfix timeline workflow
STORY_MAKER_VIDEO_BACKEND = os.getenv(
    "STORY_MAKER_VIDEO_BACKEND", "templates"
).strip().lower()
FLF_DURATION_TOLERANCE_PERCENT = int(os.getenv("FLF_DURATION_TOLERANCE_PERCENT", "15"))
# LTX output resolution (must be divisible by 32 for latent math)
VIDEO_WIDTH = int(os.getenv("VIDEO_WIDTH", "1920"))
VIDEO_HEIGHT = int(os.getenv("VIDEO_HEIGHT", "1088"))
# LTX Director Hotfix working resolution (1280x720 is invalid under ÷32)
DIRECTOR_VIDEO_WIDTH = int(os.getenv("DIRECTOR_VIDEO_WIDTH", "1280"))
DIRECTOR_VIDEO_HEIGHT = int(os.getenv("DIRECTOR_VIDEO_HEIGHT", "704"))

DEFAULT_PLANNING_MODEL = "openai/gpt-5.4-mini"
DEFAULT_PLANNING_TIMEOUT = int(os.getenv("PLANNING_MODEL_TIMEOUT", "600"))
DEFAULT_PLANNING_REASONING_EFFORT = os.getenv("PLANNING_REASONING_EFFORT", "low")
DEFAULT_SECONDARY_MODEL = "openai/gpt-5.4-mini"
SECONDARY_MODEL_TIMEOUT = int(os.getenv("SECONDARY_MODEL_TIMEOUT", "600"))
DEFAULT_SECONDARY_REASONING_EFFORT = os.getenv("SECONDARY_REASONING_EFFORT", "low")
DEFAULT_VISION_MODEL = "openai/gpt-5-mini"
DEFAULT_CROP_ANALYSIS_MODEL = "openai/gpt-5.4-mini"

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
CHARACTER_SHEET_SIZE = os.getenv("CHARACTER_SHEET_SIZE", "1152x2048")
BACKGROUND_IMAGE_SIZE = os.getenv("BACKGROUND_IMAGE_SIZE", "2048x1152")
# 8:9 album (fal custom WxH) so packed 4×2 cells are true 16:9. Prefer fal provider.
STORYBOARD_SHEET_SIZE = os.getenv("STORYBOARD_SHEET_SIZE", "1024x1152")
# Panel crop: python (white-gutter detect → uniform grid) | vision | auto
STORYBOARD_CROP_MODE = os.getenv("STORYBOARD_CROP_MODE", "python")
PANEL_IMAGE_SIZE = os.getenv("PANEL_IMAGE_SIZE", "2048x1152")
COST_REPLICATE_IMAGE = float(os.getenv("COST_REPLICATE_IMAGE", "0.01"))
COST_OPENROUTER_CALL = float(os.getenv("COST_OPENROUTER_CALL", "0.002"))
COST_LTX_VIDEO = float(os.getenv("COST_LTX_VIDEO", "0.0"))

# Provider/model reference-image caps (shot still edit / composite)
FAL_GROK_REF_LIMIT = 3
REPLICATE_SEEDREAM_REF_LIMIT = 10
REPLICATE_GPT_IMAGE_REF_LIMIT = 13  # safe cap for Replicate openai/gpt-image-2
REPLICATE_LEGACY_GROK_REF_LIMIT = 1

# LiteLLM + OpenRouter: always use openrouter/ prefix so api_base is not doubled
# (e.g. anthropic/* with api_base=/api/v1 would hit /api/v1/v1/messages otherwise).


def _normalize_openrouter_model(model_id: str) -> str:
    """Map any OpenRouter slug to litellm's openrouter/ form."""
    if model_id.startswith("openrouter/"):
        return model_id
    return f"openrouter/{model_id}"


_llm_cache: dict[tuple[str, int], object] = {}


def _require_api_key() -> None:
    if not (OPENROUTER_API_KEY or GEMINI_API_KEY or MINIMAX_API_KEY):
        raise ValueError(
            "Set OPENROUTER_API_KEY, GEMINI_API_KEY, or MINIMAX_API_KEY in .env"
        )


def _default_reasoning_model_id() -> str:
    _require_api_key()
    if OPENROUTER_API_KEY:
        return "openai/gpt-5-mini"
    if GEMINI_API_KEY:
        return "gemini/gemini-2.5-flash"
    return "openai/MiniMax-M3"


def _resolve_model_id(role_env: str, default: str) -> str:
    return os.getenv(role_env) or os.getenv("PLANNING_MODEL") or default


def get_story_developer_model_id() -> str:
    return _resolve_model_id("STORY_DEVELOPER_MODEL", DEFAULT_PLANNING_MODEL)


def get_narrative_expander_model_id() -> str:
    return _resolve_model_id("NARRATIVE_EXPANDER_MODEL", DEFAULT_PLANNING_MODEL)


def get_story_plan_model_id() -> str:
    return _resolve_model_id("STORY_PLAN_MODEL", DEFAULT_PLANNING_MODEL)


def get_secondary_model_id() -> str:
    return os.getenv("SECONDARY_MODEL") or os.getenv("LIGHT_MODEL") or DEFAULT_SECONDARY_MODEL


def get_vision_model_id() -> str:
    return os.getenv("VISION_MODEL", DEFAULT_VISION_MODEL)


def get_crop_analysis_model_id() -> str:
    return os.getenv("CROP_ANALYSIS_MODEL", DEFAULT_CROP_ANALYSIS_MODEL)


def get_crop_analysis_model_config() -> tuple[str, str | None, str | None]:
    """Model name, api_key, api_base for storyboard panel crop analysis."""
    model_id = get_crop_analysis_model_id()
    if OPENROUTER_API_KEY:
        return _normalize_openrouter_model(model_id), OPENROUTER_API_KEY, "https://openrouter.ai/api/v1"
    if GEMINI_API_KEY:
        return model_id, GEMINI_API_KEY, None
    raise ValueError("Set OPENROUTER_API_KEY or GEMINI_API_KEY for crop analysis")


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

    Defaults to ``fal`` (GPT Image 2). Keep panel / shot stills on Replicate
    via :func:`get_image_provider` — fal edit+refs for high-volume panel regen
    is typically much more expensive than Replicate ``quality=low``.
    """
    raw = (os.getenv("STORYBOARD_IMAGE_PROVIDER") or "fal").strip().lower()
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

    Defaults to ``fal`` (same preference as storyboard sheets). Override with
    ``CHARACTER_SHEET_IMAGE_PROVIDER``. Location plates and panel/shot stills
    stay on :func:`get_image_provider` (Replicate).
    """
    raw = (os.getenv("CHARACTER_SHEET_IMAGE_PROVIDER") or "").strip().lower()
    if raw:
        return _validate_image_backend(raw, label="CHARACTER_SHEET_IMAGE_PROVIDER")
    # Prefer fal when keyed — sheets benefit from fal's multi-ref edit; few calls.
    if FAL_KEY or os.environ.get("FAL_KEY"):
        return "fal"
    return get_image_provider()


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


def get_planning_reasoning_effort() -> str | None:
    effort = (os.getenv("PLANNING_REASONING_EFFORT") or DEFAULT_PLANNING_REASONING_EFFORT).strip()
    return effort or None


def get_secondary_reasoning_effort() -> str | None:
    effort = (os.getenv("SECONDARY_REASONING_EFFORT") or DEFAULT_SECONDARY_REASONING_EFFORT).strip()
    return effort or None


def get_llm(model_id: str, *, timeout: int = 300, reasoning_effort: str | None = None):
    """Return a cached LiteLlm instance for the given model id."""
    key = (model_id, timeout, reasoning_effort)
    if key in _llm_cache:
        return _llm_cache[key]

    from google.adk.models.lite_llm import LiteLlm

    _require_api_key()
    if OPENROUTER_API_KEY:
        routed_model = _normalize_openrouter_model(model_id)
        llm_kwargs: dict = {
            "model": routed_model,
            "api_key": OPENROUTER_API_KEY,
            "api_base": "https://openrouter.ai/api/v1",
            "num_retries": 3,
            "timeout": timeout,
        }
        if reasoning_effort:
            llm_kwargs["reasoning_effort"] = reasoning_effort
        llm = LiteLlm(**llm_kwargs)
    elif GEMINI_API_KEY:
        llm = LiteLlm(
            model=model_id,
            api_key=GEMINI_API_KEY,
            num_retries=3,
            timeout=min(timeout, 120),
        )
    else:
        llm = LiteLlm(
            model=model_id,
            api_key=MINIMAX_API_KEY,
            api_base="https://api.minimax.io/v1",
            num_retries=3,
            timeout=timeout,
        )

    _llm_cache[key] = llm
    return llm


def get_reasoning_model():
    model_id = os.getenv("REASONING_MODEL") or _default_reasoning_model_id()
    timeout = 600 if MINIMAX_API_KEY and not OPENROUTER_API_KEY and not GEMINI_API_KEY else 300
    return get_llm(model_id, timeout=timeout)


def get_light_model():
    return get_llm(
        get_secondary_model_id(),
        timeout=SECONDARY_MODEL_TIMEOUT,
        reasoning_effort=get_secondary_reasoning_effort(),
    )


def get_story_developer_model():
    return get_llm(
        get_story_developer_model_id(),
        timeout=DEFAULT_PLANNING_TIMEOUT,
        reasoning_effort=get_planning_reasoning_effort(),
    )


def get_narrative_expander_model():
    return get_llm(
        get_narrative_expander_model_id(),
        timeout=DEFAULT_PLANNING_TIMEOUT,
        reasoning_effort=get_planning_reasoning_effort(),
    )


def get_story_plan_model():
    return get_llm(
        get_story_plan_model_id(),
        timeout=DEFAULT_PLANNING_TIMEOUT,
        reasoning_effort=get_planning_reasoning_effort(),
    )


def get_vision_model_config() -> tuple[str, str | None, str | None]:
    """Model name, api_key, api_base for vision motion prompter."""
    model_id = get_vision_model_id()
    if OPENROUTER_API_KEY:
        return _normalize_openrouter_model(model_id), OPENROUTER_API_KEY, "https://openrouter.ai/api/v1"
    if GEMINI_API_KEY:
        return model_id, GEMINI_API_KEY, None
    raise ValueError("Set OPENROUTER_API_KEY or GEMINI_API_KEY for vision motion prompter")
