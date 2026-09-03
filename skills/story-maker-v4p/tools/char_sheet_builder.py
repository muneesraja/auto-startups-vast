"""Character model-sheet prompt builder (trimmed for v4p).

Ported from skills/story-maker/scripts/nodes/character_sheet_builder.py with the
hardcoded ``CHARACTER_CANON`` production table REMOVED. In v4p, Agent 2 (Claude)
authors full character descriptions (name, species, appearance, age, features,
wardrobe) into ``scenes.md``; this module deterministically fills the
``prompts/character_sheet_template.md`` scaffold from that data. No LLM calls.

Agent 4 may instead author a complete char-sheet prompt as text
(``prompts/characters/<cid>.txt``); ``build_images.py`` prefers that text file
and only falls back to this builder when a structured ``<cid>.json`` is present.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROMPT_DIR = os.path.join(_SKILL_DIR, "prompts")


def _load_prompt_file(name: str) -> str:
    path = os.path.join(_PROMPT_DIR, f"{name}.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt template not found: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _bullet_block(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in items if item)


def _normalize_id(character_id: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (character_id or "").strip().lower()).strip("_")


def _split_appearance_lines(appearance: str) -> list[str]:
    text = (appearance or "").strip()
    if not text:
        return []
    parts = re.split(r"[.;]\s+|\n+", text)
    return [p.strip(" •-\t") for p in parts if p.strip(" •-\t")]


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text, flags=re.IGNORECASE) is not None


def _infer_species(appearance: str, name: str) -> str:
    """Infer species from appearance + name (animals checked before humans)."""
    lower = f"{appearance} {name}".lower()
    animal_rules: tuple[tuple[tuple[str, ...], str], ...] = (
        (("horse", "pony", "mare", "stallion", "foal", "colt"), "Horse"),
        (("dog", "retriever", "canine", "puppy", "hound"), "Dog"),
        (("parrot",), "Parrot"),
        (("bird",), "Bird"),
        (("elephant",), "Elephant"),
        (("deer", "fawn", "doe", "buck", "stag"), "Deer"),
        (("cat", "kitten", "feline"), "Cat"),
    )
    for words, species in animal_rules:
        if any(_has_word(lower, w) for w in words):
            return species
    human_words = ("human", "girl", "boy", "man", "woman", "father", "mother", "child", "person")
    if any(_has_word(lower, w) for w in human_words):
        return "Human"
    return "Character"


def _default_detail_closeups(species: str, accessories: list[str]) -> list[str]:
    accessory = next((a for a in accessories if a), "")
    if species.lower() == "human":
        return [
            "the head, face, hair, and shoulders, front-on",
            "the torso and wardrobe silhouette, front-on, no head repeating panel 5",
            f"the signature accessory as worn: {accessory}" if accessory else "one signature costume piece as worn",
            "hands and feet as worn, a different crop from panels 5-7",
        ]
    return [
        "the head and face, front-on",
        "the body markings and torso, no head repeating panel 5",
        f"the signature accessory or feature as worn: {accessory}" if accessory else "one signature marking or worn detail",
        "limbs, tail, or feet — a different crop from panels 5-7",
    ]


def _accessories_for_sheet(clothing_accessories: list[str]) -> list[str]:
    out: list[str] = []
    for item in clothing_accessories:
        text = (item or "").strip()
        if text and text not in out:
            out.append(text)
    return out[:8]


def _pad_closeups(raw: list[str] | None, species: str, accessories: list[str]) -> list[str]:
    defaults = _default_detail_closeups(species, accessories)
    out = [str(x).strip() for x in (raw or []) if str(x).strip()]
    for d in defaults:
        if len(out) >= 4:
            break
        if d not in out:
            out.append(d)
    while len(out) < 4:
        out.append(defaults[len(out) % 4])
    return out[:4]


def resolve_character_sheet_fields(character: dict[str, Any]) -> dict[str, Any]:
    """Resolve a full character-sheet field set from a story-plan character dict.

    No hardcoded canon: every default is derived from the character's own
    ``appearance``/``name``/``species`` (which Agent 2 authors). Lists provided
    in the dict win; missing ones are inferred.
    """
    cid = _normalize_id(character.get("id", ""))
    name = (character.get("name") or cid or "Character").strip()
    appearance = (character.get("appearance") or "").strip()

    species = (character.get("species") or "").strip() or _infer_species(appearance, name)
    role = (character.get("role") or "").strip() or "Story Character"
    age = (character.get("age") or "").strip() or "Unspecified"
    role_description = (character.get("role_description") or appearance or f"Character in the story: {name}.").strip()

    appearance_lines = _split_appearance_lines(appearance)
    distinctive_features = character.get("distinctive_features") or appearance_lines or [appearance or name]
    clothing_accessories = character.get("clothing_accessories") or (
        appearance_lines[1:] if len(appearance_lines) > 1 else ["As described in production notes"]
    )
    personality = character.get("personality") or ["Expressive", "Consistent", "Appealing", "Animation-ready"]
    accessories = _accessories_for_sheet(clothing_accessories)
    detail_closeups = _pad_closeups(character.get("detail_closeups"), species, accessories)

    return {
        "character_id": cid or name.lower(),
        "character_name": name,
        "species": species,
        "role": role,
        "age": age,
        "role_description": role_description,
        "personality": personality,
        "distinctive_features": distinctive_features,
        "clothing_accessories": clothing_accessories,
        "accessories": accessories,
        "color_palette_primary": character.get("color_palette_primary") or ["Warm tones"],
        "color_palette_secondary": character.get("color_palette_secondary") or ["Earth tones"],
        "color_palette_accent": character.get("color_palette_accent") or ["Golden accents"],
        "detail_closeups": detail_closeups,
        "closeup_head": detail_closeups[0],
        "closeup_torso": detail_closeups[1],
        "closeup_accessory": detail_closeups[2],
        "closeup_extra": detail_closeups[3],
        "appearance": appearance,
    }


def build_character_sheet_prompt(
    character: dict[str, Any], *, render_style: str, template: str | None = None,
) -> str:
    """Fill ``character_sheet_template.md`` from a character dict."""
    fields = resolve_character_sheet_fields(character)
    template_text = template or _load_prompt_file("character_sheet_template")
    return template_text.format(
        character_name=fields["character_name"],
        species=fields["species"],
        age=fields["age"],
        distinctive_features=_bullet_block(fields["distinctive_features"]),
        clothing_accessories=_bullet_block(fields["clothing_accessories"]),
        closeup_head=fields["closeup_head"],
        closeup_torso=fields["closeup_torso"],
        closeup_accessory=fields["closeup_accessory"],
        closeup_extra=fields["closeup_extra"],
        render_style=render_style,
    )


def load_character_prompt(prompt_path: str) -> tuple[str, dict[str, Any] | None]:
    """Load a char-sheet prompt from a file.

    ``.txt`` → (full prompt text, None). ``.json`` → the JSON is returned as
    fields; the caller fills the template via :func:`build_character_sheet_prompt`.
    Returns ("", None) if the file is absent.
    """
    if not os.path.isfile(prompt_path):
        return "", None
    raw = open(prompt_path, encoding="utf-8").read().strip()
    if not raw:
        return "", None
    if prompt_path.endswith(".json"):
        try:
            return "", json.loads(raw)
        except json.JSONDecodeError:
            return raw, None
    return raw, None