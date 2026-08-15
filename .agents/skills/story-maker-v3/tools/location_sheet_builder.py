"""Location lock-sheet prompt builder (v3).

Fills ``prompts/location_sheet_template.md`` from a location dict that Agent 2
authors in ``scenes.md`` (location_id, name, description, establishing_prompt).
A location lock is a T2I empty-stage plate reused as an edit reference for every
storyboard sheet set in that location — it keeps world geography consistent.

As with char sheets, Agent 4 may author a complete location prompt as text
(``prompts/locations/<lid>.txt``); ``build_images.py`` prefers the text file and
only falls back to this builder when a structured ``<lid>.json`` is present.
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


def _normalize_id(location_id: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (location_id or "").strip().lower()).strip("_")


def resolve_location_sheet_fields(location: dict[str, Any]) -> dict[str, Any]:
    """Resolve a full location-lock field set from a location dict."""
    lid = _normalize_id(location.get("id") or location.get("location_id") or "")
    name = (location.get("name") or location.get("location_name") or lid or "Location").strip()
    description = (location.get("description") or location.get("location_description") or "").strip()
    establishing = (
        location.get("establishing_prompt")
        or location.get("establishing")
        or (description or f"An establishing wide shot of {name}.")
    ).strip()
    return {
        "location_id": lid or name.lower(),
        "location_name": name,
        "location_description": description or f"The location: {name}.",
        "establishing_prompt": establishing,
    }


def build_location_sheet_prompt(
    location: dict[str, Any], *, render_style: str, template: str | None = None,
) -> str:
    """Fill ``location_sheet_template.md`` from a location dict."""
    fields = resolve_location_sheet_fields(location)
    template_text = template or _load_prompt_file("location_sheet_template")
    return template_text.format(
        location_id=fields["location_id"],
        location_name=fields["location_name"],
        location_description=fields["location_description"],
        establishing_prompt=fields["establishing_prompt"],
        render_style=render_style,
    )


def load_location_prompt(prompt_path: str) -> tuple[str, dict[str, Any] | None]:
    """Load a location prompt from a file (``.txt`` → text; ``.json`` → fields)."""
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