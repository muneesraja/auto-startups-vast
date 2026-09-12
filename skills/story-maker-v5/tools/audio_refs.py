"""Optional audio reference discovery for story-maker-v5.

Looks under ``<run_dir>/audio/`` for per-generation, per-scene audio
references that are attached to Minimax H3's ``ref_audios`` slots at render
time and hashed into the render manifest.

Naming convention (checked most-specific first):

  <scene>_<gen>__<role>.<ext>   e.g. s1_g2__voice_S1.mp3
  <scene>_<gen>.<ext>           e.g. s1_g2.mp3        (role: reference)
  <gen>__<role>.<ext>           e.g. g2__music.wav
  <gen>.<ext>                   e.g. g2.mp3
  <scene>__<role>.<ext>         e.g. s1__ambience.flac
  <scene>.<ext>                 e.g. s1.mp3
  <role>.<ext>                  e.g. voice_S1.mp3, music.wav (episode-wide)

Episode-wide files are named by their bare role (``voice_<Sx>``, ``dialogue``,
``music``, ``ambience``) and apply to every generation; a same-role file at a
more specific scope shadows them. This is the scope ``prepare_episode.py``
materializes meta-declared refs into.

Roles (double-underscore suffix):
  voice_<Sx>   vocal timbre reference for speaker (Sx)
  dialogue     approved dialogue master to preserve verbatim
  music        music bed / source track
  ambience     ambience / soundscape reference
  reference    (default when no role suffix is present)

Supported extensions: mp3, wav, m4a, aac, flac.
"""

from __future__ import annotations

import os

AUDIO_EXTENSIONS = ("mp3", "wav", "m4a", "aac", "flac")

VALID_ROLES = ("voice", "dialogue", "music", "ambience", "reference")


def _role_for_name(stem: str) -> str:
    """Extract the role from a filename stem ('s1_g2__voice_S1' -> 'voice_S1')."""
    if "__" in stem:
        role = stem.rsplit("__", 1)[1].strip()
        if role:
            return role
    return "reference"


def find_audio_refs(run_dir: str, scene_id: str, gen_id: str) -> list[dict]:
    """Return all audio references for a generation, most-specific scope first.

    Returns a list of ``{"path": ..., "role": ..., "scope": ...}`` dicts.
    The first matching scope wins for each role — files at a more specific
    scope shadow the same role at a broader scope.
    """
    audio_dir = os.path.join(run_dir, "audio")
    if not os.path.isdir(audio_dir):
        return []

    found: list[dict] = []
    seen_roles: set[str] = set()
    scopes = (
        ("gen", f"{scene_id}_{gen_id}"),
        ("gen_short", gen_id),
        ("scene", scene_id),
        ("episode", None),
    )
    for scope, base in scopes:
        try:
            names = sorted(os.listdir(audio_dir))
        except OSError:
            return found
        for name in names:
            stem, dot, ext = name.rpartition(".")
            if not dot or ext.lower() not in AUDIO_EXTENSIONS:
                continue
            if scope == "episode":
                # Bare-role filename: voice_S1.mp3, music.wav, dialogue.mp3.
                if not (stem in VALID_ROLES or stem.startswith("voice_")):
                    continue
                role = stem
                if role in seen_roles:
                    continue
                path = os.path.join(audio_dir, name)
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    found.append({"path": path, "role": role, "scope": scope})
                    seen_roles.add(role)
            elif stem == base or stem.startswith(base + "__"):
                role = _role_for_name(stem)
                if role in seen_roles:
                    continue
                path = os.path.join(audio_dir, name)
                if os.path.isfile(path) and os.path.getsize(path) > 0:
                    found.append({"path": path, "role": role, "scope": scope})
                    seen_roles.add(role)
    return found


def find_audio_ref(run_dir: str, scene_id: str, gen_id: str) -> str | None:
    """Back-compat helper: path of the single highest-priority audio ref."""
    refs = find_audio_refs(run_dir, scene_id, gen_id)
    return refs[0]["path"] if refs else None
