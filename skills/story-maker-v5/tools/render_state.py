"""Mutable render-run state for story-maker-v5 (``<run_dir>/render_state.json``).

The render manifest is the *immutable approved plan*; this module tracks what
actually happened during execution — per-clip status, ComfyUI ``prompt_id``
(persisted immediately after queueing so an interrupted run can re-poll instead
of re-submitting), input fingerprints for dependency-aware resume, output
hashes, and tail metadata.

State transitions per clip:
  submitted -> rendering -> rendered -> accepted
                          -> failed

Writes are atomic (tempfile + os.replace).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import tempfile
from typing import Any

SCHEMA = "story-maker-v5.render_state/v1"


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def state_path(run_dir: str) -> str:
    return os.path.join(run_dir, "render_state.json")


def load_state(run_dir: str) -> dict[str, Any]:
    path = state_path(run_dir)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data.setdefault("clips", {})
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"schema": SCHEMA, "updated_at": None, "clips": {}}


def save_state(run_dir: str, state: dict[str, Any]) -> None:
    state["schema"] = SCHEMA
    state["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    path = state_path(run_dir)
    fd, tmp = tempfile.mkstemp(dir=run_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def clip_key(scene_id: str, gen_id: str) -> str:
    return f"{scene_id}/{gen_id}"


def clip_record(state: dict[str, Any], scene_id: str, gen_id: str) -> dict[str, Any]:
    return state["clips"].setdefault(clip_key(scene_id, gen_id), {})


def set_status(
    run_dir: str,
    state: dict[str, Any],
    scene_id: str,
    gen_id: str,
    status: str,
    **fields: Any,
) -> None:
    rec = clip_record(state, scene_id, gen_id)
    rec["status"] = status
    rec.update(fields)
    rec["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    save_state(run_dir, state)


def input_fingerprint(
    *,
    sheet_sha: str | None,
    prompt_sha: str | None,
    audio_shas: list[str],
    prev_output_sha: str | None,
    config_fingerprint: str,
) -> str:
    """Fingerprint of everything a clip's render depends on.

    ``prev_output_sha`` chains the dependency: when a predecessor is
    re-rendered, every downstream fingerprint changes and the clips are
    re-rendered — stale tails can never be silently reused.
    """
    material = "|".join(
        [
            sheet_sha or "",
            prompt_sha or "",
            ",".join(audio_shas),
            prev_output_sha or "none",
            config_fingerprint,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def config_fingerprint(
    *,
    seed: int,
    megapixels: float | None,
    aspect: str | None,
    workflow_sha: str | None,
) -> str:
    material = f"seed={seed}|mp={megapixels}|aspect={aspect}|wf={workflow_sha}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def is_reusable(rec: dict[str, Any], clip_path: str, fingerprint: str) -> bool:
    """A clip may be skipped only when the file exists and the recorded
    fingerprint of its inputs still matches."""
    return (
        rec.get("status") in ("rendered", "accepted")
        and rec.get("input_fingerprint") == fingerprint
        and bool(clip_path)
        and os.path.isfile(clip_path)
        and os.path.getsize(clip_path) > 0
    )
