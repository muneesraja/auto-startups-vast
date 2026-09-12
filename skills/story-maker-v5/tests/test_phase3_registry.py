"""Phase 3 tests: RegistryV2 adapter over the h3 GlobalAssetRegistry."""

import json
import os

import pytest

from tools.asset_registry_v2 import RegistryV2


def _v1_registry(assets_dir: str, run_dir: str) -> dict:
    """A flat V1-style registry at <assets_dir>/asset_registry.json."""
    os.makedirs(assets_dir, exist_ok=True)
    data = {
        "characters": {
            "char_01": {
                "output_path": os.path.join(assets_dir, "characters", "char_01.webp"),
                "fal_image_url": "https://cdn.example/char_01.webp",
            }
        },
        "locations": {
            "loc_a": {
                "output_path": os.path.join(assets_dir, "locations", "loc_a.webp"),
                "fal_image_url": "https://cdn.example/loc_a.webp",
            }
        },
        "objects": {},
        "sheets": {},
    }
    with open(os.path.join(assets_dir, "asset_registry.json"), "w") as f:
        json.dump(data, f)
    return data


def test_v1_registry_migrates_to_h3_schema(tmp_path):
    run = str(tmp_path / "epi-1")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    _v1_registry(assets, run)

    reg = RegistryV2(run, assets)
    # Backup written, schema converted.
    assert os.path.isfile(os.path.join(assets, "asset_registry.v1.bak.json"))
    with open(reg.path) as f:
        raw = json.load(f)
    assert "assets" in raw and "characters" not in raw

    # Migrated entries keep their paths/URLs and land as draft/legacy.
    series = reg.series
    char = reg._find("character_plate", "char_01")
    assert char is not None
    assert char["status"] == "draft"
    assert char["origin"] == "legacy"
    assert char["output_path"].endswith("char_01.webp")
    assert char["fal_image_url"] == "https://cdn.example/char_01.webp"
    assert char["versions"][0]["hosted_url"] == "https://cdn.example/char_01.webp"


def test_unscoped_sheet_keys_scope_on_migration(tmp_path):
    run = str(tmp_path / "epi-2")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    sheet_in_run = os.path.join(run, "storyboard_sheet_s1_g1.webp")
    with open(sheet_in_run, "wb") as f:
        f.write(b"img")
    data = {
        "sheets": {
            "s1_g1": {"output_path": sheet_in_run, "fal_image_url": "https://x/1"},
            "s1_g2": {"output_path": "/other/epi-1/s1_g2.webp", "fal_image_url": "https://x/2"},
        }
    }
    os.makedirs(assets)
    with open(os.path.join(assets, "asset_registry.json"), "w") as f:
        json.dump(data, f)

    reg = RegistryV2(run, assets)
    mine = reg._find("storyboard_sheet", "epi-2.s1_g1")
    assert mine is not None and mine["variant"] == "base"
    parked = reg._find("storyboard_sheet", "s1_g2", variant="legacy")
    assert parked is not None and parked["variant"] == "legacy"


def test_approved_only_resolution(tmp_path):
    run = str(tmp_path / "epi-1")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    _v1_registry(assets, run)

    reg = RegistryV2(run, assets)  # default: approved-only
    # Migrated char is draft → does not resolve.
    assert reg.resolve_ref_name("char_01") is None
    # Explicitly allowing drafts resolves it.
    assert reg.resolve_ref_name("char_01", allow_draft=True) == \
        "https://cdn.example/char_01.webp"

    # GATE 1 promotion makes it resolve without allow_draft.
    reg.approve_all_drafts()
    assert reg.resolve_ref_name("char_01") == "https://cdn.example/char_01.webp"


def test_cross_episode_sheet_isolation(tmp_path):
    assets = str(tmp_path / "assets")
    run1 = str(tmp_path / "epi-1")
    run2 = str(tmp_path / "epi-2")
    os.makedirs(run1)
    os.makedirs(run2)

    reg1 = RegistryV2(run1, assets, allow_draft=True)
    e = reg1.sheet("s1_g1")
    e["output_path"] = os.path.join(run1, "storyboard_sheet_s1_g1.webp")
    e["fal_image_url"] = "https://cdn.example/epi1_s1_g1.webp"
    reg1.save()

    # epi-2 sees its own scoped key empty, and unscoped name does NOT
    # resolve to epi-1's sheet.
    reg2 = RegistryV2(run2, assets, allow_draft=True)
    assert "epi-2.s1_g1" not in [e["entity_id"] for e in reg2.data.values()]
    assert reg2.resolve_ref_name("s1_g1") is None
    # Explicit scoped name resolves (cross-episode reuse is allowed).
    reg1.data[next(k for k, e in reg1.data.items()
                   if e.get("entity_id") == "epi-1.s1_g1")]["status"] = "approved"
    reg2b = RegistryV2(run2, assets, allow_draft=True)
    assert reg2b.resolve_ref_name("epi-1.s1_g1") == \
        "https://cdn.example/epi1_s1_g1.webp"


def test_save_syncs_mirrors_into_versions(tmp_path):
    run = str(tmp_path / "epi-1")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    reg = RegistryV2(run, assets, allow_draft=True)
    path = os.path.join(run, "storyboard_sheet_s1_g1.webp")
    with open(path, "wb") as f:
        f.write(b"img")
    e = reg.sheet("s1_g1")
    e["output_path"] = path
    e["fal_image_url"] = "https://cdn.example/x.webp"
    reg.save()

    reg2 = RegistryV2(run, assets, allow_draft=True)
    e2 = reg2._find("storyboard_sheet", "epi-1.s1_g1")
    assert e2["versions"][-1]["path"] == path
    assert e2["versions"][-1]["hosted_url"] == "https://cdn.example/x.webp"
    assert e2["versions"][-1]["sha256"].startswith("sha256:")
    assert e2["status"] == "draft"


def test_lock_hash_reuse_and_mismatch(tmp_path):
    run = str(tmp_path / "epi-1")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    reg = RegistryV2(run, assets)
    lock = "toddler, 3, olive skin, white onesie"
    reg._reg.add(
        kind="character_plate", series=reg.series, entity_id="char_01",
        variant="base", appearance_lock=lock,
        path=os.path.join(assets, "characters", "char_01.webp"),
        status="approved",
    )
    hit = reg._reg.resolve_approved(
        reg.series, "char_01", "base", appearance_lock=lock, kind="character_plate"
    )
    assert hit is not None
    # Changed appearance → no reuse hit → caller creates a new variant.
    miss = reg._reg.resolve_approved(
        reg.series, "char_01", "base",
        appearance_lock="toddler, 3, olive skin, BLUE onesie",
        kind="character_plate",
    )
    assert miss is None


def test_doctor_reports_legacy_sheet_keys(tmp_path):
    run = str(tmp_path / "epi-2")
    assets = str(tmp_path / "assets")
    os.makedirs(run)
    data = {"sheets": {"s1_g1": {"output_path": "/other/epi-1/s1_g1.webp",
                                "fal_image_url": "https://x/1"}}}
    os.makedirs(assets)
    with open(os.path.join(assets, "asset_registry.json"), "w") as f:
        json.dump(data, f)
    reg = RegistryV2(run, assets)
    issues = reg.doctor()
    assert any("unscoped" in i.get("issue", "") or "not found" in i.get("issue", "")
               for i in issues)
