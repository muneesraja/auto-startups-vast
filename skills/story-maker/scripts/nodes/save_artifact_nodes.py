"""Save artifact nodes — write planning and generation specs to disk."""
import json
import os
import re

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

import config
from schemas.plan import VideoShotPlan
from profiles import get_profile
from tools.workflow_builder import snap_duration_seconds, snap_ltx_duration
from ._json_util import clean_json_str
from .video_shot_cast import split_video_shots_by_anchor_cast


def _output_dir(ctx: Context) -> str:
    out = ctx.state.get("output_dir")
    if not out:
        raise ValueError("output_dir not set in state")
    os.makedirs(out, exist_ok=True)
    return out


def _stamp_planning_meta(data: dict, **model_fields: str) -> dict:
    if not isinstance(data, dict):
        return data
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
    meta.update(model_fields)
    data["_meta"] = meta
    return data


_STYLE_KEYWORDS_RE = re.compile(
    r"\b("
    r"hand-painted|storybook|oil(?: |-)?painting|watercolor|painterly|"
    r"pixar|cgi|3d|stylized|style|render|animation"
    r")\b",
    re.IGNORECASE,
)


def _apply_render_style(prompt: str, render_style: str) -> str:
    text = (prompt or "").strip()
    style = (render_style or "").strip()
    if not text:
        return style
    if not style:
        return text
    if style.lower() in text.lower():
        return text

    sentence_parts = [p.strip() for p in re.split(r"\.\s*", text) if p.strip()]
    if sentence_parts and _STYLE_KEYWORDS_RE.search(sentence_parts[-1]):
        if len(sentence_parts) == 1:
            comma_parts = [p.strip() for p in re.split(r",\s*", sentence_parts[0]) if p.strip()]
            while comma_parts and _STYLE_KEYWORDS_RE.search(comma_parts[-1]):
                comma_parts.pop()
            text = ", ".join(comma_parts) if comma_parts else sentence_parts[0]
        else:
            sentence_parts.pop()
            text = ". ".join(sentence_parts)

    text = text.strip(" ,;")
    if text and not text.endswith("."):
        text += "."
    return f"{text} {style}".strip()



async def save_developed_story(ctx: Context) -> None:
    raw = ctx.state.get("developed_story_content")
    if not raw:
        return
    content = raw.strip() if isinstance(raw, str) else str(raw).strip()
    path = os.path.join(_output_dir(ctx), "developed_story.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")
    ctx.state["developed_story_text"] = content
    ctx.state["developed_story_content"] = content
    print(f"📁 [save_developed_story] Wrote {path}")


async def save_scene_paper(ctx: Context) -> None:
    raw = ctx.state.get("scene_paper_content")
    if not raw:
        return
    content = raw.strip() if isinstance(raw, str) else str(raw).strip()
    path = os.path.join(_output_dir(ctx), "scene_paper.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")
    ctx.state["scene_paper_text"] = content
    print(f"📁 [save_scene_paper] Wrote {path}")


async def save_story_sheet_scene(ctx: Context) -> None:
    raw = ctx.state.get("story_sheet_scene_content")
    if not raw:
        return
    content = raw.strip() if isinstance(raw, str) else str(raw).strip()
    path = os.path.join(_output_dir(ctx), "story_sheet_scene.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        if not content.endswith("\n"):
            f.write("\n")
    ctx.state["story_sheet_scene_text"] = content
    print(f"📁 [save_story_sheet_scene] Wrote {path}")


async def save_narrative_outline(ctx: Context) -> None:
    raw = ctx.state.get("narrative_outline_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    parsed = _stamp_planning_meta(
        parsed,
        narrative_model=config.get_narrative_expander_model_id(),
    )
    path = os.path.join(_output_dir(ctx), "narrative_outline.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_narrative_outline] Wrote {path}")


async def save_story_plan(ctx: Context) -> None:
    raw = ctx.state.get("story_plan_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    parsed = _stamp_planning_meta(
        parsed,
        narrative_model=config.get_narrative_expander_model_id(),
        story_plan_model=config.get_story_plan_model_id(),
        secondary_model=config.get_secondary_model_id(),
        vision_model=config.get_vision_model_id(),
    )
    path = os.path.join(_output_dir(ctx), "story_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_story_plan] Wrote {path}")


async def save_audio_plan(ctx: Context) -> None:
    raw = ctx.state.get("audio_plan_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    path = os.path.join(_output_dir(ctx), "audio_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_audio_plan] Wrote {path}")


def _normalize_video_shot_plan(raw_plan: dict, story_plan: dict) -> dict:
    scenes_raw = raw_plan.get("scenes")
    if not isinstance(scenes_raw, list):
        raise ValueError("video_shot_plan.scenes must be a list")

    story_scene_order = [s.get("scene_id") for s in story_plan.get("scenes", []) if s.get("scene_id")]
    story_scene_lookup = {
        s.get("scene_id"): s for s in story_plan.get("scenes", []) if s.get("scene_id")
    }
    scene_plan_lookup = {
        s.get("scene_id"): s for s in scenes_raw if isinstance(s, dict) and s.get("scene_id")
    }

    normalized_scenes: list[dict] = []
    for scene_id in story_scene_order:
        story_scene = story_scene_lookup[scene_id]
        scene_plan = scene_plan_lookup.get(scene_id) or {"scene_id": scene_id, "video_shots": []}
        video_shots = scene_plan.get("video_shots")
        if not isinstance(video_shots, list):
            raise ValueError(f"{scene_id}.video_shots must be a list")

        panel_ids = [sh.get("shot_id") for sh in story_scene.get("shots", []) if sh.get("shot_id")]
        panel_index = {pid: idx for idx, pid in enumerate(panel_ids)}
        # LTX wall-clock: prefer scene duration_budget; panel durations are editorial only.
        budget_raw = story_scene.get("duration_budget_seconds")
        if budget_raw is not None:
            try:
                scene_budget = int(budget_raw)
            except (TypeError, ValueError):
                scene_budget = 0
        else:
            scene_budget = 0
        if scene_budget <= 0:
            # Fallback: ~8s per ~3 panels (primary LTX clip density for a sheet scene).
            scene_budget = max(8, ((len(panel_ids) + 2) // 3) * 8)

        normalized_video_shots: list[dict] = []
        consumed: list[str] = []
        for idx, shot in enumerate(video_shots, start=1):
            if not isinstance(shot, dict):
                raise ValueError(f"{scene_id}.video_shots[{idx}] must be an object")
            local_panels = shot.get("panel_ids") or []
            if not local_panels:
                raise ValueError(f"{scene_id}.video_shots[{idx}] has empty panel_ids")
            for pid in local_panels:
                if pid not in panel_index:
                    raise ValueError(f"{scene_id}.video_shots[{idx}] unknown panel_id {pid}")
            sorted_ids = sorted(local_panels, key=lambda p: panel_index[p])
            expected = list(range(panel_index[sorted_ids[0]], panel_index[sorted_ids[-1]] + 1))
            actual = [panel_index[p] for p in sorted_ids]
            if actual != expected:
                raise ValueError(
                    f"{scene_id}.video_shots[{idx}] panel_ids must be consecutive in story order"
                )
            consumed.extend(sorted_ids)
            anchor = shot.get("anchor_panel_id") or sorted_ids[0]
            if anchor not in sorted_ids:
                raise ValueError(f"{scene_id}.video_shots[{idx}] anchor_panel_id must be in panel_ids")
            raw_dur = int(shot.get("duration_seconds", 8))
            # Keep optional 3–15 if already in band; otherwise snap to primary {6,8,10}.
            if 3 <= raw_dur <= 15 and raw_dur not in (6, 8, 10):
                bounded = snap_ltx_duration(raw_dur, prefer_primary=False)
            else:
                bounded = snap_ltx_duration(raw_dur, prefer_primary=True)
            normalized_video_shots.append(
                {
                    "video_shot_id": shot.get("video_shot_id") or f"{scene_id}_vshot_{idx:02d}",
                    "scene_id": scene_id,
                    "panel_ids": sorted_ids,
                    "anchor_panel_id": anchor,
                    "duration_seconds": snap_duration_seconds(bounded, fps=25),
                    "motion_arc": str(shot.get("motion_arc") or "").strip(),
                    "pace": str(shot.get("pace") or "medium").strip().lower(),
                }
            )

        if sorted(consumed, key=lambda p: panel_index[p]) != panel_ids:
            raise ValueError(f"{scene_id}: panel coverage mismatch; must cover each panel exactly once")

        # Split groups that invent cast absent from the anchor still.
        characters = story_plan.get("characters") or []
        normalized_video_shots = split_video_shots_by_anchor_cast(
            normalized_video_shots,
            story_scene,
            characters=characters,
        )
        # Re-validate coverage after cast split.
        split_panels = [
            pid
            for vs in normalized_video_shots
            for pid in (vs.get("panel_ids") or [])
        ]
        if sorted(split_panels, key=lambda p: panel_index[p]) != panel_ids:
            raise ValueError(
                f"{scene_id}: panel coverage mismatch after cast-coherent split"
            )

        # Reconcile toward scene budget using primary LTX steps {6,8,10} when possible.
        primary = (6, 8, 10)
        snapped_total = sum(int(shot["duration_seconds"]) for shot in normalized_video_shots)
        diff = int(scene_budget) - snapped_total
        if diff != 0 and normalized_video_shots:
            step = 1 if diff > 0 else -1
            remaining = abs(diff)
            i = 0
            guard = 0
            while remaining > 0 and guard < 1000:
                shot = normalized_video_shots[i % len(normalized_video_shots)]
                candidate = int(shot["duration_seconds"]) + step
                if 3 <= candidate <= 15:
                    # Prefer landing on primary values when close.
                    if candidate in primary or remaining <= 2:
                        shot["duration_seconds"] = candidate
                        remaining -= 1
                    elif step > 0 and candidate < 10:
                        shot["duration_seconds"] = candidate
                        remaining -= 1
                    elif step < 0 and candidate > 6:
                        shot["duration_seconds"] = candidate
                        remaining -= 1
                i += 1
                guard += 1
            for shot in normalized_video_shots:
                d = int(shot["duration_seconds"])
                if d in primary:
                    shot["duration_seconds"] = d
                elif 3 <= d <= 15:
                    shot["duration_seconds"] = snap_ltx_duration(d, prefer_primary=False)
                else:
                    shot["duration_seconds"] = snap_ltx_duration(d, prefer_primary=True)
                shot["duration_seconds"] = snap_duration_seconds(
                    int(shot["duration_seconds"]), fps=25
                )

        normalized_scenes.append({"scene_id": scene_id, "video_shots": normalized_video_shots})

    return {"scenes": normalized_scenes}


async def save_video_shot_plan(ctx: Context) -> None:
    raw = ctx.state.get("video_shot_plan_content")
    if not raw:
        return
    story_raw = ctx.state.get("story_plan_content")
    if not story_raw:
        raise ValueError("story_plan_content required before saving video shot plan")

    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    story_plan = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw
    normalized = _normalize_video_shot_plan(parsed, story_plan)
    validated = VideoShotPlan(**normalized).model_dump()

    ctx.state["video_shot_plan_content"] = json.dumps(validated, indent=2, ensure_ascii=False)
    path = os.path.join(_output_dir(ctx), "video_shot_plan.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(validated, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_video_shot_plan] Wrote {path}")


async def save_scene_assets(ctx: Context) -> None:
    raw = ctx.state.get("scene_assets_content")
    if not raw:
        return
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    for scene in parsed.get("scenes", []):
        if not scene.get("background_reference_mode"):
            scene["background_reference_mode"] = "style_anchor"
    path = os.path.join(_output_dir(ctx), "scene_assets.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"📁 [save_scene_assets] Wrote {path}")


async def merge_generation_specs(ctx: Context) -> None:
    """Fan-in: merge parallel prompter outputs into generation_specs.json."""
    char_raw = clean_json_str(ctx.state.get("character_sheet_prompts_content") or "{}")
    shot_raw = clean_json_str(ctx.state.get("shot_image_specs_content") or "{}")
    scene_assets_raw = clean_json_str(ctx.state.get("scene_assets_content") or "{}")
    style_id = (ctx.state.get("style_id") or "cinematic").strip().lower()
    profile = get_profile(style_id)
    render_style = profile.render_style
    pipeline_mode = ctx.state.get("pipeline_mode") or profile.pipeline_mode
    use_backgrounds = ctx.state.get("use_backgrounds")
    if use_backgrounds is None:
        use_backgrounds = profile.use_backgrounds

    story_raw = ctx.state.get("story_plan_content")

    character_sheets = {}
    if profile.character_sheet_mode == "template":
        story_characters: list[dict] = []
        if story_raw:
            story = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw
            story_characters = [
                c for c in story.get("characters", []) if isinstance(c, dict)
            ]
        from .character_sheet_builder import build_character_sheet_specs

        character_sheets = build_character_sheet_specs(
            story_characters,
            render_style=render_style,
            style_id=style_id,
        )
    else:
        for cid, entry in char_raw.items():
            if not isinstance(entry, dict):
                continue
            character_sheets[cid] = {
                "character_id": cid,
                "sheet_prompt": _apply_render_style(
                    entry.get("sheet_prompt") or entry.get("prompt", ""),
                    render_style,
                ),
                "output_path": None,
                "fal_image_url": None,
                "status": "pending",
            }

    story_shots: dict[str, dict] = {}
    if story_raw:
        story = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw
        for scene in story.get("scenes", []):
            for shot in scene.get("shots", []):
                story_shots[shot["shot_id"]] = shot

    shot_images = {}
    if pipeline_mode == "storyboard":
        for sid, plan_shot in story_shots.items():
            shot_images[sid] = {
                "shot_id": sid,
                "characters_present": plan_shot.get("characters_present", []),
                "generation_mode": "grok_edit",
                "reference_strategy": "char_sheets_only",
                "reference_images": [],
                "image_prompt": "",
                "status": "pending",
            }
    else:
        for sid, entry in shot_raw.items():
            if isinstance(entry, dict):
                entry = dict(entry)
                entry.setdefault("shot_id", sid)
                entry.setdefault("reference_images", [])
                entry.setdefault("status", "pending")
                if entry.get("image_prompt"):
                    entry["image_prompt"] = _apply_render_style(entry["image_prompt"], render_style)
                if entry.get("base_image_prompt"):
                    entry["base_image_prompt"] = _apply_render_style(
                        entry["base_image_prompt"],
                        render_style,
                    )
                shot_images[sid] = entry

    motion = {}
    for sid, plan_shot in story_shots.items():
        motion[sid] = {
            "shot_id": sid,
            "motion_prompt": "",
            "duration_seconds": plan_shot.get("duration_seconds", 8),
            "scene_time_offset_seconds": plan_shot.get("scene_time_offset_seconds", 0),
            "pace": plan_shot.get("pace", "medium"),
            "motion_intent": plan_shot.get("motion_intent", ""),
            "camera_intent": plan_shot.get("camera_intent", ""),
            "audio_intent": plan_shot.get("audio_intent", ""),
            "vision_confirmed": False,
            "vision_source_image": None,
            "output_path": None,
            "status": "pending",
        }

    backgrounds = {}
    if use_backgrounds:
        for scene in scene_assets_raw.get("scenes", []):
            if not isinstance(scene, dict):
                continue
            if scene.get("generate_background") and scene.get("background_prompt"):
                sid = scene["scene_id"]
                backgrounds[sid] = {
                    "scene_id": sid,
                    "background_prompt": _apply_render_style(
                        scene["background_prompt"],
                        render_style,
                    ),
                    "output_path": None,
                    "fal_image_url": None,
                    "status": "pending",
                }

    specs = {
        "character_sheets": character_sheets,
        "backgrounds": backgrounds,
        "shot_images": shot_images,
        "motion": motion,
    }
    ctx.state["generation_specs_content"] = json.dumps(specs, indent=2, ensure_ascii=False)
    path = os.path.join(_output_dir(ctx), "generation_specs.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)
    print(f"📁 [merge_generation_specs] Wrote {path}")


save_developed_story_node = FunctionNode(func=save_developed_story, name="save_developed_story_node")
save_scene_paper_node = FunctionNode(func=save_scene_paper, name="save_scene_paper_node")
save_story_sheet_scene_node = FunctionNode(
    func=save_story_sheet_scene, name="save_story_sheet_scene_node"
)
save_narrative_outline_node = FunctionNode(
    func=save_narrative_outline, name="save_narrative_outline_node"
)
save_story_plan_node = FunctionNode(func=save_story_plan, name="save_story_plan_node")
save_audio_plan_node = FunctionNode(func=save_audio_plan, name="save_audio_plan_node")
save_video_shot_plan_node = FunctionNode(
    func=save_video_shot_plan, name="save_video_shot_plan_node"
)
save_scene_assets_node = FunctionNode(func=save_scene_assets, name="save_scene_assets_node")
merge_generation_specs_node = FunctionNode(
    func=merge_generation_specs, name="merge_generation_specs_node"
)
