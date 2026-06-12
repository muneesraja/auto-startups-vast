# Upload Manifest — MD5 Pitfall & Key Separator Design

**Captured:** June 2026, STV v2.0 review-fix plan (P7.1)
**Files:** `~/.hermes/skills/creative/comfyui-ops/scripts/upload_manifest.py`

## Pitfall: `record_upload()` requires file to exist on disk

`UploadManifest.record_upload(local_path, comfyui_url, comfyui_filename)` calls `compute_md5(local_path)` internally, which opens the file with `open(path, "rb")`. If the file doesn't exist, it raises `FileNotFoundError` — not a graceful "skip MD5" behavior.

**When this bites:**

1. **GC scenario:** `gc(max_age_days=30)` removes old manifest entries. If a previously-uploaded file was deleted from disk (e.g., user cleaned up), the next `record_upload()` call for the SAME path will fail because the local file is gone.
2. **Test scenarios:** Any test that calls `record_upload` with a non-existent path will fail.
3. **Migration scenario:** If you have a manifest from an old story and the original local files have been moved/archived, re-uploading to a different ComfyUI server fails.

**Current workaround in code (June 2026):** None. The bug exists and would bite in production.

**Recommended fix (deferred to v1.0):**

```python
def record_upload(self, local_path: str, comfyui_url: str, comfyui_filename: str):
    """Record a successful upload. If the local file is missing, store without MD5."""
    key = self._key(local_path, comfyui_url)
    entry = {
        "comfyui_filename": comfyui_filename,
        "uploaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        entry["md5"] = compute_md5(local_path)
        entry["mtime"] = os.path.getmtime(local_path)
    except FileNotFoundError:
        # File is gone — we still record the upload so future uploads
        # to the same path can detect the existing entry by key
        entry["md5"] = None
        entry["mtime"] = None
        entry["warning"] = "local file missing at record time"
    self.data["uploads"][key] = entry
    self._save()
```

**Testing pattern:** When writing tests for upload_manifest, use real files:

```python
def test_url_with_port(tmp_path):
    """Bug case: URL with port number should not collide with separator."""
    real_file = tmp_path / "ref.png"
    real_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # fake PNG
    mf = tmp_path / ".upload_manifest.json"
    m = UploadManifest(str(mf))
    m.record_upload(str(real_file), "http://host:8188", "sheet.png")
    uploads = m.list_uploads()
    assert uploads[0]["local_path"] == str(real_file)
    assert uploads[0]["comfyui_url"] == "http://host:8188"
```

## Key Separator Design — `||` over `:`

**Original:** `f"{local_path}:{comfyui_url}"` — collision with port numbers in URLs.

**Bug case:** Recording an upload to `http://host:8188` with local path `/path/to/file.png` produced key `/path/to/file.png:http://host:8188`. Now recording to `http://host:9999` with local path `/path/to/file.png:http://host:8188` would produce a colliding key `/path/to/file.png:http://host:8188:http://host:9999`. `list_uploads()` did `key.split(":")[0]` and `key.split(":")[1]` which would split on the WRONG colon.

**Fix:** Use `||` as separator (won't appear in URLs or Linux paths). Plus a backward-compat fallback for old `:` keys:

```python
def _key(self, local_path: str, comfyui_url: str) -> str:
    return f"{local_path}||{comfyui_url}"

def list_uploads(self) -> list:
    result = []
    for key, entry in self.data["uploads"].items():
        if "||" in key:
            local_path, comfyui_url = key.split("||", 1)
        else:
            # Backward compat: old keys used ':' separator.
            # rfind to handle local paths that may also contain ':'
            idx = key.rfind(":")
            if idx < 0:
                continue
            local_path = key[:idx]
            comfyui_url = key[idx + 1:]
        result.append({"local_path": local_path, "comfyui_url": comfyui_url, **entry})
    return result
```

**Why `rfind` not `split` for backward compat:** Local paths COULD contain `:` (unusual on Linux, common on Windows/Cygwin). The URL is always the last colon-delimited segment.

## Related

- The bug was caught by GLM-5.1's review of v2.0 (`/tmp/opencode_review.log`, June 12 2026, Issue #8)
- TDD test: `~/.hermes/skills/creative/comfyui-ops/tests/test_upload_manifest.py` (4 cases)
- Pre-existing MD5 bug discovered during P7.1 test writing (June 12 2026)
