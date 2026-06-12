#!/usr/bin/env python3
"""
verify_profiles.py — Verify that all 6 STV profiles are correctly configured.
Checks:
1. .env existence and required keys
2. Skills symlinks
3. config.yaml provider settings
"""
import os
import sys
from pathlib import Path

REQUIRED_PROFILE_CONFIG = {
    "stv-director": {
        "skills": ["story-direction"],
        "env_keys": ["MINIMAX_API_KEY"]
    },
    "stv-t2i-writer": {
        "skills": ["flux-t2i-prompting"],
        "env_keys": ["MINIMAX_API_KEY"]
    },
    "stv-i2i-writer": {
        "skills": ["flux-edit-prompting"],
        "env_keys": ["MINIMAX_API_KEY"]
    },
    "stv-motion-writer": {
        "skills": ["ltx-motion-prompting"],
        "env_keys": ["MINIMAX_API_KEY"]
    },
    "stv-reviewer": {
        "skills": ["qc-image-review"],
        "env_keys": ["MINIMAX_API_KEY", "OPENROUTER_API_KEY"]
    },
    "stv-ops": {
        "skills": ["comfyui-ops", "story-to-video-filmmaking"],
        "env_keys": ["MINIMAX_API_KEY", "COMFYUI_URL", "COMFYUI_USER", "COMFYUI_PASS"]
    },
}

def load_env(env_path: Path) -> dict:
    """Load key-value pairs from .env file."""
    env = {}
    if not env_path.exists():
        return env
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env

def verify_profiles(verbose: bool = True) -> bool:
    """Hard gate: verify all 6 STV profiles are correctly configured.
    Returns True if all OK, False otherwise."""
    all_ok = True
    home_dir = Path.home()
    
    if verbose:
        print("=== STV Profile Pre-flight Gate ===")

    for profile, reqs in REQUIRED_PROFILE_CONFIG.items():
        profile_dir = home_dir / ".hermes" / "profiles" / profile
        
        # Check profile dir exists
        if not profile_dir.exists():
            if verbose:
                print(f"❌ Profile '{profile}': Directory {profile_dir} does not exist.")
            all_ok = False
            continue
            
        profile_ok = True
        errors = []
        
        # 1. Check .env exists and has required keys
        env_file = profile_dir / ".env"
        if not env_file.exists():
            profile_ok = False
            errors.append(f"Missing .env file (expected at {env_file})")
        else:
            env_vars = load_env(env_file)
            for key in reqs["env_keys"]:
                if key not in env_vars or not env_vars[key]:
                    profile_ok = False
                    errors.append(f"Missing or empty key '{key}' in .env")

        # 2. Check skills/ has required skills (symlinks/dirs)
        for skill in reqs["skills"]:
            # Skills usually reside in skills/creative/
            skill_path = profile_dir / "skills" / "creative" / skill
            if not skill_path.exists():
                profile_ok = False
                errors.append(f"Missing skill '{skill}' (expected at {skill_path})")

        # 3. Check config.yaml provider settings
        config_file = profile_dir / "config.yaml"
        if not config_file.exists():
            profile_ok = False
            errors.append(f"Missing config.yaml (expected at {config_file})")
        else:
            # We parse config.yaml. Let's try PyYAML first, fallback to regex.
            has_correct_provider = False
            try:
                import yaml
                with open(config_file, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f)
                    if config and isinstance(config, dict):
                        model_sec = config.get("model", {})
                        if isinstance(model_sec, dict) and model_sec.get("provider") == "custom:minimax-anthropic":
                            has_correct_provider = True
            except Exception:
                # Fallback to simple text search
                with open(config_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    if "provider: custom:minimax-anthropic" in content:
                        has_correct_provider = True
                        
            if not has_correct_provider:
                profile_ok = False
                errors.append("config.yaml model.provider is not set to 'custom:minimax-anthropic'")

        # Output results
        if profile_ok:
            if verbose:
                print(f"✅ Profile '{profile}': Fully configured.")
        else:
            all_ok = False
            if verbose:
                print(f"❌ Profile '{profile}': Configuration errors found:")
                for err in errors:
                    print(f"   - {err}")
                print(f"   💡 To fix: Check credentials and configuration in {profile_dir}")
                
    if verbose:
        print("===================================\n")
        
    return all_ok

if __name__ == "__main__":
    success = verify_profiles(verbose=True)
    sys.exit(0 if success else 1)
