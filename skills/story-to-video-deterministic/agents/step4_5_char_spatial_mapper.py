import os
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.utils import instructions_utils
from config import get_light_model

def get_system_prompt() -> str:
    prompt_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "system_prompts", "char_spatial_mapper.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()

async def instruction_provider(context: ReadonlyContext) -> str:
    system_prompt = get_system_prompt()

    additional_instr = (
        "\n\nCRITICAL: Return ONLY the JSON object representing the 'character_spatial_map' namespace. "
        "Do not wrap it in markdown code block formatting (like ```json ... ```) or any other formatting. "
        "Do not call any tools. "
        "The output must be a valid JSON dictionary mapping shot IDs to lists of character placements, e.g.:\n"
        "{\n"
        "  \"scene_01_shot_04\": [\n"
        "    {\n"
        "      \"character_id\": \"char_01\",\n"
        "      \"reference_index\": 1,\n"
        "      \"screen_position\": \"left foreground\",\n"
        "      \"visual_identifier\": \"soft pink plush bunny with long floppy ears\",\n"
        "      \"action\": \"leaning forward, ears perked\"\n"
        "    },\n"
        "    {\n"
        "      \"character_id\": \"char_03\",\n"
        "      \"reference_index\": 2,\n"
        "      \"screen_position\": \"right foreground\",\n"
        "      \"visual_identifier\": \"blue butterfly with iridescent wings\",\n"
        "      \"action\": \"wings spread, perched on flower\"\n"
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Scope rules (verify each before emitting):\n"
        "1. SKIP entirely (omit from output) any shot where `continuation_from_previous == true`.\n"
        "2. SKIP entirely (omit from output) any shot where `characters_present` is empty.\n"
        "3. For every other shot, you MUST emit one list entry per character in `characters_present`.\n"
        "4. Hard list-completeness rule: every character_id in `characters_present` MUST appear in "
        "your output list for that shot, and NO character outside `characters_present` may appear.\n"
        "5. `reference_index` MUST be a unique integer starting at 1, sorted ascending within each shot's list.\n"
        "6. Each entry's `visual_identifier` and `action` should be derived from the character's appearance "
        "and the shot's ff/lf descriptions, NOT invented from whole cloth.\n\n"
        "Here is the visual blueprint JSON context:\n\n{blueprint_json_content}"
    )

    full_prompt = system_prompt + additional_instr
    return await instructions_utils.inject_session_state(full_prompt, context)

char_spatial_mapper_agent = LlmAgent(
    model=get_light_model(),
    name="char_spatial_mapper_agent",
    instruction=instruction_provider,
    tools=[],
    output_key="character_spatial_map_content",
)
