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
FAL_KEY = os.getenv("FAL_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
        if OPENROUTER_API_KEY:
            print("🤖 Using openai/gpt-5-mini as reasoning model via OPENROUTER_API_KEY (OpenRouter)")
            _reasoning_model = LiteLlm(
                model="openai/gpt-5-mini",
                api_key=OPENROUTER_API_KEY,
                api_base="https://openrouter.ai/api/v1",
                num_retries=3,
                timeout=300
            )
        elif GEMINI_API_KEY:
            print("🤖 Using gemini/gemini-2.5-flash as reasoning model via GEMINI_API_KEY")
            _reasoning_model = LiteLlm(
                model="gemini/gemini-2.5-flash",
                api_key=GEMINI_API_KEY,
                num_retries=3,
                timeout=120
            )
        elif MINIMAX_API_KEY:
            print("🤖 Using openai/MiniMax-M3 as reasoning model via MINIMAX_API_KEY")
            _reasoning_model = LiteLlm(
                model="openai/MiniMax-M3",
                api_key=MINIMAX_API_KEY,
                api_base="https://api.minimax.io/v1",
                num_retries=3,
                timeout=600
            )
        else:
            raise ValueError("Neither OPENROUTER_API_KEY, GEMINI_API_KEY, nor MINIMAX_API_KEY is set in environment or .env file.")
    return _reasoning_model

def get_light_model():
    global _light_model
    if _light_model is None:
        from google.adk.models.lite_llm import LiteLlm
        if OPENROUTER_API_KEY:
            print("🤖 Using openai/gpt-5-mini as light model via OPENROUTER_API_KEY (OpenRouter)")
            _light_model = LiteLlm(
                model="openai/gpt-5-mini",
                api_key=OPENROUTER_API_KEY,
                api_base="https://openrouter.ai/api/v1",
                num_retries=3,
                timeout=300
            )
        elif GEMINI_API_KEY:
            print("🤖 Using gemini/gemini-2.5-flash as light model via GEMINI_API_KEY")
            _light_model = LiteLlm(
                model="gemini/gemini-2.5-flash",
                api_key=GEMINI_API_KEY,
                num_retries=3,
                timeout=120
            )
        elif MINIMAX_API_KEY:
            print("🤖 Using openai/MiniMax-M2.7-highspeed as light model via MINIMAX_API_KEY")
            _light_model = LiteLlm(
                model="openai/MiniMax-M2.7-highspeed",
                api_key=MINIMAX_API_KEY,
                api_base="https://api.minimax.io/v1",
                num_retries=3,
                timeout=300
            )
        else:
            raise ValueError("Neither OPENROUTER_API_KEY, GEMINI_API_KEY, nor MINIMAX_API_KEY is set in environment or .env file.")
    return _light_model

_validation_model = None

def get_validation_model():
    global _validation_model
    if _validation_model is None:
        from google.adk.models.lite_llm import LiteLlm
        if OPENROUTER_API_KEY:
            print("🤖 Using google/gemini-3.1-flash-lite as validation model via OPENROUTER_API_KEY (OpenRouter)")
            _validation_model = LiteLlm(
                model="google/gemini-3.1-flash-lite",
                api_key=OPENROUTER_API_KEY,
                api_base="https://openrouter.ai/api/v1",
                num_retries=3
            )
        elif GEMINI_API_KEY:
            print("🤖 Using gemini/gemini-2.5-flash as validation model via GEMINI_API_KEY")
            _validation_model = LiteLlm(
                model="gemini/gemini-2.5-flash",
                api_key=GEMINI_API_KEY,
                num_retries=3,
                timeout=120
            )
        else:
            raise ValueError("Neither OPENROUTER_API_KEY nor GEMINI_API_KEY is set in environment or .env file.")
    return _validation_model

