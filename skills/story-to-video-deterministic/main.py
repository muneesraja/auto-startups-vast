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

# The global prompt_pipeline declaration is removed to allow dynamic construction inside main_async.

async def main_async():
    import json
    from datetime import datetime

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

    # Build initial state and select sub-agents dynamically based on existing files on disk
    initial_state = {
        "story_text": story_text,
        "output_dir": output_dir,
    }
    
    sub_agents = []
    
    # 1. Director's Script
    script_path = os.path.join(output_dir, "Director_script.md")
    if os.path.exists(script_path):
        print(f"📄 Found existing Director's Script on disk. Skipping Step 1.")
        with open(script_path, "r", encoding="utf-8") as f:
            initial_state["director_script_content"] = f.read()
    else:
        sub_agents.append(director_script_agent)

    # 2a. Blueprint Structure
    struct_path = os.path.join(output_dir, "director_visual_blueprint_structure.json")
    if os.path.exists(struct_path):
        print(f"📄 Found existing Structural Blueprint on disk. Skipping Step 2a.")
        with open(struct_path, "r", encoding="utf-8") as f:
            initial_state["blueprint_structure_json"] = f.read()
    else:
        sub_agents.append(blueprint_structure_agent)

    # 2b. Blueprint Visuals
    blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
    if os.path.exists(blueprint_path):
        print(f"📄 Found existing Visual Blueprint on disk. Skipping Step 2b.")
        with open(blueprint_path, "r", encoding="utf-8") as f:
            initial_state["blueprint_json_content"] = f.read()
    else:
        sub_agents.append(blueprint_visuals_agent)

    # Load prompts.json if it exists
    prompts_path = os.path.join(output_dir, "prompts.json")
    prompts_data = {}
    if os.path.exists(prompts_path):
        try:
            with open(prompts_path, "r", encoding="utf-8") as f:
                prompts_data = json.load(f)
        except Exception:
            pass

    # 3. Character Sheets
    if prompts_data.get("character_sheets"):
        print(f"📄 Found existing character sheets in prompts.json. Skipping Step 3.")
        initial_state["character_prompts_content"] = json.dumps({"character_sheets": prompts_data["character_sheets"]})
    else:
        sub_agents.append(character_sheet_prompter)

    # 4. FF Shots
    if prompts_data.get("ff_shots"):
        print(f"📄 Found existing FF shots in prompts.json. Skipping Step 4.")
        initial_state["ff_prompts_content"] = json.dumps({"ff_shots": prompts_data["ff_shots"]})
    else:
        sub_agents.append(ff_shot_prompter)

    # 5. Consistency Patches
    if prompts_data.get("consistency_patches"):
        print(f"📄 Found existing consistency patches in prompts.json. Skipping Step 5.")
        initial_state["consistency_prompts_content"] = json.dumps({"consistency_patches": prompts_data["consistency_patches"]})
    else:
        sub_agents.append(consistency_prompter)

    # 6. LF Shots
    if prompts_data.get("lf_shots"):
        print(f"📄 Found existing LF shots in prompts.json. Skipping Step 6.")
        initial_state["lf_prompts_content"] = json.dumps({"lf_shots": prompts_data["lf_shots"]})
    else:
        sub_agents.append(lf_shot_prompter)

    # 7. Motion Prompts
    if prompts_data.get("motion_prompts"):
        print(f"📄 Found existing motion prompts in prompts.json. Skipping Step 7.")
        initial_state["motion_prompts_content"] = json.dumps({"motion_prompts": prompts_data["motion_prompts"]})
    else:
        sub_agents.append(motion_prompter)

    def clean_json_str(s):
        if not s:
            return {}
        s = s.strip()
        # Remove potential think blocks
        import re
        s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
        s = re.sub(r"<thought>.*?</thought>", "", s, flags=re.DOTALL).strip()
        
        # Remove potential markdown block wrappers
        if s.startswith("```json"):
            s = s[7:]
        elif s.startswith("```"):
            s = s[3:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
        
        # Robust extract: find first '{' and last '}'
        start_idx = s.find('{')
        end_idx = s.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            s = s[start_idx:end_idx+1]
            
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

    def write_intermediate_files(state, output_dir):
        # 1. Director Script
        director_script = state.get("director_script_content")
        if director_script:
            script_path = os.path.join(output_dir, "Director_script.md")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(director_script)
            print(f"📁 [Auto-Save] Wrote Director_script.md")

        # 2. Structural Blueprint
        blueprint_struct_raw = state.get("blueprint_structure_json")
        if blueprint_struct_raw:
            blueprint_struct = clean_json_str(blueprint_struct_raw)
            struct_path = os.path.join(output_dir, "director_visual_blueprint_structure.json")
            with open(struct_path, "w", encoding="utf-8") as f:
                json.dump(blueprint_struct, f, indent=2, ensure_ascii=False)
            print(f"📁 [Auto-Save] Wrote director_visual_blueprint_structure.json")

        # 3. Complete Visual Blueprint
        blueprint_raw = state.get("blueprint_json_content")
        if blueprint_raw:
            blueprint = clean_json_str(blueprint_raw)
            blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
            with open(blueprint_path, "w", encoding="utf-8") as f:
                json.dump(blueprint, f, indent=2, ensure_ascii=False)
            print(f"📁 [Auto-Save] Wrote director_visual_blueprint.json")

        # 4. Prompts JSON
        if any(state.get(k) for k in ["character_prompts_content", "ff_prompts_content", "consistency_prompts_content", "lf_prompts_content", "motion_prompts_content"]):
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

            prompts_data = {
                "meta": {
                    "blueprint_version": 1,
                    "last_updated_by": "main_pipeline_autosave",
                    "last_updated_at": datetime.utcnow().isoformat() + "Z"
                },
                "character_sheets": char_sheets,
                "ff_shots": ff_shots,
                "consistency_patches": consistency_patches,
                "lf_shots": lf_shots,
                "motion_prompts": motion_prompts
            }

            prompts_path = os.path.join(output_dir, "prompts.json")
            with open(prompts_path, "w", encoding="utf-8") as f:
                json.dump(prompts_data, f, indent=2, ensure_ascii=False)
            print(f"📁 [Auto-Save] Wrote prompts.json")

    if sub_agents:
        prompt_pipeline = SequentialAgent(
            name="StoryToVideoPromptPipeline",
            sub_agents=sub_agents
        )

        # Set up ADK session & runner
        APP_NAME = "story_to_video_deterministic"
        session_service = InMemorySessionService()
        
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id="director",
            session_id="session_1",
            state=initial_state
        )
        
        runner = Runner(
            agent=prompt_pipeline,
            app_name=APP_NAME,
            session_service=session_service
        )
        
        user_message = types.Content(
            parts=[types.Part(text=story_text)]
        )

        print(f"\n🚀 Running ADK Prompt Generation Pipeline (Steps: {[a.name for a in sub_agents]})...")
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
                curr_session = await session_service.get_session(
                    app_name=APP_NAME,
                    user_id="director",
                    session_id="session_1"
                )
                write_intermediate_files(curr_session.state, output_dir)
            
        print("✅ Prompt generation pipeline complete!")

        # Perform final write
        final_session = await session_service.get_session(
            app_name=APP_NAME,
            user_id="director",
            session_id="session_1"
        )
        write_intermediate_files(final_session.state, output_dir)
    else:
        print("✅ All prompt files found on disk. Skipping ADK pipeline execution.")

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
