"""Canonical ``stories/<name>/`` input-folder spec for story-maker-v5.

The folder IS the API — the CLI scaffold (``scripts/init_story.py``), the
story-intake CLI (``skills/story-intake/cli.py``), and
``prepare_episode.py`` all read and write the same on-disk contract:

  stories/<name>/
    config.json            series-level defaults (all fields optional)
    series.md              optional story bible (world, tone, canon rules)
    episodes/
      episode-1/           one folder per episode
        episode-1.md         script / concept
        meta.json            per-episode overrides
        audio/               episode-scoped audio refs
        references/          episode-scoped video refs
    audio/                 series-wide audio refs (theme, shared voices)
    characters/            user-supplied character reference images (+ .md notes)
    locations/             user-supplied location reference images
    objects/               user-supplied prop reference images
    style/                 moodboard / style reference images
    references/            series-wide video clips (g1 motion/style seed)
    README.intake.md       generated field documentation

Discovery order for episode files: ``episodes/episode-N/`` folder first,
then flat ``episodes/episode-N.md``, then flat root (legacy folders like
``stories/shiva/episode-6.md`` keep working). Audio precedence when
materializing a run: meta-declared > episode folder > series folder.
"""

from __future__ import annotations

import json
import os
import re
import time

IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "webp")
VIDEO_EXTENSIONS = ("mp4", "mov", "webm")

# Asset subfolders that map into the shared registry.
ASSET_DIRS = {
    "characters": "character_plate",
    "locations": "location_lock",
    "objects": "prop",
}

STYLES = (
    "3d_animation",
    "realistic",
    "pixar",
    "comic",
    "watercolor",
    "bw_cartoon",
)

DEFAULT_CONFIG: dict = {
    "title": "",
    "style": "3d_animation",
    "style_notes": "",
    "intake_mode": "preserve_script",
    "duration_mode": "preserve_script",
    "default_duration_minutes": 0,
    "language": "en",
    "tone": "",
    "rating": "family",
    "aspect": "16:9",
    "cast": [],
    "constraints": [],
    "never_show": [],
    "defaults": {},
}

_README = """# Intake folder — {name}

Everything in this folder is **user input**. The pipeline reads it by path;
generated output always lands under `outputs/`, never here.

| Path | What goes there |
|---|---|
| `config.json` | Series defaults: style, intake/duration mode, language, tone, cast, constraints, `never_show`. All fields optional. |
| `series.md` | Story bible — world, character relationships, recurring props, canon rules. Read by Agent 1 for every episode. |
| `episodes/episode-N/episode-N.md` | The episode script or concept. Empty template is fine — fill it in, or ask the agent to draft from `series.md`. |
| `episodes/episode-N/meta.json` | Optional per-episode overrides: `title`, `target_seconds`, `intake_mode`, `audio`, `handoff_from`, `notes`. |
| `episodes/episode-N/audio/` | Audio refs used **only** by this episode — same role names as `audio/`; shadows same-named series files. |
| `episodes/episode-N/references/` | Video clips used only by this episode (g1 motion seed). |
| `audio/` | Series-wide audio refs: `voice_S1.mp3` (per-speaker voice), `music.wav`, `ambience.flac`, `dialogue.mp3`, `s1__ambience.wav` (scene-scoped), `s1_g2__voice_S1.mp3` (generation-scoped). |
| `characters/` | Character reference images (`shiva.png`) + optional `shiva.md` appearance notes. Imported **approved** — your art wins over generated sheets. |
| `locations/` | Location reference images (`kailasa.png`). Imported approved. |
| `objects/` | Prop reference images (`trishula.png`). Imported approved. |
| `style/` | Moodboard / style frames — guide the `style` choice and `style_notes`. |
| `references/` | Optional video clips used as motion/style reference for a generation-1 render. |

## config.json fields

- `title` — display title.
- `style` — `3d_animation` (default) | `realistic` | `pixar` | `comic` | `watercolor` | `bw_cartoon`.
- `style_notes` — free-text style guidance repeated verbatim in prompts.
- `intake_mode` — `preserve_script` (keep authored scenes) | `develop_from_concept` (expand a logline).
- `duration_mode` — `preserve_script` | `compress` | `expand` | `exact`.
- `default_duration_minutes` — fallback when an episode file declares none.
- `language` — dialogue language tag for `<d>[Lang] ...</d>` lines.
- `tone`, `rating`, `aspect` — production metadata.
- `cast` — `[{{"id": "char_01", "name": "Shiva", "speaker": "S1", "ref": "characters/shiva.png"}}]`.
  `speaker` binds the character to the `voice_<SN>` audio ref and the `(SN)`
  speaker ID in video prompts.
- `constraints` — hard narrative rules (BLOCKER severity downstream).
- `never_show` — global exclusions (e.g. "blood", "Shiva crying").
- `defaults` — provider/knob overrides (`image_provider`, `megapixels`, ...).

## Prepare an episode

```bash
python3 skills/story-maker-v5/scripts/prepare_episode.py \\
    --stories-root stories --series {name} --episode 1
```

or via the intake CLI:

```bash
python3 skills/story-intake/cli.py prepare {name} 1
```
"""

_SERIES_MD = """# {title} — Story Bible

<!-- World, tone, character relationships, recurring props, canon rules.
     Agent 1 reads this before writing every episode. -->

## World


## Characters


## Rules / canon


## Tone & style notes

"""

_EPISODE_MD = """# Episode {n} — <title>

<!-- Write the episode here: a full screenplay, a beat outline, or a
     one-paragraph concept. `intake_mode` in config.json decides how the
     agent treats it. -->

"""

_EPISODE_META = {
    "title": "",
    "target_seconds": 0,
    "intake_mode": "",
    "duration_mode": "",
    "audio": {},
    "handoff_from": "",
    "notes": "",
}


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "untitled"


def story_dir(stories_root: str, name: str) -> str:
    return os.path.join(stories_root, slugify(name))


def init_story(stories_root: str, name: str, *, title: str = "") -> str:
    """Scaffold ``stories/<name>/``. Idempotent — never overwrites existing
    files. Returns the story dir."""
    sd = story_dir(stories_root, name)
    ep1_dir = os.path.join(sd, "episodes", "episode-1")
    for sub in ("episodes/episode-1/audio", "episodes/episode-1/references",
                "audio", "characters", "locations", "objects",
                "style", "references"):
        os.makedirs(os.path.join(sd, sub), exist_ok=True)

    cfg_path = os.path.join(sd, "config.json")
    if not os.path.isfile(cfg_path):
        cfg = dict(DEFAULT_CONFIG)
        cfg["title"] = title or name.replace("-", " ").title()
        _atomic_json(cfg_path, cfg)

    _write_if_absent(
        os.path.join(sd, "series.md"),
        _SERIES_MD.format(title=title or name.replace("-", " ").title()),
    )
    _write_if_absent(
        os.path.join(ep1_dir, "episode-1.md"), _EPISODE_MD.format(n=1)
    )
    _write_if_absent(
        os.path.join(ep1_dir, "meta.json"),
        json.dumps(_EPISODE_META, indent=2) + "\n",
    )
    _write_if_absent(
        os.path.join(sd, "README.intake.md"), _README.format(name=slugify(name))
    )
    return sd


def _write_if_absent(path: str, text: str) -> None:
    if os.path.isfile(path):
        return
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _atomic_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_story_config(story_dir_path: str) -> dict:
    """Read ``config.json`` merged over defaults. Unknown keys pass through."""
    cfg = dict(DEFAULT_CONFIG)
    path = os.path.join(story_dir_path, "config.json")
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                user = json.load(f)
            if isinstance(user, dict):
                cfg.update(user)
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save_story_config(story_dir_path: str, cfg: dict) -> str:
    path = os.path.join(story_dir_path, "config.json")
    _atomic_json(path, cfg)
    return path


def episode_dir(story_dir_path: str, episode: int) -> str:
    """Canonical per-episode folder (may not exist yet)."""
    return os.path.join(story_dir_path, "episodes", f"episode-{episode}")


def _episode_md_in(ep_dir: str, episode: int) -> str:
    """The story markdown inside an ``episodes/episode-N/`` folder — the
    canonical ``episode-N.md``, else ``story.md``, else the first ``*.md``,
    else the canonical path (expected location, may not exist)."""
    for cand in (f"episode-{episode}.md", "story.md"):
        p = os.path.join(ep_dir, cand)
        if os.path.isfile(p):
            return p
    if os.path.isdir(ep_dir):
        mds = sorted(n for n in os.listdir(ep_dir)
                     if n.lower().endswith(".md"))
        if mds:
            return os.path.join(ep_dir, mds[0])
    return os.path.join(ep_dir, f"episode-{episode}.md")


def list_episode_files(story_dir_path: str) -> list[dict]:
    """Episodes of a story, folder-form first (``episodes/episode-N/``),
    then flat ``episodes/episode-N.md``, then flat root (legacy)."""
    found: dict[int, str] = {}
    eps_base = os.path.join(story_dir_path, "episodes")
    if os.path.isdir(eps_base):
        for n in sorted(os.listdir(eps_base)):
            m = re.match(r"episode[-\s_]?(\d+)$", n, re.IGNORECASE)
            if m and os.path.isdir(os.path.join(eps_base, n)):
                num = int(m.group(1))
                found[num] = _episode_md_in(os.path.join(eps_base, n), num)
    for base in (eps_base, story_dir_path):
        if not os.path.isdir(base):
            continue
        for n in sorted(os.listdir(base)):
            m = re.match(r"episode[-\s_]?(\d+)\b.*\.md$", n, re.IGNORECASE)
            if m:
                found.setdefault(int(m.group(1)), os.path.join(base, n))
    return [
        {"episode": num, "path": found[num],
         "name": os.path.basename(found[num]),
         "dir": os.path.dirname(found[num])}
        for num in sorted(found)
    ]


def list_user_assets(story_dir_path: str) -> dict[str, list[dict]]:
    """Scan ``characters/`` ``locations/`` ``objects/`` ``style/`` and
    ``references/`` for user-supplied media. Each entry carries the file
    path, its entity id (filename stem), and any ``<stem>.md`` sidecar."""
    out: dict[str, list[dict]] = {}
    for sub, exts in (
        ("characters", IMAGE_EXTENSIONS),
        ("locations", IMAGE_EXTENSIONS),
        ("objects", IMAGE_EXTENSIONS),
        ("style", IMAGE_EXTENSIONS),
        ("references", VIDEO_EXTENSIONS),
    ):
        folder = os.path.join(story_dir_path, sub)
        items: list[dict] = []
        if os.path.isdir(folder):
            for name in sorted(os.listdir(folder)):
                p = os.path.join(folder, name)
                stem, dot, ext = name.rpartition(".")
                if not os.path.isfile(p) or ext.lower() not in exts:
                    continue
                sidecar = os.path.join(folder, stem + ".md")
                items.append({
                    "name": name,
                    "entity_id": slugify(stem).replace("-", "_"),
                    "path": p,
                    "rel": os.path.relpath(p, story_dir_path),
                    "notes": sidecar if os.path.isfile(sidecar) else "",
                })
        out[sub] = items
    return out


# -- intake operations (story-intake CLI / any manager uses these) --------------

_PREFIX_FOR = {"characters": "char", "locations": "loc", "objects": "obj"}
_ENTITY_RE = re.compile(r"^(char|loc|obj)_\d+$")


def next_entity_id(story_dir_path: str, kind: str) -> str:
    """Next free canonical id for an asset folder — ``char_02`` etc.,
    counting both files on disk and ``cast[]`` entries in config."""
    prefix = _PREFIX_FOR[kind]
    used = {
        i["entity_id"]
        for i in list_user_assets(story_dir_path).get(kind) or []
    }
    for c in load_story_config(story_dir_path).get("cast") or []:
        cid = str((c or {}).get("id", ""))
        if cid.startswith(prefix + "_"):
            used.add(cid)
    n = 1
    while f"{prefix}_{n:02d}" in used:
        n += 1
    return f"{prefix}_{n:02d}"


def audio_ref_name(role: str, ext: str, *, speaker: str = "",
                   scene: str = "", gen: str = "") -> str:
    """Build a role/scope-convention audio filename (tools/audio_refs.py).

    ``voice`` needs ``speaker`` (``S1`` → ``voice_S1.mp3``); ``scene``/``gen``
    add the ``s1__`` / ``s1_g2__`` scope prefix.
    """
    from tools import audio_refs as ar

    if role == "voice" and not speaker:
        raise ValueError("voice role needs a speaker (e.g. S1)")
    r = f"voice_{speaker}" if role == "voice" else role
    if role not in ar.VALID_ROLES and not r.startswith("voice_"):
        raise ValueError(f"bad role: {role}")
    if scene and gen:
        stem = f"{scene}_{gen}__{r}"
    elif scene:
        stem = f"{scene}__{r}"
    elif gen:
        stem = f"{gen}__{r}"
    else:
        stem = r
    return f"{stem}.{ext}"


def import_file(story_dir_path: str, kind: str, src: str, *,
                entity: str = "", role: str = "reference",
                speaker: str = "", scene: str = "", gen: str = "",
                episode: int | None = None) -> str:
    """Copy a user file into the story folder under the naming convention.

    - ``characters|locations|objects``: ``entity`` (or ``new``/empty → next
      free canonical id) becomes ``<kind>/<entity>.<ext>``.
    - ``audio``: role/scope params build the filename; ``episode`` routes it
      to ``episodes/episode-N/audio/`` instead of series ``audio/``.
    - ``style`` / ``references``: keep the original filename; ``episode``
      routes references into ``episodes/episode-N/references/``.

    Returns the story-relative destination path.
    """
    from tools import audio_refs as ar

    allowed = {
        "characters": IMAGE_EXTENSIONS, "locations": IMAGE_EXTENSIONS,
        "objects": IMAGE_EXTENSIONS, "style": IMAGE_EXTENSIONS,
        "audio": ar.AUDIO_EXTENSIONS, "references": VIDEO_EXTENSIONS,
    }
    if kind not in allowed:
        raise ValueError(f"bad kind: {kind}")
    ext = src.rpartition(".")[2].lower()
    if ext not in allowed[kind]:
        raise ValueError(
            f"{kind}/ accepts {', '.join(allowed[kind])} — got .{ext}")
    if not os.path.isfile(src):
        raise FileNotFoundError(src)

    if kind in _PREFIX_FOR:
        e = entity.strip()
        if not e or e == "new":
            e = next_entity_id(story_dir_path, kind)
        e = re.sub(r"[^A-Za-z0-9_]+", "_", e)
        dest_dir = os.path.join(story_dir_path, kind)
        fname = f"{e}.{ext}"
    elif kind == "audio":
        fname = audio_ref_name(role, ext, speaker=speaker,
                               scene=scene, gen=gen)
        dest_dir = (os.path.join(episode_dir(story_dir_path, episode),
                                 "audio")
                    if episode is not None
                    else os.path.join(story_dir_path, "audio"))
    elif kind == "references" and episode is not None:
        dest_dir = os.path.join(episode_dir(story_dir_path, episode),
                                "references")
        fname = os.path.basename(src)
    else:
        dest_dir = os.path.join(story_dir_path, kind)
        fname = os.path.basename(src)

    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, fname)
    import shutil as _sh
    _sh.copy2(src, dest)
    return os.path.relpath(dest, story_dir_path)


def story_warnings(story_dir_path: str) -> list[str]:
    """Input-quality checks for a story folder: empty episodes, cast refs
    pointing at missing files, non-canonical asset ids, audio names that
    match no role, and flat files shadowed by an episode folder."""
    cfg = load_story_config(story_dir_path)
    assets = list_user_assets(story_dir_path)
    episodes = list_episode_files(story_dir_path)
    warn: list[str] = []

    cast_refs, cast_ids = set(), set()
    for c in cfg.get("cast") or []:
        cid, ref = (c or {}).get("id") or "", (c or {}).get("ref") or ""
        if cid:
            cast_ids.add(cid)
        if ref:
            cast_refs.add(os.path.normpath(ref))
            if not os.path.isfile(os.path.join(story_dir_path, ref)):
                warn.append(f"cast {cid or '?'}: ref '{ref}' missing on disk")
    for e in episodes:
        try:
            if not open(e["path"], encoding="utf-8").read().strip():
                warn.append(f"{e['name']} is empty")
        except OSError:
            pass
    for n in {e["episode"] for e in episodes}:
        if not os.path.isdir(episode_dir(story_dir_path, n)):
            continue
        for alt in (os.path.join(story_dir_path, "episodes",
                                 f"episode-{n}.md"),
                    os.path.join(story_dir_path, f"episode-{n}.md")):
            if os.path.isfile(alt):
                warn.append(
                    f"{os.path.relpath(alt, story_dir_path)} is shadowed by "
                    f"episodes/episode-{n}/ — remove the flat file")
    for section in ("characters", "locations", "objects"):
        for item in assets.get(section) or []:
            rel = os.path.normpath(item["rel"])
            if not _ENTITY_RE.match(item["entity_id"]) \
                    and rel not in cast_refs:
                warn.append(
                    f"{item['rel']}: id '{item['entity_id']}' isn't canonical "
                    "(char_NN/loc_NN/obj_NN) and isn't mapped in cast")
            elif (section == "characters"
                  and item["entity_id"] not in cast_ids
                  and rel not in cast_refs):
                warn.append(
                    f"{item['rel']}: not in cast — add a cast row to bind "
                    "speaker/ref")
    audio_dirs = [os.path.join(story_dir_path, "audio")]
    for e in episodes:
        audio_dirs.append(os.path.join(e["dir"], "audio"))
    for ad in audio_dirs:
        if not os.path.isdir(ad):
            continue
        for n in sorted(os.listdir(ad)):
            p = os.path.join(ad, n)
            stem = n.rpartition(".")[0]
            if (not os.path.isfile(p)
                    or n.rpartition(".")[2].lower() not in _audio_exts()):
                continue
            if not _audio_stem_ok(stem):
                warn.append(
                    f"{os.path.relpath(p, story_dir_path)}: doesn't match a "
                    "role name (voice_S1, music, s1__ambience, …) — ignored")
    return warn


def _audio_exts() -> tuple:
    from tools import audio_refs as ar
    return ar.AUDIO_EXTENSIONS


_AUDIO_STEM_RE = re.compile(
    r"^(s\d+(_g\d+)?__)?(voice_[A-Za-z0-9]+|dialogue|music|ambience"
    r"|reference)$|^s\d+(_g\d+)?$|^g\d+(__.+)?$")


def _audio_stem_ok(stem: str) -> bool:
    return bool(_AUDIO_STEM_RE.match(stem))
