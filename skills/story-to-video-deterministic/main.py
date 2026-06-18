import os
import sys
import argparse
import asyncio
from google.adk.agents import SequentialAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Add local package root to sys.path so configs can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT_OUTPUT_BASE_DIR
from agents.step1_director_script import director_script_agent
from agents.step2a_blueprint_structure import blueprint_structure_agent
from agents.step2b_blueprint_visuals import blueprint_visuals_agent
from agents.step3_character_prompter import character_sheet_prompter
from agents.step4_ff_prompter import ff_shot_prompter
from agents.step5_consistency_prompter import consistency_prompter
from agents.step6_lf_prompter import lf_shot_prompter
from agents.step7_motion_prompter import motion_prompter

from scripts.wave_organizer import organize_waves
from scripts.wave_executor import execute_wave

# Construct SequentialAgent pipeline (Steps 1 to 7)
prompt_pipeline = SequentialAgent(
    name="StoryToVideoPromptPipeline",
    sub_agents=[
        director_script_agent,       # Step 1
        blueprint_structure_agent,   # Step 2a
        blueprint_visuals_agent,     # Step 2b
        character_sheet_prompter,    # Step 3
        ff_shot_prompter,            # Step 4
        consistency_prompter,        # Step 5
        lf_shot_prompter,            # Step 6
        motion_prompter,             # Step 7
    ]
)

async def main_async():
    parser = argparse.ArgumentParser(description="Deterministic Story-to-Video Pipeline")
    parser.add_argument("--story", required=True, help="Story text or path to file containing story text")
    parser.add_argument("--name", required=True, help="Name of the story output directory")
    parser.add_argument("--dir", default=None, help="Custom absolute path to output directory")
    args = parser.parse_args()

    # Read story from string or file
    story_text = args.story
    if os.path.exists(story_text):
        with open(story_text, "r", encoding="utf-8") as f:
            story_text = f.read()

    output_dir = args.dir
    if not output_dir:
        output_dir = os.path.join(DEFAULT_OUTPUT_BASE_DIR, args.name)

    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory initialized at: {output_dir}")

    # Set up ADK session & runner
    APP_NAME = "story_to_video_deterministic"
    session_service = InMemorySessionService()
    
    # We pass the story_text and output_dir as initial session state
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id="director",
        session_id="session_1",
        state={
            "story_text": story_text,
            "output_dir": output_dir,
        }
    )
    
    runner = Runner(
        agent=prompt_pipeline,
        app_name=APP_NAME,
        session_service=session_service
    )
    
    user_message = types.Content(
        parts=[types.Part(text=story_text)]
    )

    print("\n🚀 Running ADK Prompt Generation Pipeline (Steps 1-7)...")
    async for event in runner.run_async(
        user_id="director",
        session_id="session_1",
        new_message=user_message,
    ):
        author = getattr(event, "author", "unknown")
        content_text = ""
        if hasattr(event, "content") and event.content and event.content.parts:
            content_text = "".join(p.text for p in event.content.parts if p.text)[:100]
        print(f"[{author}] {event.__class__.__name__}: {content_text}")
        if hasattr(event, "actions") and event.actions and event.actions.state_delta:
            print(f"   State delta: {list(event.actions.state_delta.keys())}")
        
    print("✅ Prompt generation pipeline complete!")

    # Retrieve final session state
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id="director",
        session_id="session_1"
    )
    state = session.state

    import json
    from datetime import datetime
    
    def clean_json_str(s):
        if not s:
            return {}
        s = s.strip()
        # Remove potential markdown block wrappers
        if s.startswith("```json"):
            s = s[7:]
        elif s.startswith("```"):
            s = s[3:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
        try:
            return json.loads(s)
        except Exception as e:
            print(f"⚠️ Error parsing JSON from agent output: {e}\nRaw content: {s[:200]}...")
            return {}

    def get_namespace_dict(data, key):
        if not isinstance(data, dict):
            return {}
        if key in data:
            return data[key]
        return data

    char_sheets_raw = clean_json_str(state.get("character_prompts_content"))
    ff_shots_raw = clean_json_str(state.get("ff_prompts_content"))
    consistency_patches_raw = clean_json_str(state.get("consistency_prompts_content"))
    lf_shots_raw = clean_json_str(state.get("lf_prompts_content"))
    motion_prompts_raw = clean_json_str(state.get("motion_prompts_content"))

    char_sheets = get_namespace_dict(char_sheets_raw, "character_sheets")
    ff_shots = get_namespace_dict(ff_shots_raw, "ff_shots")
    consistency_patches = get_namespace_dict(consistency_patches_raw, "consistency_patches")
    lf_shots = get_namespace_dict(lf_shots_raw, "lf_shots")
    motion_prompts = get_namespace_dict(motion_prompts_raw, "motion_prompts")

    # Construct the final PromptsFile structure
    prompts_data = {
        "meta": {
            "blueprint_version": 1,
            "last_updated_by": "main_pipeline",
            "last_updated_at": datetime.utcnow().isoformat() + "Z"
        },
        "character_sheets": char_sheets,
        "ff_shots": ff_shots,
        "consistency_patches": consistency_patches,
        "lf_shots": lf_shots,
        "motion_prompts": motion_prompts
    }

    # Validate using Pydantic model
    from schemas.prompts import PromptsFile
    try:
        PromptsFile(**prompts_data)
        print("✅ Pydantic validation for prompts.json passed successfully!")
    except Exception as e:
        print(f"⚠️ Pydantic validation for prompts.json failed: {e}")

    # Write prompts.json to disk
    prompts_path = os.path.join(output_dir, "prompts.json")
    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(prompts_data, f, indent=2, ensure_ascii=False)
    print(f"📁 Successfully wrote merged prompts.json to: {prompts_path}")

    # Write Director_script.md to disk
    director_script = state.get("director_script_content")
    if director_script:
        script_path = os.path.join(output_dir, "Director_script.md")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(director_script)
        print(f"📁 Successfully wrote Director_script.md to: {script_path}")
    else:
        print("⚠️ Warning: director_script_content is missing from state")

    # Write director_visual_blueprint_structure.json to disk
    blueprint_struct_raw = state.get("blueprint_structure_json")
    if blueprint_struct_raw:
        blueprint_struct = clean_json_str(blueprint_struct_raw)
        struct_path = os.path.join(output_dir, "director_visual_blueprint_structure.json")
        with open(struct_path, "w", encoding="utf-8") as f:
            json.dump(blueprint_struct, f, indent=2, ensure_ascii=False)
        print(f"📁 Successfully wrote director_visual_blueprint_structure.json to: {struct_path}")
    else:
        print("⚠️ Warning: blueprint_structure_json is missing from state")

    # Write director_visual_blueprint.json to disk
    blueprint_raw = state.get("blueprint_json_content")
    if blueprint_raw:
        blueprint = clean_json_str(blueprint_raw)
        blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
        with open(blueprint_path, "w", encoding="utf-8") as f:
            json.dump(blueprint, f, indent=2, ensure_ascii=False)
        print(f"📁 Successfully wrote director_visual_blueprint.json to: {blueprint_path}")
    else:
        print("⚠️ Warning: blueprint_json_content is missing from state")

    # Step 8: Run Wave Organizer
    print("\n📋 Running Wave Organizer (Step 8)...")
    organize_waves(output_dir)

    # Step 9: Run Wave Executor (Wave 1)
    print("\n🌊 Running Wave 1 Executor (Step 9)...")
    await execute_wave(output_dir, wave=1)

    # Run Wave Executor (Wave 2)
    print("\n🌊 Running Wave 2 Executor...")
    await execute_wave(output_dir, wave=2)
    
    print("\n🎉 Deterministic pipeline successfully completed all steps!")

if __name__ == "__main__":
    asyncio.run(main_async())
