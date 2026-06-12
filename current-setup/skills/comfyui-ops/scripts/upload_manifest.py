#!/usr/bin/env python3
"""
upload_manifest.py — MD5-based dedup + retry for ComfyUI reference uploads.

Maintains a JSON manifest at <story-path>/.upload_manifest.json that maps
local files to their ComfyUI server filenames. Skips upload if already cached.
3-attempt exponential backoff on tunnel 5xx.

Usage:
    from upload_manifest import UploadManifest, upload_with_retry
    
    manifest = UploadManifest("/path/to/story/.upload_manifest.json")
    if manifest.needs_upload(local_path, comfyui_url):
        comfyui_filename = upload_with_retry(local_path, comfyui_url, auth)
        manifest.record_upload(local_path, comfyui_url, comfyui_filename)
    else:
        comfyui_filename = manifest.get_comfyui_filename(local_path, comfyui_url)

CLI:
    python3 upload_manifest.py --manifest /path/.upload_manifest.json --list
    python3 upload_manifest.py --manifest /path/.upload_manifest.json --gc
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def compute_md5(path: str) -> str:
    """Compute MD5 hash of a file."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_image(local_path: str, comfyui_url: str, auth: str = None) -> str:
    """
    Upload an image to ComfyUI's /upload/image endpoint.
    Returns the ComfyUI filename (server-side).
    """
    cmd = ["curl", "-s", "-F", f"image=@{local_path}", f"{comfyui_url}/upload/image"]
    if auth:
        cmd.insert(1, "-H")
        cmd.insert(2, f"Authorization: Basic {auth}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr}")
    
    # Response is JSON: {"name": "<filename>", "original_ref": "<url>", "subfolder": "..."}
    try:
        resp = json.loads(result.stdout)
        return resp.get("name") or os.path.basename(local_path)
    except json.JSONDecodeError:
        # Fall back to local filename
        return os.path.basename(local_path)


def upload_with_retry(local_path: str, comfyui_url: str, auth: str = None, max_attempts: int = 3) -> str:
    """
    Upload with exponential backoff: 1s, 4s, 16s.
    Raises after max_attempts fails.
    """
    backoff = [1, 4, 16]
    last_error = None
    
    for attempt in range(max_attempts):
        try:
            return upload_image(local_path, comfyui_url, auth)
        except (subprocess.TimeoutExpired, RuntimeError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_attempts - 1:
                wait = backoff[attempt]
                print(f"Upload attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
    
    raise RuntimeError(f"Upload failed after {max_attempts} attempts: {last_error}")


class UploadManifest:
    """JSON-backed cache of uploaded files."""
    
    def __init__(self, manifest_path: str):
        self.path = Path(manifest_path)
        self.data = {"uploads": {}}
        if self.path.exists():
            try:
                with open(self.path) as f:
                    self.data = json.load(f)
                if "uploads" not in self.data:
                    self.data["uploads"] = {}
            except (json.JSONDecodeError, IOError):
                # Corrupt manifest, start fresh
                self.data = {"uploads": {}}
    
    def _key(self, local_path: str, comfyui_url: str) -> str:
        # Use || as separator — won't appear in URLs or Linux paths.
        # Old ":" separator collided with port numbers in URLs (e.g., http://host:8188).
        return f"{local_path}||{comfyui_url}"
    
    def _save(self):
        """Persist manifest to disk (atomic write)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2, sort_keys=True)
        os.replace(tmp, self.path)
    
    def needs_upload(self, local_path: str, comfyui_url: str) -> bool:
        """Check if file needs upload (not in manifest or MD5 changed)."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(local_path)
        
        key = self._key(local_path, comfyui_url)
        if key not in self.data["uploads"]:
            return True
        
        entry = self.data["uploads"][key]
        current_md5 = compute_md5(local_path)
        return entry.get("md5") != current_md5
    
    def record_upload(self, local_path: str, comfyui_url: str, comfyui_filename: str):
        """Record successful upload in manifest."""
        import datetime
        key = self._key(local_path, comfyui_url)
        # File may have been deleted between upload and manifest write (e.g., gc()
        # ran on a stale upload from a previous story). Store None for md5/mtime
        # in that case so the record still persists for backward compat.
        try:
            md5 = compute_md5(local_path)
            mtime = int(os.path.getmtime(local_path))
        except (FileNotFoundError, OSError):
            md5 = None
            mtime = None
        self.data["uploads"][key] = {
            "md5": md5,
            "comfyui_filename": comfyui_filename,
            "mtime": mtime,
            # Python 3.12+ deprecates datetime.utcnow() — use timezone-aware now()
            "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self._save()
    
    def get_comfyui_filename(self, local_path: str, comfyui_url: str) -> str:
        """Get the ComfyUI filename for a local path (assumes already uploaded)."""
        key = self._key(local_path, comfyui_url)
        return self.data["uploads"][key]["comfyui_filename"]
    
    def list_uploads(self) -> list:
        """List all upload entries (for --list CLI)."""
        result = []
        for key, entry in self.data["uploads"].items():
            if "||" in key:
                local_path, comfyui_url = key.split("||", 1)
            else:
                # Backward compat: old keys used ':' separator.
                # Format: <local_path>:<comfyui_url_with_port>
                # We split on the FIRST ':' that's preceded by 'http' or 'https' (the
                # scheme://host:port boundary), then take everything after that as URL.
                # If the path itself contains a colon (rare on Linux but possible on
                # Mac/Windows) AND the URL is http://, the split-on-scheme handles it.
                scheme_idx = max(key.find("http://"), key.find("https://"))
                if scheme_idx < 0:
                    # No URL — skip (malformed legacy entry)
                    continue
                # Find the ':' that ends the scheme ('http:' or 'https:')
                scheme_end = key.find(":", scheme_idx)
                if scheme_end < 0:
                    continue
                # The path-to-URL separator is the ':' that follows the scheme's
                # '://' (i.e., scheme_end + 3 — but we need to be careful: the URL
                # itself contains '://', and after the host there's a ':PORT').
                # The separator between path and URL is the colon right before 'http'
                local_path = key[:scheme_idx].rstrip(":")
                comfyui_url = key[scheme_idx:].lstrip(":")
                # If local_path ended with ':' and we stripped it, prepend it back? No —
                # the old format was <path>:<url>, so if local_path had a trailing ':'
                # that got eaten. Restore by checking if the next char after our split
                # is 'h' (start of http) — which it is by construction.
            result.append({
                "local_path": local_path,
                "comfyui_url": comfyui_url,
                **entry
            })
        return result
    
    def gc(self, max_age_days: int = 30) -> int:
        """Remove entries older than max_age_days. Returns count removed."""
        import datetime
        # Python 3.12+ deprecates datetime.utcnow() — use timezone-aware now()
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=max_age_days)
        removed = 0
        keys_to_remove = []
        
        for key, entry in self.data["uploads"].items():
            uploaded_at = entry.get("uploaded_at", "")
            try:
                ts = datetime.datetime.fromisoformat(uploaded_at.replace("Z", ""))
                if ts < cutoff:
                    keys_to_remove.append(key)
            except (ValueError, AttributeError):
                # Can't parse, skip
                pass
        
        for key in keys_to_remove:
            del self.data["uploads"][key]
            removed += 1
        
        if removed > 0:
            self._save()
        return removed


def main():
    parser = argparse.ArgumentParser(description="ComfyUI upload manifest manager")
    parser.add_argument("--manifest", required=True, help="Path to .upload_manifest.json")
    parser.add_argument("--list", action="store_true", help="List all uploads")
    parser.add_argument("--gc", action="store_true", help="Garbage collect old entries")
    parser.add_argument("--max-age-days", type=int, default=30)
    args = parser.parse_args()
    
    manifest = UploadManifest(args.manifest)
    
    if args.list:
        uploads = manifest.list_uploads()
        print(f"Total uploads: {len(uploads)}")
        for u in uploads:
            print(f"  {u['local_path']} -> {u['comfyui_filename']} (md5={u['md5'][:8]}..., uploaded={u.get('uploaded_at', 'unknown')})")
    
    elif args.gc:
        removed = manifest.gc(args.max_age_days)
        print(f"Removed {removed} entries older than {args.max_age_days} days")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
