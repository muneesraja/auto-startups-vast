"""Object/prop sheet prompt builder (v3).

Fills ``prompts/object_sheet_template.md`` from an object dict that Agent 1
authors in ``developed_story.md`` (id, name, description, appearance).
An object sheet is a 4K T2I plate reused as a reference for storyboard sheets
and video prompts — it keeps prop appearance consistent across scenes and
episodes.

As with char/location sheets, Agent 4 may author a complete object prompt as
text (``prompts/objects/<oid>.txt``); ``build_images.py`` prefers the text file
and only falls back to this builder when a structured ``<oid>.json`` is present.
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


def _normalize_id(object_id: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", (object_id or "").strip().lower()).strip("_")


def resolve_object_sheet_fields(obj: dict[str, Any]) -> dict[str, Any]:
    """Resolve a full object-sheet field set from an object dict."""
    oid = _normalize_id(obj.get("id") or obj.get("object_id") or "")
    name = (obj.get("name") or obj.get("object_name") or oid or "Object").strip()
    description = (obj.get("description") or obj.get("object_description") or "").strip()
    appearance = (obj.get("appearance") or obj.get("object_appearance") or "").strip()
    return {
        "object_id": oid or name.lower(),
        "object_name": name,
        "object_description": description or f"The object: {name}.",
        "object_appearance": appearance or description or name,
    }


def build_object_sheet_prompt(
    obj: dict[str, Any], *, render_style: str, template: str | None = None,
) -> str:
    """Fill ``object_sheet_template.md`` from an object dict."""
    fields = resolve_object_sheet_fields(obj)
    template_text = template or _load_prompt_file("object_sheet_template")
    return template_text.format(
        object_id=fields["object_id"],
        object_name=fields["object_name"],
        object_description=fields["object_description"],
        object_appearance=fields["object_appearance"],
        render_style=render_style,
    )


def load_object_prompt(prompt_path: str) -> tuple[str, dict[str, Any] | None]:
    """Load an object prompt from a file (``.txt`` → text; ``.json`` → fields)."""
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
