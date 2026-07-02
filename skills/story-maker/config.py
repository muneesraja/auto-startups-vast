import os
from pathlib import Path

from dotenv import load_dotenv

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

DEFAULT_PLANNING_MODEL = "openai/gpt-5-mini"
DEFAULT_PLANNING_TIMEOUT = int(os.getenv("PLANNING_MODEL_TIMEOUT", "600"))
DEFAULT_SECONDARY_MODEL = "z-ai/glm-5.2"
SECONDARY_MODEL_TIMEOUT = int(os.getenv("SECONDARY_MODEL_TIMEOUT", "600"))
DEFAULT_VISION_MODEL = "openai/gpt-5-mini"

DEFAULT_IMAGE_PROVIDER = "fal"
GROK_REPLICATE_MODEL = os.getenv("GROK_REPLICATE_MODEL", "openai/gpt-image-2")
REPLICATE_IMAGE_QUALITY = os.getenv("REPLICATE_IMAGE_QUALITY", "low")

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


def get_narrative_expander_model_id() -> str:
    return _resolve_model_id("NARRATIVE_EXPANDER_MODEL", DEFAULT_PLANNING_MODEL)


def get_story_plan_model_id() -> str:
    return _resolve_model_id("STORY_PLAN_MODEL", DEFAULT_PLANNING_MODEL)


def get_secondary_model_id() -> str:
    return os.getenv("SECONDARY_MODEL") or os.getenv("LIGHT_MODEL") or DEFAULT_SECONDARY_MODEL


def get_vision_model_id() -> str:
    return os.getenv("VISION_MODEL", DEFAULT_VISION_MODEL)


def get_image_provider() -> str:
    """Return active Grok image backend: fal | replicate."""
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


def get_llm(model_id: str, *, timeout: int = 300):
    """Return a cached LiteLlm instance for the given model id."""
    key = (model_id, timeout)
    if key in _llm_cache:
        return _llm_cache[key]

    from google.adk.models.lite_llm import LiteLlm

    _require_api_key()
    if OPENROUTER_API_KEY:
        routed_model = _normalize_openrouter_model(model_id)
        llm = LiteLlm(
            model=routed_model,
            api_key=OPENROUTER_API_KEY,
            api_base="https://openrouter.ai/api/v1",
            num_retries=3,
            timeout=timeout,
        )
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
    return get_llm(get_secondary_model_id(), timeout=SECONDARY_MODEL_TIMEOUT)


def get_narrative_expander_model():
    return get_llm(get_narrative_expander_model_id(), timeout=DEFAULT_PLANNING_TIMEOUT)


def get_story_plan_model():
    return get_llm(get_story_plan_model_id(), timeout=DEFAULT_PLANNING_TIMEOUT)


def get_vision_model_config() -> tuple[str, str | None, str | None]:
    """Model name, api_key, api_base for vision motion prompter."""
    model_id = get_vision_model_id()
    if OPENROUTER_API_KEY:
        return _normalize_openrouter_model(model_id), OPENROUTER_API_KEY, "https://openrouter.ai/api/v1"
    if GEMINI_API_KEY:
        return model_id, GEMINI_API_KEY, None
    raise ValueError("Set OPENROUTER_API_KEY or GEMINI_API_KEY for vision motion prompter")
