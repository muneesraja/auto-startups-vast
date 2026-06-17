#!/usr/bin/env python3
import os
import json
import re
import urllib.request
import urllib.error
import ssl

def load_env():
    # Load environment variables from workspace root .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.abspath(os.path.join(script_dir, "..", "..", "..", ".env"))
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
    print("Environment variables loaded.")

def parse_story(file_path):
    print(f"Parsing story from: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Split by bolded scene headers, e.g. **[Scene 1 - The Forest Edge - Day]**
    pattern = r"\*\*\[Scene\s+(\d+)\s+-\s+([^\]]+)\]\*\*"
    parts = re.split(pattern, content)
    
    if len(parts) < 4:
        raise ValueError("Story format doesn't match expected Scene header pattern.")
        
    shots = []
    for i in range(1, len(parts), 3):
        scene_id = int(parts[i])
        title_cont = parts[i+1].strip()
        shot_content = parts[i+2].strip()
        
        # Split title and continuity, e.g. "The Forest Edge - Day" or "The Glow - Continuous"
        title_cont_parts = title_cont.split(" - ")
        title = title_cont_parts[0].strip()
        continuity_raw = title_cont_parts[1].strip() if len(title_cont_parts) > 1 else "Cut"
        
        # Parse cinematography and narrative
        cinematography = ""
        narrative = shot_content
        cin_match = re.match(r"\*([^*]+)\*(.*)", shot_content, re.DOTALL)
        if cin_match:
            cinematography = cin_match.group(1).strip()
            narrative = cin_match.group(2).strip()
            
        # Determine characters present
        characters_present = []
        lower_content = (cinematography + " " + narrative).lower()
        if "bramble" in lower_content:
            characters_present.append("bramble")
        if "clover" in lower_content:
            characters_present.append("clover")
        if "hazel" in lower_content:
            characters_present.append("hazel")
            
        # Determine default shot mapping parameters
        shots.append({
            "scene_id": scene_id,
            "title": title,
            "continuity_raw": continuity_raw,
            "cinematography": cinematography,
            "narrative": narrative,
            "characters_present": characters_present
        })
        
    print(f"Successfully parsed {len(shots)} shots.")
    return shots

SYSTEM_PROMPT = """You are an expert AI cinematography director analyzing shot descriptions for an FFLF (First Frame Last Frame) video generation model.
Your task is to analyze the narrative, camera movement, and physical action of a shot to:
1. Estimate the optimal segment duration in seconds (an integer between 2 and 8).
2. Write a precise Last Frame (LF) edit instruction detailing the change between the beginning and the end of the shot.
3. Write a motion prompt describing the camera and subject movements for the LTX video model.

FFLF Duration Guidelines:
- 2 seconds: Micro-motion or expression-only changes. e.g., a character looking up, nose twitching, eyes widening in curiosity, subtle facial adjustments. Long durations cause model hallucination or visual freezing.
- 3 to 4 seconds: Gentle camera panning, slight camera pushes/pulls (dolly in/out), or simple physical gestures (reaching out a paw, a character turning their head). Example: "Looked up and the camera pans towards the sun" should be 4 seconds.
- 5 to 6 seconds: Moderate action or movement. A character walking a short distance, picking up an object, or prying a root.
- 7 to 8 seconds: Large spatial displacement, traversal of a scene, or complex sequential actions (e.g. running across a clearing).

Respond with a single JSON object containing:
{
  "duration_seconds": <int between 2 and 8>,
  "lf_edit_instruction": "<text detailing the change from the beginning of the shot to the end. Maintain context and focus on visual deltas>",
  "motion_prompt": "<motion prompt for LTX-Video, 20-60 words describing subject and camera motion>",
  "reasoning": "<short explanation of why this duration and motion description was chosen>"
}
"""

def call_openrouter(system_prompt, user_prompt, api_key):
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers=headers)
    context = ssl._create_unverified_context()
    
    try:
        with urllib.request.urlopen(req, timeout=30, context=context) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            choice = resp_data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            return json.loads(content)
    except Exception as e:
        print(f"Error querying OpenRouter: {e}")
        return None

def main():
    load_env()
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ Error: OPENROUTER_API_KEY is not defined in the environment or .env file.")
        return
        
    story_dir = "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-cinematic/rabbit-forest-rescue"
    story_md_path = os.path.join(story_dir, "Story.md")
    
    if not os.path.exists(story_md_path):
        print(f"❌ Error: Story.md file not found at {story_md_path}")
        return
        
    shots = parse_story(story_md_path)
    
    # Process each shot and query OpenRouter
    estimated_shots = []
    director_decisions = []
    prompt_rationale = {}
    
    # Track sequence metrics
    shot_prefixes = []
    for idx, s in enumerate(shots, start=1):
        scene_prefix = f"s{s['scene_id']:02d}"
        # We want sequential shot numbers globally or per scene. Let's do it per scene.
        # Count how many shots in this scene so far
        shots_in_scene = len([x for x in shot_prefixes if x.startswith(scene_prefix)]) + 1
        shot_id_str = f"{scene_prefix}_sh{shots_in_scene:02d}"
        shot_prefixes.append(shot_id_str)
        s["shot_id_str"] = shot_id_str
        s["shot_in_scene"] = shots_in_scene
        
        # Apply contextual character overrides
        if shot_id_str == "s02_sh02":
            s["characters_present"] = ["clover", "hazel"]
        elif shot_id_str == "s02_sh05":
            s["characters_present"] = ["bramble", "clover", "hazel"]
    
    print("\n--- Estimating Durations via GPT-4o-mini ---")
    for idx, s in enumerate(shots):
        shot_id = s["shot_id_str"]
        print(f"Analyzing shot {shot_id}: {s['title']}")
        
        user_prompt = f"""Shot ID: {shot_id}
Title: {s['title']}
Cinematography: {s['cinematography']}
Narrative: {s['narrative']}
"""
        
        res = call_openrouter(SYSTEM_PROMPT, user_prompt, api_key)
        if not res:
            print(f"⚠️ Failed to get estimation for shot {shot_id}, using defaults.")
            res = {
                "duration_seconds": 5,
                "lf_edit_instruction": "The scene progresses forward with natural motion.",
                "motion_prompt": f"The camera pans slowly, showing characters moving in the forest.",
                "reasoning": "Fallback default duration"
            }
            
        print(f"   Estimated Duration: {res['duration_seconds']}s")
        print(f"   Reasoning: {res['reasoning']}")
        
        # Build prompt rationale for director log
        prompt_rationale[shot_id] = {
            "ff_prompt_reasoning": s["narrative"],
            "lf_edit_reasoning": res["lf_edit_instruction"],
            "motion_reasoning": res["motion_prompt"],
            "duration_reasoning": res["reasoning"]
        }
        
        # Determine continuity
        continuity = "start"
        continues_from = None
        shot_type = "chain_start"
        ff_source = "ideogram"
        lf_source = "klein_from_ff"
        
        if idx > 0:
            prev_shot = shots[idx-1]
            if s["continuity_raw"].lower() == "continuous":
                continuity = "##continue"
                continues_from = prev_shot["shot_id_str"]
                shot_type = "continuation"
                ff_source = "extracted_tail"
                lf_source = "klein_from_extracted_tail"
            else:
                continuity = "##cut"
                
            director_decisions.append({
                "from_shot": prev_shot["shot_id_str"],
                "to_shot": shot_id,
                "decision": continuity,
                "reasoning": f"Scene continuity marked as {s['continuity_raw']}"
            })
            
        # Build prompt
        style_string = "Cinematic 3D Pixar-style, soft volumetric lighting, warm color palette"
        
        # Draft a beautiful scene still prompt for Ideogram if this is a chain start
        ff_prompt = None
        if ff_source == "ideogram":
            # Combine characters and narrative
            char_list_str = ", ".join(s["characters_present"]) if s["characters_present"] else "a rabbit"
            ff_prompt = f"Wide cinematic still. {s['narrative'].strip()} Styled as 3D Pixar character models, rich textures, soft volumetric light."
            
        estimated_shots.append({
            "shot_id": s["shot_in_scene"],
            "shot_type": shot_type,
            "continuity": continuity,
            "continues_from": continues_from,
            "narrative": s["narrative"],
            "cinematography_notes": s["cinematography"],
            "characters_present": s["characters_present"],
            "ff_source": ff_source,
            "ff_prompt": ff_prompt,
            "ff_edit_instructions": {
                c: f"Replace the character in the scene with the character from reference image {i+1} exactly."
                for i, c in enumerate(s["characters_present"])
            } if ff_source == "ideogram" else None,
            "lf_source": lf_source,
            "lf_edit_instruction": res["lf_edit_instruction"],
            "lf_edit_references": s["characters_present"],
            "motion_prompt": res["motion_prompt"],
            "overrides": {
                "segment_duration": res["duration_seconds"]
            }
        })

    # Group into scenes
    scenes_map = {}
    for es, s in zip(estimated_shots, shots):
        scene_id = s["scene_id"]
        if scene_id not in scenes_map:
            scenes_map[scene_id] = {
                "scene_id": scene_id,
                "scene_title": f"Scene {scene_id}",
                "scene_summary": f"Sequence of shots for scene {scene_id}",
                "shots": []
            }
        scenes_map[scene_id]["shots"].append(es)
        
    scenes_list = [scenes_map[k] for k in sorted(scenes_map.keys())]

    # Generate cinematic_prompt.json
    cinematic_prompt = {
        "version": "3.0",
        "pipeline": "cinematic-v2",
        "models": {
            "character_sheet_generator": "ideogram-4-t2i",
            "scene_generator": "ideogram-4-t2i",
            "consistency_editor": "flux-2-klein-image-edit",
            "video_engine": "ltx-23-fflf-seed-hunter"
        },
        "global": {
            "style": "Cinematic 3D Pixar-style, soft volumetric lighting, warm color palette",
            "resolution_preset": "1080p",
            "fps": 25,
            "segment_duration": 5,
            "overlap_seconds": 1.0,
            "input_ref_strength": 0.8,
            "end_ref_strength": 0.8,
            "seed_base": 42,
            "auto_select_motion": True,
            "max_continuous_shots": 3,
            "quality_gate": {
                "enabled": True,
                "provider": "openrouter",
                "min_composition_score": 7,
                "min_identity_score": 7,
                "min_motion_score": 7
            },
            "prompt_enhancer": {
                "enabled": True,
                "provider": "openrouter",
                "model": "google/gemini-3.1-flash-lite",
                "fallback_model": "openai/gpt-4o-mini",
                "cache_prompts": True,
                "cache_dir": "enhanced_prompts"
            }
        },
        "characters": [
            {
                "id": "bramble",
                "display_name": "Bramble the baby rabbit",
                "description": "A tiny cute baby rabbit with soft brown fur, oversized floppy ears, large dark expressive eyes, and a fuzzy white tail",
                "style_notes": "3D Pixar-style rendering, soft fur rendering, chibi proportions, large head-to-body ratio",
                "edit_prompt_descriptor": "the baby rabbit with oversized floppy ears",
                "character_sheet_path": None,
                "character_sheet_prompt": "Professional character reference sheet for Bramble the baby rabbit. Front view, 3/4 view, and side profile. A tiny cute baby rabbit with soft brown fur, oversized floppy ears, large dark expressive eyes, and a fuzzy white tail. Clean plain light-grey background, studio lighting, 3D Pixar-style rendering."
            },
            {
                "id": "clover",
                "display_name": "Clover the mother rabbit",
                "description": "A gentle adult female rabbit with soft grey fur, wearing a tiny knitted green collar around her neck, kind dark eyes",
                "style_notes": "3D Pixar-style rendering, gentle features, soft grey fur",
                "edit_prompt_descriptor": "the grey mother rabbit wearing a green collar",
                "character_sheet_path": None,
                "character_sheet_prompt": "Professional character reference sheet for Clover the mother rabbit. Front view, 3/4 view, and side profile. A gentle adult female rabbit with soft grey fur, wearing a tiny knitted green collar around her neck, kind dark eyes. Clean plain light-grey background, studio lighting, 3D Pixar-style rendering."
            },
            {
                "id": "hazel",
                "display_name": "Hazel the father rabbit",
                "description": "A sturdy adult male rabbit with thick brown fur, strong build, intelligent eyes",
                "style_notes": "3D Pixar-style rendering, sturdy build, strong features, thick brown fur",
                "edit_prompt_descriptor": "the sturdy brown father rabbit",
                "character_sheet_path": None,
                "character_sheet_prompt": "Professional character reference sheet for Hazel the father rabbit. Front view, 3/4 view, and side profile. A sturdy adult male rabbit with thick brown fur, strong build, intelligent eyes. Clean plain light-grey background, studio lighting, 3D Pixar-style rendering."
            }
        ],
        "director_plan": {
            "story_summary": "A young rabbit named Bramble gets trapped in the forest roots, and is later rescued and reunited with his parents Clover and Hazel.",
            "total_scenes": len(scenes_list),
            "scenes": scenes_list
        }
    }
    
    # Save cinematic_prompt.json
    prompt_out_path = os.path.join(story_dir, "cinematic_prompt.json")
    with open(prompt_out_path, "w", encoding="utf-8") as f:
        json.dump(cinematic_prompt, f, indent=2)
    print(f"🎉 Saved cinematic_prompt.json to {prompt_out_path}")
    
    # Generate director_log.json
    director_log = {
        "created_at": "2026-06-16T14:00:00Z",
        "agent_model": "gpt-4o-mini",
        "story_source": "Story.md",
        "total_scenes": len(scenes_list),
        "total_shots": len(shots),
        "decisions": director_decisions,
        "prompt_rationale": prompt_rationale,
        "character_design_notes": {
            "bramble": "Oversized floppy ears and fuzzy white tail acts as a strong consistency edit anchor.",
            "clover": "Knitted green collar provides an explicit visual signature.",
            "hazel": "Sturdy brown body provides identity separation from Bramble."
        }
    }
    
    # Save director_log.json
    log_out_path = os.path.join(story_dir, "director_log.json")
    with open(log_out_path, "w", encoding="utf-8") as f:
        json.dump(director_log, f, indent=2)
    print(f"🎉 Saved director_log.json to {log_out_path}")

if __name__ == "__main__":
    main()
