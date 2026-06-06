#!/usr/bin/env python3
"""Debug evaluation for scene_004_shot004."""
import os
import json

# Load API key from .env file
env_path = '/root/.hermes/.env'
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key] = val

from gemini_eval import resolve_provider, call_openrouter_vision, parse_eval_response, build_eval_prompt, compute_weighted_score

CHARS_DIR = '/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun/characters'
image_path = '/root/Syncthing/obsidian-vault/growthlabs-docs/story-to-video/pluffy-bun/scenes/scene_004_shot004_00006_.png'

ref_names = ['puffy_reference_sheet_final.png', 'jalapeno_reference_sheet_v4.png']
ref_paths = [os.path.join(CHARS_DIR, r) for r in ref_names]

eval_context = {
    'characters_present': ['puffy', 'jalapeno'],
    'setting': 'Cream World village',
    'action': 'General Jalapeno watches chaos as soldiers bounced by fluffy bun',
    'mood': 'shocked, comedic',
    'expected_expressions': {'jalapeno': 'furious disbelief, jaw clenched'}
}
prompt_text = 'Characters must match reference images.'

eval_prompt = build_eval_prompt(eval_context, prompt_text, reference_names=ref_names)

print('=== Evaluation Debug ===')
print(f'Generated image: {os.path.basename(image_path)} ({os.path.getsize(image_path)/1024:.0f} KB)')
print(f'Reference images: {len(ref_paths)}')
for i, (name, path) in enumerate(zip(ref_names, ref_paths)):
    print(f'  {i+2}. {name} ({os.path.getsize(path)/1024:.0f} KB)')
print()

provider_name, api_key, call_fn = resolve_provider('openrouter')
print(f'Provider: {provider_name}, Key length: {len(api_key)}')
print()

response = call_fn(eval_prompt, image_path, api_key, reference_images=ref_paths)

reasoning = ''
if isinstance(response, dict):
    reasoning = response.get('reasoning', '')
    response_text = response['response']
else:
    response_text = response

print(f'Response length: {len(response_text)} chars')
print()

result = parse_eval_response(response_text)
if result:
    scores = result.get('category_scores', {})
    weighted = compute_weighted_score(scores)
    print(f'Scores: {scores}')
    print(f'Weighted: {weighted:.2f}/10')
    print(f'Passed: {result.get("passed", False)}')
    if result.get('issues'):
        print(f'Issues: {result["issues"][:3]}')
else:
    print('PARSE FAILED')
    print(f'Raw: {response_text[:500]}')
