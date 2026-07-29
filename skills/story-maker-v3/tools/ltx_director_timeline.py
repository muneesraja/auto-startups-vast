"""Build LTX Director timeline_data + relay widgets for headless API runs."""

from __future__ import annotations

import json
import math
import uuid


def snap_ltx_frames(seconds: float, fps: int = 24) -> int:
    """Pixel frames for LTX (8n+1 rule)."""
    raw = max(1, int(round(seconds * fps)))
    return int(math.ceil((raw - 1) / 8.0) * 8) + 1


def _seg_id() -> str:
    return uuid.uuid4().hex[:12]


def build_contiguous_relay(
    segments: list[dict],
    *,
    start_frame: int,
    duration_frames: int,
) -> tuple[str, str]:
    """Mirror ltx_director.js commitChanges contiguous prompt/length logic."""
    end_frame = start_frame + duration_frames
    sorted_segments = sorted(segments, key=lambda s: int(s.get("start", 0)))
    contiguous_lengths: list[int] = []
    contiguous_prompts: list[str] = []
    current_cursor = start_frame
    pending_gap = 0

    for seg in sorted_segments:
        seg_start = int(seg.get("start", 0))
        seg_len = int(seg.get("length", 1))
        if seg_start + seg_len <= start_frame:
            continue
        if seg_start >= end_frame:
            break

        effective_start = max(seg_start, start_frame)
        if effective_start > current_cursor:
            gap_length = min(effective_start, end_frame) - current_cursor
            if contiguous_lengths:
                contiguous_lengths[-1] += gap_length
            else:
                pending_gap += gap_length

        clipped_end = min(seg_start + seg_len, end_frame)
        clipped_length = clipped_end - effective_start
        contiguous_lengths.append(clipped_length + pending_gap)
        contiguous_prompts.append(seg.get("prompt", "") or "")
        pending_gap = 0
        current_cursor = max(current_cursor, seg_start + seg_len)

    clamped_cursor = min(current_cursor, end_frame)
    if contiguous_lengths and clamped_cursor < end_frame:
        contiguous_lengths[-1] += end_frame - clamped_cursor

    return " | ".join(contiguous_prompts), ",".join(str(x) for x in contiguous_lengths)


def build_guide_strength(
    segments: list[dict],
    *,
    start_frame: int,
    duration_frames: int,
) -> str:
    end_frame = start_frame + duration_frames
    strengths = []
    for seg in sorted(segments, key=lambda s: int(s.get("start", 0))):
        if seg.get("type") == "text":
            continue
        seg_start = int(seg.get("start", 0))
        seg_len = int(seg.get("length", 1))
        if seg_start + seg_len <= start_frame or seg_start >= end_frame:
            continue
        if not (seg.get("imageFile") or seg.get("imageB64")):
            continue
        val = seg.get("guideStrength", 1.0)
        strengths.append(f"{float(val):.2f}")
    return ",".join(strengths)


def build_i2v_timeline(
    *,
    image_file: str,
    motion_prompt: str,
    global_prompt: str = "",
    duration_frames: int,
    guide_strength: float = 0.8,
    fps: int = 24,
    start_frame: int = 0,
) -> dict:
    """Simple I2V: one image guide at frame 0 + one text segment for motion."""
    image_seg = {
        "id": _seg_id(),
        "type": "image",
        "start": start_frame,
        "length": 1,
        "prompt": "",
        "imageFile": image_file,
        "guideStrength": float(guide_strength),
        "isEndFrame": False,
    }
    text_seg = {
        "id": _seg_id(),
        "type": "text",
        "start": start_frame,
        "length": duration_frames,
        "prompt": motion_prompt,
    }
    segments = [image_seg, text_seg]
    local_prompts, segment_lengths = build_contiguous_relay(
        [text_seg], start_frame=start_frame, duration_frames=duration_frames
    )
    guide_strength_str = build_guide_strength(
        segments, start_frame=start_frame, duration_frames=duration_frames
    )
    timeline = {
        "mainTrackEnabled": True,
        "audioTrackEnabled": False,
        "motionTrackEnabled": False,
        "propHeight": 90,
        "globalPropHeight": 60,
        "showFilenames": True,
        "overrideAudio": False,
        "inpaint_audio": True,
        "global_prompt": global_prompt,
        "retake_global_prompt": "",
        "retakeMode": False,
        "retakeStart": 24,
        "retakeLength": 48,
        "retakePrompt": "",
        "retakeStrength": 1.0,
        "retakeVideo": None,
        "normalStartFrame": start_frame,
        "normalDurationFrames": duration_frames,
        "segments": [image_seg, text_seg],
        "motionSegments": [],
        "audioSegments": [],
    }
    return {
        "timeline_data": json.dumps(timeline, separators=(",", ":")),
        "local_prompts": local_prompts,
        "segment_lengths": segment_lengths,
        "guide_strength": guide_strength_str,
        "start_frame": start_frame,
        "end_frame": start_frame + duration_frames,
        "duration_frames": duration_frames,
        "duration_seconds": duration_frames / float(fps),
        "frame_rate": fps,
    }


def build_flf_timeline(
    *,
    first_image_file: str,
    last_image_file: str,
    motion_prompt: str,
    global_prompt: str = "",
    duration_frames: int,
    first_guide_strength: float = 0.7,
    last_guide_strength: float = 0.85,
    fps: int = 24,
    start_frame: int = 0,
    anchor_frames: int = 24,
) -> dict:
    """FLF: start guide @ frame 0, end guide with isEndFrame on last frame, text between."""
    anchor = max(1, min(anchor_frames, duration_frames // 3))
    middle_len = max(1, duration_frames - 2 * anchor)
    last_start = start_frame + duration_frames - anchor

    first_seg = {
        "id": _seg_id(),
        "type": "image",
        "start": start_frame,
        "length": anchor,
        "prompt": "",
        "imageFile": first_image_file,
        "guideStrength": float(first_guide_strength),
        "isEndFrame": False,
    }
    text_seg = {
        "id": _seg_id(),
        "type": "text",
        "start": start_frame + anchor,
        "length": middle_len,
        "prompt": motion_prompt,
    }
    last_seg = {
        "id": _seg_id(),
        "type": "image",
        "start": last_start,
        "length": anchor,
        "prompt": "",
        "imageFile": last_image_file,
        "guideStrength": float(last_guide_strength),
        "isEndFrame": True,
    }
    segments = [first_seg, text_seg, last_seg]
    local_prompts, segment_lengths = build_contiguous_relay(
        [text_seg], start_frame=start_frame, duration_frames=duration_frames
    )
    guide_strength_str = build_guide_strength(
        segments, start_frame=start_frame, duration_frames=duration_frames
    )
    timeline = {
        "mainTrackEnabled": True,
        "audioTrackEnabled": False,
        "motionTrackEnabled": False,
        "propHeight": 90,
        "globalPropHeight": 60,
        "showFilenames": True,
        "overrideAudio": False,
        "inpaint_audio": True,
        "global_prompt": global_prompt,
        "retake_global_prompt": "",
        "retakeMode": False,
        "retakeStart": 24,
        "retakeLength": 48,
        "retakePrompt": "",
        "retakeStrength": 1.0,
        "retakeVideo": None,
        "normalStartFrame": start_frame,
        "normalDurationFrames": duration_frames,
        "segments": segments,
        "motionSegments": [],
        "audioSegments": [],
    }
    return {
        "timeline_data": json.dumps(timeline, separators=(",", ":")),
        "local_prompts": local_prompts,
        "segment_lengths": segment_lengths,
        "guide_strength": guide_strength_str,
        "start_frame": start_frame,
        "end_frame": start_frame + duration_frames,
        "duration_frames": duration_frames,
        "duration_seconds": duration_frames / float(fps),
        "frame_rate": fps,
    }


def _normalize_motion_segments(raw_segments: list | None) -> list[dict]:
    """Return sorted ratio segments with clamped bounds."""
    out: list[dict] = []
    for item in raw_segments or []:
        if not isinstance(item, dict):
            continue
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            continue
        try:
            start = float(item.get("start_ratio", 0.0))
            end = float(item.get("end_ratio", 1.0))
        except (TypeError, ValueError):
            continue
        start = max(0.0, min(1.0, start))
        end = max(0.0, min(1.0, end))
        if end <= start:
            continue
        out.append({"start_ratio": start, "end_ratio": end, "prompt": prompt})
    out.sort(key=lambda s: (s["start_ratio"], s["end_ratio"]))
    return out


def ratios_to_text_segments(
    motion_segments: list[dict],
    *,
    duration_frames: int,
    start_frame: int = 0,
) -> list[dict]:
    """Convert AD ratio beats into pixel-frame Prompt Relay text segments.

    Segments are snapped so their lengths sum exactly to ``duration_frames``.
    """
    normalized = _normalize_motion_segments(motion_segments)
    if not normalized:
        return []

    # Allocate frames by span weight; fix rounding on the last segment.
    weights = [s["end_ratio"] - s["start_ratio"] for s in normalized]
    total_w = sum(weights) or 1.0
    lengths: list[int] = []
    remaining = duration_frames
    for i, w in enumerate(weights):
        if i == len(weights) - 1:
            lengths.append(max(1, remaining))
        else:
            length = max(1, int(round(duration_frames * (w / total_w))))
            length = min(length, max(1, remaining - (len(weights) - i - 1)))
            lengths.append(length)
            remaining -= length

    cursor = start_frame
    text_segs: list[dict] = []
    for seg, length in zip(normalized, lengths):
        text_segs.append(
            {
                "id": _seg_id(),
                "type": "text",
                "start": cursor,
                "length": length,
                "prompt": seg["prompt"],
            }
        )
        cursor += length
    return text_segs


def flatten_motion_segments_prompt(motion_segments: list[dict] | None) -> str:
    """Join timed beats into one legacy flat motion_prompt."""
    parts = [
        str(s.get("prompt") or "").strip()
        for s in _normalize_motion_segments(motion_segments)
    ]
    return " ".join(p for p in parts if p)


def _placement_ratio(guide: dict) -> float:
    placement = str(guide.get("placement") or "").strip().lower()
    if placement == "start":
        return 0.0
    if placement == "middle":
        try:
            raw = guide.get("start_ratio")
            return float(raw) if raw is not None else 0.5
        except (TypeError, ValueError):
            return 0.5
    if placement == "end":
        return 1.0
    try:
        return max(0.0, min(1.0, float(guide.get("start_ratio", 0.0))))
    except (TypeError, ValueError):
        return 0.0


def normalize_guide_frames(raw_guides: list | None) -> list[dict]:
    """Normalize AD guide frames into sorted ratio placements."""
    out: list[dict] = []
    for item in raw_guides or []:
        if not isinstance(item, dict):
            continue
        panel_id = str(item.get("panel_id") or "").strip()
        image_file = str(item.get("image_file") or item.get("imageFile") or "").strip()
        if not panel_id and not image_file:
            continue
        ratio = _placement_ratio(item)
        placement = str(item.get("placement") or "").strip().lower() or None
        is_end = bool(item.get("is_end_frame") or item.get("isEndFrame"))
        if placement == "end" or ratio >= 0.999:
            is_end = True
            ratio = 1.0
            placement = placement or "end"
        elif placement == "start":
            ratio = 0.0
            is_end = False
        elif placement == "middle":
            is_end = False
        strength = item.get("guide_strength", item.get("guideStrength"))
        try:
            strength_f = float(strength) if strength is not None else None
        except (TypeError, ValueError):
            strength_f = None
        out.append(
            {
                "panel_id": panel_id,
                "image_file": image_file,
                "placement": placement,
                "start_ratio": ratio,
                "is_end_frame": is_end,
                "guide_strength": strength_f,
            }
        )
    out.sort(key=lambda g: (g["start_ratio"], 1 if g["is_end_frame"] else 0))
    return out


def guide_frames_to_image_segments(
    guides: list[dict],
    *,
    duration_frames: int,
    start_frame: int = 0,
    default_start_strength: float = 0.7,
    default_middle_strength: float = 0.55,
    default_end_strength: float = 0.85,
    anchor_frames: int = 24,
) -> list[dict]:
    """Convert normalized guide frames into LTX Director image segments."""
    if not guides:
        return []
    anchor = max(1, min(anchor_frames, max(1, duration_frames // 4)))
    image_segments: list[dict] = []
    for guide in guides:
        image_file = guide.get("image_file") or ""
        if not image_file:
            continue
        ratio = float(guide.get("start_ratio", 0.0))
        is_end = bool(guide.get("is_end_frame"))
        strength = guide.get("guide_strength")
        if strength is None:
            if is_end or ratio >= 0.999:
                strength = default_end_strength
            elif ratio <= 0.001:
                strength = default_start_strength
            else:
                strength = default_middle_strength

        if is_end or ratio >= 0.999:
            seg_start = start_frame + max(0, duration_frames - anchor)
            length = min(anchor, duration_frames)
            is_end = True
        elif ratio <= 0.001:
            seg_start = start_frame
            length = 1 if len(guides) == 1 else max(1, min(anchor, duration_frames // 3))
        else:
            seg_start = start_frame + int(round(ratio * (duration_frames - 1)))
            seg_start = max(start_frame, min(start_frame + duration_frames - 1, seg_start))
            length = 1

        image_segments.append(
            {
                "id": _seg_id(),
                "type": "image",
                "start": seg_start,
                "length": length,
                "prompt": "",
                "imageFile": image_file,
                "guideStrength": float(strength),
                "isEndFrame": is_end,
            }
        )
    return image_segments


def build_guided_timeline(
    *,
    image_segments: list[dict],
    text_segments: list[dict],
    global_prompt: str = "",
    duration_frames: int,
    fps: int = 24,
    start_frame: int = 0,
) -> dict:
    """Assemble timeline_data + relay widgets from image guides + text beats."""
    segments = list(image_segments) + list(text_segments)
    local_prompts, segment_lengths = build_contiguous_relay(
        text_segments, start_frame=start_frame, duration_frames=duration_frames
    )
    guide_strength_str = build_guide_strength(
        segments, start_frame=start_frame, duration_frames=duration_frames
    )
    timeline = {
        "mainTrackEnabled": True,
        "audioTrackEnabled": False,
        "motionTrackEnabled": False,
        "propHeight": 90,
        "globalPropHeight": 60,
        "showFilenames": True,
        "overrideAudio": False,
        "inpaint_audio": True,
        "global_prompt": global_prompt,
        "retake_global_prompt": "",
        "retakeMode": False,
        "retakeStart": 24,
        "retakeLength": 48,
        "retakePrompt": "",
        "retakeStrength": 1.0,
        "retakeVideo": None,
        "normalStartFrame": start_frame,
        "normalDurationFrames": duration_frames,
        "segments": segments,
        "motionSegments": [],
        "audioSegments": [],
    }
    return {
        "timeline_data": json.dumps(timeline, separators=(",", ":")),
        "local_prompts": local_prompts,
        "segment_lengths": segment_lengths,
        "guide_strength": guide_strength_str,
        "start_frame": start_frame,
        "end_frame": start_frame + duration_frames,
        "duration_frames": duration_frames,
        "duration_seconds": duration_frames / float(fps),
        "frame_rate": fps,
    }


def build_timeline_from_beats(
    beats: list[dict],
    *,
    image_files: dict[str, str] | None = None,
    global_prompt: str = "",
    fps: int = 24,
    start_frame: int = 0,
    default_start_strength: float = 0.7,
    default_bridge_strength: float = 0.55,
    default_end_strength: float = 0.9,
) -> dict:
    """Assemble an LTX Director timeline from a free-form AD beat list.

    Unlike the ratio-based ``guide_frames``/``motion_segments`` pair, durations
    live on ``text`` beats (motion windows); ``guide`` beats are *instants*
    (optionally held for ``anchor_seconds``) pinned wherever they fall in
    story order. Clip duration = sum of the text beat durations — guide
    beats do not consume timeline budget. Supports leading text (an
    un-anchored, T2V-style opening before the first guide lands) and
    trailing text (a beat after the last/end guide). ``role: "end"`` (or
    ``is_end_frame``) pins that guide to the true final frames regardless of
    story position, matching FLF last-frame convention.
    """
    if not beats:
        raise ValueError("beats timeline requires at least one beat")

    image_files = image_files or {}
    text_total_seconds = sum(
        float(b.get("duration_seconds") or 0.0) for b in beats if b.get("kind") == "text"
    )
    if text_total_seconds <= 0:
        text_total_seconds = 1.0
    duration_frames = snap_ltx_frames(text_total_seconds, fps=fps)
    end_frame_total = start_frame + duration_frames

    text_indices = [i for i, b in enumerate(beats) if b.get("kind") == "text"]
    text_lengths: dict[int, int] = {}
    if text_indices:
        weights = [max(0.0, float(beats[i].get("duration_seconds") or 0.0)) for i in text_indices]
        total_w = sum(weights) or float(len(weights))
        remaining = duration_frames
        for pos, idx in enumerate(text_indices):
            if pos == len(text_indices) - 1:
                text_lengths[idx] = max(1, remaining)
            else:
                w = weights[pos] if weights[pos] else (total_w / len(weights))
                length = max(1, int(round(duration_frames * (w / total_w))))
                length = min(length, max(1, remaining - (len(text_indices) - pos - 1)))
                text_lengths[idx] = length
                remaining -= length

    image_segments: list[dict] = []
    text_segments: list[dict] = []
    cursor = start_frame

    for i, beat in enumerate(beats):
        if beat.get("kind") == "text":
            length = text_lengths.get(i, 1)
            prompt = str(beat.get("prompt") or "").strip()
            if prompt:
                text_segments.append(
                    {
                        "id": _seg_id(),
                        "type": "text",
                        "start": cursor,
                        "length": length,
                        "prompt": prompt,
                    }
                )
            cursor += length
            continue

        panel_id = str(beat.get("panel_id") or "")
        image_file = str(beat.get("image_file") or image_files.get(panel_id) or "")
        if not image_file:
            continue
        role = str(beat.get("role") or "").strip().lower() or None
        is_end = bool(beat.get("is_end_frame")) or role == "end"

        strength = beat.get("guide_strength")
        if strength is None:
            if is_end:
                strength = default_end_strength
            elif role == "start":
                strength = default_start_strength
            else:
                strength = default_bridge_strength

        anchor_seconds = float(beat.get("anchor_seconds") or 0.0)
        length = max(1, int(round(anchor_seconds * fps))) if anchor_seconds > 0 else 1

        if is_end:
            seg_start = max(start_frame, end_frame_total - length)
        else:
            seg_start = max(start_frame, min(cursor, end_frame_total - 1))

        image_segments.append(
            {
                "id": _seg_id(),
                "type": "image",
                "start": seg_start,
                "length": length,
                "prompt": "",
                "imageFile": image_file,
                "guideStrength": float(strength),
                "isEndFrame": is_end,
            }
        )

    if not image_segments:
        raise ValueError("beats timeline resolved no usable guide image segments")

    return build_guided_timeline(
        image_segments=image_segments,
        text_segments=text_segments,
        global_prompt=global_prompt,
        duration_frames=duration_frames,
        fps=fps,
        start_frame=start_frame,
    )


def build_timeline_from_director_clip(
    clip: dict,
    *,
    first_image_file: str,
    last_image_file: str | None = None,
    guide_image_files: dict[str, str] | None = None,
    global_prompt: str = "",
    fps: int = 24,
    render: dict | None = None,
) -> dict:
    """Map an Assistant Director clip/render-unit onto an LTX Director timeline.

    Prefers the free-form ``beats`` timeline when present (durations on text
    beats, guides as instants — see ``build_timeline_from_beats``). Otherwise
    prefers explicit ``guide_frames`` (start/middle/end stills). Otherwise
    falls back to classic I2V / FLF start+end guides. Prefers
    ``motion_segments`` for Prompt Relay; otherwise uses flat ``motion_prompt``.
    """
    if clip.get("beats"):
        start_id = clip.get("start_panel_id") or clip.get("first_panel_id")
        end_id = clip.get("end_panel_id") or clip.get("last_panel_id") or start_id
        uploaded = dict(guide_image_files or {})
        if start_id and first_image_file:
            uploaded.setdefault(start_id, first_image_file)
        if end_id and last_image_file:
            uploaded.setdefault(end_id, last_image_file)
        if render is None:
            from tools.ltx_render_params import resolve_clip_render_params

            render = resolve_clip_render_params(clip, prefer_stored=True)
        first_strength = float(render.get("i2v_strength", 0.7))
        last_strength = float(render.get("last_frame_strength", 0.85))
        bridge_strength = max(0.4, min(first_strength - 0.1, 0.6))
        return build_timeline_from_beats(
            clip.get("beats") or [],
            image_files=uploaded,
            global_prompt=(global_prompt or clip.get("global_prompt") or "").strip(),
            fps=fps,
            default_start_strength=first_strength,
            default_bridge_strength=bridge_strength,
            default_end_strength=last_strength,
        )

    start_id = clip.get("start_panel_id") or clip.get("first_panel_id")
    end_id = clip.get("end_panel_id") or clip.get("last_panel_id") or start_id
    workflow = (clip.get("workflow") or clip.get("mode") or "i2v").lower()
    guides_preview = normalize_guide_frames(clip.get("guide_frames"))
    if workflow in ("i2v_hold", "i2v") or start_id == end_id:
        if any(g.get("is_end_frame") for g in guides_preview) and len(guides_preview) > 1:
            workflow = "flf2v"
        else:
            workflow = "i2v"
    else:
        workflow = "flf2v"

    resolved_global = (global_prompt or clip.get("global_prompt") or "").strip()
    motion_prompt = (clip.get("motion_prompt") or "").strip()
    motion_segments = _normalize_motion_segments(clip.get("motion_segments"))
    if not motion_prompt and motion_segments:
        motion_prompt = flatten_motion_segments_prompt(motion_segments)

    duration_seconds = float(clip.get("duration_seconds") or 6)
    duration_frames = snap_ltx_frames(duration_seconds, fps=fps)
    start_frame = 0

    if render is None:
        from tools.ltx_render_params import resolve_clip_render_params

        render = resolve_clip_render_params(clip, prefer_stored=True)

    first_strength = float(render.get("i2v_strength", 0.7))
    last_strength = float(render.get("last_frame_strength", 0.85))
    middle_strength = max(0.45, min(first_strength - 0.15, 0.6))

    text_segments = ratios_to_text_segments(
        motion_segments,
        duration_frames=duration_frames,
        start_frame=start_frame,
    )

    guides = guides_preview
    uploaded = guide_image_files or {}
    if guides:
        resolved_guides = []
        for g in guides:
            panel = g.get("panel_id") or ""
            image_file = (
                g.get("image_file")
                or uploaded.get(panel)
                or (
                    first_image_file
                    if panel == start_id
                    else (last_image_file if panel == end_id else "")
                )
            )
            if not image_file:
                continue
            item = dict(g)
            item["image_file"] = image_file
            resolved_guides.append(item)
        image_segments = guide_frames_to_image_segments(
            resolved_guides,
            duration_frames=duration_frames,
            start_frame=start_frame,
            default_start_strength=first_strength,
            default_middle_strength=middle_strength,
            default_end_strength=last_strength,
        )
        if image_segments:
            if not text_segments:
                text_segments = [
                    {
                        "id": _seg_id(),
                        "type": "text",
                        "start": start_frame,
                        "length": duration_frames,
                        "prompt": motion_prompt,
                    }
                ]
            return build_guided_timeline(
                image_segments=image_segments,
                text_segments=text_segments,
                global_prompt=resolved_global,
                duration_frames=duration_frames,
                fps=fps,
                start_frame=start_frame,
            )

    if not text_segments:
        if workflow == "flf2v":
            if not last_image_file:
                raise ValueError("FLF timeline requires last_image_file")
            return build_flf_timeline(
                first_image_file=first_image_file,
                last_image_file=last_image_file,
                motion_prompt=motion_prompt,
                global_prompt=resolved_global,
                duration_frames=duration_frames,
                first_guide_strength=first_strength,
                last_guide_strength=last_strength,
                fps=fps,
            )
        return build_i2v_timeline(
            image_file=first_image_file,
            motion_prompt=motion_prompt,
            global_prompt=resolved_global,
            duration_frames=duration_frames,
            guide_strength=first_strength,
            fps=fps,
        )

    image_segments = [
        {
            "id": _seg_id(),
            "type": "image",
            "start": start_frame,
            "length": 1 if workflow == "i2v" else max(1, min(24, duration_frames // 3)),
            "prompt": "",
            "imageFile": first_image_file,
            "guideStrength": first_strength,
            "isEndFrame": False,
        }
    ]
    if workflow == "flf2v":
        if not last_image_file:
            raise ValueError("FLF timeline requires last_image_file")
        anchor = max(1, min(24, duration_frames // 3))
        image_segments.append(
            {
                "id": _seg_id(),
                "type": "image",
                "start": start_frame + duration_frames - anchor,
                "length": anchor,
                "prompt": "",
                "imageFile": last_image_file,
                "guideStrength": last_strength,
                "isEndFrame": True,
            }
        )

    return build_guided_timeline(
        image_segments=image_segments,
        text_segments=text_segments,
        global_prompt=resolved_global,
        duration_frames=duration_frames,
        fps=fps,
        start_frame=start_frame,
    )
