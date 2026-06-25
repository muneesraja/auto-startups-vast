import os
import fal_client
import httpx
import config

def generate_grok_t2i(prompt: str, output_path: str, resolution: str = "1k") -> dict:
    """Generates an image using xai/grok-imagine-image via fal-client.
    Downloads the resulting image and saves it to output_path.
    """
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    if not os.environ.get("FAL_KEY"):
        return {"status": "error", "message": "FAL_KEY is not set in environment or config."}
        
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result = fal_client.subscribe(
            "xai/grok-imagine-image",
            arguments={
                "prompt": prompt,
                "num_images": 1,
                "resolution": resolution,
                "aspect_ratio": "16:9",
                "output_format": "png"
            }
        )
        images = result.get("images", [])
        if not images:
            return {"status": "error", "message": f"Grok T2I call succeeded but returned no images: {result}"}
            
        image_url = images[0]["url"]
        
        # Download the image
        resp = httpx.get(image_url, timeout=60.0)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
            
        return {
            "status": "success",
            "message": f"Successfully generated Grok T2I image: {output_path}",
            "generated_image_path": output_path,
            "fal_image_url": image_url
        }
    except Exception as e:
        return {"status": "error", "message": f"Grok T2I generation failed: {str(e)}"}

def generate_grok_edit(prompt: str, image_urls: list[str], output_path: str, resolution: str = "1k") -> dict:
    """Generates an image using xai/grok-imagine-image/edit via fal-client with reference image_urls.
    Downloads the resulting image and saves it to output_path.
    """
    if not os.environ.get("FAL_KEY"):
        os.environ["FAL_KEY"] = config.FAL_KEY or ""
    if not os.environ.get("FAL_KEY"):
        return {"status": "error", "message": "FAL_KEY is not set in environment or config."}
        
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result = fal_client.subscribe(
            "xai/grok-imagine-image/edit",
            arguments={
                "prompt": prompt,
                "image_urls": image_urls,
                "num_images": 1,
                "resolution": resolution,
                "aspect_ratio": "16:9",
                "output_format": "png"
            }
        )
        images = result.get("images", [])
        if not images:
            return {"status": "error", "message": f"Grok Edit call succeeded but returned no images: {result}"}
            
        image_url = images[0]["url"]
        
        # Download the image
        resp = httpx.get(image_url, timeout=60.0)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
            
        return {
            "status": "success",
            "message": f"Successfully generated Grok Edit image: {output_path}",
            "generated_image_path": output_path,
            "fal_image_url": image_url
        }
    except Exception as e:
        return {"status": "error", "message": f"Grok Edit generation failed: {str(e)}"}
