from pydantic import BaseModel, Field
from typing import Optional

class DeltaFromFF(BaseModel):
    camera_change: str = Field(description="Camera movement between FF and LF")
    subject_changes: str = Field(description="What the subject does differently")
    environment_changes: str = Field(description="Background element changes")
    particle_effects: str = Field(description="Small floating elements")

class ShotFF(BaseModel):
    description: str
    camera_framing: str
    character_expressions: dict[str, str] = {}
    source: Optional[str] = None  # "extracted_from_previous_video" for continuations
    ideogram_prompt: Optional[dict] = None
    ideogram_prompt_status: str = "pending"
    consistency_prompt: Optional[str] = None
    consistency_prompt_status: str = "pending"
    consistency_references: list[str] = []
    generated_image_path: Optional[str] = None
    consistent_image_path: Optional[str] = None
    generation_status: str = "pending"

class ShotLF(BaseModel):
    description: str
    camera_framing: str
    character_expressions: dict[str, str] = {}
    delta_from_ff: DeltaFromFF
    flux_edit_prompt: Optional[str] = None
    flux_edit_prompt_status: str = "pending"
    flux_references: list[str] = []
    generated_image_path: Optional[str] = None
    generation_status: str = "pending"

class ShotMotion(BaseModel):
    prompt: Optional[str] = None
    prompt_status: str = "pending"
    video_path: Optional[str] = None
    extracted_last_frame_path: Optional[str] = None
    generation_status: str = "pending"

class Shot(BaseModel):
    shot_id: str
    shot_index: int
    duration_seconds: int = Field(ge=2, le=5)
    continuation_from_previous: bool
    wave: int = Field(ge=1, le=2)
    characters_present: list[str] = []
    director_notes: str
    ff: ShotFF
    lf: ShotLF
    motion: ShotMotion

class Scene(BaseModel):
    scene_id: str
    scene_title: str
    scene_duration_seconds: int
    environment: str
    time_of_day: str
    lighting: str
    shots: list[Shot]

class Character(BaseModel):
    id: str
    name: str
    appearance: str
    character_sheet_prompt: Optional[dict] = None
    character_sheet_path: Optional[str] = None
    character_sheet_status: str = "pending"

class BlueprintMeta(BaseModel):
    story_title: str
    style: str
    aesthetic: str
    total_duration_seconds: int
    total_scenes: int
    total_shots: int
    created_at: str
    last_updated_at: str
    version: int = 1

class Blueprint(BaseModel):
    meta: BlueprintMeta
    characters: list[Character]
    scenes: list[Scene]
