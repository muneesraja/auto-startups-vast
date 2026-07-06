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
    duration_seconds: int = Field(ge=4, le=16, default=8)
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


class GenerationSpecs(BaseModel):
    character_sheets: dict[str, CharacterSheetSpec] = Field(default_factory=dict)
    backgrounds: dict[str, SceneBackgroundSpec] = Field(default_factory=dict)
    shot_images: dict[str, ShotImageSpec] = Field(default_factory=dict)
    motion: dict[str, MotionSpec] = Field(default_factory=dict)

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
        return self
