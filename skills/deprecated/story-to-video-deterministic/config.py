import os
from dotenv import load_dotenv

# Load environment variables from .env in workspace root
# Current file is skills/story-to-video-deterministic/config.py, workspace root is ../../
config_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.dirname(os.path.dirname(config_dir))
dotenv_path = os.path.join(workspace_root, ".env")
load_dotenv(dotenv_path)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188")
COMFYUI_AUTH = os.getenv("COMFYUI_AUTH")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")

# Default outputs directory
DEFAULT_OUTPUT_BASE_DIR = "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-deterministic"
WORKFLOWS_DIR = os.path.join(workspace_root, "workflows", "comfyui")

# We defer initialization of LiteLlm model clients until needed to prevent import-time
# API key errors if key isn't populated immediately, or to make mocking/testing easier.
_reasoning_model = None
_light_model = None

def get_reasoning_model():
    global _reasoning_model
    if _reasoning_model is None:
        from google.adk.models.lite_llm import LiteLlm
        if not MINIMAX_API_KEY:
            raise ValueError("MINIMAX_API_KEY is not set in environment or .env file.")
        _reasoning_model = LiteLlm(
            model="openai/MiniMax-M3",
            api_key=MINIMAX_API_KEY,
            api_base="https://api.minimax.io/v1",
            num_retries=3
        )
    return _reasoning_model

def get_light_model():
    global _light_model
    if _light_model is None:
        from google.adk.models.lite_llm import LiteLlm
        if not MINIMAX_API_KEY:
            raise ValueError("MINIMAX_API_KEY is not set in environment or .env file.")
        _light_model = LiteLlm(
            model="openai/MiniMax-M2.7-highspeed",
            api_key=MINIMAX_API_KEY,
            api_base="https://api.minimax.io/v1",
            num_retries=3
        )
    return _light_model
