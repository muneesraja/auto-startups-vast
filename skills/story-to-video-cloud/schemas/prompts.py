from pydantic import BaseModel
from typing import Optional

class PromptsMeta(BaseModel):
    blueprint_version: int
    last_updated_by: str
    last_updated_at: str

class CharacterSheetEntry(BaseModel):
    prompt_type: str = "grok_t2i"
    prompt: Optional[str] = None
    reference_images: list[str] = []
    output_path: Optional[str] = None
    fal_image_url: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_3_character_prompter"

class FFShotEntry(BaseModel):
    prompt_type: str = "grok_edit"  # "grok_edit" or "extracted_frame"
    prompt: Optional[str] = None
    reference_images: list[str] = []
    output_path: Optional[str] = None
    fal_image_url: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_4_ff_prompter"

class LFShotEntry(BaseModel):
    prompt_type: str = "grok_edit"
    prompt: Optional[str] = None
    reference_images: list[str] = []
    output_path: Optional[str] = None
    fal_image_url: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_5_lf_prompter"

class CharacterSpatialEntry(BaseModel):
    character_id: str
    reference_index: int
    screen_position: str
    visual_identifier: str
    action: str

class MotionPromptEntry(BaseModel):
    prompt: Optional[str] = None
    duration_seconds: int
    ff_image: Optional[str] = None
    lf_image: Optional[str] = None
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_6_motion_prompter"
    character_sounds: Optional[dict[str, list[str]]] = None

class PromptsFile(BaseModel):
    meta: PromptsMeta
    character_sheets: dict[str, CharacterSheetEntry] = {}
    ff_shots: dict[str, FFShotEntry] = {}
    lf_shots: dict[str, LFShotEntry] = {}
    lf_delta_plan: dict[str, str] = {}
    character_spatial_map: dict[str, list[CharacterSpatialEntry]] = {}
    motion_prompts: dict[str, MotionPromptEntry] = {}
