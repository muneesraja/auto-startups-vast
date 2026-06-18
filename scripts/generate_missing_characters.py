import os
import json
import ssl
import urllib.request
import re
from dotenv import load_dotenv

workspace_root = "/Users/muneesraja/projects/brainstorm/aurora"
dotenv_path = os.path.join(workspace_root, ".env")
load_dotenv(dotenv_path)

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")

def call_minimax(system_prompt, user_prompt):
    url = "https://api.minimax.io/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {MINIMAX_API_KEY}"
    }
    
    data = {
        "model": "MiniMax-M2.7-highspeed",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.2
    }

    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST")
    context = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, timeout=60, context=context) as response:
            body = response.read().decode("utf-8")
            res_json = json.loads(body)
            content = res_json["choices"][0]["message"]["content"]
            return content
    except Exception as e:
        print(f"Error calling MiniMax: {e}")
        return None

def clean_json_str(s):
    if not s:
        return {}
    s = s.strip()
    # Remove potential think blocks
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
    s = re.sub(r"<thought>.*?</thought>", "", s, flags=re.DOTALL).strip()
    
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()
    
    start_idx = s.find('{')
    end_idx = s.rfind('}')
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        s = s[start_idx:end_idx+1]
        
    try:
        return json.loads(s)
    except Exception as e:
        print(f"Error parsing JSON: {e}\nRaw: {s[:200]}...")
        return {}

def main():
    blueprint_path = "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-deterministic/leo_adventure/director_visual_blueprint.json"
    prompts_path = "/Users/muneesraja/Documents/growthlabs-vault/story-to-video-deterministic/leo_adventure/prompts.json"
    
    if not os.path.exists(blueprint_path) or not os.path.exists(prompts_path):
        print("Required files not found!")
        return

    with open(blueprint_path, "r", encoding="utf-8") as f:
        blueprint = json.load(f)

    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    # Read the system prompt for character sheet prompter
    system_prompt_path = os.path.join(workspace_root, "skills", "story-to-video-deterministic", "system_prompts", "character_sheet_prompter.md")
    with open(system_prompt_path, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # We want to generate prompts for char_01, char_02, char_03, char_04
    characters = blueprint.get("characters", [])
    
    if "character_sheets" not in prompts:
        prompts["character_sheets"] = {}

    for char in characters:
        char_id = char["id"]
        char_name = char["name"]
        char_appearance = char.get("appearance", "")
        
        # Check if already generated in prompts
        if char_id in prompts["character_sheets"] and prompts["character_sheets"][char_id].get("status") == "generated":
            print(f"Skipping {char_id} ({char_name}), already generated.")
            continue
            
        print(f"Generating prompt for {char_id} ({char_name})...")
        
        user_prompt = (
            f"Here is the character to generate a sheet for:\n"
            f"Character ID: {char_id}\n"
            f"Name: {char_name}\n"
            f"Appearance: {char_appearance}\n\n"
            f"Aesthetic notes from visual blueprint: Pixar/Disney 3D animated movie style.\n\n"
            f"Generate a valid Ideogram 4 JSON prompt for this character turnaround using the bounding box template. "
            f"Return ONLY the JSON object matching the template. No markdown backticks, no comments."
        )
        
        raw_res = call_minimax(system_prompt, user_prompt)
        if raw_res:
            parsed_prompt = clean_json_str(raw_res)
            if parsed_prompt:
                # Structure it like step3_character_prompter output
                prompts["character_sheets"][char_id] = {
                    "prompt_type": "ideogram_json",
                    "prompt": parsed_prompt,
                    "output_path": None,
                    "status": "pending",
                    "generated_by": "generate_missing_characters_script"
                }
                print(f"Successfully added prompt for {char_id}.")
            else:
                print(f"Failed to parse prompt for {char_id}.")
        else:
            print(f"Failed to get prompt from MiniMax for {char_id}.")

    # Save prompts.json
    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2, ensure_ascii=False)
    print("Successfully updated prompts.json on disk!")

if __name__ == "__main__":
    main()
