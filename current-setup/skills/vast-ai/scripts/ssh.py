#!/usr/bin/env python3
"""
ssh.py — SSH key management and command building for Vast.ai instances.
"""

import os
import sys

# Ensure sibling modules are importable when loaded standalone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import log, run_cmd

# Module-level SSH key path — set by detect_ssh_key() or main()
SSH_KEY_PATH: str = ""


def get_fallback_pubkey_b64() -> str:
    """Return base64-encoded fallback public key for env injection."""
    fallback_pub = os.path.expanduser("~/.ssh/vast_fallback.pub")
    if not os.path.exists(fallback_pub):
        return ""
    import base64
    with open(fallback_pub, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def generate_fallback_key() -> str:
    """Generate the fallback SSH key if missing."""
    key_path = os.path.expanduser("~/.ssh/vast_fallback")
    if os.path.exists(key_path) and os.path.exists(key_path + ".pub"):
        return key_path
    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True)
    gen_result = run_cmd(
        "ssh-keygen -t ed25519 -f ~/.ssh/vast_fallback -N '' -C 'vast-fallback'",
        timeout=30
    )
    if gen_result["code"] != 0:
        log("⚠️", f"Fallback SSH key generation failed: {gen_result['stderr']}")
        return ""
    log("✅", "Generated fallback SSH key at ~/.ssh/vast_fallback")
    return key_path


def detect_ssh_key(vast_client) -> str:
    """Detect or generate SSH key for Vast.ai.

    Priority:
    1. ~/.ssh/vast_fallback (guaranteed — injected into every instance)
    2. ~/.ssh/vast_ai_dedicated (registered with Vast.ai dashboard)
    3. ~/.ssh/id_ed25519 (default system key)

    Args:
        vast_client: Initialized VastAI client instance.

    Returns validated key path or raises exception.
    """
    global SSH_KEY_PATH

    # Step 0: Fallback key (our guaranteed access — ALWAYS works on instances
    # where we inject the pubkey in fast-provision.sh)
    fallback_key = os.path.expanduser("~/.ssh/vast_fallback")
    if os.path.exists(fallback_key):
        log("✅", "Using fallback SSH key at ~/.ssh/vast_fallback")
        SSH_KEY_PATH = fallback_key
        return fallback_key

    # Step 1: Vast.ai registered keys
    dedicated_key = os.path.expanduser("~/.ssh/vast_ai_dedicated")
    default_key = os.path.expanduser("~/.ssh/id_ed25519")

    key_to_try = None
    if os.path.exists(dedicated_key) and os.path.exists(dedicated_key + ".pub"):
        log("ℹ️", "Found dedicated Vast.ai key at ~/.ssh/vast_ai_dedicated")
        key_to_try = dedicated_key
    elif os.path.exists(default_key) and os.path.exists(default_key + ".pub"):
        log("ℹ️", "Found default SSH key at ~/.ssh/id_ed25519")
        key_to_try = default_key

    if key_to_try:
        pub_path = key_to_try + ".pub"
        if os.path.exists(pub_path):
            try:
                local_pub = open(pub_path).read().strip()
                registered_keys = vast_client.show_ssh_keys()
                for key_info in registered_keys:
                    if isinstance(key_info, dict) and key_info.get("public_key", "") == local_pub:
                        log("✅", f"SSH key {key_to_try} matched Vast.ai registered key")
                        SSH_KEY_PATH = key_to_try
                        return key_to_try
                log("⚠️", f"Key at {key_to_try} not found in Vast.ai registered keys - will register it")
            except Exception as e:
                log("⚠️", f"Could not validate SSH key against Vast.ai: {e} - using existing key")
                SSH_KEY_PATH = key_to_try
                return key_to_try

    # Step 2: Generate new dedicated key if no match
    log("⚠️", "No matching SSH key found - generating new dedicated key for Vast.ai")
    log("⚠️", "IMPORTANT: OLD instances will NOT have this key")

    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True)

    gen_result = run_cmd(
        "ssh-keygen -t ed25519 -f ~/.ssh/vast_ai_dedicated -N '' -C 'aurora-vast-dedicated'",
        timeout=30
    )
    if gen_result["code"] != 0:
        raise RuntimeError(f"SSH key generation failed: {gen_result['stderr']}")
    log("✅", "Generated new SSH key at ~/.ssh/vast_ai_dedicated")

    pub_key_path = os.path.expanduser("~/.ssh/vast_ai_dedicated.pub")
    with open(pub_key_path, "r") as f:
        pub_key = f.read().strip()

    log("📋", "Registering new key with Vast.ai...")
    try:
        reg_result = vast_client.create_ssh_key("aurora-vast-dedicated", pub_key)
        log("✅", f"SSH key registered with Vast.ai: {reg_result}")
    except Exception as e:
        log("⚠️", f"Could not register SSH key with Vast.ai: {e}")

    SSH_KEY_PATH = dedicated_key
    return dedicated_key


def setup_ssh_config():
    """Add SSH config entry for Vast.ai hosts to use dedicated key automatically."""
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    os.makedirs(os.path.dirname(ssh_config_path), exist_ok=True)

    # Check if entry already exists
    if os.path.exists(ssh_config_path):
        with open(ssh_config_path, "r") as f:
            existing = f.read()
        if "Host ssh*.vast.ai" in existing:
            log("ℹ️", "SSH config entry for ssh*.vast.ai already exists")
            return

    # Add new entry
    with open(ssh_config_path, "a") as f:
        f.write("\n# Vast.ai dedicated SSH key configuration\n")
        f.write("Host ssh*.vast.ai\n")
        f.write(f"    IdentityFile {os.path.expanduser('~/.ssh/vast_ai_dedicated')}\n")
    log("✅", "Added SSH config entry for ssh*.vast.ai hosts")


def build_ssh_cmd(ssh_host: str, ssh_port: str, ssh_key_path: str) -> str:
    """Build SSH command string with key, host key checking disabled, and port."""
    key_param = f"-i {ssh_key_path}" if ssh_key_path else ""
    return f"ssh {key_param} -o StrictHostKeyChecking=no -o ConnectTimeout=10 -p {ssh_port} root@{ssh_host}"
