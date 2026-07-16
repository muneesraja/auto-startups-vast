"""Assistant-director storyboard video planning + mixed I2V/FLF generation nodes."""
from __future__ import annotations

import json
import os
from typing import Any

try:
    from google.adk.agents.context import Context
    from google.adk.workflow import FunctionNode
except ImportError:  # pragma: no cover
    class Context:  # type: ignore[override]
        pass

    class FunctionNode:  # type: ignore[override]
        def __init__(self, func, name: str):
            self.func = func
            self.name = name


def _storyboard_video_mode(ctx: Context | None = None) -> str:
    if ctx is not None:
        mode = (ctx.state.get("storyboard_video_mode") or "").strip().lower()
        if mode:
            return mode
    try:
        import config

        return str(getattr(config, "STORYBOARD_VIDEO_MODE", "fallback")).strip().lower()
    except Exception:
        return "fallback"


def is_director_video_mode(ctx: Context | None = None) -> bool:
    return _storyboard_video_mode(ctx) in ("director", "flf", "flf2v", "ad")


def _load_specs(output_dir: str, ctx: Context | None = None) -> dict:
    if ctx is not None:
        raw = ctx.state.get("generation_specs_content")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
    path = os.path.join(output_dir, "generation_specs.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_specs(output_dir: str, specs: dict, ctx: Context | None = None) -> None:
    path = os.path.join(output_dir, "generation_specs.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)
    if ctx is not None:
        ctx.state["generation_specs_content"] = specs


def _load_plan(output_dir: str, ctx: Context | None = None) -> dict:
    from scripts.nodes.plan_io import load_plan

    if ctx is not None:
        raw = ctx.state.get("plan_content")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass
    return load_plan(output_dir) or {}


def _load_scene_paper(output_dir: str, ctx: Context | None = None) -> str:
    if ctx is not None:
        text = ctx.state.get("scene_paper_text") or ctx.state.get("scene_paper_content")
        if text:
            return str(text)
    path = os.path.join(output_dir, "scene_paper.md")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def _sheet_path(output_dir: str, scene_id: str, specs: dict) -> str | None:
    sheets = specs.get("storyboard_sheets") or {}
    for key, entry in sheets.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("scene_id") == scene_id or key.startswith(f"{scene_id}_"):
            path = entry.get("output_path")
            if path and os.path.isfile(path):
                return path
    candidate = os.path.join(output_dir, "storyboard_sheets", f"{scene_id}_sheet_01.png")
    if os.path.isfile(candidate):
        return candidate
    return None


def _still_paths(specs: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for sid, entry in (specs.get("shot_images") or {}).items():
        if not isinstance(entry, dict):
            continue
        path = entry.get("output_path")
        if path and os.path.isfile(path):
            out[sid] = path
    return out


def _only_scenes(ctx: Context) -> list[str] | None:
    scenes = ctx.state.get("only_scenes")
    if not scenes:
        return None
    return [s for s in scenes if s]


def load_or_migrate_scene_plan(
    specs: dict,
    scene_id: str,
    scene: dict,
    *,
    fps: int = 25,
) -> dict | None:
    """Prefer storyboard_video_scenes; migrate legacy flf2v_scenes if needed."""
    from scripts.nodes.flf_storyboard_planner import migrate_legacy_flf_scene

    modern = (specs.get("storyboard_video_scenes") or {}).get(scene_id)
    if isinstance(modern, dict) and (modern.get("segments") or modern.get("clips")):
        return modern
    legacy = (specs.get("flf2v_scenes") or {}).get(scene_id)
    if isinstance(legacy, dict) and (legacy.get("clips") or legacy.get("segments")):
        migrated = migrate_legacy_flf_scene(legacy, scene, fps=fps)
        migrated["status"] = legacy.get("status") or "planned"
        if legacy.get("sheet_path"):
            migrated["sheet_path"] = legacy["sheet_path"]
        return migrated
    return None


def persist_scene_plan(specs: dict, scene_plan: dict) -> dict:
    scene_id = scene_plan["scene_id"]
    specs.setdefault("storyboard_video_scenes", {})[scene_id] = scene_plan
    # Keep legacy mirror for older tooling
    specs.setdefault("flf2v_scenes", {})[scene_id] = {
        **scene_plan,
        "clips": scene_plan.get("clips") or [],
    }
    return specs


async def plan_storyboard_video_scene(
    *,
    output_dir: str,
    scene_id: str,
    plan: dict | None = None,
    scene_paper: str | None = None,
    specs: dict | None = None,
    fps: int = 25,
) -> dict[str, Any]:
    """Plan one scene with the assistant director (vision)."""
    from scripts.nodes.flf_storyboard_planner import (
        panel_ids_in_order,
        plan_flf_clips_from_storyboard,
    )

    plan = plan or {}
    specs = specs if specs is not None else _load_specs(output_dir)
    scene_paper = scene_paper if scene_paper is not None else _load_scene_paper(output_dir)
    scene = next(
        (s for s in (plan.get("scenes") or []) if s.get("scene_id") == scene_id),
        None,
    )
    if not scene:
        raise ValueError(f"Scene {scene_id} not found in plan")

    sheet = _sheet_path(output_dir, scene_id, specs)
    if not sheet:
        raise FileNotFoundError(f"Missing storyboard sheet for {scene_id}")

    result = await plan_flf_clips_from_storyboard(
        sheet_path=sheet,
        scene=scene,
        panel_ids=panel_ids_in_order(scene),
        fps=fps,
        scene_paper=scene_paper,
        still_paths=_still_paths(specs),
    )
    result["sheet_path"] = sheet
    return result


def generate_storyboard_video_clips(
    *,
    output_dir: str,
    scene_plan: dict,
    specs: dict | None = None,
    skip_existing: bool = True,
    clip_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Render director clips with I2V or FLF2V in editorial order.

    Backend selection (orthogonal to STORYBOARD_VIDEO_MODE planning gate):
      STORY_MAKER_VIDEO_BACKEND=templates   → ltx-i2v / ltx-flf2v (default)
      STORY_MAKER_VIDEO_BACKEND=director_v2 → LTX Director Hotfix timeline
    """
    import config
    from tools.comfyui_tools import generate_ltx_flf2v_video, generate_ltx_i2v_video
    from tools.ltx_director_workflow import (
        DIRECTOR_FPS,
        generate_ltx_director_from_clip,
    )
    from tools.ltx_render_params import resolve_clip_render_params

    backend = (config.STORY_MAKER_VIDEO_BACKEND or "templates").strip().lower()
    use_director_v2 = backend in ("director_v2", "director", "hotfix", "ltx_director")

    specs = specs if specs is not None else _load_specs(output_dir)
    stills = _still_paths(specs)
    videos_dir = os.path.join(output_dir, "videos")
    os.makedirs(videos_dir, exist_ok=True)

    clips = scene_plan.get("clips") or []
    if not clips and scene_plan.get("segments"):
        clips = [
            c
            for seg in scene_plan["segments"]
            for c in (seg.get("clips") or [])
        ]

    wanted = {c.strip() for c in (clip_ids or []) if c and str(c).strip()}
    if wanted:
        clips = [c for c in clips if (c.get("clip_id") or "") in wanted]
        missing = wanted - {(c.get("clip_id") or "") for c in clips}
        if missing:
            print(f"  ⚠️ unknown clip_ids skipped: {sorted(missing)}")

    results: list[dict] = []
    for clip in clips:
        clip_id = clip.get("clip_id") or "clip"
        start_id = clip.get("start_panel_id") or clip.get("first_panel_id")
        end_id = clip.get("end_panel_id") or clip.get("last_panel_id") or start_id
        out_path = os.path.join(videos_dir, f"{clip_id}.mp4")
        entry = {**clip, "output_path": out_path, "status": "pending"}

        if skip_existing and os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            entry["status"] = "skipped_exists"
            results.append(entry)
            print(f"  ⏭️ skip existing {clip_id}")
            continue

        first_path = stills.get(start_id or "")
        last_path = stills.get(end_id or "")
        if not first_path or not last_path:
            entry["status"] = "error"
            entry["message"] = f"Missing stills {start_id}/{end_id}"
            results.append(entry)
            print(f"  ❌ {entry['message']}")
            continue

        prompt = (clip.get("motion_prompt") or "").strip()
        duration = int(clip.get("duration_seconds") or 6)
        workflow = (clip.get("workflow") or clip.get("mode") or "i2v").lower()
        if workflow in ("i2v_hold", "i2v") or start_id == end_id:
            workflow = "i2v"
        else:
            workflow = "flf2v"

        render = resolve_clip_render_params(clip, prefer_stored=True)
        entry.update(render)

        print(
            f"  ▶ {clip_id} [{workflow}] backend={backend} {start_id} → {end_id} "
            f"continuous={clip.get('continuous')} dur={duration}s "
            f"class={render['motion_class']} strength={render['i2v_strength']} "
            f"cfg={render['cfg']}"
        )

        if use_director_v2:
            result = generate_ltx_director_from_clip(
                clip,
                first_frame_path=first_path,
                last_frame_path=last_path if workflow == "flf2v" else None,
                output_path=out_path,
                global_prompt=(clip.get("global_prompt") or "").strip(),
                fps=DIRECTOR_FPS,
            )
        elif workflow == "i2v":
            result = generate_ltx_i2v_video(
                first_path,
                prompt,
                out_path,
                duration_seconds=duration,
                fps=25,
                i2v_strength=render["i2v_strength"],
                cfg=render["cfg"],
            )
        else:
            result = generate_ltx_flf2v_video(
                first_path,
                last_path,
                prompt,
                out_path,
                duration_seconds=duration,
                fps=25,
                first_frame_strength=render["i2v_strength"],
                last_frame_strength=render["last_frame_strength"],
                cfg=render["cfg"],
            )

        if result.get("status") == "success":
            entry["status"] = "completed"
            entry["output_path"] = result.get("video_path") or out_path
            entry["workflow"] = workflow
            if use_director_v2:
                entry["render_backend"] = "director_v2"
        else:
            entry["status"] = "error"
            entry["message"] = result.get("message") or "unknown error"
            print(f"  ❌ {clip_id}: {entry['message']}")
        results.append(entry)

    # Write results back into segments when present
    by_id = {c["clip_id"]: c for c in results if c.get("clip_id")}
    for seg in scene_plan.get("segments") or []:
        for clip in seg.get("clips") or []:
            cid = clip.get("clip_id")
            if cid in by_id:
                clip.update(
                    {
                        k: by_id[cid][k]
                        for k in (
                            "status",
                            "output_path",
                            "message",
                            "workflow",
                            "motion_class",
                            "guidance",
                            "i2v_strength",
                            "cfg",
                            "last_frame_strength",
                            "global_prompt",
                            "motion_segments",
                            "render_backend",
                        )
                        if k in by_id[cid]
                    }
                )

    # When filtering clip_ids, merge into the full plan rather than dropping others.
    if wanted:
        full_clips = scene_plan.get("clips") or []
        if not full_clips and scene_plan.get("segments"):
            full_clips = [
                c
                for seg in scene_plan["segments"]
                for c in (seg.get("clips") or [])
            ]
        merged = []
        updated = {c["clip_id"]: c for c in results if c.get("clip_id")}
        for clip in full_clips:
            cid = clip.get("clip_id")
            merged.append(updated.get(cid, clip) if cid in updated else clip)
        scene_plan["clips"] = merged
        results = merged
    else:
        scene_plan["clips"] = results

    scene_plan["duration_total_seconds"] = sum(
        int(c.get("duration_seconds") or 0) for c in scene_plan["clips"]
    )
    scene_plan["status"] = (
        "completed"
        if scene_plan["clips"]
        and all(
            c.get("status") in ("completed", "skipped_exists")
            for c in scene_plan["clips"]
        )
        else "partial"
    )
    return scene_plan


async def storyboard_director_planner(ctx: Context) -> None:
    """Plan assistant-director video for storyboard scenes (no-op outside director mode)."""
    if not is_director_video_mode(ctx):
        print("⏭️ [storyboard_director_planner] STORYBOARD_VIDEO_MODE != director — skip")
        return
    if (ctx.state.get("pipeline_mode") or "") != "storyboard":
        print("⏭️ [storyboard_director_planner] not storyboard pipeline — skip")
        return
    if bool(ctx.state.get("stop_before_generation", False)):
        return

    output_dir = ctx.state["output_dir"]
    plan = _load_plan(output_dir, ctx)
    scene_paper = _load_scene_paper(output_dir, ctx)
    specs = _load_specs(output_dir, ctx)
    only = _only_scenes(ctx)

    scenes = plan.get("scenes") or []
    planned = 0
    for scene in scenes:
        scene_id = scene.get("scene_id")
        if not scene_id:
            continue
        if only and scene_id not in only:
            continue
        existing = load_or_migrate_scene_plan(specs, scene_id, scene)
        if (
            existing
            and existing.get("status") in ("planned", "completed", "partial")
            and (existing.get("segments") or existing.get("clips"))
            and not bool(ctx.state.get("fresh"))
        ):
            # Re-normalize migrated legacy into modern key
            persist_scene_plan(specs, existing)
            print(f"  ⏭️ reuse director plan {scene_id} ({len(existing.get('clips') or [])} clips)")
            planned += 1
            continue
        print(f"  ▶ director plan {scene_id}")
        scene_plan = await plan_storyboard_video_scene(
            output_dir=output_dir,
            scene_id=scene_id,
            plan=plan,
            scene_paper=scene_paper,
            specs=specs,
        )
        persist_scene_plan(specs, scene_plan)
        planned += 1
        print(
            f"  ✅ {scene_id}: {len(scene_plan.get('clips') or [])} clips, "
            f"scene_total={scene_plan.get('duration_total_seconds')}s"
        )
        if scene_plan.get("repairs"):
            print(f"     repairs: {scene_plan['repairs'][:5]}")

    _save_specs(output_dir, specs, ctx)
    print(f"✅ [storyboard_director_planner] planned {planned} scene(s)")


async def storyboard_video_router(ctx: Context) -> None:
    """Route after panel regen: director vs fallback I2V motion path."""
    if is_director_video_mode(ctx) and (ctx.state.get("pipeline_mode") or "") == "storyboard":
        ctx.route = "director"
        print("🔀 [storyboard_video_router] → director")
    else:
        ctx.route = "fallback"
        print("🔀 [storyboard_video_router] → fallback")


async def storyboard_director_video_generator(ctx: Context) -> None:
    """Generate mixed I2V/FLF clips from assistant-director plans."""
    if not is_director_video_mode(ctx):
        return
    if bool(ctx.state.get("stop_before_generation", False)):
        return

    output_dir = ctx.state["output_dir"]
    plan = _load_plan(output_dir, ctx)
    specs = _load_specs(output_dir, ctx)
    only = _only_scenes(ctx)

    for scene in plan.get("scenes") or []:
        scene_id = scene.get("scene_id")
        if not scene_id:
            continue
        if only and scene_id not in only:
            continue
        scene_plan = load_or_migrate_scene_plan(specs, scene_id, scene)
        if not scene_plan or not (scene_plan.get("clips") or scene_plan.get("segments")):
            print(f"  ⚠️ no director plan for {scene_id}; skip generate")
            continue
        print(f"Generating director clips for {scene_id}...")
        out = generate_storyboard_video_clips(
            output_dir=output_dir,
            scene_plan=scene_plan,
            specs=specs,
            skip_existing=not bool(ctx.state.get("fresh")),
        )
        persist_scene_plan(specs, out)
        ok = sum(1 for c in out.get("clips") or [] if c.get("status") in ("completed", "skipped_exists"))
        err = sum(1 for c in out.get("clips") or [] if c.get("status") == "error")
        print(f"  Done {scene_id}: ok={ok} err={err} status={out.get('status')}")

    _save_specs(output_dir, specs, ctx)
    print("✅ [storyboard_director_video_generator] complete")


storyboard_director_planner_node = FunctionNode(
    func=storyboard_director_planner, name="storyboard_director_planner_node"
)
storyboard_video_router_node = FunctionNode(
    func=storyboard_video_router, name="storyboard_video_router_node"
)
storyboard_director_video_generator_node = FunctionNode(
    func=storyboard_director_video_generator,
    name="storyboard_director_video_generator_node",
)
