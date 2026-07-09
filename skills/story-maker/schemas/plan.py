from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PlanMeta(BaseModel):
    story_title: str
    style: str
    aesthetic: str
    color_palette: str | None = None
    target_duration_seconds: int | None = None
    duration_tolerance_percent: int = 15
    total_duration_seconds: int = 0
    total_scenes: int = 0
    total_shots: int = 0


class StoryCharacter(BaseModel):
    id: str
    name: str
    appearance: str
    voice_profile: str


LtxShotType = Literal[
    "establishing", "action", "reaction", "dialogue", "insert", "transition"
]
LtxComplexity = Literal["simple", "moderate", "complex"]
FrameStrategy = Literal["empty_then_enter", "at_rest_then_react", "in_action_continuous"]


class CharacterBlocking(BaseModel):
    character_id: str
    position: str = ""
    facing: str = ""


class ShotBrief(BaseModel):
    shot_id: str
    scene_id: str
    duration_seconds: int = Field(ge=1, le=16)
    characters_present: list[str] = Field(default_factory=list)
    director_notes: str = ""
    description: str
    scene_time_offset_seconds: int = Field(default=0, ge=0)
    environment_state: str = ""
    pace: Literal["slow", "medium", "fast"] = "medium"
    continuity_from_previous: bool = False
    ltx_shot_type: LtxShotType = "action"
    ltx_complexity: LtxComplexity = "moderate"
    frame_strategy: FrameStrategy | None = None
    motion_intent: str = ""
    camera_intent: str = ""
    audio_intent: str = ""
    subject_position: str = ""
    facing_direction: str = ""
    eyeline: str = ""
    background_region: str = ""


class StoryScene(BaseModel):
    scene_id: str
    title: str
    environment: str
    time_of_day: str
    lighting: str
    background_population: str = ""
    staging: str = ""
    blocking: list[CharacterBlocking] = Field(default_factory=list)
    shots: list[ShotBrief]


class StoryPlan(BaseModel):
    meta: PlanMeta
    characters: list[StoryCharacter]
    scenes: list[StoryScene]

    @model_validator(mode="after")
    def validate_story_plan(self) -> StoryPlan:
        char_ids = {c.id for c in self.characters}
        shot_count = 0
        duration_sum = 0
        for scene in self.scenes:
            for block in scene.blocking:
                if block.character_id not in char_ids:
                    raise ValueError(
                        f"Scene {scene.scene_id} blocking unknown character {block.character_id}"
                    )
            for shot in scene.shots:
                shot_count += 1
                duration_sum += shot.duration_seconds
                if shot.scene_id != scene.scene_id:
                    raise ValueError(f"Shot {shot.shot_id} scene_id mismatch")
                for cid in shot.characters_present:
                    if cid not in char_ids:
                        raise ValueError(f"Shot {shot.shot_id} unknown character {cid}")
        if self.meta.total_shots and self.meta.total_shots != shot_count:
            raise ValueError("meta.total_shots mismatch")
        if self.meta.total_duration_seconds and self.meta.total_duration_seconds != duration_sum:
            raise ValueError("meta.total_duration_seconds mismatch")
        return self

    def iter_shots(self):
        for scene in self.scenes:
            for shot in scene.shots:
                yield scene, shot

    def character_map(self) -> dict[str, StoryCharacter]:
        return {c.id: c for c in self.characters}


class StoryPlanDraft(BaseModel):
    meta: dict
    characters: list[StoryCharacter]
    scenes: list[StoryScene]

    def to_plan(self) -> StoryPlan:
        shot_count = sum(len(s.shots) for s in self.scenes)
        duration_sum = sum(sh.duration_seconds for s in self.scenes for sh in s.shots)
        meta = dict(self.meta)
        meta.setdefault("total_shots", shot_count)
        meta.setdefault("total_scenes", len(self.scenes))
        meta.setdefault("total_duration_seconds", duration_sum)
        return StoryPlan(meta=PlanMeta(**meta), characters=self.characters, scenes=self.scenes)


class AudioCue(BaseModel):
    dialogue: list[dict] = Field(default_factory=list)
    music: str | None = None
    sfx: list[str] = Field(default_factory=list)
    ambience: str | None = None


class ShotAudio(BaseModel):
    shot_id: str
    audio: AudioCue = Field(default_factory=AudioCue)
    transition: str | None = None


class SceneAudioMeta(BaseModel):
    scene_id: str
    music_bed: str | None = None
    ending_state: str | None = None


class AudioPlan(BaseModel):
    scenes: list[SceneAudioMeta]
    shots: dict[str, ShotAudio]

    @model_validator(mode="after")
    def validate_audio(self) -> AudioPlan:
        for shot_id, shot_audio in self.shots.items():
            if shot_audio.shot_id != shot_id:
                raise ValueError(f"Shot audio key {shot_id} != shot_id {shot_audio.shot_id}")
        return self


class SceneAsset(BaseModel):
    scene_id: str
    generate_background: bool = False
    background_prompt: str | None = None
    background_reference_mode: Literal["style_anchor", "full_plate"] = "style_anchor"
    rationale: str = ""


class SceneAssetsPlan(BaseModel):
    scenes: list[SceneAsset]


class NarrativeOutlineMeta(BaseModel):
    story_title: str
    target_duration_seconds: int
    duration_tolerance_percent: int = 15
    planned_act_count: int = 0
    logline: str | None = None
    theme: str | None = None
    protagonist_want: str | None = None


class NarrativeSceneOutline(BaseModel):
    scene_id: str
    title: str
    duration_budget_seconds: int = Field(ge=0)
    beats: list[str] = Field(default_factory=list)


class NarrativeAct(BaseModel):
    act_id: str
    title: str
    duration_budget_seconds: int = Field(ge=0)
    summary: str = ""
    scenes: list[NarrativeSceneOutline] = Field(default_factory=list)


class NarrativeOutline(BaseModel):
    meta: NarrativeOutlineMeta
    acts: list[NarrativeAct]


class VideoShot(BaseModel):
    video_shot_id: str
    scene_id: str
    panel_ids: list[str] = Field(default_factory=list)
    anchor_panel_id: str
    duration_seconds: int = Field(ge=1, le=16)
    motion_arc: str = ""
    pace: Literal["slow", "medium", "fast"] = "medium"

    @model_validator(mode="after")
    def validate_video_shot(self) -> "VideoShot":
        if not self.panel_ids:
            raise ValueError("panel_ids must not be empty")
        if self.anchor_panel_id not in self.panel_ids:
            raise ValueError("anchor_panel_id must be one of panel_ids")
        return self


class VideoShotScenePlan(BaseModel):
    scene_id: str
    video_shots: list[VideoShot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scene_plan(self) -> "VideoShotScenePlan":
        seen: set[str] = set()
        for shot in self.video_shots:
            if shot.scene_id != self.scene_id:
                raise ValueError(
                    f"Video shot {shot.video_shot_id} scene_id mismatch for {self.scene_id}"
                )
            if shot.video_shot_id in seen:
                raise ValueError(f"Duplicate video_shot_id {shot.video_shot_id}")
            seen.add(shot.video_shot_id)
        return self


class VideoShotPlan(BaseModel):
    scenes: list[VideoShotScenePlan] = Field(default_factory=list)
