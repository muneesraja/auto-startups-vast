from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ReferenceSlot(BaseModel):
    role: Literal["character_sheet", "scene_background", "prior_shot"]
    asset_id: str
    priority: int = 0


class ShotImageSpec(BaseModel):
    shot_id: str
    generation_mode: Literal["grok_edit", "grok_t2i"]
    reference_strategy: Literal[
        "char_sheets_only", "char_sheets_and_background", "no_references"
    ]
    reference_slots: list[ReferenceSlot] = Field(default_factory=list)
    image_prompt: str
    reference_images: list[str] = Field(default_factory=list)
    output_path: str | None = None
    fal_image_url: str | None = None
    status: str = "pending"


class MotionSpec(BaseModel):
    shot_id: str
    motion_prompt: str = ""
    duration_seconds: int = Field(ge=1, le=16, default=8)
    scene_time_offset_seconds: int = Field(default=0, ge=0)
    pace: Literal["slow", "medium", "fast"] = "medium"
    motion_intent: str = ""
    camera_intent: str = ""
    audio_intent: str = ""
    vision_confirmed: bool = False
    vision_source_image: str | None = None
    output_path: str | None = None
    status: str = "pending"


class CharacterSheetSpec(BaseModel):
    character_id: str
    sheet_prompt: str
    output_path: str | None = None
    fal_image_url: str | None = None
    status: str = "pending"


class SceneBackgroundSpec(BaseModel):
    scene_id: str
    background_prompt: str
    output_path: str | None = None
    fal_image_url: str | None = None
    status: str = "pending"


class LocationSheetSpec(BaseModel):
    location_id: str
    sheet_prompt: str
    output_path: str | None = None
    fal_image_url: str | None = None
    status: str = "pending"


class DirectorMotionSegment(BaseModel):
    """Timed Prompt Relay beat within one Director clip (ratios of clip duration)."""

    start_ratio: float = Field(ge=0.0, le=1.0)
    end_ratio: float = Field(ge=0.0, le=1.0)
    prompt: str = ""

    @model_validator(mode="after")
    def validate_span(self) -> DirectorMotionSegment:
        if self.end_ratio <= self.start_ratio:
            raise ValueError("motion segment end_ratio must be > start_ratio")
        if not str(self.prompt or "").strip():
            raise ValueError("motion segment prompt must be non-empty")
        return self


class DirectorClip(BaseModel):
    """One render unit: I2V standalone or FLF2V first→last transition."""

    clip_id: str
    segment_id: str
    start_panel_id: str
    end_panel_id: str
    workflow: Literal["i2v", "flf2v"]
    continuous: bool = False
    duration_seconds: int = Field(ge=3, le=10, default=6)
    pace: Literal["slow", "medium", "fast"] = "fast"
    motion_class: Literal[
        "talking",
        "walking",
        "horse_riding",
        "forest_exploration",
        "large_reveal",
        "fast_action",
        "general",
    ] = "general"
    guidance: Literal["balanced", "prompt_follow", "strong"] = "balanced"
    i2v_strength: float = Field(ge=0.4, le=0.95, default=0.7)
    cfg: float = Field(ge=1.0, le=1.5, default=1.0)
    last_frame_strength: float | None = Field(default=None, ge=0.5, le=1.0)
    # LTX Director layers: global look + timed Prompt Relay beats.
    # motion_prompt remains the legacy flat fallback / template-backend prompt.
    global_prompt: str = ""
    motion_segments: list[DirectorMotionSegment] = Field(default_factory=list)
    motion_prompt: str = ""
    rationale: str = ""
    output_path: str | None = None
    status: str = "pending"

    @model_validator(mode="after")
    def validate_workflow(self) -> DirectorClip:
        if self.start_panel_id == self.end_panel_id and self.workflow != "i2v":
            raise ValueError("standalone clip must use workflow=i2v")
        if self.start_panel_id != self.end_panel_id and self.workflow != "flf2v":
            raise ValueError("transition clip must use workflow=flf2v")
        return self


class DirectorSegment(BaseModel):
    """Hard-cut-separated editorial segment containing one or more linked clips."""

    segment_id: str
    cut_before: bool = False
    motion_brief: str = ""
    clips: list[DirectorClip] = Field(default_factory=list)


class StoryboardVideoScenePlan(BaseModel):
    """Assistant-director plan for one storyboard scene."""

    scene_id: str
    sheet_path: str | None = None
    duration_budget_seconds: int = Field(ge=1, default=24)
    duration_total_seconds: int = Field(ge=0, default=0)
    segments: list[DirectorSegment] = Field(default_factory=list)
    repairs: list[str] = Field(default_factory=list)
    status: str = "planned"


class GenerationSpecs(BaseModel):
    character_sheets: dict[str, CharacterSheetSpec] = Field(default_factory=dict)
    location_sheets: dict[str, LocationSheetSpec] = Field(default_factory=dict)
    backgrounds: dict[str, SceneBackgroundSpec] = Field(default_factory=dict)
    shot_images: dict[str, ShotImageSpec] = Field(default_factory=dict)
    motion: dict[str, MotionSpec] = Field(default_factory=dict)
    storyboard_video_scenes: dict[str, StoryboardVideoScenePlan] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_keys(self) -> GenerationSpecs:
        for key, spec in self.character_sheets.items():
            if spec.character_id != key:
                raise ValueError(f"character_sheets key {key} != character_id")
        for key, spec in self.shot_images.items():
            if spec.shot_id != key:
                raise ValueError(f"shot_images key {key} != shot_id")
        for key, spec in self.motion.items():
            if spec.shot_id != key:
                raise ValueError(f"motion key {key} != shot_id")
        for key, spec in self.backgrounds.items():
            if spec.scene_id != key:
                raise ValueError(f"backgrounds key {key} != scene_id")
        for key, spec in self.location_sheets.items():
            if spec.location_id != key:
                raise ValueError(f"location_sheets key {key} != location_id")
        for key, spec in self.storyboard_video_scenes.items():
            if spec.scene_id != key:
                raise ValueError(f"storyboard_video_scenes key {key} != scene_id")
        return self
