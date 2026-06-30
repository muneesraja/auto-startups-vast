import os

import fal_client
import httpx

import config

NO_TEXT_CLAUSE = (
    " No text, no captions, no subtitles, no title cards, no watermark, "
    "no logos, no letters, no words, no numbers, no UI overlays."
)


def _grok_resolution() -> str:
    return os.getenv("GROK_IMAGE_RESOLUTION", "1k")


def _ensure_no_text(prompt: str) -> str:
    lower = prompt.lower()
    if "no text" in lower or "no captions" in lower or "no subtitles" in lower:
        return prompt
    return prompt.rstrip() + NO_TEXT_CLAUSE


def generate_grok_t2i(
    prompt: str, output_path: str, resolution: str | None = None
) -> dict:
    """Generate an image with xai/grok-imagine-image via fal.ai."""
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    if not os.environ.get("FAL_KEY"):
        return {"status": "error", "message": "FAL_KEY is not set in environment or config."}

    resolution = resolution or _grok_resolution()
    final_prompt = _ensure_no_text(prompt)

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        result = fal_client.subscribe(
            "xai/grok-imagine-image",
            arguments={
                "prompt": final_prompt,
                "num_images": 1,
                "resolution": resolution,
                "aspect_ratio": "16:9",
                "output_format": "png",
            },
        )
        images = result.get("images", [])
        if not images:
            return {
                "status": "error",
                "message": f"Grok T2I returned no images: {result}",
            }

        image_url = images[0]["url"]
        resp = httpx.get(image_url, timeout=120.0)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)

        return {
            "status": "success",
            "generated_image_path": output_path,
            "fal_image_url": image_url,
            "revised_prompt": result.get("revised_prompt"),
        }
    except Exception as e:
        return {"status": "error", "message": f"Grok T2I failed: {e}"}


def generate_grok_edit(
    prompt: str,
    image_urls: list[str],
    output_path: str,
    resolution: str | None = None,
) -> dict:
    """Generate an edited image with xai/grok-imagine-image/edit via fal.ai."""
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    if not os.environ.get("FAL_KEY"):
        return {"status": "error", "message": "FAL_KEY is not set in environment or config."}
    if not image_urls:
        return {"status": "error", "message": "Grok Edit requires at least one reference image URL."}

    resolution = resolution or _grok_resolution()
    final_prompt = _ensure_no_text(prompt)

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        result = fal_client.subscribe(
            "xai/grok-imagine-image/edit",
            arguments={
                "prompt": final_prompt,
                "image_urls": image_urls,
                "num_images": 1,
                "resolution": resolution,
                "aspect_ratio": "16:9",
                "output_format": "png",
            },
        )
        images = result.get("images", [])
        if not images:
            return {
                "status": "error",
                "message": f"Grok Edit returned no images: {result}",
            }

        image_url = images[0]["url"]
        resp = httpx.get(image_url, timeout=120.0)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)

        return {
            "status": "success",
            "generated_image_path": output_path,
            "fal_image_url": image_url,
            "revised_prompt": result.get("revised_prompt"),
        }
    except Exception as e:
        return {"status": "error", "message": f"Grok Edit failed: {e}"}
