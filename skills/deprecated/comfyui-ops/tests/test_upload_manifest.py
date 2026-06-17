"""Test the upload_manifest key separator fix."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/root/.hermes/skills/creative/comfyui-ops/scripts")))

import json
import os
from upload_manifest import UploadManifest


def test_url_with_port():
    """Bug case: URL with port number should not collide with separator."""
    mf = "/tmp/test-manifest-port.json"
    if os.path.exists(mf):
        os.remove(mf)
    m = UploadManifest(mf)
    m.record_upload("/path/with:colons.png", "http://host:8188", "sheet.png")
    uploads = m.list_uploads()
    assert len(uploads) == 1
    assert uploads[0]["local_path"] == "/path/with:colons.png", f"got: {uploads[0]['local_path']}"
    assert uploads[0]["comfyui_url"] == "http://host:8188", f"got: {uploads[0]['comfyui_url']}"
    assert uploads[0]["comfyui_filename"] == "sheet.png"
    print("✓ Test 1 PASS: URL with port doesn't collide")


def test_multiple_records():
    """Multiple records should be stored and retrieved correctly."""
    mf = "/tmp/test-manifest-multi.json"
    if os.path.exists(mf):
        os.remove(mf)
    m = UploadManifest(mf)
    m.record_upload("/path/with:colons.png", "http://host:8188", "sheet.png")
    m.record_upload("/other.png", "http://other:9999", "other.png")
    uploads = m.list_uploads()
    assert len(uploads) == 2
    paths = [u["local_path"] for u in uploads]
    urls = [u["comfyui_url"] for u in uploads]
    assert "/path/with:colons.png" in paths
    assert "/other.png" in paths
    assert "http://host:8188" in urls
    assert "http://other:9999" in urls
    print("✓ Test 2 PASS: Multiple records round-trip correctly")


def test_backward_compat_with_old_colon_key():
    """Old manifests with ':' separator should still parse correctly."""
    mf = "/tmp/test-manifest-legacy.json"
    if os.path.exists(mf):
        os.remove(mf)
    m = UploadManifest(mf)
    # Manually inject an old-style key
    m.data["uploads"]["/old/path.png:http://legacy:8088"] = {
        "comfyui_filename": "legacy.png",
        "uploaded_at": "2020-01-01",
    }
    uploads = m.list_uploads()
    assert len(uploads) == 1
    assert uploads[0]["local_path"] == "/old/path.png", f"got: {uploads[0]['local_path']}"
    assert uploads[0]["comfyui_url"] == "http://legacy:8088", f"got: {uploads[0]['comfyui_url']}"
    print("✓ Test 3 PASS: Backward compat with old ':' separator")


def test_dedup_works():
    """Same local_path + comfyui_url should be deduped (single record)."""
    mf = "/tmp/test-manifest-dedup.json"
    if os.path.exists(mf):
        os.remove(mf)
    m = UploadManifest(mf)
    m.record_upload("/path.png", "http://host:8188", "sheet.png")
    m.record_upload("/path.png", "http://host:8188", "sheet.png")  # Same thing
    uploads = m.list_uploads()
    assert len(uploads) == 1, f"expected 1, got {len(uploads)}"
    print("✓ Test 4 PASS: Dedup works")


if __name__ == "__main__":
    test_url_with_port()
    test_multiple_records()
    test_backward_compat_with_old_colon_key()
    test_dedup_works()
    print("\n✓ All tests pass")
