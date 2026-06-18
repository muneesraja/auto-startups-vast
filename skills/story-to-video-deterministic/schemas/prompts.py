from pydantic import BaseModel
from typing import Optional

class PromptsMeta(BaseModel):
    blueprint_version: int
    last_updated_by: str
    last_updated_at: str

class CharacterSheetEntry(BaseModel):
    prompt_type: str = "ideogram_json"
    prompt: Optional[dict] = None
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_3_character_prompter"

class FFShotEntry(BaseModel):
    prompt_type: str  # "ideogram_json" or "extracted_frame"
    prompt: Optional[dict] = None
    reference_images: list[str] = []
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str

class ConsistencyPatchEntry(BaseModel):
    prompt_type: str = "flux_edit"
    prompt: Optional[str] = None
    reference_images: list[str] = []
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_5_consistency_prompter"

class LFShotEntry(BaseModel):
    prompt_type: str = "flux_edit"
    prompt: Optional[str] = None
    reference_images: list[str] = []
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_6_lf_prompter"

class MotionPromptEntry(BaseModel):
    prompt: Optional[str] = None
    duration_seconds: int
    ff_image: Optional[str] = None
    lf_image: Optional[str] = None
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_7_motion_prompter"

class PromptsFile(BaseModel):
    meta: PromptsMeta
    character_sheets: dict[str, CharacterSheetEntry] = {}
    ff_shots: dict[str, FFShotEntry] = {}
    consistency_patches: dict[str, ConsistencyPatchEntry] = {}
    lf_shots: dict[str, LFShotEntry] = {}
    motion_prompts: dict[str, MotionPromptEntry] = {}
