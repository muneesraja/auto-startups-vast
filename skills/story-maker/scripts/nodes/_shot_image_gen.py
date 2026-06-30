"""Shared shot image generation helpers."""
from __future__ import annotations

import asyncio
import os
import re

from tools.fal_tools import generate_grok_edit, generate_grok_t2i

_REF_PATTERN = re.compile(r"\{\{+([^}]+)\}\}+")
_MAX_RETRIES = 3


def resolve_ref(ref_str: str, specs: dict) -> str:
    if not isinstance(ref_str, str):
        return ref_str
    match = _REF_PATTERN.search(ref_str)
    if not match:
        return ref_str
    parts = match.group(1).strip().split(".")
    if len(parts) != 3:
        return ref_str
    namespace, key, field = parts
    val = specs.get(namespace, {}).get(key, {}).get(field)
    if not val:
        raise KeyError(f"Unresolved reference: {ref_str}")
    return val


async def retry_async(fn, label: str):
    last_err = None
    for attempt in range(1, _MAX_RETRIES + 1):
        result = await asyncio.to_thread(fn)
        if result.get("status") == "success":
            return result
        last_err = result.get("message", "unknown error")
        print(f"   Retry {attempt}/{_MAX_RETRIES} {label}: {last_err}")
        await asyncio.sleep(2 * attempt)
    raise RuntimeError(f"{label} failed: {last_err}")


async def generate_one_shot_image(
    shot_id: str,
    entry: dict,
    specs: dict,
    images_dir: str,
) -> None:
    """Generate or regenerate a single shot still; mutates entry in place."""
    out_path = os.path.join(images_dir, f"{shot_id}.png")
    mode = entry.get("generation_mode", "grok_edit")
    prompt = entry.get("image_prompt", "")
    print(f"  Shot image: {shot_id} ({mode})")

    if mode == "grok_t2i":
        def _gen(p=prompt, path=out_path):
            return generate_grok_t2i(p, path)

        result = await retry_async(_gen, f"shot t2i {shot_id}")
    else:
        ref_urls = [resolve_ref(ref, specs) for ref in entry.get("reference_images", [])]
        if not ref_urls:
            print(f"    No refs for {shot_id}; falling back to grok_t2i")

            def _gen(p=prompt, path=out_path):
                return generate_grok_t2i(p, path)

            result = await retry_async(_gen, f"shot t2i {shot_id}")
        else:
            def _gen(p=prompt, urls=ref_urls, path=out_path):
                return generate_grok_edit(p, urls, path)

            result = await retry_async(_gen, f"shot edit {shot_id}")

    entry["output_path"] = result["generated_image_path"]
    entry["fal_image_url"] = result["fal_image_url"]
    if result.get("revised_prompt"):
        entry["revised_prompt"] = result["revised_prompt"]
    entry["status"] = "completed"
    entry.pop("image_qa_status", None)
    entry.pop("image_qa_reason", None)
