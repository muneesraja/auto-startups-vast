"""Episode intake: turn ``stories/<series>/`` folders (or a single file) into
an explicit ``episode_spec.json`` under the run dir.

The ``stories/`` directory is user-managed and read by path — it is not an
implicit production database. Discovery looks for:

  episodes/episode-<N>/episode-<N>.md   canonical per-episode folder
  episodes/episode-<N>.md               flat-in-episodes fallback
  episode-<N>.md                        flat-root fallback (legacy folders)
  Episode*.md                           case-insensitive fallback globs
  Story.md                              series-level fallback

Series-level ``config.json`` (see tools/story_input.py) supplies defaults —
``intake_mode``, ``duration_mode``, ``style``, ``language``, ``cast``,
``constraints``, ``never_show``, ``default_duration_minutes`` — which the
optional sidecar ``episodes/episode-<N>.meta.json`` (or flat
``episode-<N>.meta.json``) then overrides per episode:

  {
    "title": "...", "intake_mode": "preserve_script | develop_from_concept",
    "duration_mode": "fixed | auto", "target_seconds": 180,
    "audio": {"voice_refs": {"S1": "path.mp3"},
              "music_track": "...", "dialogue_master": "...",
              "ambience": "..."},
    "handoff_from": "epi-5",
    "cast": [...], "notes": "..."
  }

Audio paths in the sidecar may be absolute or relative to the story folder;
``materialize_audio`` copies them into ``<run>/audio/`` using the
``tools.audio_refs`` naming convention (bare-role names are episode-wide;
per-generation/per-scene materialization is deferred to the authoring stage
when scene ids are known).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time

AUDIO_EXTENSIONS = ("mp3", "wav", "m4a", "aac", "flac")
SCHEMA = "story-maker-v5.episode_spec/v1"

_STATUS_SCHEMA = "story-maker-v5.status/v1"
_INDEX_SCHEMA = "story-maker-v5.episodes_index/v1"

# Episode lifecycle stages. Writing stages are tracked in the story-level
# episodes.json index; production stages in the run's status.json.
WRITING_STAGES = ("draft", "planned", "ready")
PRODUCTION_STAGES = (
    "planned",
    "assets_approved",
    "render_approved",
    "rendering",
    "qc_pending",
    "complete",
)


class EpisodeNotFoundError(Exception):
    pass


def _is_audio(path: str) -> bool:
    return path.rpartition(".")[2].lower() in AUDIO_EXTENSIONS


def _episode_glob(base: str, episode: int | None) -> list[str]:
    """Matching episode markdown files inside one directory."""
    if not os.path.isdir(base):
        return []
    if episode is not None:
        exact = os.path.join(base, f"episode-{episode}.md")
        if os.path.isfile(exact):
            return [exact]
        pat = rf"episode[-\s_]?{episode}\b.*\.md$"
    else:
        pat = r"episode[-\s_]?\d+\b.*\.md$"
    return [
        os.path.join(base, n) for n in sorted(os.listdir(base))
        if re.match(pat, n, re.IGNORECASE)
    ]


def find_episode_story(stories_root: str, series: str, episode: int | None) -> str:
    """Locate the episode's source story file.

    Search order: ``episodes/episode-N/`` folder (canonical), then flat
    ``episodes/episode-N.md``, then the flat story root (legacy folders).
    Raises EpisodeNotFoundError listing what was searched when nothing
    matches.
    """
    from tools.story_input import episode_dir, _episode_md_in

    story_dir = os.path.join(stories_root, series)
    if not os.path.isdir(story_dir):
        raise EpisodeNotFoundError(
            f"story folder not found: {story_dir}"
        )
    if episode is not None:
        ep_dir = episode_dir(story_dir, episode)
        if os.path.isdir(ep_dir):
            cand = _episode_md_in(ep_dir, episode)
            if os.path.isfile(cand):
                return cand
    else:
        # No episode requested: prefer the lowest-numbered folder episode.
        eps_base = os.path.join(story_dir, "episodes")
        if os.path.isdir(eps_base):
            dirs = sorted(
                int(m.group(1))
                for n in os.listdir(eps_base)
                if (m := re.match(r"episode[-\s_]?(\d+)$", n, re.IGNORECASE))
                and os.path.isdir(os.path.join(eps_base, n))
            )
            for num in dirs:
                cand = _episode_md_in(episode_dir(story_dir, num), num)
                if os.path.isfile(cand):
                    return cand
    for base in (os.path.join(story_dir, "episodes"), story_dir):
        hits = _episode_glob(base, episode)
        if hits:
            return hits[0]
    fallback = os.path.join(story_dir, "Story.md")
    if os.path.isfile(fallback):
        return fallback
    raise EpisodeNotFoundError(
        f"no episode story in {story_dir} — looked for "
        f"episodes/episode-{episode}/episode-{episode}.md, "
        f"episodes/episode-{episode}.md, episode-{episode}.md, "
        "Episode*.md, Story.md"
    )


def find_episode_number(stories_root: str, series: str, story_path: str) -> int | None:
    """Infer the episode number from a discovered filename."""
    m = re.search(r"episode[-\s_]?(\d+)", os.path.basename(story_path), re.IGNORECASE)
    return int(m.group(1)) if m else None


def load_meta(story_dir: str, episode: int | None) -> dict:
    """Load per-episode meta. Search order: ``episodes/episode-N/meta.json``
    (canonical), ``episodes/episode-N/episode-N.meta.json``,
    ``episodes/episode-N.meta.json``, flat ``episode-N.meta.json``, then the
    ``episode.meta.json`` / ``story.meta.json`` fallbacks."""
    candidates = []
    if episode is not None:
        candidates += [
            os.path.join("episodes", f"episode-{episode}", "meta.json"),
            os.path.join("episodes", f"episode-{episode}",
                         f"episode-{episode}.meta.json"),
            os.path.join("episodes", f"episode-{episode}.meta.json"),
            f"episode-{episode}.meta.json",
        ]
    candidates += ["episode.meta.json", "story.meta.json"]
    for rel in candidates:
        path = os.path.join(story_dir, rel)
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    return {}


def build_episode_spec(
    *,
    series: str,
    episode: int,
    story_path: str,
    meta: dict,
    stories_root: str,
    outputs_root: str,
    story_file_arg: str | None = None,
    config: dict | None = None,
) -> dict:
    """Merge discovered story + sidecar meta + series ``config.json`` into
    an EpisodeSpec dict.

    Precedence per field: episode meta > series config > built-in default.
    ``cast`` concatenates (config cast is the roster; meta may add
    episode-specific roles) with meta entries overriding by ``id``.
    """
    cfg = config or {}
    run_dir = os.path.join(outputs_root, series, f"epi-{episode}")
    audio = dict(meta.get("audio") or {})
    cast = {c.get("id"): c for c in (cfg.get("cast") or []) if c.get("id")}
    for c in (meta.get("cast") or []):
        if c.get("id"):
            cast[c["id"]] = {**cast.get(c["id"], {}), **c}
    spec = {
        "schema": SCHEMA,
        "series": series,
        "episode": episode,
        "title": meta.get("title") or "",
        "source": os.path.relpath(os.path.abspath(story_path)),
        "source_file_arg": story_file_arg,
        "intake_mode": (
            meta.get("intake_mode") or cfg.get("intake_mode")
            or "preserve_script"
        ),
        "duration_mode": (
            meta.get("duration_mode") or cfg.get("duration_mode") or "auto"
        ),
        "target_seconds": int(
            meta.get("target_seconds")
            or (float(cfg.get("default_duration_minutes") or 0) * 60)
            or 0
        ),
        "style": cfg.get("style") or "3d_animation",
        "style_notes": cfg.get("style_notes") or "",
        "language": cfg.get("language") or "en",
        "tone": cfg.get("tone") or "",
        "rating": cfg.get("rating") or "",
        "aspect": cfg.get("aspect") or "16:9",
        "constraints": list(cfg.get("constraints") or []),
        "never_show": list(cfg.get("never_show") or []),
        "audio": audio,
        "handoff_from": meta.get("handoff_from") or "",
        "cast": [cast[k] for k in cast],
        "notes": meta.get("notes") or "",
        "run_dir": os.path.relpath(os.path.abspath(run_dir)),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    return spec


def _audio_dest_name(role: str, src: str, scene_id: str = "",
                     gen_id: str = "") -> str:
    """Map a meta-declared audio role to the audio_refs naming convention.

    Episode-wide refs get a bare-role name (``voice_S1.mp3``); scene/gen
    materialization is an authoring-stage concern once scene ids exist.
    """
    ext = src.rpartition(".")[2].lower() or "mp3"
    if scene_id and gen_id:
        return f"{scene_id}_{gen_id}__{role}.{ext}"
    if scene_id:
        return f"{scene_id}__{role}.{ext}"
    return f"{role}.{ext}"


def materialize_audio(spec: dict, run_dir: str, story_dir: str) -> list[str]:
    """Copy audio refs into ``<run>/audio/``.

    Precedence (later writes win on name clashes):

      1. ``<story>/audio/``                    series-wide refs, verbatim
      2. ``<story>/episodes/episode-N/audio/`` this episode's refs, verbatim
         — shadows same-named series files
      3. meta-declared refs                    renamed to their role
         (``voice_refs {S1: path}`` → ``voice_S1.<ext>``, ``music_track`` →
         ``music.<ext>``, ``dialogue_master`` → ``dialogue.<ext>``,
         ``ambience`` → ``ambience.<ext>``) — the most explicit wins

    Bare-role names act as episode-wide references; scoped names
    (``s1__ambience.wav``, ``s1_g2__voice_S1.mp3``) keep their scope when
    copied. Returns the list of written file paths.
    """
    audio_dir = os.path.join(run_dir, "audio")
    written: list[str] = []

    def _copy_verbatim(src_dir: str, overwrite: bool) -> None:
        if not os.path.isdir(src_dir):
            return
        os.makedirs(audio_dir, exist_ok=True)
        for name in sorted(os.listdir(src_dir)):
            p = os.path.join(src_dir, name)
            if not os.path.isfile(p) or not _is_audio(p):
                continue
            dest = os.path.join(audio_dir, name)
            if overwrite or not os.path.exists(dest):
                if not os.path.exists(dest):
                    written.append(dest)
                shutil.copy2(p, dest)

    _copy_verbatim(os.path.join(story_dir, "audio"), overwrite=False)
    ep_audio = os.path.join(
        story_dir, "episodes", f"episode-{spec['episode']}", "audio")
    _copy_verbatim(ep_audio, overwrite=True)

    audio = spec.get("audio") or {}
    declared: list[tuple[str, str]] = []
    for speaker, path in (audio.get("voice_refs") or {}).items():
        declared.append((f"voice_{speaker}", path))
    for key, role in (
        ("music_track", "music"),
        ("dialogue_master", "dialogue"),
        ("ambience", "ambience"),
        ("reference", "reference"),
    ):
        if audio.get(key):
            declared.append((role, audio[key]))

    for role, src in declared:
        src_path = src if os.path.isabs(src) else os.path.join(story_dir, src)
        if not os.path.isfile(src_path):
            raise FileNotFoundError(
                f"audio ref declared in meta not found: {src_path}"
            )
        os.makedirs(audio_dir, exist_ok=True)
        dest = os.path.join(audio_dir, _audio_dest_name(role, src_path))
        if not os.path.exists(dest):
            written.append(dest)
        shutil.copy2(src_path, dest)
    return written


_ENTITY_ID_RE = re.compile(r"^(char|loc|obj)_\d+$")


def materialize_user_assets(
    spec: dict, run_dir: str, story_dir: str, assets_dir: str
) -> dict:
    """Import user-supplied media from the story folder.

    - ``characters/`` ``locations/`` ``objects/`` images are copied into
      ``<assets_dir>/<section>/<entity_id>.<ext>`` and registered in the
      shared registry as ``origin: user`` + ``status: approved`` —
      pre-approved by the user, they win over generated sheets.
    - ``cast[].ref`` entries map an image to an explicit entity id;
      otherwise the filename stem is the id (``char_01.png`` → ``char_01``).
    - ``series.md`` → ``<run>/series_bible.md`` (Agent 1 context).
    - ``style/`` images → ``<run>/style/``; ``references/`` clips →
      ``<run>/references/``.

    Returns ``{"imported": [...], "warnings": [...]}``; non-conforming
    entity ids warn instead of failing.
    """
    from tools import story_input as si

    imported: list[dict] = []
    warnings: list[str] = []
    assets = si.list_user_assets(story_dir)

    # cast[].ref gives an explicit image→entity mapping that shadows the
    # filename convention.
    ref_to_entity: dict[str, str] = {}
    for c in spec.get("cast") or []:
        ref = (c or {}).get("ref") or ""
        cid = (c or {}).get("id") or ""
        if ref and cid:
            ref_to_entity[os.path.normpath(ref)] = cid

    registry = None
    try:
        from tools.asset_registry_v2 import RegistryV2

        registry = RegistryV2(run_dir, assets_dir, series=spec["series"])
    except Exception as exc:  # pragma: no cover - h3 module absent
        warnings.append(f"asset registry unavailable: {exc}")

    for section in ("characters", "locations", "objects"):
        for item in assets.get(section) or []:
            rel = os.path.relpath(item["path"], story_dir)
            entity = ref_to_entity.get(os.path.normpath(rel),
                                       item["entity_id"])
            if not _ENTITY_ID_RE.match(entity):
                warnings.append(
                    f"{section}/{item['name']}: entity id '{entity}' is not "
                    f"a canonical id (char_NN/loc_NN/obj_NN) — add a cast "
                    "entry or rename the file"
                )
            dest_dir = os.path.join(assets_dir, section)
            os.makedirs(dest_dir, exist_ok=True)
            ext = item["name"].rpartition(".")[2].lower()
            dest = os.path.join(dest_dir, f"{entity}.{ext}")
            shutil.copy2(item["path"], dest)
            if item.get("notes"):
                shutil.copy2(
                    item["notes"], os.path.join(dest_dir, f"{entity}.md")
                )
            if registry is not None:
                entry = {
                    "characters": registry.character,
                    "locations": registry.location,
                    "objects": registry.object,
                }[section](entity)
                entry["output_path"] = dest
                entry["origin"] = "user"
                entry["status"] = "approved"
            imported.append({"section": section, "entity": entity,
                             "dest": dest})
    if registry is not None:
        registry.save()

    bible = os.path.join(story_dir, "series.md")
    if os.path.isfile(bible):
        shutil.copy2(bible, os.path.join(run_dir, "series_bible.md"))

    for sub, key in (("style", "style"), ("references", "references")):
        for item in assets.get(sub) or []:
            dest_dir = os.path.join(run_dir, key)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, item["name"])
            shutil.copy2(item["path"], dest)
            imported.append({"section": sub, "entity": item["entity_id"],
                             "dest": dest})

    # Episode-scoped references/ shadow same-named series files.
    ep_refs = os.path.join(
        story_dir, "episodes", f"episode-{spec['episode']}", "references")
    if os.path.isdir(ep_refs):
        dest_dir = os.path.join(run_dir, "references")
        for name in sorted(os.listdir(ep_refs)):
            p = os.path.join(ep_refs, name)
            ext = name.rpartition(".")[2].lower()
            if os.path.isfile(p) and ext in si.VIDEO_EXTENSIONS:
                dest = os.path.join(dest_dir, name)
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(p, dest)
                imported.append({"section": "references",
                                 "entity": name.rpartition(".")[0],
                                 "dest": dest})

    return {"imported": imported, "warnings": warnings}


def write_episode_spec(spec: dict, run_dir: str) -> str:
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "episode_spec.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


# -- status tracking ----------------------------------------------------------


def _load_json(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _atomic_write(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def set_production_status(
    run_dir: str, stage: str, *, extra: dict | None = None
) -> dict:
    """Write ``<run>/status.json`` for a production stage transition."""
    if stage not in PRODUCTION_STAGES:
        raise ValueError(f"unknown production stage: {stage}")
    path = os.path.join(run_dir, "status.json")
    data = _load_json(path)
    history = data.get("history") or []
    history.append(
        {"stage": stage, "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    )
    data.update(
        {
            "schema": _STATUS_SCHEMA,
            "stage": stage,
            "history": history,
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    )
    if extra:
        data.update(extra)
    _atomic_write(path, data)
    return data


def set_writing_status(
    story_dir: str, episode: int, stage: str, *, run_dir: str = ""
) -> dict:
    """Update ``<story>/episodes.json`` — the series-level index of writing
    readiness plus the latest production stage per episode."""
    path = os.path.join(story_dir, "episodes.json")
    idx = _load_json(path)
    episodes = idx.setdefault("episodes", {})
    key = f"epi-{episode}"
    entry = episodes.setdefault(key, {})
    entry["writing"] = stage
    entry["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if run_dir:
        entry["run_dir"] = os.path.relpath(os.path.abspath(run_dir))
    idx["schema"] = _INDEX_SCHEMA
    _atomic_write(path, idx)
    return idx


def set_index_production(
    story_dir: str, episode: int, stage: str, *, run_dir: str = ""
) -> dict:
    """Record the latest production stage in the series index without
    touching the writing stage."""
    path = os.path.join(story_dir, "episodes.json")
    idx = _load_json(path)
    episodes = idx.setdefault("episodes", {})
    entry = episodes.setdefault(f"epi-{episode}", {})
    entry["production"] = stage
    entry["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if run_dir:
        entry["run_dir"] = os.path.relpath(os.path.abspath(run_dir))
    idx["schema"] = _INDEX_SCHEMA
    _atomic_write(path, idx)
    return idx


def episode_status(run_dir: str) -> dict:
    """Read the current status view for one run dir."""
    status = _load_json(os.path.join(run_dir, "status.json"))
    return status or {"stage": "planned", "history": []}
