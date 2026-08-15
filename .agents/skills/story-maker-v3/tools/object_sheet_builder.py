"""Object / prop sheet prompt builder (v3).

Fills ``prompts/object_sheet_template.md`` from an objects/props spec.
An objects sheet is a 4K (3840x2160) T2I production asset board showing key props
and objects used across an episode or scene for visual and material consistency.
"""

from __future__ import annotations

import json
import os
from typing import Any

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROMPT_DIR = os.path.join(_SKILL_DIR, "prompts")


def _load_prompt_file(name: str) -> str:
    path = os.path.join(_PROMPT_DIR, f"{name}.md")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Prompt template not found: {path}")
    with open(path, encoding="utf-8") as f:
        return f.read()


def build_object_sheet_prompt(
    data: dict[str, Any], *, render_style: str, template: str | None = None,
) -> str:
    """Fill ``object_sheet_template.md`` from a dict of object definitions."""
    template_text = template or _load_prompt_file("object_sheet_template")
    return template_text.format(
        context_title=data.get("context_title", "Scene Objects & Props"),
        hero_props=data.get("hero_props", "").strip(),
        secondary_props=data.get("secondary_props", "").strip(),
        render_style=render_style,
    )


def load_object_prompt(prompt_path: str) -> tuple[str, dict[str, Any] | None]:
    """Load an object prompt from a file (``.txt`` -> text; ``.json`` -> fields)."""
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
