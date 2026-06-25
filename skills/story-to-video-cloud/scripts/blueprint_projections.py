import json

def project_for_character_prompter(blueprint: dict) -> str:
    """Step 3 Character Sheet Prompter needs:
    - meta (style, aesthetic)
    - characters list (id, name, appearance)
    """
    projected = {
        "meta": {
            "style": blueprint.get("meta", {}).get("style"),
            "aesthetic": blueprint.get("meta", {}).get("aesthetic"),
        },
        "characters": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "appearance": c.get("appearance"),
            }
            for c in blueprint.get("characters", [])
        ]
    }
    return json.dumps(projected, indent=2, ensure_ascii=False)

def project_for_spatial_mapper(blueprint: dict) -> str:
    """Step 4.5 Char Spatial Mapper needs:
    - per-shot: shot_id, characters_present, ff.description, lf.description, continuation_from_previous
    """
    projected_scenes = []
    for scene in blueprint.get("scenes", []):
        projected_shots = []
        for shot in scene.get("shots", []):
            projected_shots.append({
                "shot_id": shot.get("shot_id"),
                "continuation_from_previous": shot.get("continuation_from_previous"),
                "characters_present": shot.get("characters_present", []),
                "ff": {
                    "description": shot.get("ff", {}).get("description"),
                },
                "lf": {
                    "description": shot.get("lf", {}).get("description"),
                }
            })
        projected_scenes.append({
            "scene_id": scene.get("scene_id"),
            "shots": projected_shots
        })
    
    projected = {
        "scenes": projected_scenes
    }
    return json.dumps(projected, indent=2, ensure_ascii=False)

def project_for_ff_prompter(blueprint: dict) -> str:
    """Step 4 FF Prompter needs:
    - characters (id, name, appearance) for reference mapping
    - per-scene: environment, time_of_day, lighting
    - per-shot: shot_id, characters_present, continuation_from_previous,
      ff.description, ff.camera_framing, ff.character_expressions
    """
    projected_scenes = []
    for scene in blueprint.get("scenes", []):
        projected_shots = []
        for shot in scene.get("shots", []):
            projected_shots.append({
                "shot_id": shot.get("shot_id"),
                "continuation_from_previous": shot.get("continuation_from_previous"),
                "characters_present": shot.get("characters_present", []),
                "ff": {
                    "description": shot.get("ff", {}).get("description"),
                    "camera_framing": shot.get("ff", {}).get("camera_framing"),
                    "character_expressions": shot.get("ff", {}).get("character_expressions", {}),
                }
            })
        projected_scenes.append({
            "scene_id": scene.get("scene_id"),
            "environment": scene.get("environment"),
            "time_of_day": scene.get("time_of_day"),
            "lighting": scene.get("lighting"),
            "shots": projected_shots
        })
    
    projected = {
        "characters": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "appearance": c.get("appearance"),
            }
            for c in blueprint.get("characters", [])
        ],
        "scenes": projected_scenes
    }
    return json.dumps(projected, indent=2, ensure_ascii=False)

def project_for_lf_delta_planner(blueprint: dict) -> str:
    """Step 5 LF Delta Planner needs:
    - per-shot: shot_id, duration_seconds, continuation_from_previous,
      ff.description, lf.description
    """
    projected_scenes = []
    for scene in blueprint.get("scenes", []):
        projected_shots = []
        for shot in scene.get("shots", []):
            projected_shots.append({
                "shot_id": shot.get("shot_id"),
                "duration_seconds": shot.get("duration_seconds"),
                "continuation_from_previous": shot.get("continuation_from_previous"),
                "ff": {
                    "description": shot.get("ff", {}).get("description"),
                },
                "lf": {
                    "description": shot.get("lf", {}).get("description"),
                }
            })
        projected_scenes.append({
            "scene_id": scene.get("scene_id"),
            "shots": projected_shots
        })
    
    projected = {
        "scenes": projected_scenes
    }
    return json.dumps(projected, indent=2, ensure_ascii=False)

def project_for_lf_prompter(blueprint: dict) -> str:
    """Step 5.5 LF Prompter needs:
    - characters (id, name, appearance) for reference mapping
    - per-scene: environment, time_of_day, lighting
    - per-shot: shot_id, characters_present, use_ff_as_lf_reference, continuation_from_previous,
      lf.description, lf.camera_framing, lf.character_expressions, lf.delta_from_ff
    """
    projected_scenes = []
    for scene in blueprint.get("scenes", []):
        projected_shots = []
        for shot in scene.get("shots", []):
            raw_delta = shot.get("lf", {}).get("delta_from_ff", {})
            if isinstance(raw_delta, dict):
                delta = {
                    "camera_change": raw_delta.get("camera_change"),
                    "subject_changes": raw_delta.get("subject_changes"),
                    "environment_changes": raw_delta.get("environment_changes"),
                    "particle_effects": raw_delta.get("particle_effects"),
                }
            else:
                delta = raw_delta
                
            projected_shots.append({
                "shot_id": shot.get("shot_id"),
                "continuation_from_previous": shot.get("continuation_from_previous"),
                "use_ff_as_lf_reference": shot.get("use_ff_as_lf_reference", False),
                "characters_present": shot.get("characters_present", []),
                "lf": {
                    "description": shot.get("lf", {}).get("description"),
                    "camera_framing": shot.get("lf", {}).get("camera_framing"),
                    "character_expressions": shot.get("lf", {}).get("character_expressions", {}),
                    "delta_from_ff": delta,
                }
            })
        projected_scenes.append({
            "scene_id": scene.get("scene_id"),
            "environment": scene.get("environment"),
            "time_of_day": scene.get("time_of_day"),
            "lighting": scene.get("lighting"),
            "shots": projected_shots
        })
        
    projected = {
        "characters": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "appearance": c.get("appearance"),
            }
            for c in blueprint.get("characters", [])
        ],
        "scenes": projected_scenes
    }
    return json.dumps(projected, indent=2, ensure_ascii=False)

def project_for_motion_prompter(blueprint: dict) -> str:
    """Step 6 Motion Prompter needs:
    - meta.style for style hints
    - characters (id, name)
    - per-shot: shot_id, duration_seconds, characters_present, director_notes,
      ff.description, lf.description
    """
    projected_scenes = []
    for scene in blueprint.get("scenes", []):
        projected_shots = []
        for shot in scene.get("shots", []):
            projected_shots.append({
                "shot_id": shot.get("shot_id"),
                "duration_seconds": shot.get("duration_seconds"),
                "characters_present": shot.get("characters_present", []),
                "director_notes": shot.get("director_notes"),
                "ff": {
                    "description": shot.get("ff", {}).get("description"),
                },
                "lf": {
                    "description": shot.get("lf", {}).get("description"),
                }
            })
        projected_scenes.append({
            "scene_id": scene.get("scene_id"),
            "shots": projected_shots
        })
        
    projected = {
        "meta": {
            "style": blueprint.get("meta", {}).get("style"),
        },
        "characters": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
            }
            for c in blueprint.get("characters", [])
        ],
        "scenes": projected_scenes
    }
    return json.dumps(projected, indent=2, ensure_ascii=False)
