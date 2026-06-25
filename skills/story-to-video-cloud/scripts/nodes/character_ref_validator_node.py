import os
import json
import re
import asyncio
import litellm

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

from ._json_util import clean_json_str

# System Prompt for Gemini reasoning
SYSTEM_PROMPT = """You are a precision video pipeline validator. Your job is to determine if a specific character is present/described in a shot's prompt.

You will be given:
1. The shot prompt text.
2. The character's name and appearance description.

Analyze the prompt text to see if it mentions or clearly describes the character (either by name, species, or appearance description keywords). 
Be careful: sometimes nouns in the prompt might match the character's keyword, but actually refer to something else in the environment (e.g. 'a tree branch' vs a bird character named 'Branch', or 'wildflowers' vs a character named 'Flower').

Return a JSON object in this format:
{
  "should_reference": true or false,
  "explanation": "Brief explanation of why"
}
"""

def extract_keywords(char_name: str, appearance: str) -> list[str]:
    if not appearance:
        return []
    desc_lower = appearance.lower()
    split_words = [" with ", " in ", " at ", " on ", " wearing ", " holding ", " peeking ", " standing ", " sitting ", " lying ", " running ", " walking ", " silhouette ", " profile "]
    main_phrase = desc_lower
    for sw in split_words:
        if sw in desc_lower:
            main_phrase = desc_lower.split(sw)[0]
            break

    # Clean punctuation and tokenize
    words = re.findall(r"\b[a-z]{3,}\b", main_phrase)
    
    # Adjectives/stopwords to filter out
    adjectives_and_stopwords = {
        "a", "an", "the", "and", "or", "but", "chubby", "fluffy", "adorable", "sad", 
        "happy", "little", "big", "small", "young", "old", "cute", "scared", "excited", 
        "playful", "gentle", "whimsical", "soft", "beautiful", "charming", "tiny",
        "giant", "character", "sheet", "style", "render", "animated", "movie", "pixar",
        "disney", "storybook", "feel", "texture", "eyes", "nose", "ears", "mouth", "fur",
        "paw", "paws", "cream", "white", "black", "grey", "gray", "brown", "red", "green",
        "blue", "yellow", "orange", "purple", "color", "colored"
    }
    
    keywords = [w for w in words if w not in adjectives_and_stopwords]
    if not keywords:
        keywords = [w for w in words if w not in {"a", "an", "the", "and", "or", "but", "with", "in", "at", "on"}]
        
    # Also add the character's name itself
    name_words = re.findall(r"\b[a-z]{2,}\b", char_name.lower())
    return list(set(name_words + keywords))

async def llm_validate_presence(prompt_text: str, char_name: str, char_appearance: str) -> bool:
    """Query Gemini via LiteLLM to check if character is truly in the prompt."""
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")
    
    if openrouter_key:
        model_name = "openrouter/google/gemini-2.5-flash"
        api_key = openrouter_key
        api_base = "https://openrouter.ai/api/v1"
    elif gemini_key:
        model_name = "gemini/gemini-2.5-flash"
        api_key = gemini_key
        api_base = None
    else:
        print("⚠️ No API keys for validation LLM. Defaulting validation to True.")
        return True

    user_content = f"Shot Prompt: \"{prompt_text}\"\nCharacter Name: \"{char_name}\"\nCharacter Appearance: \"{char_appearance}\""
    
    try:
        response = await litellm.acompletion(
            model=model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            api_key=api_key,
            api_base=api_base,
            response_format={"type": "json_object"},
            timeout=10,
        )
        content = response.choices[0].message.content
        parsed = json.loads(content)
        should_ref = parsed.get("should_reference", False)
        print(f"🤖 [RefValidator LLM] Checked '{char_name}' presence: {should_ref}. Reason: {parsed.get('explanation')}")
        return should_ref
    except Exception as e:
        print(f"⚠️ Error during LLM validation call: {e}. Defaulting validation to True.")
        return True

async def run_character_ref_validator(ctx: Context) -> None:
    """Keyword-based character reference check with LLM validation.
    
    Ensures that for both FF and LF prompts:
    - If a character's keywords/name appears in the prompt, they are referenced.
    - If they are referenced but the LLM says they aren't actually in the prompt, they are removed.
    - Updates blueprint and prompts on disk/state to maintain absolute consistency.
    """
    output_dir = ctx.state.get("output_dir")
    if not output_dir:
        return

    blueprint_path = os.path.join(output_dir, "director_visual_blueprint.json")
    prompts_path = os.path.join(output_dir, "prompts.json")

    if not os.path.exists(blueprint_path) or not os.path.exists(prompts_path):
        print("⚠️ [RefValidator] Blueprint or prompts.json missing. Skipping reference check.")
        return

    with open(blueprint_path, "r", encoding="utf-8") as f:
        blueprint = json.load(f)
    with open(prompts_path, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    # 1. Map characters
    char_lookup = {c["id"]: c for c in blueprint.get("characters", [])}
    char_keywords = {
        cid: extract_keywords(c.get("name", ""), c.get("appearance", ""))
        for cid, c in char_lookup.items()
    }

    # Helper to find shot entry in blueprint
    def get_blueprint_shot(shot_id: str):
        for scene in blueprint.get("scenes", []):
            for shot in scene.get("shots", []):
                if shot.get("shot_id") == shot_id:
                    return shot
        return None

    # Track if anything changed
    changed_prompts = False
    changed_blueprint = False

    # Process FF and LF prompts
    for ns in ("ff_shots", "lf_shots"):
        shot_entries = prompts.get(ns, {})
        for shot_id, entry in shot_entries.items():
            if not isinstance(entry, dict):
                continue
            
            prompt_type = entry.get("prompt_type")
            if prompt_type == "extracted_frame":
                continue

            prompt_text = entry.get("prompt")
            if not prompt_text:
                continue

            bp_shot = get_blueprint_shot(shot_id)
            if not bp_shot:
                continue

            current_bp_chars = set(bp_shot.get("characters_present", []))
            refs = entry.get("reference_images") or []
            
            # Map of active referenced character sheets
            referenced_chars = set()
            for ref in refs:
                if ref.startswith("{{character_sheets.") and ref.endswith(".fal_image_url}}"):
                    char_id = ref.split(".")[1]
                    referenced_chars.add(char_id)

            # Pass 1: Check for keywords in prompt that are NOT currently referenced
            for cid, keywords in char_keywords.items():
                if cid in referenced_chars:
                    continue  # already referenced
                
                # Check if name or any keywords appear in the prompt
                prompt_lower = prompt_text.lower()
                matches = [kw for kw in keywords if kw in prompt_lower]
                if matches:
                    print(f"🔍 [RefValidator] Found potential match for '{char_lookup[cid]['name']}' in {shot_id} prompt: keywords {matches}")
                    # Validate with LLM
                    is_present = await llm_validate_presence(
                        prompt_text,
                        char_lookup[cid].get("name", ""),
                        char_lookup[cid].get("appearance", "")
                    )
                    if is_present:
                        current_bp_chars.add(cid)
                        # Add reference
                        ref_str = f"{{{{character_sheets.{cid}.fal_image_url}}}}"
                        if ref_str not in refs:
                            refs.append(ref_str)
                        changed_prompts = True
                        changed_blueprint = True

            # Pass 2: Check if referenced characters are NOT in prompt text (cov mismatch)
            # Run LLM check for any referenced character to confirm they are indeed described
            for cid in list(referenced_chars):
                prompt_lower = prompt_text.lower()
                # Run quick check if they appear to be mentioned
                keywords = char_keywords.get(cid, [])
                matches = [kw for kw in keywords if kw in prompt_lower]
                if not matches:
                    print(f"🔍 [RefValidator] Mismatch: '{char_lookup[cid]['name']}' is referenced in {shot_id} but name/keywords not found in prompt.")
                    # Ask LLM to confirm if they should be there
                    is_present = await llm_validate_presence(
                        prompt_text,
                        char_lookup[cid].get("name", ""),
                        char_lookup[cid].get("appearance", "")
                    )
                    if not is_present:
                        # Remove from reference list and blueprint
                        current_bp_chars.discard(cid)
                        ref_str = f"{{{{character_sheets.{cid}.fal_image_url}}}}"
                        if ref_str in refs:
                            refs.remove(ref_str)
                        changed_prompts = True
                        changed_blueprint = True

            # Update structures
            if changed_blueprint:
                bp_shot["characters_present"] = sorted(list(current_bp_chars))
            if changed_prompts:
                entry["reference_images"] = refs

    # Save changes to disk and state if modified
    if changed_blueprint:
        with open(blueprint_path, "w", encoding="utf-8") as f:
            json.dump(blueprint, f, indent=2, ensure_ascii=False)
        ctx.state["blueprint_json_content"] = blueprint
        print(f"💾 [RefValidator] Updated {blueprint_path}")

    if changed_prompts:
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(prompts, f, indent=2, ensure_ascii=False)
        # Update specific state sections
        ctx.state["ff_prompts_content"] = prompts["ff_shots"]
        ctx.state["lf_prompts_content"] = prompts["lf_shots"]
        print(f"💾 [RefValidator] Updated {prompts_path}")

character_ref_validator_node = FunctionNode(func=run_character_ref_validator, name="character_ref_validator_node")
