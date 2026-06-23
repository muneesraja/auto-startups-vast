from pydantic import BaseModel
from typing import Optional, Union

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
    base_image: Optional[str] = None
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_5_consistency_prompter"

class LFShotEntry(BaseModel):
    prompt_type: str = "ideogram_t2i"
    prompt: Optional[Union[dict, str]] = None
    reference_images: list[str] = []
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_6_lf_prompter"

class LFConsistencyPatchEntry(BaseModel):
    """Mirrors ConsistencyPatchEntry but for LF. Same Flux Klein 9B edit semantics:
    base_image = LF image; reference_images = character sheets only.

    Critically, the prompt must preserve the LF's delta from FF (the whole point
    of the LF) and only swap identity.
    """
    prompt_type: str = "flux_edit"
    prompt: Optional[str] = None
    reference_images: list[str] = []
    base_image: Optional[str] = None
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_8_lf_consistency_prompter"

class CharacterSpatialEntry(BaseModel):
    """One character's placement within a shot. Listed per shot_id in
    `character_spatial_map`. Drives per-character-anchored consistency prompts
    (esp. for 2+ character shots where Flux Klein needs an explicit spatial cue
    to avoid identity swaps)."""
    character_id: str
    reference_index: int
    screen_position: str
    visual_identifier: str
    action: str

class VisionReviewCharacter(BaseModel):
    character_id: str
    visible: Optional[bool] = None
    identity_match: Optional[float] = None
    pose_preserved: Optional[bool] = None
    problems: list[str] = []

class VisionReviewEntry(BaseModel):
    """Audit-mode vision review. Does NOT block video generation; runs as a
    Wave-1 phase after both FF and LF consistency patches complete. Writes a
    review JSON file alongside the other artifacts and surfaces problems for
    later repair-loop iteration."""
    pass_status: bool = False
    score: Optional[float] = None
    frame_analyzed: Optional[str] = None
    characters: list[VisionReviewCharacter] = []
    recommended_action: Optional[str] = None
    notes: Optional[str] = None
    status: str = "pending"

class MotionPromptEntry(BaseModel):
    prompt: Optional[str] = None
    duration_seconds: int
    ff_image: Optional[str] = None
    lf_image: Optional[str] = None
    output_path: Optional[str] = None
    status: str = "pending"
    generated_by: str = "step_7_motion_prompter"

class LFDeltaPlanEntry(BaseModel):
    delta_type: str

class PromptsFile(BaseModel):
    meta: PromptsMeta
    character_sheets: dict[str, CharacterSheetEntry] = {}
    ff_shots: dict[str, FFShotEntry] = {}
    consistency_patches: dict[str, ConsistencyPatchEntry] = {}
    lf_shots: dict[str, LFShotEntry] = {}
    lf_consistency_patches: dict[str, LFConsistencyPatchEntry] = {}
    lf_delta_plan: dict[str, str] = {}
    character_spatial_map: dict[str, list[CharacterSpatialEntry]] = {}
    ff_vision_reviews: dict[str, VisionReviewEntry] = {}
    lf_vision_reviews: dict[str, VisionReviewEntry] = {}
    motion_prompts: dict[str, MotionPromptEntry] = {}
