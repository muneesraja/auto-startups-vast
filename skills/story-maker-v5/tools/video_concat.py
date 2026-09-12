import os
import subprocess
from pathlib import Path


def concat_videos(video_paths: list[str], output_path: str) -> dict:
    """Concatenate shot videos in order into one film.

    Tries a stream-copy concat first (all clips come from the same H3 render
    pipeline, so codecs/parameters normally match — this avoids a re-encode
    generation of quality loss). Falls back to libx264/aac re-encode when the
    copy fails.
    """
    existing = [p for p in video_paths if p and os.path.isfile(p)]
    if not existing:
        return {"status": "error", "message": "No video files to concatenate."}

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    list_path = str(Path(output_path).with_suffix(".concat.txt"))

    with open(list_path, "w", encoding="utf-8") as f:
        for path in existing:
            escaped = path.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    copy_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    reencode_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        result = subprocess.run(copy_cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0 or not os.path.isfile(output_path):
            # Stream copy failed (codec/param mismatch) — re-encode.
            try:
                if os.path.isfile(output_path):
                    os.remove(output_path)
            except OSError:
                pass
            result = subprocess.run(reencode_cmd, capture_output=True, text=True, timeout=600)
            if result.returncode != 0:
                return {
                    "status": "error",
                    "message": f"ffmpeg concat failed: {result.stderr[-500:]}",
                }
        if not os.path.isfile(output_path):
            return {"status": "error", "message": "ffmpeg completed but output missing."}
        return {
            "status": "success",
            "output_path": output_path,
            "segment_count": len(existing),
        }
    except Exception as e:
        return {"status": "error", "message": f"ffmpeg concat failed: {e}"}
    finally:
        try:
            os.remove(list_path)
        except OSError:
            pass
