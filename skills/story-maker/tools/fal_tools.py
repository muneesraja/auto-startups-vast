import os

import fal_client
import httpx

import config


def generate_grok_t2i(prompt: str, output_path: str, resolution: str = "1k") -> dict:
    """Generate an image with xai/grok-imagine-image via fal.ai."""
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    if not os.environ.get("FAL_KEY"):
        return {"status": "error", "message": "FAL_KEY is not set in environment or config."}

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        result = fal_client.subscribe(
            "xai/grok-imagine-image",
            arguments={
                "prompt": prompt,
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
        }
    except Exception as e:
        return {"status": "error", "message": f"Grok T2I failed: {e}"}


def generate_grok_edit(
    prompt: str, image_urls: list[str], output_path: str, resolution: str = "1k"
) -> dict:
    """Generate an edited image with xai/grok-imagine-image/edit via fal.ai."""
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    if not os.environ.get("FAL_KEY"):
        return {"status": "error", "message": "FAL_KEY is not set in environment or config."}
    if not image_urls:
        return {"status": "error", "message": "Grok Edit requires at least one reference image URL."}

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        result = fal_client.subscribe(
            "xai/grok-imagine-image/edit",
            arguments={
                "prompt": prompt,
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
        }
    except Exception as e:
        return {"status": "error", "message": f"Grok Edit failed: {e}"}
