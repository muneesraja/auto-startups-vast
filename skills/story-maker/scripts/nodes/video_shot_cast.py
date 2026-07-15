"""Cast-coherent video_shot grouping for reel_v2 start-frame fidelity.

A following panel may stay in a group only if its characters_present is a
subset of the anchor panel's cast. Empty anchor = environment-only clip.
"""
from __future__ import annotations

import re
from typing import Any


def panel_cast_map(story_scene: dict) -> dict[str, frozenset[str]]:
    """Map shot_id → frozenset of character ids present on that panel."""
    out: dict[str, frozenset[str]] = {}
    for shot in story_scene.get("shots") or []:
        sid = shot.get("shot_id")
        if not sid:
            continue
        chars = [c for c in (shot.get("characters_present") or []) if c]
        out[sid] = frozenset(chars)
    return out


def cast_is_subset(panel_cast: frozenset[str], anchor_cast: frozenset[str]) -> bool:
    """True when panel cast ⊆ anchor cast (empty ⊆ empty)."""
    return panel_cast.issubset(anchor_cast)


def chunk_panels_by_anchor_cast(
    panel_ids: list[str],
    cast_by_panel: dict[str, frozenset[str]],
) -> list[list[str]]:
    """Split consecutive panels into cast-coherent groups (anchor = first)."""
    if not panel_ids:
        return []
    groups: list[list[str]] = []
    current: list[str] = []
    anchor_cast: frozenset[str] = frozenset()
    for pid in panel_ids:
        panel_cast = cast_by_panel.get(pid, frozenset())
        if not current:
            current = [pid]
            anchor_cast = panel_cast
            continue
        if cast_is_subset(panel_cast, anchor_cast):
            current.append(pid)
        else:
            groups.append(current)
            current = [pid]
            anchor_cast = panel_cast
    if current:
        groups.append(current)
    return groups


def _roster_name_patterns(characters: list[dict] | None) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for c in characters or []:
        for raw in (c.get("name"), c.get("id")):
            token = str(raw or "").strip()
            if len(token) < 2:
                continue
            patterns.append(re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE))
    return patterns


def motion_arc_mentions_roster(motion_arc: str, characters: list[dict] | None) -> bool:
    text = (motion_arc or "").strip()
    if not text:
        return False
    for pat in _roster_name_patterns(characters):
        if pat.search(text):
            return True
    return False


def build_environment_motion_arc(
    member_shots: list[dict],
    *,
    duration_seconds: int = 8,
) -> str:
    """Timed env/camera-only arc from member panel intents (no roster subjects)."""
    intents: list[str] = []
    cameras: list[str] = []
    for shot in member_shots:
        mi = str(shot.get("motion_intent") or "").strip()
        ci = str(shot.get("camera_intent") or "").strip()
        if mi:
            intents.append(mi.rstrip("."))
        if ci:
            cameras.append(ci.rstrip("."))
    primary = intents[0] if intents else "Light and leaves shift across the empty stage"
    cam = cameras[0] if cameras else "Slow establishing camera move"
    mid = intents[1] if len(intents) > 1 else "environment micro-motion continues"
    end = intents[-1] if len(intents) > 2 else mid
    dur = max(3, int(duration_seconds or 8))
    t1 = max(1, dur // 4)
    t2 = max(t1 + 1, dur // 2)
    t3 = max(t2 + 1, (3 * dur) // 4)
    return (
        f"Over the first {t1} seconds, {cam.lower()} while {primary.lower()}; "
        f"then through the midpoint ({t1}–{t2}s) {mid.lower()} with continuous "
        f"leaf, light, and particle micro-motion; "
        f"by {t2}–{t3}s settle the camera as {end.lower()}; "
        f"in the final seconds hold with ambient environment motion only."
    )


def ensure_env_safe_motion_arc(
    motion_arc: str,
    *,
    anchor_cast: frozenset[str],
    member_shots: list[dict],
    characters: list[dict] | None,
    duration_seconds: int = 8,
) -> str:
    """For empty anchors, replace arcs that invent roster names or are blank."""
    if anchor_cast:
        return (motion_arc or "").strip()
    arc = (motion_arc or "").strip()
    if not arc or motion_arc_mentions_roster(arc, characters):
        return build_environment_motion_arc(
            member_shots, duration_seconds=duration_seconds
        )
    return arc


def split_video_shots_by_anchor_cast(
    video_shots: list[dict],
    story_scene: dict,
    *,
    characters: list[dict] | None = None,
) -> list[dict]:
    """Re-chunk validated consecutive video_shots into cast-coherent groups.

    Preserves pace from the source group that contributed the first panel.
    Renumbers video_shot_id as ``{scene_id}_vshot_{nn}``.
    """
    scene_id = story_scene.get("scene_id") or ""
    cast_by_panel = panel_cast_map(story_scene)
    shot_lookup = {
        sh.get("shot_id"): sh
        for sh in (story_scene.get("shots") or [])
        if isinstance(sh, dict) and sh.get("shot_id")
    }

    # Flatten source groups in order, remembering source metadata per panel.
    panel_meta: dict[str, dict[str, Any]] = {}
    ordered_panels: list[str] = []
    source_group_panels: dict[str, tuple[str, ...]] = {}
    for vshot in video_shots:
        if not isinstance(vshot, dict):
            continue
        panels = list(vshot.get("panel_ids") or [])
        src_key = tuple(panels)
        for pid in panels:
            if pid in panel_meta:
                continue
            ordered_panels.append(pid)
            source_group_panels[pid] = src_key
            panel_meta[pid] = {
                "pace": str(vshot.get("pace") or "medium").strip().lower(),
                "duration_seconds": int(vshot.get("duration_seconds") or 8),
                "motion_arc": str(vshot.get("motion_arc") or "").strip(),
            }

    groups = chunk_panels_by_anchor_cast(ordered_panels, cast_by_panel)
    out: list[dict] = []
    for idx, group in enumerate(groups, start=1):
        anchor = group[0]
        anchor_cast = cast_by_panel.get(anchor, frozenset())
        meta = panel_meta.get(anchor) or {}
        duration = int(meta.get("duration_seconds") or 8)
        member_shots = [shot_lookup[pid] for pid in group if pid in shot_lookup]
        source_arc = str(meta.get("motion_arc") or "").strip()
        src_panels = source_group_panels.get(anchor) or tuple(group)
        group_unchanged = tuple(group) == src_panels

        if not anchor_cast:
            motion_arc = build_environment_motion_arc(
                member_shots, duration_seconds=duration
            )
        elif (
            group_unchanged
            and source_arc
            and not motion_arc_mentions_forbidden_cast(
                source_arc, characters, anchor_cast
            )
        ):
            # Keep planner arc only when the group was already cast-coherent
            # and does not name off-cast roster subjects.
            motion_arc = source_arc
        else:
            parts = [
                str(s.get("motion_intent") or "").strip().rstrip(".")
                for s in member_shots
                if str(s.get("motion_intent") or "").strip()
            ]
            if parts:
                motion_arc = (
                    "Over the first seconds "
                    + "; then ".join(parts)
                    + "; continuous micro-motion throughout."
                )
            else:
                motion_arc = source_arc or (
                    "Over the first seconds the primary action begins; "
                    "then follows through with clear body change; "
                    "continuous micro-motion throughout."
                )

        # Second-pass / sticky bad arcs: if cast is present but arc still
        # names no allowed cast and reads like an establishing empty plate
        # inherited from a parent group, rebuild from member intents.
        if anchor_cast and source_arc and motion_arc == source_arc:
            if motion_arc_mentions_forbidden_cast(
                motion_arc, characters, anchor_cast
            ) or _arc_looks_like_empty_establish(motion_arc, characters, anchor_cast):
                parts = [
                    str(s.get("motion_intent") or "").strip().rstrip(".")
                    for s in member_shots
                    if str(s.get("motion_intent") or "").strip()
                ]
                if parts:
                    motion_arc = (
                        "Over the first seconds "
                        + "; then ".join(parts)
                        + "; continuous micro-motion throughout."
                    )

        out.append(
            {
                "video_shot_id": f"{scene_id}_vshot_{idx:02d}",
                "scene_id": scene_id,
                "panel_ids": list(group),
                "anchor_panel_id": anchor,
                "duration_seconds": duration,
                "motion_arc": motion_arc,
                "pace": str(meta.get("pace") or "medium"),
            }
        )
    return out


def motion_arc_mentions_forbidden_cast(
    motion_arc: str,
    characters: list[dict] | None,
    anchor_cast: frozenset[str],
) -> bool:
    """True when arc names a roster character not on the anchor cast."""
    text = (motion_arc or "").strip()
    if not text:
        return False
    for c in characters or []:
        cid = str(c.get("id") or "").strip()
        if not cid or cid in anchor_cast:
            continue
        for token in (c.get("name"), cid):
            token_s = str(token or "").strip()
            if len(token_s) < 2:
                continue
            if re.search(rf"\b{re.escape(token_s)}\b", text, re.IGNORECASE):
                return True
    return False


def _arc_looks_like_empty_establish(
    motion_arc: str,
    characters: list[dict] | None,
    anchor_cast: frozenset[str],
) -> bool:
    """Heuristic: cast-anchor arc that never names allowed cast and talks reveal/empty."""
    text = (motion_arc or "").strip()
    if not text or not anchor_cast:
        return False
    names_allowed = False
    for c in characters or []:
        cid = str(c.get("id") or "").strip()
        if cid not in anchor_cast:
            continue
        for token in (c.get("name"), cid):
            token_s = str(token or "").strip()
            if len(token_s) >= 2 and re.search(
                rf"\b{re.escape(token_s)}\b", text, re.IGNORECASE
            ):
                names_allowed = True
                break
        if names_allowed:
            break
    if names_allowed:
        return False
    return bool(
        re.search(
            r"\b(empty|establishing|reveal|sunlit sanctuary|crossing birds)\b",
            text,
            re.IGNORECASE,
        )
    )


def synthesize_cast_coherent_video_shots(
    story_view: dict,
    *,
    max_group_size: int = 3,
) -> dict:
    """Synthesize video_shots with cast-coherent chunking (and soft size cap)."""
    characters = story_view.get("characters") or []
    scenes_out: list[dict] = []
    for scene in story_view.get("scenes") or []:
        scene_id = scene.get("scene_id")
        if not scene_id:
            continue
        panels = [sh.get("shot_id") for sh in scene.get("shots") or [] if sh.get("shot_id")]
        cast_by_panel = panel_cast_map(scene)
        cast_groups = chunk_panels_by_anchor_cast(panels, cast_by_panel)
        # Soft-cap group length while remaining cast-coherent.
        sized: list[list[str]] = []
        for group in cast_groups:
            for i in range(0, len(group), max_group_size):
                sized.append(group[i : i + max_group_size])
        vshots: list[dict] = []
        for idx, group in enumerate(sized, start=1):
            member_shots = [
                sh
                for sh in (scene.get("shots") or [])
                if sh.get("shot_id") in group
            ]
            # Preserve story order within member_shots
            order = {pid: i for i, pid in enumerate(group)}
            member_shots = sorted(
                member_shots, key=lambda s: order.get(s.get("shot_id"), 0)
            )
            anchor_cast = cast_by_panel.get(group[0], frozenset())
            if not anchor_cast:
                arc = build_environment_motion_arc(member_shots, duration_seconds=8)
            else:
                arc = (
                    "Over the first seconds the primary subject begins the panel action; "
                    "then follows through with clear body and hand change; "
                    "by the midpoint the next panel beat continues the same arc; "
                    "in the final seconds settle into the last panel's end state with "
                    "environment micro-motion throughout."
                )
            vshots.append(
                {
                    "video_shot_id": f"{scene_id}_vshot_{idx:02d}",
                    "scene_id": scene_id,
                    "panel_ids": group,
                    "anchor_panel_id": group[0],
                    "duration_seconds": 8,
                    "motion_arc": arc,
                    "pace": "fast",
                }
            )
        # ensure_env_safe already baked for empty; still run split noop for renumber
        vshots = split_video_shots_by_anchor_cast(
            vshots, scene, characters=characters
        )
        scenes_out.append({"scene_id": scene_id, "video_shots": vshots})
    return {"scenes": scenes_out}
