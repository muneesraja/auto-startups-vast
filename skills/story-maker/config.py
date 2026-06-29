import os
from dotenv import load_dotenv

config_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(os.path.dirname(config_dir))
dotenv_path = os.path.join(workspace_root, ".env")
load_dotenv(dotenv_path)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
COMFYUI_AUTH = os.getenv("COMFYUI_AUTH")
FAL_KEY = os.getenv("FAL_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")

DEFAULT_OUTPUT_BASE_DIR = os.getenv(
    "STORY_MAKER_OUTPUT_DIR",
    os.path.join(workspace_root, "outputs", "story-maker"),
)
WORKFLOWS_DIR = os.path.join(config_dir, "assets", "workflow-templates")
I2V_TEMPLATE_NAME = "ltx-i2v"

_reasoning_model = None


def get_reasoning_model():
    global _reasoning_model
    if _reasoning_model is None:
        from google.adk.models.lite_llm import LiteLlm

        if OPENROUTER_API_KEY:
            _reasoning_model = LiteLlm(
                model="openai/gpt-5-mini",
                api_key=OPENROUTER_API_KEY,
                api_base="https://openrouter.ai/api/v1",
                num_retries=3,
                timeout=300,
            )
        elif GEMINI_API_KEY:
            _reasoning_model = LiteLlm(
                model="gemini/gemini-2.5-flash",
                api_key=GEMINI_API_KEY,
                num_retries=3,
                timeout=120,
            )
        elif MINIMAX_API_KEY:
            _reasoning_model = LiteLlm(
                model="openai/MiniMax-M3",
                api_key=MINIMAX_API_KEY,
                api_base="https://api.minimax.io/v1",
                num_retries=3,
                timeout=600,
            )
        else:
            raise ValueError(
                "Set OPENROUTER_API_KEY, GEMINI_API_KEY, or MINIMAX_API_KEY in .env"
            )
    return _reasoning_model


_light_model = None


def get_light_model():
    global _light_model
    if _light_model is None:
        from google.adk.models.lite_llm import LiteLlm

        if OPENROUTER_API_KEY:
            _light_model = LiteLlm(
                model="openai/gpt-5-mini",
                api_key=OPENROUTER_API_KEY,
                api_base="https://openrouter.ai/api/v1",
                num_retries=3,
                timeout=300,
            )
        elif GEMINI_API_KEY:
            _light_model = LiteLlm(
                model="gemini/gemini-2.5-flash",
                api_key=GEMINI_API_KEY,
                num_retries=3,
                timeout=120,
            )
        elif MINIMAX_API_KEY:
            _light_model = LiteLlm(
                model="openai/MiniMax-M2.7-highspeed",
                api_key=MINIMAX_API_KEY,
                api_base="https://api.minimax.io/v1",
                num_retries=3,
                timeout=300,
            )
        else:
            raise ValueError(
                "Set OPENROUTER_API_KEY, GEMINI_API_KEY, or MINIMAX_API_KEY in .env"
            )
    return _light_model
