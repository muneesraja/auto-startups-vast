"""Character model-sheet prompt builder (trimmed for v3).

Ported from skills/story-maker/scripts/nodes/character_sheet_builder.py with the
hardcoded ``CHARACTER_CANON`` production table REMOVED. In v3, Agent 2 (Claude)
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

EXPRESSION_LIST = [
    "Happy", "Laughing", "Curious", "Amazed", "Surprised", "Thinking",
    "Sleepy", "Excited", "Worried", "Sad", "Embarrassed", "Determined",
]

TURNAROUND_VIEWS = [
    "Front View", "3/4 Front", "Left Side", "Right Side",
    "Back View", "3/4 Rear", "Top View", "Bottom View",
]


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


def _default_action_poses(name: str, species: str) -> list[str]:
    label = name or "the character"
    if species.lower() == "human":
        return [
            f"{label} standing happily", f"{label} walking forward", f"{label} waving",
            f"{label} looking up in wonder", f"{label} sitting relaxed",
            f"{label} running with energy", f"{label} reaching outward", f"{label} laughing",
            f"{label} thinking thoughtfully", f"{label} posing confidently",
        ]
    return [
        f"{label} in neutral standing pose", f"{label} in alert pose", f"{label} in playful pose",
        f"{label} in resting pose", f"{label} in motion pose", f"{label} looking toward camera",
        f"{label} turning head curiously", f"{label} in expressive close-action pose",
        f"{label} in dynamic movement pose", f"{label} in friendly interaction pose",
    ]


def _default_detail_closeups(species: str) -> list[str]:
    if species.lower() == "human":
        return ["Face", "Eyes", "Hair texture", "Hands", "Feet", "Outfit fabric", "Accessories"]
    return ["Face", "Eyes", "Body markings", "Texture detail", "Limbs or wings", "Tail or feet"]


_ACCESSORY_HINTS = (
    "accessor", "scarf", "bag", "satchel", "belt", "boot", "shoe", "bracelet",
    "vest", "hat", "pack", "collar", "bead", "patch", "footwear",
)


def _accessories_for_sheet(clothing_accessories: list[str], detail_closeups: list[str]) -> list[str]:
    out: list[str] = []
    for item in clothing_accessories:
        text = (item or "").strip()
        if text and text not in out:
            out.append(text)
    if out:
        return out[:8]
    for item in detail_closeups:
        text = (item or "").strip()
        if not text:
            continue
        if any(h in text.lower() for h in _ACCESSORY_HINTS) and text not in out:
            out.append(text)
    return out[:8] or ["Key costume accessories as worn on the character"]


def _default_scale_reference(name: str, species: str) -> str:
    label = name or "the character"
    if species.lower() == "human":
        return (
            f"Show {label} standing beside a neutral gray adult silhouette.\n\n"
            "Height:\nApproximately 120 cm (4 ft)\n\nInclude a simple height reference line."
        )
    return (
        f"Show {label} beside a neutral gray silhouette of the same species.\n\n"
        "Include a simple height reference line."
    )


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
    detail_closeups = character.get("detail_closeups") or _default_detail_closeups(species)
    accessories = _accessories_for_sheet(clothing_accessories, detail_closeups)

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
        "scale_reference": character.get("scale_reference") or _default_scale_reference(name, species),
        "action_poses": character.get("action_poses") or _default_action_poses(name, species),
        "detail_closeups": detail_closeups,
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
        accessories=_bullet_block(fields["accessories"]),
        scale_reference=fields["scale_reference"],
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