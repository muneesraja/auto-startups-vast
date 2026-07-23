from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

StylePace = Literal["slow", "medium", "fast"]
PipelineMode = Literal["per_shot", "storyboard"]
CharacterSheetMode = Literal["llm", "template"]
StoryboardSheetMode = Literal["llm", "template"]


@dataclass(frozen=True)
class StyleProfile:
    id: str
    label: str
    prompt_dir: str | None
    render_style: str
    default_target_seconds: int
    min_shot_seconds: int
    max_shot_seconds: int
    default_pace: StylePace
    pipeline_mode: PipelineMode = "per_shot"
    panels_per_sheet: int = 0
    min_panels_per_sheet: int = 0
    use_backgrounds: bool = True
    character_sheet_mode: CharacterSheetMode = "llm"
    storyboard_sheet_mode: StoryboardSheetMode = "llm"


PROFILES: dict[str, StyleProfile] = {
    "cinematic": StyleProfile(
        id="cinematic",
        label="Cinematic",
        prompt_dir=None,
        render_style="3D CGI Pixar-style animated film, stylized cartoon render, not photorealistic",
        default_target_seconds=120,
        min_shot_seconds=6,
        max_shot_seconds=10,
        default_pace="medium",
        pipeline_mode="per_shot",
        panels_per_sheet=0,
        use_backgrounds=True,
    ),
    "reels": StyleProfile(
        id="reels",
        label="Fast Reels",
        prompt_dir="reels",
        render_style="3D CGI Pixar-style animated film, stylized cartoon render, not photorealistic",
        default_target_seconds=30,
        min_shot_seconds=6,
        max_shot_seconds=10,
        default_pace="fast",
        pipeline_mode="per_shot",
        panels_per_sheet=0,
        use_backgrounds=True,
    ),
    "reel_v2": StyleProfile(
        id="reel_v2",
        label="Storyboard Reels",
        prompt_dir="reel_v2",
        render_style="3D CGI Pixar-style animated film, stylized cartoon render, not photorealistic",
        default_target_seconds=30,
        min_shot_seconds=6,
        max_shot_seconds=10,
        default_pace="fast",
        pipeline_mode="storyboard",
        panels_per_sheet=8,
        min_panels_per_sheet=8,
        use_backgrounds=False,
        character_sheet_mode="template",
        storyboard_sheet_mode="template",
    ),
}


def get_profile(style_id: str) -> StyleProfile:
    key = (style_id or "").strip().lower()
    if key in PROFILES:
        return PROFILES[key]
    valid = ", ".join(sorted(PROFILES))
    raise ValueError(f"Unknown style profile {style_id!r}; valid: {valid}")


def resolve_style(cli_value: str | None, env_value: str | None) -> StyleProfile:
    selected = (cli_value or env_value or "cinematic").strip().lower()
    return get_profile(selected)
