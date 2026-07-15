"""Deterministic character model-sheet prompt builder (reel_v2 / research-aligned)."""
from __future__ import annotations

import os
import re
from typing import Any

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXPRESSION_LIST = [
    "Happy",
    "Laughing",
    "Curious",
    "Amazed",
    "Surprised",
    "Thinking",
    "Sleepy",
    "Excited",
    "Worried",
    "Sad",
    "Embarrassed",
    "Determined",
]

TURNAROUND_VIEWS = [
    "Front View",
    "3/4 Front",
    "Left Side",
    "Right Side",
    "Back View",
    "3/4 Rear",
    "Top View",
    "Bottom View",
]

# Production canon keyed by normalized character id (from Research/story-board/*).
CHARACTER_CANON: dict[str, dict[str, Any]] = {
    "naila": {
        "species": "Human",
        "role": "Main Character",
        "age": "5 Years",
        "role_description": (
            "Young girl living at the center of a beautiful forest animal sanctuary with her father."
        ),
        "personality": [
            "Curious",
            "Kind-hearted",
            "Compassionate",
            "Cheerful",
            "Brave",
            "Innocent",
            "Gentle",
            "Playful",
            "Animal Lover",
            "Adventurous",
        ],
        "distinctive_features": [
            "Curly dark brown shoulder-length hair",
            "Large expressive warm brown eyes",
            "Light brown skin",
            "Soft rounded cheeks",
            "Small button nose",
            "Friendly bright smile",
            "Childlike Pixar proportions",
            "Expressive eyebrows",
            "Soft innocent facial features",
        ],
        "clothing_accessories": [
            "Forest-green knee-length dress",
            "Subtle leaf embroidery near the hem",
            "Brown leather waist belt",
            "Small wooden bead bracelet",
            "Barefoot",
            "Natural forest-inspired clothing",
        ],
        "color_palette_primary": ["Forest Green", "Warm Brown", "Cream White"],
        "color_palette_secondary": ["Leaf Green", "Earth Brown"],
        "color_palette_accent": ["Golden Yellow", "Soft Orange"],
        "scale_reference": (
            "Show Naila standing beside a neutral gray adult silhouette.\n\n"
            "Height:\nApproximately 105 cm (3 ft 5 in)\n\n"
            "Include a simple height reference line."
        ),
        "action_poses": [
            "Standing happily",
            "Running through the forest",
            "Waving",
            "Jumping with excitement",
            "Sitting while talking to animals",
            "Gently hugging Azhagi (imaginary interaction only)",
            "Looking upward in wonder",
            "Walking proudly",
            "Holding a small basket of flowers",
            "Reaching toward a butterfly",
        ],
        "detail_closeups": [
            "Face",
            "Eyes",
            "Hair texture",
            "Hands",
            "Wooden bracelet",
            "Leaf embroidery on dress",
            "Bare feet",
            "Dress fabric texture",
        ],
    },
    "father": {
        "species": "Human",
        "role": "Supporting Character",
        "age": "Early 40s",
        "role_description": "Kind forest caretaker and Naila's father who protects the sanctuary.",
        "personality": [
            "Kind",
            "Protective",
            "Patient",
            "Warm",
            "Responsible",
            "Gentle",
            "Steady",
            "Encouraging",
        ],
        "distinctive_features": [
            "Athletic build",
            "Medium beard",
            "Warm smile",
            "Kind eyes",
            "Broad shoulders",
            "Confident but gentle posture",
            "Forest caretaker identity",
        ],
        "clothing_accessories": [
            "Khaki ranger shirt with rolled sleeves",
            "Khaki ranger trousers",
            "Leather belt",
            "Leather boots",
            "Simple forest caretaker tools on belt",
        ],
        "color_palette_primary": ["Khaki Tan", "Earth Brown", "Cream White"],
        "color_palette_secondary": ["Forest Green", "Warm Brown"],
        "color_palette_accent": ["Golden Yellow", "Soft Orange"],
        "scale_reference": (
            "Show Father standing beside a neutral gray adult silhouette.\n\n"
            "Height:\nApproximately 178 cm (5 ft 10 in)\n\n"
            "Include a simple height reference line."
        ),
        "action_poses": [
            "Standing watch over the sanctuary",
            "Walking through the forest path",
            "Kneeling to greet an animal",
            "Pointing toward the treehouse",
            "Carrying a wooden crate of supplies",
            "Waving hello warmly",
            "Resting hand on a wooden fence",
            "Looking out over the sanctuary",
            "Helping Naila climb a low step",
            "Sitting on a porch step at sunset",
        ],
        "detail_closeups": [
            "Face",
            "Eyes",
            "Beard texture",
            "Hands",
            "Leather boots",
            "Ranger shirt fabric",
            "Belt and tools",
            "Khaki trouser folds",
        ],
    },
    "azhagi": {
        "species": "Golden Retriever",
        "role": "Animal Companion",
        "age": "Young Adult",
        "role_description": "Friendly golden retriever companion who protects and plays with Naila.",
        "personality": [
            "Friendly",
            "Protective",
            "Loyal",
            "Playful",
            "Gentle",
            "Alert",
            "Affectionate",
        ],
        "distinctive_features": [
            "Fluffy golden fur",
            "Soft floppy ears",
            "Expressive protective face",
            "Gentle brown eyes",
            "Relaxed tail",
            "Warm cream-to-gold fur gradient",
            "Medium dog proportions",
        ],
        "clothing_accessories": [
            "Simple forest-themed collar (optional)",
            "Natural fur markings only",
            "No clothing",
        ],
        "color_palette_primary": ["Golden Yellow", "Cream White", "Warm Brown"],
        "color_palette_secondary": ["Honey Gold", "Soft Tan"],
        "color_palette_accent": ["Leaf Green", "Earth Brown"],
        "scale_reference": (
            "Show Azhagi standing beside a neutral gray dog silhouette.\n\n"
            "Height at shoulder:\nApproximately 58 cm (23 in)\n\n"
            "Include a simple height reference line."
        ),
        "action_poses": [
            "Sitting alert",
            "Running beside Naila",
            "Play bow",
            "Wagging tail happily",
            "Lying down relaxed",
            "Sniffing the ground curiously",
            "Looking up at Naila",
            "Trotting through grass",
            "Panting with a happy expression",
            "Standing protectively at Naila's side",
        ],
        "detail_closeups": [
            "Face",
            "Eyes",
            "Ears",
            "Paws",
            "Tail fur",
            "Golden coat texture",
            "Nose",
            "Collar detail",
        ],
    },
    "neju": {
        "species": "Green Parrot",
        "role": "Animal Companion",
        "age": "Adult",
        "role_description": "Colorful green parrot helper with bright personality and expressive eyes.",
        "personality": [
            "Curious",
            "Cheerful",
            "Expressive",
            "Playful",
            "Alert",
            "Mischievous",
            "Loyal",
        ],
        "distinctive_features": [
            "Bright green plumage",
            "Orange beak",
            "Blue wing tips",
            "Large expressive eyes",
            "Compact bird body",
            "Short tail",
            "Rounded head",
            "Subtle feather shading",
        ],
        "clothing_accessories": [
            "Natural feather markings only",
            "No clothing",
            "No accessories",
        ],
        "color_palette_primary": ["Bright Green", "Orange", "Blue"],
        "color_palette_secondary": ["Leaf Green", "Sky Blue"],
        "color_palette_accent": ["Golden Yellow", "Cream White"],
        "scale_reference": (
            "Show Neju perched beside a neutral gray bird silhouette.\n\n"
            "Height:\nApproximately 25 cm (10 in)\n\n"
            "Include a simple height reference line."
        ),
        "action_poses": [
            "Perched upright",
            "Wings slightly spread",
            "Head tilted curiously",
            "About to take flight",
            "Landing on a branch (imaginary prop only)",
            "Preening feathers",
            "Looking toward Naila",
            "Chirping with open beak",
            "Hopping on one foot",
            "Ruffling feathers playfully",
        ],
        "detail_closeups": [
            "Face",
            "Eyes",
            "Beak",
            "Wing feathers",
            "Tail feathers",
            "Green plumage texture",
            "Feet and claws",
            "Blue wing tip detail",
        ],
    },
}


def _load_prompt_file(name: str, *, style_id: str | None = None) -> str:
    style = (style_id or os.getenv("STORY_STYLE") or "").strip().lower()
    candidates: list[str] = []
    if style and style != "cinematic":
        candidates.append(os.path.join(_SKILL_DIR, "prompts", style, f"{name}.md"))
    candidates.append(os.path.join(_SKILL_DIR, "prompts", f"{name}.md"))
    for path in candidates:
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return f.read()
    raise FileNotFoundError(f"Prompt file not found for {name!r}; tried: {candidates}")


def _bullet_block(items: list[str]) -> str:
    return "\n".join(f"• {item}" for item in items if item)


def _palette_block(items: list[str]) -> str:
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
    """Whole-word match only — avoids 'man' matching inside 'mane'/'German'."""
    return re.search(rf"\b{re.escape(word)}\b", text, flags=re.IGNORECASE) is not None


def _infer_species(appearance: str, name: str) -> str:
    """Infer species from appearance + name.

    Animals are checked before humans so tokens like \"mane\" never flip a horse
    to Human via a naive substring match on \"man\".
    """
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

    human_words = (
        "human",
        "girl",
        "boy",
        "man",
        "woman",
        "father",
        "mother",
        "child",
        "person",
    )
    if any(_has_word(lower, w) for w in human_words):
        return "Human"
    return "Character"


def _default_action_poses(name: str, species: str) -> list[str]:
    label = name or "the character"
    if species.lower() in {"human"}:
        return [
            f"{label} standing happily",
            f"{label} walking forward",
            f"{label} waving",
            f"{label} looking up in wonder",
            f"{label} sitting relaxed",
            f"{label} running with energy",
            f"{label} reaching outward",
            f"{label} laughing",
            f"{label} thinking thoughtfully",
            f"{label} posing confidently",
        ]
    return [
        f"{label} in neutral standing pose",
        f"{label} in alert pose",
        f"{label} in playful pose",
        f"{label} in resting pose",
        f"{label} in motion pose",
        f"{label} looking toward camera",
        f"{label} turning head curiously",
        f"{label} in expressive close-action pose",
        f"{label} in dynamic movement pose",
        f"{label} in friendly interaction pose",
    ]


def _default_detail_closeups(species: str) -> list[str]:
    if species.lower() == "human":
        return ["Face", "Eyes", "Hair texture", "Hands", "Feet", "Outfit fabric", "Accessories"]
    return ["Face", "Eyes", "Body markings", "Texture detail", "Limbs or wings", "Tail or feet"]


_ACCESSORY_HINTS = (
    "accessor",
    "scarf",
    "bag",
    "satchel",
    "belt",
    "boot",
    "shoe",
    "bracelet",
    "vest",
    "hat",
    "pack",
    "collar",
    "bead",
    "patch",
    "footwear",
)


def _accessories_for_sheet(
    clothing_accessories: list[str],
    detail_closeups: list[str],
) -> list[str]:
    """Prefer outfit/accessory bullets; fall back to accessory-like detail close-ups."""
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
        low = text.lower()
        if any(h in low for h in _ACCESSORY_HINTS) and text not in out:
            out.append(text)
    return out[:8] or ["Key costume accessories as worn on the character"]


def _default_scale_reference(name: str, species: str) -> str:
    label = name or "the character"
    if species.lower() == "human":
        return (
            f"Show {label} standing beside a neutral gray adult silhouette.\n\n"
            "Height:\nApproximately 120 cm (4 ft)\n\n"
            "Include a simple height reference line."
        )
    return (
        f"Show {label} beside a neutral gray silhouette of the same species.\n\n"
        "Include a simple height reference line."
    )


def resolve_character_sheet_fields(character: dict[str, Any]) -> dict[str, Any]:
    """Merge story-plan character data with production canon defaults."""
    cid = _normalize_id(character.get("id", ""))
    name = (character.get("name") or cid or "Character").strip()
    appearance = (character.get("appearance") or "").strip()
    canon = CHARACTER_CANON.get(cid, {})

    species = (
        (character.get("species") or "").strip()
        or canon.get("species")
        or _infer_species(appearance, name)
    )
    role = canon.get("role") or "Story Character"
    age = canon.get("age") or "Unspecified"
    role_description = canon.get("role_description") or appearance or f"Character in the story: {name}."

    appearance_lines = _split_appearance_lines(appearance)
    distinctive_features = canon.get("distinctive_features") or appearance_lines or [appearance or name]
    clothing_accessories = canon.get("clothing_accessories") or (
        appearance_lines[1:] if len(appearance_lines) > 1 else ["As described in production notes"]
    )
    personality = canon.get("personality") or ["Expressive", "Consistent", "Appealing", "Animation-ready"]
    detail_closeups = canon.get("detail_closeups") or _default_detail_closeups(species)
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
        "color_palette_primary": canon.get("color_palette_primary") or ["Warm tones"],
        "color_palette_secondary": canon.get("color_palette_secondary") or ["Earth tones"],
        "color_palette_accent": canon.get("color_palette_accent") or ["Golden accents"],
        "scale_reference": canon.get("scale_reference") or _default_scale_reference(name, species),
        "action_poses": canon.get("action_poses") or _default_action_poses(name, species),
        "detail_closeups": detail_closeups,
        "appearance": appearance,
    }


def build_character_sheet_prompt(
    character: dict[str, Any],
    *,
    sheet_number: int = 1,
    render_style: str,
    template: str | None = None,
    style_id: str | None = "reel_v2",
) -> str:
    """Build a lean identity-sheet prompt for one character (regen-friendly)."""
    fields = resolve_character_sheet_fields(character)
    template_text = template or _load_prompt_file("character_sheet_template", style_id=style_id)

    prompt = template_text.format(
        sheet_number=f"{sheet_number:02d}",
        character_name=fields["character_name"],
        species=fields["species"],
        age=fields["age"],
        distinctive_features=_bullet_block(fields["distinctive_features"]),
        clothing_accessories=_bullet_block(fields["clothing_accessories"]),
        accessories=_bullet_block(fields["accessories"]),
        scale_reference=fields["scale_reference"],
        render_style=render_style,
    )
    return prompt


def build_character_sheet_specs(
    characters: list[dict[str, Any]],
    *,
    render_style: str,
    style_id: str | None = "reel_v2",
    template: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Build generation_specs character_sheets entries from story-plan characters."""
    specs: dict[str, dict[str, Any]] = {}
    for index, character in enumerate(characters, start=1):
        if not isinstance(character, dict):
            continue
        cid = (character.get("id") or "").strip()
        if not cid:
            continue
        sheet_prompt = build_character_sheet_prompt(
            character,
            sheet_number=index,
            render_style=render_style,
            template=template,
            style_id=style_id,
        )
        specs[cid] = {
            "character_id": cid,
            "sheet_prompt": sheet_prompt,
            "output_path": None,
            "fal_image_url": None,
            "status": "pending",
        }
    return specs
