#!/usr/bin/env python3
"""Regenerate 3 failing shots with correct references from prompt.json."""
import os
import sys

# Load API key from .env file
env_path = '/root/.hermes/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val

import json
from comfyui_api import get_available_images
from generate_scene import load_prompts, generate_shot, evaluate_with_gemini
from workflow_builder import load_workflow_template

COMFYUI_URL = 'https://bowl-implications-adaptation-rising.trycloudflare.com'

# Read ComfyUI auth from file
auth_file = '/tmp/comfyui_auth.txt'
if os.path.exists(auth_file):
    with open(auth_file) as f:
        user, passwd = f.read().strip().split(':', 1)
    COMFYUI_AUTH = (user, passwd)
else:
    print("ComfyUI auth file not found")
    sys.exit(1)

CHARS_DIR = '/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun/characters'
PROMPT_PATH = '/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun/prompt.json'
SCENES_DIR = '/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun/scenes'

# Load prompt.json
prompts_data = load_prompts(PROMPT_PATH)
global_cfg = prompts_data['global']
workflow_template = load_workflow_template(prompts_data['workflow_template'])

# Get available images
available = get_available_images(COMFYUI_URL, auth=COMFYUI_AUTH)
print(f'Found {len(available)} images available')

# Upload character references if missing
from comfyui_api import upload_image
for ref in ['puffy_reference_sheet_final.png', 'jalapeno_reference_sheet_v4.png']:
    if ref not in available:
        ref_path = os.path.join(CHARS_DIR, ref)
        if os.path.exists(ref_path):
            result = upload_image(ref_path, COMFYUI_URL, auth=COMFYUI_AUTH)
            if result:
                available.add(ref)

# Only regenerate scene_004_shot004
refined_shots = {
    'scene_004_shot004': {
        'refined_prompt': 'Characters in this scene must match the provided reference images exactly: - Puffy (first reference): small round red bun, golden sheen, dot eyes, stubby limbs. - Jalapeno (second reference): large red chilli pepper, green stem hat, narrow eyes, sharp teeth. Scene: Puffy the red bun is the CENTRAL character, bouncing energetically through a formation of chilli pepper soldiers, sending them flying in all directions. Puffy is small, round, and red with a golden sheen. General Jalapeno stands behind the formation, his jaw clenched in furious disbelief, one eye twitching, brows pulled together in rage and shock. The setting is a pastel cream world with soft-serve hills. Camera: wide shot showing Puffy bouncing through soldiers with Jalapeno reacting. 3D Pixar-style animation, pastel color palette.',
    },
}

# Regenerate each shot
results = {}
for shot_prefix, refinements in refined_shots.items():
    shot_data = None
    for shot in prompts_data['shots']:
        if shot['filename_prefix'] == shot_prefix:
            shot_data = shot
            break

    if not shot_data:
        print(f'{shot_prefix}: Not found in prompt.json')
        continue

    refs = shot_data.get('references', [])
    shot_copy = {**shot_data, 'prompt': refinements['refined_prompt']}

    print(f'\n{"="*60}')
    print(f'Regenerating {shot_prefix}')
    print(f'References: {refs}')
    print(f'{"="*60}')

    image_path = generate_shot(
        shot_copy, global_cfg, workflow_template,
        COMFYUI_URL, SCENES_DIR, available,
        auth=COMFYUI_AUTH
    )

    if not image_path:
        print(f'Generation failed for {shot_prefix}')
        results[shot_prefix] = {'score': 0, 'passed': False, 'error': 'generation failed'}
        continue

    print(f'Generated: {image_path}')

    result = evaluate_with_gemini(
        image_path, shot_copy,
        provider='openrouter',
        references_base_dir=CHARS_DIR
    )

    if result:
        score = result.get('score', 0)
        passed = result.get('passed', False)
        results[shot_prefix] = {'score': score, 'passed': passed}
        print(f'Score: {score:.2f}/10 | {"PASS" if passed else "FAIL"}')
        if result.get('issues'):
            for issue in result['issues'][:3]:
                print(f'  Issue: {issue}')
    else:
        results[shot_prefix] = {'score': 0, 'passed': False, 'error': 'eval failed'}
        print('Evaluation failed')

print(f'\n{"="*60}')
print('REGENERATION SUMMARY')
print(f'{"="*60}')
for shot, data in results.items():
    status = 'PASS' if data.get('passed') else 'FAIL'
    print(f'{status} {shot}: {data.get("score", 0):.2f}/10')
