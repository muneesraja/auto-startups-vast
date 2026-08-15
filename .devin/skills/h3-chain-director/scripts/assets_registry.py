"""Global asset registry for h3-chain-director.

A cross-episode, lock-hash-keyed, versioned, approval-gated registry of
character plates, location locks, style plates, storyboard sheets, props and
audio.  Persisted at ``<repo_root>/assets/registry.json`` with atomic writes
and a file lock so two parallel episode runs can't lose each other's entries.

This is deliberately separate from ``story-maker-v3``'s per-run
``AssetRegistry`` (which tracks only ``{output_path, fal_image_url}`` for one
episode).  The global registry is additive: legacy plates are indexed in place
(``origin: "legacy"``) and ``story-maker-v3`` is not modified.

Schema (one entry per entity+variant)::

    {
      "asset_id": "char.bamboo-the-dino.char_01.base",
      "kind": "character_plate",            # | location_lock | style_plate | storyboard_sheet | prop | audio
      "series": "bamboo-the-dino",
      "entity_id": "char_01",
      "variant": "base",
      "appearance_lock": "toddler, 3, olive skin, ...",
      "lock_hash": "sha256:...",
      "status": "approved",                 # planned | draft | approved | superseded | rejected
      "current": 3,
      "versions": [{"v":3,"path":"...","sha256":"...","provider":"...","model":"...",
                    "prompt_file":"...","cost_usd":0.24,"created":"...","approved_by":"...",
                    "notes":"..."}],
      "usage": [{"series":"...","episode":2,"run":"epi-2","stage":"S8"}],
      "derived_from": [],                   # sheet lineage
      "shared": false,
      "origin": "legacy" | "generated"
    }

The cache key is ``lock_hash``: same character + same lock ⇒ reuse (no
regeneration, no re-review).  A changed lock ⇒ a new variant/version, never an
overwrite of an approved asset.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SKILL_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _SKILL_ROOT.parents[2]  # .devin/skills/h3-chain-director -> repo root

DEFAULT_ASSETS_DIR = _REPO_ROOT / "assets"
DEFAULT_REGISTRY_PATH = DEFAULT_ASSETS_DIR / "registry.json"
DEFAULT_LOCK_PATH = DEFAULT_ASSETS_DIR / "registry.lock"

VALID_KINDS = (
    "character_plate",
    "location_lock",
    "style_plate",
    "storyboard_sheet",
    "prop",
    "audio",
)
VALID_STATUSES = ("planned", "draft", "approved", "superseded", "rejected")

# Files skipped when indexing legacy directories.
_SKIP_NAMES = {".DS_Store", "Thumbs.db"}
_SKIP_SUFFIXES = (".tmp_bak", ".bak", ".tmp")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RegistryError(Exception):
    """Base error for registry operations."""


class AssetNotFound(RegistryError):
    pass


class LockMismatch(RegistryError):
    """Raised when an appearance_lock doesn't match the resolved asset's lock."""


class AssetExists(RegistryError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def compute_lock_hash(appearance_lock: str) -> str:
    """SHA-256 of the byte-exact appearance lock string."""
    return "sha256:" + hashlib.sha256(appearance_lock.encode("utf-8")).hexdigest()


def compute_file_hash(path: str | os.PathLike) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def make_asset_id(kind: str, series: str, entity_id: str, variant: str) -> str:
    kind_prefix = {
        "character_plate": "char",
        "location_lock": "loc",
        "style_plate": "style",
        "storyboard_sheet": "sheet",
        "prop": "prop",
        "audio": "audio",
    }.get(kind, kind)
    return f"{kind_prefix}.{series}.{entity_id}.{variant}"


def _is_skip(path: Path) -> bool:
    if path.name in _SKIP_NAMES:
        return True
    return any(path.name.endswith(suf) for suf in _SKIP_SUFFIXES)


# ---------------------------------------------------------------------------
# File lock (cross-process, advisory)
# ---------------------------------------------------------------------------


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class GlobalAssetRegistry:
    """The global, cross-episode asset registry.

    Usage::

        reg = GlobalAssetRegistry()
        entry = reg.resolve("bamboo-the-dino", "char_01", "base",
                            appearance_lock="toddler, 3, ...")
        if entry:
            path = reg.approved_path(entry)   # reuse — do not regenerate
        else:
            entry = reg.add(kind="character_plate", series="bamboo-the-dino",
                            entity_id="char_01", variant="base",
                            appearance_lock="toddler, 3, ...",
                            path="assets/.../v1.webp", ...)
    """

    def __init__(
        self,
        registry_path: str | os.PathLike | None = None,
        assets_dir: str | os.PathLike | None = None,
    ):
        self.registry_path = Path(registry_path) if registry_path else DEFAULT_REGISTRY_PATH
        self.assets_dir = Path(assets_dir) if assets_dir else DEFAULT_ASSETS_DIR
        self.lock_path = self.registry_path.with_suffix(".lock")
        self._data: dict[str, dict] = self._load()

    # -- persistence -------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        if self.registry_path.is_file():
            try:
                with open(self.registry_path, encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict) and isinstance(loaded.get("assets"), dict):
                    return loaded["assets"]
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_locked(self) -> None:
        """Atomic write under the file lock.  Caller must hold no stale cache."""
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        payload = {"assets": self._data}
        with _file_lock(self.lock_path):
            fd, tmp = tempfile.mkstemp(
                dir=str(self.assets_dir), suffix=".tmp", prefix="registry_"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                os.replace(tmp, self.registry_path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)

    def reload(self) -> None:
        """Re-read from disk (use after another process may have written)."""
        self._data = self._load()

    # -- lookups -----------------------------------------------------------

    def get(self, asset_id: str) -> dict | None:
        return self._data.get(asset_id)

    def resolve(
        self,
        series: str,
        entity_id: str,
        variant: str = "base",
        *,
        appearance_lock: str | None = None,
        kind: str | None = None,
    ) -> dict | None:
        """Find an entry by (series, entity_id, variant).

        If ``appearance_lock`` is given, verify the lock hash matches.  If it
        doesn't match, return None (caller should create a new variant) rather
        than raising — the caller decides whether a mismatch is an error or a
        new-variant signal.
        """
        # Try exact asset_id match first.
        if kind:
            aid = make_asset_id(kind, series, entity_id, variant)
            entry = self._data.get(aid)
        else:
            entry = None
            for e in self._data.values():
                if (
                    e.get("series") == series
                    and e.get("entity_id") == entity_id
                    and e.get("variant") == variant
                ):
                    entry = e
                    break
        if entry is None:
            return None
        if appearance_lock is not None:
            lh = compute_lock_hash(appearance_lock)
            if entry.get("lock_hash") not in (lh, "unknown"):
                return None  # lock mismatch → not a reuse hit
        return entry

    def resolve_approved(
        self,
        series: str,
        entity_id: str,
        variant: str = "base",
        *,
        appearance_lock: str | None = None,
        kind: str | None = None,
    ) -> dict | None:
        """Like :meth:`resolve` but only returns ``approved`` entries."""
        entry = self.resolve(
            series, entity_id, variant, appearance_lock=appearance_lock, kind=kind
        )
        if entry and entry.get("status") == "approved":
            return entry
        return None

    def approved_path(self, entry: dict) -> str | None:
        """Return the on-disk path of the current approved version, or None."""
        if entry.get("status") != "approved":
            return None
        v = entry.get("current")
        versions = entry.get("versions") or []
        for ver in versions:
            if ver.get("v") == v:
                return ver.get("path")
        return None

    def find_by_lock(
        self, series: str, appearance_lock: str, *, kind: str | None = None
    ) -> list[dict]:
        """Find all entries for a series whose lock_hash matches."""
        lh = compute_lock_hash(appearance_lock)
        results = []
        for e in self._data.values():
            if e.get("series") != series:
                continue
            if e.get("lock_hash") != lh:
                continue
            if kind and e.get("kind") != kind:
                continue
            results.append(e)
        return results

    def list_series(self, series: str) -> list[dict]:
        return [e for e in self._data.values() if e.get("series") == series]

    # -- mutations ---------------------------------------------------------

    def add(
        self,
        *,
        kind: str,
        series: str,
        entity_id: str,
        variant: str = "base",
        appearance_lock: str,
        path: str,
        provider: str = "",
        model: str = "",
        prompt_file: str = "",
        cost_usd: float = 0.0,
        notes: str = "",
        shared: bool = False,
        derived_from: list[str] | None = None,
        status: str = "draft",
        origin: str = "generated",
    ) -> dict:
        """Add a new asset entry (or a new version of an existing one).

        If the entry already exists and is ``approved``, adding a new version
        creates ``v = current+1`` with ``status: draft`` and leaves the
        approved version frozen.  Use :meth:`approve` to promote it.
        """
        if kind not in VALID_KINDS:
            raise RegistryError(f"invalid kind: {kind}")
        if status not in VALID_STATUSES:
            raise RegistryError(f"invalid status: {status}")

        asset_id = make_asset_id(kind, series, entity_id, variant)
        lock_hash = compute_lock_hash(appearance_lock)
        file_hash = compute_file_hash(path) if os.path.isfile(path) else ""

        version_entry = {
            "v": 1,
            "path": str(path),
            "sha256": file_hash,
            "provider": provider,
            "model": model,
            "prompt_file": prompt_file,
            "cost_usd": round(cost_usd, 4),
            "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "approved_by": "",
            "notes": notes,
        }

        existing = self._data.get(asset_id)
        if existing is None:
            entry: dict[str, Any] = {
                "asset_id": asset_id,
                "kind": kind,
                "series": series,
                "entity_id": entity_id,
                "variant": variant,
                "appearance_lock": appearance_lock,
                "lock_hash": lock_hash,
                "status": status,
                "current": 1 if status == "approved" else 0,
                "versions": [version_entry],
                "usage": [],
                "derived_from": derived_from or [],
                "shared": shared,
                "origin": origin,
            }
            self._data[asset_id] = entry
        else:
            # Lock must match (or be unknown) to add a version to the same variant.
            if existing.get("lock_hash") not in (lock_hash, "unknown"):
                raise LockMismatch(
                    f"lock mismatch for {asset_id}: existing "
                    f"{existing.get('lock_hash')} vs new {lock_hash}. "
                    "Create a new variant instead."
                )
            if existing.get("lock_hash") == "unknown":
                existing["lock_hash"] = lock_hash
                existing["appearance_lock"] = appearance_lock
            next_v = max((v.get("v", 0) for v in existing.get("versions", [])), default=0) + 1
            version_entry["v"] = next_v
            existing.setdefault("versions", []).append(version_entry)
            if status == "approved":
                existing["status"] = "approved"
                existing["current"] = next_v
            else:
                existing["status"] = status  # draft/superseded/rejected
            entry = existing

        self._save_locked()
        return entry

    def approve(self, asset_id: str, *, approved_by: str = "user", notes: str = "") -> dict:
        """Promote the latest version of an entry to approved."""
        entry = self._data.get(asset_id)
        if entry is None:
            raise AssetNotFound(asset_id)
        versions = entry.get("versions") or []
        if not versions:
            raise RegistryError(f"no versions to approve for {asset_id}")
        latest = versions[-1]
        latest["approved_by"] = approved_by
        if notes:
            latest["notes"] = notes
        entry["status"] = "approved"
        entry["current"] = latest["v"]
        self._save_locked()
        return entry

    def supersede(self, asset_id: str, *, reason: str = "") -> dict:
        """Mark an approved asset as superseded (immutable — not deleted)."""
        entry = self._data.get(asset_id)
        if entry is None:
            raise AssetNotFound(asset_id)
        entry["status"] = "superseded"
        if reason:
            entry.setdefault("supersede_reason", reason)
        self._save_locked()
        return entry

    def record_usage(
        self,
        asset_id: str,
        *,
        series: str,
        episode: int,
        run: str,
        stage: str,
    ) -> dict:
        entry = self._data.get(asset_id)
        if entry is None:
            raise AssetNotFound(asset_id)
        entry.setdefault("usage", []).append(
            {"series": series, "episode": episode, "run": run, "stage": stage}
        )
        self._save_locked()
        return entry

    def plan(
        self,
        *,
        series: str,
        episode: int,
        needed: list[dict],
    ) -> dict:
        """Given a list of needed assets, classify each as reuse or generate.

        ``needed`` items: ``{kind, entity_id, variant, appearance_lock}``.

        Returns ``{"reuse": [...], "generate": [...], "projected_cost_usd": float}``.
        """
        reuse: list[dict] = []
        generate: list[dict] = []
        cost = 0.0
        for item in needed:
            entry = self.resolve_approved(
                series,
                item["entity_id"],
                item.get("variant", "base"),
                appearance_lock=item.get("appearance_lock"),
                kind=item.get("kind"),
            )
            if entry:
                reuse.append(
                    {
                        "asset_id": entry["asset_id"],
                        "path": self.approved_path(entry),
                        "variant": entry["variant"],
                    }
                )
            else:
                generate.append(item)
                cost += item.get("est_cost_usd", 0.24)
        return {"reuse": reuse, "generate": generate, "projected_cost_usd": round(cost, 2)}

    # -- doctor ------------------------------------------------------------

    def doctor(self) -> list[dict]:
        """Verify every version's sha256 matches the file on disk.

        Returns a list of issues: ``{asset_id, version, issue, path}``.
        """
        issues: list[dict] = []
        for asset_id, entry in self._data.items():
            for ver in entry.get("versions", []):
                path = ver.get("path", "")
                if not path:
                    issues.append(
                        {"asset_id": asset_id, "version": ver.get("v"), "issue": "missing path"}
                    )
                    continue
                if not os.path.isfile(path):
                    issues.append(
                        {
                            "asset_id": asset_id,
                            "version": ver.get("v"),
                            "issue": "file not found",
                            "path": path,
                        }
                    )
                    continue
                actual = compute_file_hash(path)
                if ver.get("sha256") and ver["sha256"] != actual:
                    issues.append(
                        {
                            "asset_id": asset_id,
                            "version": ver.get("v"),
                            "issue": "sha256 mismatch (file modified or renamed)",
                            "path": path,
                            "expected": ver["sha256"],
                            "actual": actual,
                        }
                    )
        return issues

    # -- legacy adoption ---------------------------------------------------

    def index_legacy(
        self,
        root: str | os.PathLike,
        *,
        series: str | None = None,
        dry_run: bool = False,
    ) -> list[dict]:
        """Walk a legacy ``outputs/story-maker-v3/<series>/assets/**`` tree and
        register every plate in place.

        Files are NOT moved.  Each is registered with ``origin: "legacy"``,
        ``status: "draft"``, and ``sha256`` computed.  Appearance locks are
        left as ``"unknown"`` (forcing one explicit confirmation before first
        reuse) unless a sibling ``.txt`` prompt file exists, in which case its
        text is used as the lock.

        Returns a list of registered entries (or would-be entries if dry_run).
        """
        root = Path(root)
        if not root.is_dir():
            raise RegistryError(f"legacy root not found: {root}")

        registered: list[dict] = []
        for kind, subdir, prefix in (
            ("character_plate", "characters", "char"),
            ("location_lock", "locations", "loc"),
        ):
            kind_dir = root / subdir
            if not kind_dir.is_dir():
                continue
            for path in sorted(kind_dir.iterdir()):
                if _is_skip(path) or not path.is_file():
                    continue
                # Derive entity_id from filename: char_01.webp -> char_01
                entity_id = path.stem
                if not entity_id.startswith(prefix):
                    continue
                series_name = series or root.parent.name

                # Look for a sibling prompt file for the appearance lock.
                lock = "unknown"
                prompt_file = ""
                for txt in (path.with_suffix(".txt"), kind_dir / f"{entity_id}.txt"):
                    if txt.is_file():
                        lock = txt.read_text(encoding="utf-8").strip()
                        prompt_file = str(txt)
                        break

                asset_id = make_asset_id(kind, series_name, entity_id, "base")
                if self._data.get(asset_id) and not dry_run:
                    continue  # already indexed

                if dry_run:
                    registered.append(
                        {
                            "asset_id": asset_id,
                            "path": str(path),
                            "lock": lock,
                            "would_register": True,
                        }
                    )
                else:
                    entry = self.add(
                        kind=kind,
                        series=series_name,
                        entity_id=entity_id,
                        variant="base",
                        appearance_lock=lock,
                        path=str(path),
                        prompt_file=str(prompt_file),
                        status="draft",
                        origin="legacy",
                    )
                    registered.append(entry)
        return registered
