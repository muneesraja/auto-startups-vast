"""Sheet map + production plan save/normalize + specs build from plan.json."""
from __future__ import annotations

import json
import os
import re

from google.adk.agents.context import Context
from google.adk.workflow import FunctionNode

import config
from profiles import get_profile
from schemas.plan import ProductionPlanDraft
from ._json_util import clean_json_str
from .plan_io import (
    apply_story_view_to_plan,
    apply_video_shots_to_plan,
    save_plan_dict,
    story_plan_view,
    sync_legacy_state,
    video_shot_plan_view,
)
from .save_artifact_nodes import (
    _apply_render_style,
    _normalize_video_shot_plan,
    _asset_dir,
    _output_dir,
    _stamp_planning_meta,
)
from .sheet_map import render_sheet_map_markdown, sheet_map_context_for_prompt
from .video_shot_cast import synthesize_cast_coherent_video_shots


async def sheet_map_builder(ctx: Context) -> None:
    """Deterministic sheet map for storyboard mode; no-op context for per_shot."""
    pipeline_mode = ctx.state.get("pipeline_mode") or "per_shot"
    scene_paper = ctx.state.get("scene_paper_text") or ctx.state.get("scene_paper_content") or ""
    panels_per_sheet = int(ctx.state.get("panels_per_sheet") or 0)

    if pipeline_mode != "storyboard" or panels_per_sheet <= 0 or not scene_paper:
        ctx.state["sheet_map_context"] = ""
        ctx.state["story_sheet_scene_text"] = ""
        print("ℹ️ [sheet_map_builder] Skipped (per_shot or empty scene paper)")
        return

    ctx.state["sheet_map_context"] = sheet_map_context_for_prompt(
        scene_paper, panels_per_sheet=panels_per_sheet
    )
    # Keep in-memory map text for any prompt that still references it; do not
    # require it as a durable resume artifact.
    ctx.state["story_sheet_scene_text"] = render_sheet_map_markdown(
        scene_paper, panels_per_sheet=panels_per_sheet
    )
    print(
        f"✅ [sheet_map_builder] Built deterministic sheet map "
        f"({panels_per_sheet} panels/sheet)"
    )


def _default_assets_for_profile(profile, scene: dict) -> dict:
    assets = dict(scene.get("assets") or {})
    if profile.pipeline_mode == "storyboard" or not profile.use_backgrounds:
        assets.setdefault("generate_background", False)
        assets.setdefault("background_reference_mode", "style_anchor")
        assets.setdefault("background_prompt", "")
        assets.setdefault("rationale", "storyboard / no background plates")
    else:
        assets.setdefault("generate_background", True)
        assets.setdefault("background_reference_mode", "style_anchor")
        assets.setdefault("background_prompt", assets.get("background_prompt") or "")
        assets.setdefault("rationale", assets.get("rationale") or "")
    return assets


def _ensure_shot_audio(shot: dict) -> dict:
    shot = dict(shot)
    raw_audio = shot.get("audio")
    if isinstance(raw_audio, dict):
        audio = dict(raw_audio)
    elif isinstance(raw_audio, str) and raw_audio.strip():
        audio = {"ambience": raw_audio.strip()}
    else:
        audio = {}
    audio.setdefault("dialogue", [])
    audio.setdefault("music", "")
    audio.setdefault("sfx", [])
    audio.setdefault("ambience", "")
    audio.setdefault("transition", None)
    if not isinstance(audio.get("dialogue"), list):
        audio["dialogue"] = []
    if not isinstance(audio.get("sfx"), list):
        audio["sfx"] = []
    shot["audio"] = audio
    return shot



def _coerce_audio_scene(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        return {"music_bed": value.strip(), "ending_state": ""}
    return {}


def _repair_characters(characters: list) -> list[dict]:
    out = []
    for i, ch in enumerate(characters or [], start=1):
        if not isinstance(ch, dict):
            continue
        item = dict(ch)
        cid = (item.get("id") or "").strip() or f"char_{i:02d}"
        item["id"] = cid
        item.setdefault("name", cid)
        appearance = (
            item.get("appearance")
            or item.get("visual_identity")
            or item.get("design_notes")
            or item.get("role")
            or item["name"]
        )
        item["appearance"] = appearance
        item.setdefault("voice_profile", item.get("role") or "natural spoken voice")
        out.append(item)
    return out


def _coerce_director_transition(value) -> str | None:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if raw in ("continue", "continuous", "cont"):
        return "continue"
    if raw in ("match_cut", "matchcut", "cut", "hard_cut", "transition"):
        return "match_cut"
    return None


def _coerce_director_guide_role(value) -> str | None:
    raw = str(value or "").strip().lower()
    if raw in ("start", "middle", "end"):
        return raw
    if raw in ("hold", "waypoint"):
        return "middle"
    return None


def _cast_set(shot: dict) -> frozenset[str]:
    return frozenset(str(c).strip() for c in (shot.get("characters_present") or []) if c)


def migrate_director_panel_metadata(shots: list[dict]) -> list[dict]:
    """Fill director_* fields for legacy plans; preserve authored values.

    Defaults:
    - director_transition_after: continue when next panel cast ⊆ current and camera
      is compatible; else match_cut. Last panel defaults to match_cut.
    - director_chain_group / guide_role: derived from continue runs when missing.
    - director_continuity_note: left empty when unknown.
    """
    if not shots:
        return shots
    out = [dict(s) for s in shots]
    # Normalize / derive transition edges.
    for i, shot in enumerate(out):
        authored = _coerce_director_transition(shot.get("director_transition_after"))
        if authored:
            shot["director_transition_after"] = authored
            continue
        if i >= len(out) - 1:
            shot["director_transition_after"] = "match_cut"
            continue
        nxt = out[i + 1]
        cur_cast, next_cast = _cast_set(shot), _cast_set(nxt)
        same_cam = (
            str(shot.get("camera_intent") or "").strip().lower()
            == str(nxt.get("camera_intent") or "").strip().lower()
        )
        cont_from = bool(nxt.get("continuity_from_previous"))
        if cont_from:
            shot["director_transition_after"] = "continue"
        elif not cur_cast and next_cast:
            shot["director_transition_after"] = "match_cut"
        elif next_cast and next_cast.issubset(cur_cast):
            shot["director_transition_after"] = "continue"
        elif cur_cast == next_cast and (same_cam or not shot.get("camera_intent")):
            shot["director_transition_after"] = "continue"
        else:
            shot["director_transition_after"] = "match_cut"

    # Derive chain groups + guide roles when missing on the whole scene.
    has_any_group = any(s.get("director_chain_group") for s in out)
    if not has_any_group:
        group = 1
        run: list[int] = []

        def _flush_run(indices: list[int]) -> None:
            nonlocal group
            if not indices:
                return
            # Soft-cap continuous runs at 4 panels per group (one multi-guide unit).
            # Shared boundary between units is applied later in chain construction.
            for start in range(0, len(indices), 4):
                chunk = indices[start : start + 4]
                for j, idx in enumerate(chunk):
                    out[idx]["director_chain_group"] = group
                    if len(chunk) == 1:
                        role = "start"
                    elif j == 0:
                        role = "start"
                    elif j == len(chunk) - 1:
                        role = "end"
                    else:
                        role = "middle"
                    if not _coerce_director_guide_role(out[idx].get("director_guide_role")):
                        out[idx]["director_guide_role"] = role
                group += 1

        for i, shot in enumerate(out):
            run.append(i)
            is_cut = shot.get("director_transition_after") == "match_cut" or i == len(out) - 1
            if is_cut:
                _flush_run(run)
                run = []
    else:
        for shot in out:
            if shot.get("director_chain_group") is not None:
                try:
                    shot["director_chain_group"] = max(1, int(shot["director_chain_group"]))
                except (TypeError, ValueError):
                    shot["director_chain_group"] = None
            role = _coerce_director_guide_role(shot.get("director_guide_role"))
            shot["director_guide_role"] = role
            note = shot.get("director_continuity_note")
            shot["director_continuity_note"] = str(note or "").strip()

    for shot in out:
        if shot.get("director_continuity_note") is None:
            shot["director_continuity_note"] = ""
        else:
            shot["director_continuity_note"] = str(shot.get("director_continuity_note") or "").strip()
        if not shot.get("director_bridge_to_next"):
            bridge = (
                shot.get("bridge_to_next")
                or shot.get("bridge")
                or shot.get("director_bridge")
                or ""
            )
            shot["director_bridge_to_next"] = str(bridge).strip()
        else:
            shot["director_bridge_to_next"] = str(
                shot.get("director_bridge_to_next") or ""
            ).strip()
        role = _coerce_director_guide_role(shot.get("director_guide_role"))
        if role:
            shot["director_guide_role"] = role
        if shot.get("director_chain_group") is not None:
            try:
                shot["director_chain_group"] = max(1, int(shot["director_chain_group"]))
            except (TypeError, ValueError):
                shot["director_chain_group"] = None
    return out


def validate_director_panel_metadata(shots: list[dict]) -> list[str]:
    """Return repair/reject messages for authored director metadata."""
    issues: list[str] = []
    if not shots:
        return issues
    by_group: dict[int, list[tuple[int, dict]]] = {}
    for i, shot in enumerate(shots):
        gid = shot.get("director_chain_group")
        if gid is None:
            continue
        try:
            gid_i = int(gid)
        except (TypeError, ValueError):
            issues.append(f"{shot.get('shot_id')}: invalid director_chain_group")
            continue
        by_group.setdefault(gid_i, []).append((i, shot))

    for gid, members in sorted(by_group.items()):
        idxs = [i for i, _ in members]
        if idxs != list(range(idxs[0], idxs[-1] + 1)):
            issues.append(f"group {gid}: panels are not consecutive")
        roles = []
        for _, shot in members:
            role = _coerce_director_guide_role(shot.get("director_guide_role"))
            if role:
                roles.append(role)
        # Guide roles should not put end before start within order.
        if "start" in roles and "end" in roles:
            if roles.index("end") < roles.index("start"):
                issues.append(f"group {gid}: guide-role order conflicts with panel order")
        # continue interiors should carry a continuity note or spatial lock.
        for pos, (i, shot) in enumerate(members):
            if pos >= len(members) - 1:
                continue
            edge = shot.get("director_transition_after") or "continue"
            if edge == "continue":
                note = str(shot.get("director_continuity_note") or "").strip()
                spatial = any(
                    str(shot.get(k) or "").strip()
                    for k in (
                        "subject_position",
                        "facing_direction",
                        "camera_intent",
                        "background_region",
                    )
                )
                if not note and not spatial:
                    issues.append(
                        f"{shot.get('shot_id')}: continue edge lacks continuity note "
                        "or spatial/camera lock"
                    )
    # match_cut should not orphan the next panel — shared boundary is the current panel.
    for i, shot in enumerate(shots[:-1]):
        if shot.get("director_transition_after") == "match_cut":
            # Shared boundary handoff is implicit (this panel ends unit, next starts).
            # Flag only if next panel jumps group without sharing this panel as start.
            g_cur = shot.get("director_chain_group")
            g_next = shots[i + 1].get("director_chain_group")
            if g_cur is not None and g_next is not None and g_cur == g_next:
                issues.append(
                    f"{shot.get('shot_id')}: match_cut inside same chain group "
                    "(expected group boundary)"
                )
    return issues


def _repair_shot_fields(shot: dict, scene_id: str) -> dict:
    item = dict(shot)
    item.setdefault("scene_id", scene_id)
    if not item.get("description"):
        item["description"] = (
            item.pop("visual", None)
            or item.get("visual_description")
            or item.get("panel_visual")
            or ""
        )
    else:
        item.pop("visual", None)
    if not item.get("motion_intent"):
        item["motion_intent"] = item.pop("motion", None) or item.get("action") or ""
    else:
        item.pop("motion", None)
    if not item.get("camera_intent"):
        item["camera_intent"] = item.pop("cam", None) or item.get("camera") or ""
    else:
        item.pop("cam", None)
    item.setdefault("characters_present", [])
    item.setdefault("duration_seconds", 2)
    item.setdefault("pace", "fast")
    item.setdefault("ltx_shot_type", "action")
    item.setdefault("ltx_complexity", "simple")
    item.setdefault("environment_state", item.get("spatial") or item.get("light") or "")
    if isinstance(item.get("environment_state"), dict):
        # LLM sometimes nests audio_intent into environment_state.
        nested = item["environment_state"]
        item["environment_state"] = (
            nested.get("environment_state")
            or nested.get("description")
            or ""
        )
        if not item.get("audio_intent") and nested.get("audio_intent"):
            item["audio_intent"] = nested.get("audio_intent")
    elif item.get("environment_state") is not None and not isinstance(
        item.get("environment_state"), str
    ):
        item["environment_state"] = str(item.get("environment_state"))
    if not str(item.get("description") or "").strip():
        item["description"] = "Panel beat."
    try:
        item["duration_seconds"] = int(round(float(item.get("duration_seconds") or 2)))
    except (TypeError, ValueError):
        item["duration_seconds"] = 2
    item["duration_seconds"] = max(1, min(16, item["duration_seconds"]))

    # Preserve optional Director metadata aliases from scene-paper style keys.
    if item.get("director_transition_after") is None:
        alias = item.get("continuity") or item.get("transition_after")
        coerced = _coerce_director_transition(alias)
        if coerced:
            item["director_transition_after"] = coerced
    else:
        coerced = _coerce_director_transition(item.get("director_transition_after"))
        item["director_transition_after"] = coerced
    if item.get("director_guide_role") is None:
        alias = item.get("guide_role")
        coerced_role = _coerce_director_guide_role(alias)
        if coerced_role:
            item["director_guide_role"] = coerced_role
    else:
        item["director_guide_role"] = _coerce_director_guide_role(
            item.get("director_guide_role")
        )
    if not item.get("director_continuity_note"):
        note = item.get("director_note") or item.get("continuity_note") or ""
        item["director_continuity_note"] = str(note).strip()
    else:
        item["director_continuity_note"] = str(item.get("director_continuity_note") or "").strip()
    if not item.get("director_bridge_to_next"):
        bridge = (
            item.get("bridge_to_next")
            or item.get("bridge")
            or item.get("director_bridge")
            or ""
        )
        item["director_bridge_to_next"] = str(bridge).strip()
    else:
        item["director_bridge_to_next"] = str(
            item.get("director_bridge_to_next") or ""
        ).strip()
    if item.get("director_chain_group") is not None:
        try:
            item["director_chain_group"] = max(1, int(item["director_chain_group"]))
        except (TypeError, ValueError):
            item["director_chain_group"] = None
    return item


def _character_name_patterns(characters: list[dict]) -> list[tuple[str, re.Pattern[str]]]:
    """Build (char_id, pattern) pairs for roster name/id hits (longest names first)."""
    entries: list[tuple[str, str]] = []
    for ch in characters or []:
        if not isinstance(ch, dict):
            continue
        cid = (ch.get("id") or "").strip()
        if not cid:
            continue
        names = {cid}
        name = (ch.get("name") or "").strip()
        if name:
            names.add(name)
        for raw in names:
            if raw:
                entries.append((cid, raw))
    # Prefer longer literals so "Neju" does not steal a substring of a longer name.
    entries.sort(key=lambda pair: len(pair[1]), reverse=True)
    patterns: list[tuple[str, re.Pattern[str]]] = []
    seen_pat: set[str] = set()
    for cid, raw in entries:
        key = raw.lower()
        if key in seen_pat:
            continue
        seen_pat.add(key)
        patterns.append(
            (cid, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(raw)}(?![A-Za-z0-9_])", re.I))
        )
    return patterns


def _infer_characters_present(shot: dict, patterns: list[tuple[str, re.Pattern[str]]]) -> list[str]:
    """Fill empty characters_present from roster name/id mentions in shot text."""
    existing = [c for c in (shot.get("characters_present") or []) if c]
    if existing:
        return existing
    haystack = " ".join(
        [
            str(shot.get("description") or ""),
            str(shot.get("motion_intent") or ""),
            str(shot.get("environment_state") or ""),
        ]
    )
    if not haystack.strip() or not patterns:
        return []
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for cid, pattern in patterns:
        if cid in seen:
            continue
        match = pattern.search(haystack)
        if match:
            hits.append((match.start(), cid))
            seen.add(cid)
    hits.sort(key=lambda item: item[0])
    return [cid for _, cid in hits]


def _fill_empty_characters_present(scenes: list[dict], characters: list[dict]) -> None:
    patterns = _character_name_patterns(characters)
    if not patterns:
        return
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            shot["characters_present"] = _infer_characters_present(shot, patterns)


def _character_reference_slots(character_ids: list[str]) -> list[dict]:
    return [
        {"role": "character_sheet", "asset_id": cid, "priority": i}
        for i, cid in enumerate(character_ids)
        if cid
    ]



def _slug_location_key(text: str) -> str:
    raw = "".join(ch.lower() if ch.isalnum() else "_" for ch in (text or "").strip())
    while "__" in raw:
        raw = raw.replace("__", "_")
    return raw.strip("_") or "place"


def _synthesize_locations_from_scenes(scenes: list[dict]) -> list[dict]:
    """Build locations[] from unique scene.environment values."""
    locations: list[dict] = []
    seen: dict[str, str] = {}
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        env = (scene.get("environment") or "").strip() or "story world"
        key = _slug_location_key(env)
        if key in seen:
            continue
        loc_id = f"loc_{len(locations) + 1:02d}"
        seen[key] = loc_id
        tod = (scene.get("time_of_day") or "day").strip()
        lighting = (scene.get("lighting") or "natural light").strip()
        staging = (scene.get("staging") or "").strip()
        establishing = (
            f"Wide empty-stage establishing view of {env}. "
            f"Time of day: {tod}. Lighting: {lighting}. "
            f"{('Geography: ' + staging + '. ') if staging else ''}"
            "No named characters. Landmark-readable Pixar environment plate."
        )
        locations.append(
            {
                "id": loc_id,
                "name": env.title() if env.islower() else env,
                "description": env,
                "establishing_prompt": establishing,
            }
        )
    return locations


def _assign_scene_location_ids(scenes: list[dict], locations: list[dict]) -> None:
    env_to_id: dict[str, str] = {}
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        lid = (loc.get("id") or "").strip()
        desc = (loc.get("description") or loc.get("name") or "").strip().lower()
        if lid and desc:
            env_to_id[_slug_location_key(desc)] = lid
    fallback = (locations[0].get("id") if locations else "") or ""
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        existing = (scene.get("location_id") or "").strip()
        if existing:
            continue
        env = (scene.get("environment") or "").strip()
        scene["location_id"] = env_to_id.get(_slug_location_key(env), fallback)


def _repair_locations(locations: list) -> list[dict]:
    out = []
    for i, loc in enumerate(locations or [], start=1):
        if not isinstance(loc, dict):
            continue
        item = dict(loc)
        lid = (item.get("id") or "").strip() or f"loc_{i:02d}"
        item["id"] = lid
        name = (item.get("name") or item.get("description") or lid).strip()
        item["name"] = name
        desc = (item.get("description") or name).strip()
        item["description"] = desc
        prompt = (item.get("establishing_prompt") or "").strip()
        if not prompt:
            item["establishing_prompt"] = (
                f"Wide empty-stage establishing view of {desc}. "
                "No named characters. Landmark-readable Pixar environment plate."
            )
        out.append(item)
    return out


def normalize_production_plan(plan: dict, ctx: Context) -> dict:
    """Fill defaults, normalize video_shots, stamp meta."""
    style_id = (ctx.state.get("style_id") or "cinematic").strip().lower()
    profile = get_profile(style_id)
    pipeline_mode = ctx.state.get("pipeline_mode") or profile.pipeline_mode

    meta = dict(plan.get("meta") or {})
    if ctx.state.get("target_duration_seconds") and not meta.get("target_duration_seconds"):
        meta["target_duration_seconds"] = ctx.state["target_duration_seconds"]
    if ctx.state.get("duration_tolerance_percent") is not None:
        meta.setdefault(
            "duration_tolerance_percent", ctx.state.get("duration_tolerance_percent", 15)
        )
    plan = dict(plan)
    plan["meta"] = meta
    plan["characters"] = _repair_characters(plan.get("characters") or [])
    plan["locations"] = _repair_locations(plan.get("locations") or [])

    scenes = []
    for scene in plan.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        updated = dict(scene)
        scene_id = (updated.get("scene_id") or "").strip() or "scene_01"
        updated["scene_id"] = scene_id
        updated.setdefault("title", scene_id.replace("_", " ").title())
        updated.setdefault("environment", "story world")
        updated.setdefault("time_of_day", "day")
        updated.setdefault("lighting", "natural light")
        if updated.get("title") in (None, ""):
            updated["title"] = scene_id.replace("_", " ").title()
        if updated.get("environment") in (None, ""):
            updated["environment"] = "story world"
        if updated.get("time_of_day") in (None, ""):
            updated["time_of_day"] = "day"
        if updated.get("lighting") in (None, ""):
            updated["lighting"] = "natural light"
        if not updated.get("director_motion_spine"):
            spine = (
                updated.get("motion_spine")
                or updated.get("director_spine")
                or ""
            )
            updated["director_motion_spine"] = str(spine).strip()
        else:
            updated["director_motion_spine"] = str(
                updated.get("director_motion_spine") or ""
            ).strip()
        updated["assets"] = _default_assets_for_profile(profile, updated)
        updated["audio_scene"] = _coerce_audio_scene(updated.get("audio_scene"))
        updated["shots"] = [
            _ensure_shot_audio(_repair_shot_fields(s, scene_id))
            for s in (updated.get("shots") or [])
            if isinstance(s, dict)
        ]
        updated["shots"] = migrate_director_panel_metadata(updated["shots"])
        for issue in validate_director_panel_metadata(updated["shots"]):
            print(f"⚠️ [normalize_production_plan] director metadata: {issue}")
        if updated.get("duration_budget_seconds") is None:
            updated["duration_budget_seconds"] = sum(
                int(s.get("duration_seconds", 0) or 0) for s in updated["shots"]
            )
        else:
            try:
                updated["duration_budget_seconds"] = int(round(float(updated["duration_budget_seconds"])))
            except (TypeError, ValueError):
                updated["duration_budget_seconds"] = sum(
                    int(s.get("duration_seconds", 0) or 0) for s in updated["shots"]
                )
        updated.setdefault("video_shots", [])
        scenes.append(updated)
    plan["scenes"] = scenes
    _fill_empty_characters_present(plan["scenes"], plan.get("characters") or [])

    if not plan.get("locations"):
        plan["locations"] = _synthesize_locations_from_scenes(scenes)
    else:
        plan["locations"] = _repair_locations(plan.get("locations") or [])
    _assign_scene_location_ids(plan["scenes"], plan["locations"])

    if pipeline_mode == "storyboard":
        loc_ids = {
            (loc.get("id") or "").strip()
            for loc in (plan.get("locations") or [])
            if isinstance(loc, dict) and (loc.get("id") or "").strip()
        }
        for scene in plan["scenes"]:
            lid = (scene.get("location_id") or "").strip()
            if not lid:
                print(
                    f"⚠️ [normalize_production_plan] scene {scene.get('scene_id')} "
                    "missing location_id after synthesize"
                )
            elif lid not in loc_ids:
                print(
                    f"⚠️ [normalize_production_plan] scene {scene.get('scene_id')} "
                    f"unknown location_id {lid!r}; reassigning"
                )
                scene["location_id"] = ""
        _assign_scene_location_ids(plan["scenes"], plan["locations"])

    # Soft-fill meta totals before timeline enrich
    shot_count = sum(len(s.get("shots", [])) for s in scenes)
    duration_sum = sum(
        int(sh.get("duration_seconds", 0)) for s in scenes for sh in s.get("shots", [])
    )
    plan["meta"]["total_shots"] = shot_count
    plan["meta"]["total_scenes"] = len(scenes)
    plan["meta"]["total_duration_seconds"] = duration_sum

    # Authoritative scene budgets from scene_paper.md (reel_v2) —
    # skip when assistant-director owns wall-clock durations.
    if pipeline_mode == "storyboard":
        from scripts.nodes.storyboard_director_nodes import is_director_video_mode

        scene_paper = (
            ctx.state.get("scene_paper_text")
            or ctx.state.get("scene_paper_content")
            or ""
        )
        if scene_paper and not is_director_video_mode(ctx):
            from scripts.nodes.flf_storyboard_planner import apply_scene_paper_budgets_to_plan

            plan = apply_scene_paper_budgets_to_plan(plan, scene_paper)
            scenes = plan.get("scenes") or scenes

    if pipeline_mode == "storyboard":
        story_view = story_plan_view(plan)
        video_raw = video_shot_plan_view(plan)
        # If LLM omitted video_shots, synthesize one-per-panel groups of ~3
        needs_synth = all(not (s.get("video_shots") or []) for s in video_raw.get("scenes", []))
        if needs_synth:
            video_raw = _synthesize_video_shots(story_view)
        normalized_video = _normalize_video_shot_plan(video_raw, story_view)
        plan = apply_video_shots_to_plan(plan, normalized_video)

    plan = _stamp_planning_meta(
        plan,
        production_plan_model=config.get_story_plan_model_id(),
        secondary_model=config.get_secondary_model_id(),
        vision_model=config.get_vision_model_id(),
    )
    # Draft validation (fills totals if needed)
    try:
        draft = ProductionPlanDraft(
            meta=plan.get("meta") or {},
            characters=plan.get("characters") or [],
            locations=plan.get("locations") or [],
            scenes=plan.get("scenes") or [],
        )
        validated = draft.to_plan().model_dump()
        if "_meta" in plan:
            validated["_meta"] = plan["_meta"]
        plan = validated
    except Exception as exc:
        print(f"⚠️ [normalize_production_plan] soft validation warning: {exc}")
    return plan


def _synthesize_video_shots(story_view: dict, *, group_size: int = 3) -> dict:
    """Synthesize video_shots with cast-coherent groups (soft max group_size)."""
    return synthesize_cast_coherent_video_shots(story_view, max_group_size=group_size)


async def save_production_plan(ctx: Context) -> None:
    raw = ctx.state.get("plan_content")
    if not raw:
        raise ValueError("plan_content missing after production_plan_author")
    parsed = clean_json_str(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, dict):
        raise ValueError("production plan must be a JSON object")
    plan = normalize_production_plan(parsed, ctx)
    path = save_plan_dict(_output_dir(ctx), plan)
    sync_legacy_state(ctx.state, plan)
    print(f"📁 [save_production_plan] Wrote {path}")


async def persist_enriched_plan(ctx: Context) -> None:
    """After timeline/duration updates to story_plan_content, rewrite plan.json."""
    plan_raw = ctx.state.get("plan_content")
    story_raw = ctx.state.get("story_plan_content")
    if not plan_raw or not story_raw:
        return
    plan = clean_json_str(plan_raw) if isinstance(plan_raw, str) else plan_raw
    story = clean_json_str(story_raw) if isinstance(story_raw, str) else story_raw
    merged = apply_story_view_to_plan(plan, story)
    # Re-normalize video shot durations against updated panel totals for storyboard
    pipeline_mode = ctx.state.get("pipeline_mode") or "per_shot"
    if pipeline_mode == "storyboard" and any(
        (s.get("video_shots") or []) for s in merged.get("scenes", [])
    ):
        video_raw = video_shot_plan_view(merged)
        try:
            normalized_video = _normalize_video_shot_plan(video_raw, story_plan_view(merged))
            merged = apply_video_shots_to_plan(merged, normalized_video)
        except Exception as exc:
            print(f"⚠️ [persist_enriched_plan] video shot re-normalize skipped: {exc}")
    path = save_plan_dict(_output_dir(ctx), merged)
    sync_legacy_state(ctx.state, merged)
    print(f"📁 [persist_enriched_plan] Updated {path}")



def _build_location_sheet_prompt(loc: dict, *, render_style: str, style_id: str) -> str:
    from .storyboard_sheet_builder import _load_prompt_file

    template = _load_prompt_file("location_sheet_template", style_id=style_id)
    establishing = (loc.get("establishing_prompt") or "").strip()
    description = (loc.get("description") or loc.get("name") or "").strip()
    if not establishing:
        establishing = (
            f"Wide empty-stage establishing view of {description}. "
            "No named characters."
        )
    return template.format(
        location_id=loc.get("id") or "",
        location_name=loc.get("name") or loc.get("id") or "",
        location_description=description,
        establishing_prompt=establishing,
        render_style=render_style,
    )


async def build_generation_specs_from_plan(ctx: Context) -> None:
    """Code-build generation_specs.json from plan (+ optional LLM prompter outputs)."""
    from .character_sheet_builder import build_character_sheet_specs

    style_id = (ctx.state.get("style_id") or "cinematic").strip().lower()
    profile = get_profile(style_id)
    render_style = profile.render_style
    pipeline_mode = ctx.state.get("pipeline_mode") or profile.pipeline_mode
    use_backgrounds = ctx.state.get("use_backgrounds")
    if use_backgrounds is None:
        use_backgrounds = profile.use_backgrounds

    plan_raw = ctx.state.get("plan_content") or ctx.state.get("story_plan_content")
    if not plan_raw:
        raise ValueError("plan_content required to build generation_specs")
    plan = clean_json_str(plan_raw) if isinstance(plan_raw, str) else plan_raw
    # If we only have a story-plan-shaped dict, wrap usage still works via views.
    if plan.get("scenes") and isinstance(plan["scenes"][0], dict) and "assets" in plan["scenes"][0]:
        story = story_plan_view(plan)
    else:
        story = plan
        # Reconstruct minimal assets from scene_assets_content if needed
        assets_raw = clean_json_str(ctx.state.get("scene_assets_content") or "{}")
        assets_lookup = {
            s.get("scene_id"): s
            for s in assets_raw.get("scenes", [])
            if isinstance(s, dict)
        }
        wrapped_scenes = []
        for scene in story.get("scenes", []):
            sid = scene.get("scene_id")
            wrapped_scenes.append({**scene, "assets": assets_lookup.get(sid) or {}})
        plan = {**story, "scenes": wrapped_scenes}

    char_raw = clean_json_str(ctx.state.get("character_sheet_prompts_content") or "{}")
    shot_raw = clean_json_str(ctx.state.get("shot_image_specs_content") or "{}")

    character_sheets = {}
    chars_dir = _asset_dir(ctx, "characters")
    if profile.character_sheet_mode == "template":
        character_sheets = build_character_sheet_specs(
            [c for c in story.get("characters", []) if isinstance(c, dict)],
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

    # Seed character sheet paths under asset_root; reuse existing PNGs across parts.
    for cid, entry in list(character_sheets.items()):
        if not isinstance(entry, dict):
            continue
        out_path = os.path.join(chars_dir, f"{cid}.png")
        entry["output_path"] = out_path
        if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
            entry["status"] = "completed"
            entry.setdefault("fal_image_url", None)

    story_shots: dict[str, dict] = {}
    for scene in story.get("scenes", []):
        for shot in scene.get("shots", []):
            story_shots[shot["shot_id"]] = shot

    shot_images = {}
    if pipeline_mode == "storyboard":
        for sid, plan_shot in story_shots.items():
            char_ids = [
                cid
                for cid in (plan_shot.get("characters_present") or [])
                if cid
            ]
            shot_images[sid] = {
                "shot_id": sid,
                "characters_present": char_ids,
                "generation_mode": "grok_edit",
                "reference_strategy": "char_sheets_only",
                "reference_slots": _character_reference_slots(char_ids),
                "reference_images": [
                    f"{{{{character_sheets.{cid}.fal_image_url}}}}" for cid in char_ids
                ],
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
                    entry["image_prompt"] = _apply_render_style(
                        entry["image_prompt"], render_style
                    )
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
        for scene in plan.get("scenes", []):
            if not isinstance(scene, dict):
                continue
            assets = scene.get("assets") or {}
            if assets.get("generate_background") and assets.get("background_prompt"):
                sid = scene["scene_id"]
                backgrounds[sid] = {
                    "scene_id": sid,
                    "background_prompt": _apply_render_style(
                        assets["background_prompt"],
                        render_style,
                    ),
                    "output_path": None,
                    "fal_image_url": None,
                    "status": "pending",
                }

    location_sheets = {}
    if pipeline_mode == "storyboard":
        locs_dir = _asset_dir(ctx, "locations")
        for loc in plan.get("locations") or []:
            if not isinstance(loc, dict):
                continue
            lid = (loc.get("id") or "").strip()
            if not lid:
                continue
            prompt = _build_location_sheet_prompt(
                loc, render_style=render_style, style_id=style_id
            )
            out_path = os.path.join(locs_dir, f"{lid}.png")
            status = "pending"
            if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                status = "completed"
            location_sheets[lid] = {
                "location_id": lid,
                "sheet_prompt": _apply_render_style(prompt, render_style),
                "output_path": out_path,
                "fal_image_url": None,
                "status": status,
            }

    # Seed background paths under asset_root when used.
    if backgrounds:
        bg_dir = _asset_dir(ctx, "backgrounds")
        for sid, entry in backgrounds.items():
            if not isinstance(entry, dict):
                continue
            out_path = os.path.join(bg_dir, f"{sid}.png")
            entry["output_path"] = out_path
            if os.path.isfile(out_path) and os.path.getsize(out_path) > 0:
                entry["status"] = "completed"

    specs = {
        "character_sheets": character_sheets,
        "location_sheets": location_sheets,
        "backgrounds": backgrounds,
        "shot_images": shot_images,
        "motion": motion,
    }
    ctx.state["generation_specs_content"] = json.dumps(specs, indent=2, ensure_ascii=False)
    path = os.path.join(_output_dir(ctx), "generation_specs.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)
    print(f"📁 [build_generation_specs_from_plan] Wrote {path}")


async def specs_entry_router(ctx: Context) -> None:
    """Storyboard builds specs in code; per_shot fans out to LLM prompters."""
    pipeline_mode = ctx.state.get("pipeline_mode") or "per_shot"
    if pipeline_mode == "storyboard":
        ctx.route = "storyboard"
    else:
        ctx.route = "per_shot"


sheet_map_builder_node = FunctionNode(func=sheet_map_builder, name="sheet_map_builder_node")
save_production_plan_node = FunctionNode(
    func=save_production_plan, name="save_production_plan_node"
)
persist_enriched_plan_node = FunctionNode(
    func=persist_enriched_plan, name="persist_enriched_plan_node"
)
build_generation_specs_from_plan_node = FunctionNode(
    func=build_generation_specs_from_plan, name="build_generation_specs_from_plan_node"
)
specs_entry_router_node = FunctionNode(func=specs_entry_router, name="specs_entry_router_node")
