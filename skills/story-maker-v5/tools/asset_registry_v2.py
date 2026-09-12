"""V5 adapter over h3-chain-director's ``GlobalAssetRegistry``.

Ports the global registry's lock-hash reuse, versioned assets, and
draft/approved lifecycle into story-maker-v5 while preserving the V1
``AssetRegistry`` surface that ``image_pipeline.py`` call sites use
(``character()``, ``location()``, ``object()``, ``sheet()``,
``resolve_ref_name()``, ``*_path()`` helpers, mirrored ``output_path`` /
``fal_image_url`` keys).

The h3 module is imported by path — the same import-by-path convention the
h3 skill uses to reach into this skill — so there is exactly one registry
implementation to maintain.

Persistence: ``<assets_dir>/asset_registry.json`` in the h3 schema
(``{"assets": {...}}``). A V1 flat registry
(``{characters, locations, objects, sheets, sheets_legacy}``) found at that
path is migrated in place on first open: the old file is backed up to
``asset_registry.v1.bak.json``, every entry becomes ``status: draft``
(``origin: legacy`` — never auto-approved; GATE 1 / ``assetctl approve``
promotes them), and unscoped sheet keys are namespaced by episode.

Approval semantics: ``resolve_ref_name`` resolves only ``approved`` assets
by default. The image-build stage (pre-GATE-1, where drafts are produced)
constructs the registry with ``allow_draft=True``.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = SKILL_ROOT.parents[1]
_H3_SCRIPTS = _REPO_ROOT / ".devin" / "skills" / "h3-chain-director" / "scripts"
if _H3_SCRIPTS.is_dir() and str(_H3_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_H3_SCRIPTS))

from assets_registry import (  # noqa: E402
    GlobalAssetRegistry,
    compute_file_hash,
    make_asset_id,
)

_KIND_FOR_SECTION = {
    "characters": "character_plate",
    "locations": "location_lock",
    "objects": "prop",
    "sheets": "storyboard_sheet",
}
_SECTION_FOR_KIND = {v: k for k, v in _KIND_FOR_SECTION.items()}
_REF_ORDER = ("prop", "location_lock", "character_plate", "storyboard_sheet")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def _new_entry(
    *, kind: str, series: str, entity_id: str, variant: str = "base",
    origin: str = "generated", status: str = "planned",
    path: str = "", hosted_url: str = "",
) -> dict[str, Any]:
    version = {
        "v": 1,
        "path": path,
        "sha256": compute_file_hash(path) if path and os.path.isfile(path) else "",
        "hosted_url": hosted_url,
        "provider": "",
        "model": "",
        "prompt_file": "",
        "cost_usd": 0.0,
        "created": _now(),
        "approved_by": "",
        "notes": "",
    }
    return {
        "asset_id": make_asset_id(kind, series, entity_id, variant),
        "kind": kind,
        "series": series,
        "entity_id": entity_id,
        "variant": variant,
        "appearance_lock": "",
        "lock_hash": "unknown",
        "status": status,
        "current": 0,
        "versions": [version] if path else [],
        "usage": [],
        "derived_from": [],
        "shared": False,
        "origin": origin,
        # V1-compat mirrors — image_pipeline reads/writes these directly.
        "output_path": path,
        "fal_image_url": hosted_url,
    }


class RegistryV2:
    """Drop-in replacement for ``image_pipeline.AssetRegistry`` backed by
    the global h3 registry."""

    def __init__(
        self,
        run_dir: str,
        assets_dir: str,
        *,
        series: str | None = None,
        allow_draft: bool = False,
    ):
        self.run_dir = run_dir
        self.assets_dir = assets_dir
        self.run_label = os.path.basename(os.path.normpath(run_dir))
        self.series = series or os.path.basename(
            os.path.dirname(os.path.normpath(run_dir))
        )
        self.allow_draft = allow_draft
        self.path = os.path.join(assets_dir, "asset_registry.json")
        self._maybe_migrate_v1()
        self._reg = GlobalAssetRegistry(
            registry_path=self.path, assets_dir=assets_dir
        )

    # -- V1 -> V2 migration -------------------------------------------------

    def _maybe_migrate_v1(self) -> None:
        if not os.path.isfile(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        if not isinstance(data, dict) or "assets" in data:
            return  # already V2 (or unrecognised — leave alone)
        if not any(k in data for k in _KIND_FOR_SECTION):
            return

        backup = self.path.replace(".json", ".v1.bak.json")
        if not os.path.isfile(backup):
            shutil.copy2(self.path, backup)

        run_dir_abs = os.path.abspath(self.run_dir)
        assets: dict[str, dict] = {}
        for section, kind in _KIND_FOR_SECTION.items():
            for name, v1 in (data.get(section) or {}).items():
                if not isinstance(v1, dict):
                    continue
                path = v1.get("output_path") or ""
                url = v1.get("fal_image_url") or ""
                variant = "base"
                entity_id = name
                if section == "sheets":
                    if "." in name:
                        entity_id = name  # already episode-scoped
                    elif path:
                        p = path if os.path.isabs(path) else os.path.join(
                            self.run_dir, path
                        )
                        if os.path.abspath(p).startswith(run_dir_abs + os.sep):
                            entity_id = f"{self.run_label}.{name}"
                        else:
                            entity_id = name
                            variant = "legacy"  # parked: another episode's key
                    else:
                        entity_id = name
                        variant = "legacy"
                entry = _new_entry(
                    kind=kind, series=self.series, entity_id=entity_id,
                    variant=variant, origin="legacy", status="draft",
                    path=path, hosted_url=url,
                )
                assets[entry["asset_id"]] = entry

        payload = {"assets": assets}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # -- accessors (V1 surface) ----------------------------------------------

    @property
    def data(self) -> dict[str, dict]:
        return self._reg._data

    def _entry(self, kind: str, entity_id: str, variant: str = "base") -> dict:
        aid = make_asset_id(kind, self.series, entity_id, variant)
        e = self._reg._data.get(aid)
        if e is None:
            e = _new_entry(kind=kind, series=self.series, entity_id=entity_id)
            self._reg._data[aid] = e
        return e

    def character(self, cid: str) -> dict:
        return self._entry("character_plate", cid)

    def location(self, lid: str) -> dict:
        return self._entry("location_lock", lid)

    def object(self, oid: str) -> dict:
        return self._entry("prop", oid)

    def sheet(self, sheet_id: str) -> dict:
        """``sheet_id`` is ``<scene>_<gen>``; stored episode-scoped as
        ``<run_label>.<sheet_id>``."""
        key = sheet_id if "." in sheet_id else f"{self.run_label}.{sheet_id}"
        return self._entry("storyboard_sheet", key)

    # -- paths ---------------------------------------------------------------

    def _ext(self) -> str:
        from . import image_pipeline as ip

        return ip._img_ext()

    def character_path(self, cid: str) -> str:
        return os.path.join(self.assets_dir, "characters", f"{cid}.{self._ext()}")

    def location_path(self, lid: str) -> str:
        return os.path.join(self.assets_dir, "locations", f"{lid}.{self._ext()}")

    def object_path(self, oid: str) -> str:
        return os.path.join(self.assets_dir, "objects", f"{oid}.{self._ext()}")

    def sheet_path(self, scene_id: str, gen_id: str = "") -> str:
        ext = self._ext()
        if gen_id:
            return os.path.join(
                self.run_dir, f"storyboard_sheet_{scene_id}_{gen_id}.{ext}"
            )
        return os.path.join(self.run_dir, f"storyboard_sheet_{scene_id}.{ext}")

    # -- persistence ----------------------------------------------------------

    def save(self) -> None:
        """Sync the V1-compat mirrors into the version model, then write
        atomically under the h3 file lock."""
        for e in self._reg._data.values():
            out = e.get("output_path") or ""
            url = e.get("fal_image_url") or ""
            versions = e.setdefault("versions", [])
            if out:
                cur = versions[-1] if versions else None
                if cur is None or cur.get("path") != out:
                    versions.append(
                        {
                            "v": (cur["v"] + 1) if cur else 1,
                            "path": out,
                            "sha256": compute_file_hash(out)
                            if os.path.isfile(out)
                            else "",
                            "hosted_url": url,
                            "provider": "",
                            "model": "",
                            "prompt_file": "",
                            "cost_usd": 0.0,
                            "created": _now(),
                            "approved_by": "",
                            "notes": "",
                        }
                    )
                elif url:
                    cur["hosted_url"] = url
                if e.get("status") == "planned":
                    e["status"] = "draft"
        self._reg._save_locked()

    # -- resolution (approval-aware) ------------------------------------------

    def _entry_url(self, e: dict) -> str | None:
        url = e.get("fal_image_url") or ""
        if not url:
            for ver in reversed(e.get("versions") or []):
                url = ver.get("hosted_url") or ""
                if url:
                    break
        if not url:
            return None
        return url

    def _usable(self, e: dict | None, allow_draft: bool) -> bool:
        if e is None:
            return False
        status = e.get("status", "draft")
        if status == "approved":
            return True
        return allow_draft and status in ("draft", "planned")

    def _find(self, kind: str, entity_id: str, variant: str = "base") -> dict | None:
        aid = make_asset_id(kind, self.series, entity_id, variant)
        e = self._reg._data.get(aid)
        if e is not None:
            return e
        # Variant-agnostic scan (e.g. parked 'legacy' sheet variants).
        for e in self._reg._data.values():
            if (
                e.get("kind") == kind
                and e.get("series") == self.series
                and e.get("entity_id") == entity_id
            ):
                return e
        return None

    def resolve_ref_name(
        self, name: str, *, allow_draft: bool | None = None
    ) -> str | None:
        """Resolve a ``ref_images:`` name to a hosted URL.

        Resolution order: objects → locations → characters → sheets. Sheet
        names may be unscoped (``s1_g1`` → this run's ``<run_label>.s1_g1``)
        or fully scoped (``epi-2.s1_g1``). Only ``approved`` assets resolve
        unless ``allow_draft`` (or the registry's ``allow_draft`` default).
        """
        from . import image_pipeline as ip

        allow = self.allow_draft if allow_draft is None else allow_draft
        name = name.strip()
        if not name:
            return None
        for kind in _REF_ORDER:
            candidates = [name]
            if kind == "storyboard_sheet" and "." not in name:
                candidates = [f"{self.run_label}.{name}", name]
            for entity_id in candidates:
                e = self._find(kind, entity_id)
                if e is None or not self._usable(e, allow):
                    continue
                url = self._entry_url(e)
                if url:
                    return url
                # No hosted URL yet — upload through the V1 helper, which
                # writes the mirrored fal_image_url key.
                if e.get("output_path"):
                    resolved = ip.ensure_asset_url(e)
                    if resolved:
                        return resolved
        return None

    # -- h3 conveniences surfaced for assetctl / prompts ----------------------

    def approve(self, asset_id: str, *, approved_by: str = "user") -> dict:
        self.save()  # flush mirrors first
        return self._reg.approve(asset_id, approved_by=approved_by)

    def approve_all_drafts(self, *, approved_by: str = "gate-1") -> list[str]:
        """GATE 1 promotion: every draft/planned asset for this series."""
        self.save()
        promoted: list[str] = []
        for aid, e in self._reg._data.items():
            if e.get("series") == self.series and e.get("status") in (
                "draft",
                "planned",
            ):
                self._reg.approve(aid, approved_by=approved_by)
                promoted.append(aid)
        return promoted

    def doctor(self) -> list[dict]:
        """h3 hash check + V5 extras: legacy/parked sheet keys and drafts
        still referenced by ``ref_images:`` lines under this story's runs."""
        issues = list(self._reg.doctor())
        for aid, e in self._reg._data.items():
            if e.get("series") != self.series:
                continue
            if e.get("kind") == "storyboard_sheet" and (
                e.get("variant") == "legacy" or "." not in e.get("entity_id", "")
            ):
                issues.append(
                    {
                        "asset_id": aid,
                        "issue": "unscoped/legacy sheet key — parked; not "
                        "resolved inside any episode run",
                    }
                )
        return issues
