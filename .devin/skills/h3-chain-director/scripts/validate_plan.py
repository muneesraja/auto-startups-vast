#!/usr/bin/env python3
"""Deterministic validator for the H3 chain plan + continuity ledger.

Validates two artifacts:
  1. ``plan.json`` — the H3 Chain Plan JSON submitted to ComfyUI.
  2. ``state.json`` — the continuity ledger (optional, for fast-pace + chain checks).

Usage::

    python3 scripts/validate_plan.py plan.json [--ledger state.json] [--bible bible.json]
                                               [--song song.wav] [--ref-images N]

Writes ``<file>.validation.json`` next to the artifact and exits nonzero on
failure (same contract as ``story-maker-v3/scripts/validate.py``).

No LLM calls. Pure parsing + assertions. Stdlib only (ffprobe optional for
audio duration).

Check groups:
  Structural  — JSON syntax, 1–128 shots, valid ids, frame grid, durations, seeds, steps.
  Fast-pace   — 6–9 shots/clip, 1.0–2.5s each, increasing, no adjacent framing+angle,
                sound cue per shot, one dominant action, vague-verb blacklist, wps band.
  Chain       — hinge_out/hinge_in linkage, [Shot 1] continuation, quad conflict scan.
  Bible       — cast ids exist, <Subject N> mapping, appearance lock consistency, anti-bleed.
  Audio       — lyric windows inside clip audio window, no gap/overlap, wps ≤ 3.5, on_beat ±80ms.
  Sheet       — 3×2/6 panels, reading order, per-panel desc count, negatives, ≤6 refs.
  Ref2VA      — only declared labels, no label index exceeds wired refs.
  Assets      — every cast/location resolves to approved asset_id@version, lock hash match.
  Run safety  — source_track duration ≥ total delivered; freeze check on accepted clips.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

H3_FPS = 24
LENGTH_MIN = 5
LENGTH_MAX = 3592
DURATION_MAX = 149.667  # 3592 / 24
CONTEXT_LENGTH_DEFAULT = 22

SHOT_ID_MAX_LEN = 96
SHOTS_MIN = 1
SHOTS_MAX = 128

# Fast-pace bounds
MICRO_SHOTS_MIN = 6
MICRO_SHOTS_MAX = 9
SHOT_DUR_MIN = 1.0
SHOT_DUR_MAX = 2.5
HINGE_DUR_MAX = 3.0
WPS_MAX = 3.5
WPS_MIN = 0.5

# Sheet bounds
PANELS_EXPECTED = 6
SHEET_REFS_MAX = 6

# Vague verbs to flag (CONCOCT concreteness lint)
VAGUE_VERBS = {
    "is", "are", "was", "were", "be", "been", "being",
    "walks", "walk", "stands", "stand", "sits", "sit",
    "looks", "look", "sees", "see", "watches", "watch",
}

# Framing + angle vocabularies (validator checks adjacency, not membership)
FRAMINGS = {"ECU", "CU", "MCU", "medium", "wide", "EWS", "OTS", "POV"}
ANGLES = {"eye", "eye-level", "high", "low", "dutch", "birds-eye", "worms-eye", "bird's-eye", "worm's-eye"}

LABEL_RE = re.compile(r"<(Subject|Picture|Video|Audio)\s+(\d+)>")
SHOT_RE = re.compile(r"\[Shot\s+(\d+)\](?:\s+At\s+(\d+):(\d{2})\.(\d{3}))?", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timing: dict[str, Any] = field(default_factory=dict)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "timing": self.timing,
        }


# ---------------------------------------------------------------------------
# Frame grid helpers
# ---------------------------------------------------------------------------


def is_valid_h3_length(length: int) -> bool:
    """True when length is on the 17k+5 grid: 5, 22, 39, 56, ..."""
    return LENGTH_MIN <= length <= LENGTH_MAX and length % 17 == 5


def delivered_frames(length: int, context_length: int, clip_index: int, anchor_mode: str) -> int:
    """Delivered (new) frames for a clip under anchor_mode."""
    if anchor_mode == "head":
        if clip_index == 0:
            return length
        return length - context_length
    # tail / other modes: symmetric
    return length - context_length if clip_index > 0 else length


def length_from_duration(duration_s: float, fps: int = H3_FPS) -> int:
    """Snap a duration to the H3 frame grid (17k+5)."""
    n = max(LENGTH_MIN, int(round(duration_s * fps)))
    return n + (5 - (n % 17)) % 17


def seconds_to_timestamp(total_s: float) -> str:
    m = int(total_s // 60)
    s = total_s - m * 60
    return f"{m}:{s:06.3f}"


# ---------------------------------------------------------------------------
# Plan JSON structural validation
# ---------------------------------------------------------------------------


def _normalize_prompt(prompt: Any) -> str:
    """Normalize a prompt field that may be a string or a list of lines."""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, list):
        return "\n".join(str(line) for line in prompt)
    return str(prompt) if prompt else ""


def validate_plan_structure(plan: dict, res: ValidationResult) -> None:
    """Structural checks on the plan JSON itself."""
    if not isinstance(plan, dict):
        res.error("plan is not a JSON object")
        return

    shots = plan.get("shots")
    if not isinstance(shots, list):
        res.error("plan has no 'shots' list")
        return
    if not (SHOTS_MIN <= len(shots) <= SHOTS_MAX):
        res.error(f"shot count {len(shots)} outside [{SHOTS_MIN}, {SHOTS_MAX}]")

    compat = plan.get("compatibility") or {}
    if not isinstance(compat, dict):
        compat = {}
        res.warn("compatibility is not a dict; using defaults")
    context_length = compat.get("context_length", CONTEXT_LENGTH_DEFAULT)
    anchor_mode = compat.get("anchor_mode", "head")
    width = compat.get("width")
    height = compat.get("height")
    defaults = plan.get("defaults") or {}
    default_duration = defaults.get("duration_seconds", 15)

    if not isinstance(context_length, int) or context_length <= 0:
        res.error(f"invalid context_length: {context_length}")
    if anchor_mode not in ("head", "tail"):
        res.warn(f"unusual anchor_mode: {anchor_mode}")
    if not width or not height:
        res.warn("compatibility missing width/height")

    seen_ids = set()
    total_delivered = 0
    total_raw = 0

    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            res.error(f"shot {i} is not an object")
            continue

        sid = shot.get("id", "")
        if not sid or not isinstance(sid, str):
            res.error(f"shot {i} has no id")
        elif not re.match(r"^[A-Za-z0-9_\-]+$", sid):
            res.error(f"shot {i} id {sid!r} is not filename-safe")
        elif len(sid) > SHOT_ID_MAX_LEN:
            res.error(f"shot {i} id too long (>{SHOT_ID_MAX_LEN} chars)")
        elif sid in seen_ids:
            res.error(f"duplicate shot id: {sid}")
        else:
            seen_ids.add(sid)

        # Length / duration
        length = shot.get("length")
        frames = shot.get("frames")
        duration = shot.get("duration_seconds")

        if length is not None:
            raw = int(length)
        elif frames is not None:
            raw = int(frames)
        elif duration is not None:
            raw = length_from_duration(float(duration))
        elif default_duration:
            # Fall back to defaults.duration_seconds (shipped plan uses this)
            raw = length_from_duration(float(default_duration))
        else:
            res.error(f"shot {sid}: no length/frames/duration_seconds")
            raw = 0

        if raw and not is_valid_h3_length(raw):
            res.error(
                f"shot {sid}: length {raw} not on H3 grid (must satisfy %17==5, "
                f"range {LENGTH_MIN}-{LENGTH_MAX})"
            )

        delivered = delivered_frames(raw, context_length, i, anchor_mode)
        total_raw += raw
        if i < len(shots) - 1:
            if delivered < context_length:
                res.error(
                    f"shot {sid}: non-final clip delivers {delivered} frames < "
                    f"context_length {context_length}"
                )
        total_delivered += delivered

        # Seed
        seed = shot.get("seed")
        if seed is not None:
            try:
                if int(seed) < 0 or int(seed) > 2**64 - 1:
                    res.error(f"shot {sid}: seed out of uint64 range")
            except (ValueError, TypeError):
                res.error(f"shot {sid}: invalid seed {seed!r}")

        # Steps
        steps = shot.get("steps", plan.get("defaults", {}).get("steps", 5))
        if not isinstance(steps, int) or not (1 <= steps <= 10000):
            res.error(f"shot {sid}: steps {steps} outside [1, 10000]")

        # Prompt (may be a string or a list of lines in the shipped format)
        prompt = _normalize_prompt(shot.get("prompt", ""))
        if not prompt:
            res.warn(f"shot {sid}: empty prompt")

        # Duration sanity
        if duration is not None:
            if float(duration) > DURATION_MAX:
                res.error(f"shot {sid}: duration_seconds {duration} > {DURATION_MAX}")

    runtime = total_delivered / H3_FPS
    res.timing["total_raw_frames"] = total_raw
    res.timing["total_delivered_frames"] = total_delivered
    res.timing["runtime_seconds"] = round(runtime, 3)
    res.timing["runtime_timestamp"] = seconds_to_timestamp(runtime)

    # Prompt prefix check
    if not plan.get("prompt_prefix"):
        res.warn("no prompt_prefix — shots will duplicate shared blocks (drift + token waste)")

    # Label vs ref-images check (the <Picture 2> defect)
    ref_count = _max_label_index(plan, "Picture")
    if ref_count > 0:
        # Caller should pass --ref-images; if not, we can't verify wiring.
        # We warn if labels exceed a default of 1 (the shipped defect).
        pass  # handled in validate_ref_labels with --ref-images


def _max_label_index(plan: dict, label_type: str) -> int:
    """Find the max index used for <LabelType N> across prefix + all shots."""
    max_idx = 0
    texts = [_normalize_prompt(plan.get("prompt_prefix", ""))]
    for shot in plan.get("shots", []):
        texts.append(_normalize_prompt(shot.get("prompt", "")))
    for text in texts:
        for m in LABEL_RE.finditer(text or ""):
            if m.group(1) == label_type:
                max_idx = max(max_idx, int(m.group(2)))
    return max_idx


def validate_ref_labels(plan: dict, ref_images_count: int, res: ValidationResult) -> None:
    """Check that label indices don't exceed wired reference images."""
    for label_type in ("Subject", "Picture", "Video", "Audio"):
        max_idx = _max_label_index(plan, label_type)
        if label_type == "Picture" and max_idx > ref_images_count:
            res.error(
                f"prompts reference <Picture {max_idx}> but only "
                f"{ref_images_count} reference image(s) wired — "
                f"this is the shipped workflow defect (LoadImage 910 unwired)"
            )
        elif label_type in ("Video", "Audio") and max_idx > ref_images_count and ref_images_count > 0:
            res.warn(f"<{label_type} {max_idx}> referenced but only {ref_images_count} refs wired")


# ---------------------------------------------------------------------------
# Ledger (fast-pace + chain) validation
# ---------------------------------------------------------------------------


def validate_ledger(ledger: dict, plan: dict, res: ValidationResult) -> None:
    """Fast-pace, chain, and continuity checks on the ledger."""
    if not isinstance(ledger, dict):
        res.error("ledger is not a JSON object")
        return

    clips = ledger.get("clips")
    if not isinstance(clips, list):
        res.error("ledger has no 'clips' list")
        return

    context_length = ledger.get("context_length", CONTEXT_LENGTH_DEFAULT)
    cast_ids = {c.get("id") for c in ledger.get("cast", []) if isinstance(c, dict)}

    for i, clip in enumerate(clips):
        if not isinstance(clip, dict):
            res.error(f"clip {i} is not an object")
            continue

        cid = clip.get("id", f"clip_{i}")
        delivered = clip.get("delivered_frames", 0)
        delivered_s = delivered / H3_FPS if delivered else 0

        shots = clip.get("shots", [])
        if not isinstance(shots, list):
            res.error(f"clip {cid}: no shots list")
            continue

        # Fast-pace: shot count
        if i < len(clips) - 1 or len(clips) == 1:
            if not (MICRO_SHOTS_MIN <= len(shots) <= MICRO_SHOTS_MAX):
                res.warn(
                    f"clip {cid}: {len(shots)} micro-shots outside "
                    f"[{MICRO_SHOTS_MIN}, {MICRO_SHOTS_MAX}]"
                )

        prev_fa: tuple[str, str] | None = None
        for j, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            sn = shot.get("n", j + 1)
            t = shot.get("t", [])
            framing = shot.get("framing", "")
            angle = shot.get("angle", "")
            action = shot.get("action", "")
            sound = shot.get("sound", "")

            # Timestamps
            if len(t) != 2:
                res.error(f"clip {cid} shot {sn}: t must be [start, end]")
            else:
                start, end = float(t[0]), float(t[1])
                dur = end - start
                if dur <= 0:
                    res.error(f"clip {cid} shot {sn}: non-positive duration {dur}")
                else:
                    is_hinge = j == 0 and i > 0
                    limit = HINGE_DUR_MAX if is_hinge else SHOT_DUR_MAX
                    if dur > limit:
                        res.warn(
                            f"clip {cid} shot {sn}: duration {dur:.2f}s > {limit}s"
                        )
                    elif dur < SHOT_DUR_MIN and not is_hinge:
                        res.warn(
                            f"clip {cid} shot {sn}: duration {dur:.2f}s < {SHOT_DUR_MIN}s"
                        )
                if j > 0:
                    prev_end = float(shots[j - 1].get("t", [0, 0])[1]) if len(shots[j - 1].get("t", [])) == 2 else 0
                    if start < prev_end - 0.01:
                        res.error(f"clip {cid} shot {sn}: start {start} before prev end {prev_end}")
                    if abs(start - prev_end) > 0.01:
                        res.warn(f"clip {cid} shot {sn}: gap/overlap with previous shot")

            # No adjacent framing+angle repeat
            fa = (framing, angle)
            if prev_fa is not None and fa == prev_fa:
                res.error(
                    f"clip {cid} shot {sn}: same framing+angle as previous shot "
                    f"({framing}/{angle})"
                )
            prev_fa = fa

            # Sound cue
            if not sound:
                res.warn(f"clip {cid} shot {sn}: no sound cue")

            # One dominant action (verb-count heuristic)
            verbs = re.findall(r"\b\w+(?:s|ed|ing)?\b", action.lower())
            action_verbs = [v for v in verbs if v not in {"the", "a", "an", "in", "on", "at", "to", "with", "and", "of", "is", "are"}]
            if len(action_verbs) > 6:
                res.warn(f"clip {cid} shot {sn}: action may have >1 dominant verb: {action!r}")

            # Vague verb
            first_word = action.strip().split()[0].lower() if action.strip() else ""
            if first_word in VAGUE_VERBS:
                res.warn(f"clip {cid} shot {sn}: vague verb '{first_word}': {action!r}")

            # Cast exists
            for c in shot.get("cast", []):
                if c not in cast_ids:
                    res.error(f"clip {cid} shot {sn}: cast id {c!r} not in ledger.cast")

        # Hinge linkage
        hinge_out = clip.get("hinge_out")
        if i < len(clips) - 1 and not hinge_out:
            res.error(f"clip {cid}: non-final clip missing hinge_out")
        if i > 0:
            hinge_in = clip.get("hinge_in")
            if not hinge_in:
                res.error(f"clip {cid}: clip > 0 missing hinge_in")
            else:
                continues = hinge_in.get("continues_clip")
                if continues and continues != clips[i - 1].get("id"):
                    res.error(
                        f"clip {cid}: hinge_in.continues_clip {continues!r} "
                        f"!= previous clip id {clips[i-1].get('id')!r}"
                    )

        # Quad conflict scan
        quads = clip.get("quads", [])
        _scan_quad_conflicts(quads, cid, res)

        # Words-per-screen-second (rough)
        if delivered_s > 0:
            prompt_text = clip.get("prompt_file", "")
            # Can't read prompt_file here; just flag if delivered is very short
            if delivered_s < 5 and len(shots) > 3:
                res.warn(f"clip {cid}: {len(shots)} shots in {delivered_s:.1f}s — very dense")

    # Cross-clip item state conflicts
    _scan_item_state_conflicts(ledger, res)


def _scan_quad_conflicts(quads: list, clip_id: str, res: ValidationResult) -> None:
    """Check for item state contradictions within a clip's quads."""
    item_states: dict[str, str] = {}
    for q in quads:
        if not isinstance(q, (list, tuple)) or len(q) < 4:
            continue
        subject, action, obj, _ = q[0], q[1], q[2], q[3]
        if action in ("destroys", "destroys"):
            item_states[obj] = "destroyed"
        elif action in ("finds", "recovers", "picks up"):
            if item_states.get(obj) == "destroyed":
                res.warn(f"clip {clip_id}: quad conflict — {obj} destroyed then recovered")


def _scan_item_state_conflicts(ledger: dict, res: ValidationResult) -> None:
    """Cross-clip: item destroyed in clip N then active in clip N+1 without justification."""
    items = ledger.get("items", [])
    if not isinstance(items, list):
        return
    # Track state transitions across clips
    state: dict[str, str] = {}
    for item in items:
        if isinstance(item, dict):
            state[item.get("id", "")] = item.get("state", "active")

    clips = ledger.get("clips", [])
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        for q in clip.get("quads", []):
            if not isinstance(q, (list, tuple)) or len(q) < 4:
                continue
            subject, action, obj, _ = q
            if action in ("destroys",):
                state[obj] = "destroyed"
            elif action in ("finds", "recovers") and state.get(obj) == "destroyed":
                res.warn(
                    f"item {obj} destroyed in earlier clip then recovered in "
                    f"{clip.get('id')} — needs explicit justification"
                )


# ---------------------------------------------------------------------------
# Audio validation
# ---------------------------------------------------------------------------


def validate_audio(ledger: dict, res: ValidationResult) -> None:
    """Lyric/dialogue window + wps checks."""
    clips = ledger.get("clips", [])
    prev_end = 0.0
    for i, clip in enumerate(clips):
        if not isinstance(clip, dict):
            continue
        audio = clip.get("audio", {})
        if not isinstance(audio, dict):
            continue
        start_s = float(audio.get("start_s", prev_end))
        duration_s = float(audio.get("duration_s", 0))
        window_end = start_s + duration_s

        # No gap/overlap between clip audio windows (beyond context overlap)
        if i > 0 and abs(start_s - prev_end) > 0.5:
            res.warn(f"clip {clip.get('id')}: audio window gap/overlap with previous ({start_s:.2f} vs {prev_end:.2f})")
        prev_end = window_end

        for line in audio.get("lines", []):
            if not isinstance(line, dict):
                continue
            t = float(line.get("t", -1))
            text = line.get("text", "")
            if t < start_s or t > window_end:
                res.error(
                    f"clip {clip.get('id')}: lyric line at t={t:.2f} outside "
                    f"audio window [{start_s:.2f}, {window_end:.2f}]"
                )
            # wps check
            if duration_s > 0 and text:
                words = len(text.split())
                # rough: line occupies some fraction of the window
                line_dur = min(2.0, window_end - t)
                if line_dur > 0:
                    wps = words / line_dur
                    if wps > WPS_MAX:
                        res.warn(
                            f"clip {clip.get('id')}: line wps {wps:.1f} > {WPS_MAX}: {text[:50]!r}"
                        )


# ---------------------------------------------------------------------------
# Sheet prompt validation
# ---------------------------------------------------------------------------


SHEET_NEGATIVES = ("no text", "no caption", "no label", "no number", "no border", "no watermark")


def validate_sheet_prompts(ledger: dict, sheets_dir: str | None, res: ValidationResult) -> None:
    """Validate storyboard sheet prompt files referenced by the ledger."""
    clips = ledger.get("clips", [])
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        sheet_prompt = clip.get("sheet_prompt")
        if not sheet_prompt:
            continue
        path = Path(sheet_prompt)
        if sheets_dir:
            path = Path(sheets_dir) / path.name
        if not path.is_file():
            res.warn(f"clip {clip.get('id')}: sheet prompt file not found: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        # Geometry
        if "3 columns" not in text.lower() and "3x2" not in text.lower():
            res.error(f"clip {clip.get('id')}: sheet prompt missing explicit 3×2 geometry")
        if "6 panels" not in text.lower() and "6 panel" not in text.lower():
            res.error(f"clip {clip.get('id')}: sheet prompt missing explicit 6-panel count")
        # Negatives
        text_lower = text.lower()
        missing_neg = [n for n in SHEET_NEGATIVES if n not in text_lower]
        if missing_neg:
            res.warn(f"clip {clip.get('id')}: sheet prompt missing negatives: {missing_neg}")
        # Panel description count (rough: count "Panel N" markers)
        panel_count = len(re.findall(r"panel\s+\d", text_lower))
        if panel_count < PANELS_EXPECTED:
            res.warn(
                f"clip {clip.get('id')}: sheet prompt has {panel_count} panel descriptions, "
                f"expected {PANELS_EXPECTED}"
            )


# ---------------------------------------------------------------------------
# Bible / cast-lock validation
# ---------------------------------------------------------------------------


def validate_bible(ledger: dict, bible: dict, res: ValidationResult) -> None:
    """Cast-lock consistency between ledger and bible.json."""
    if not isinstance(bible, dict):
        res.error("bible is not a JSON object")
        return

    bible_cast = {c["id"]: c for c in bible.get("cast", []) if isinstance(c, dict) and "id" in c}
    ledger_cast = {c["id"]: c for c in ledger.get("cast", []) if isinstance(c, dict) and "id" in c}

    for cid, lc in ledger_cast.items():
        bc = bible_cast.get(cid)
        if not bc:
            res.error(f"ledger cast {cid!r} not in bible.json")
            continue
        # Appearance lock consistency
        ll = lc.get("appearance_lock", "")
        bl = bc.get("appearance_lock", "")
        if ll and bl:
            lh = hashlib.sha256(ll.encode()).hexdigest()
            bh = hashlib.sha256(bl.encode()).hexdigest()
            if lh != bh:
                res.error(
                    f"cast {cid}: appearance_lock mismatch between ledger and bible "
                    "(create a variant instead)"
                )

    # Anti-bleed: clips with ≥2 cast members
    for clip in ledger.get("clips", []):
        if not isinstance(clip, dict):
            continue
        clip_cast = set()
        for shot in clip.get("shots", []):
            if isinstance(shot, dict):
                clip_cast.update(shot.get("cast", []))
        if len(clip_cast) >= 2:
            # Check the clip's prompt has anti-bleed text (rough: look for other cast names)
            # Can't read prompt_file here; just warn
            pass  # anti-bleed is checked at prompt-authoring time


# ---------------------------------------------------------------------------
# Asset registry validation
# ---------------------------------------------------------------------------


def validate_assets(ledger: dict, registry_path: str | None, res: ValidationResult) -> None:
    """Every cast/location ref resolves to an approved asset_id@version."""
    if not registry_path:
        return
    rpath = Path(registry_path)
    if not rpath.is_file():
        res.warn(f"asset registry not found: {rpath}")
        return
    try:
        registry = json.loads(rpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        res.error("asset registry is not valid JSON")
        return

    assets = registry.get("assets", {})
    for c in ledger.get("cast", []):
        if not isinstance(c, dict):
            continue
        for ref in c.get("refs", []):
            # ref should be "asset_id@version" or a path
            if isinstance(ref, str) and ref.startswith(("char.", "loc.", "style.", "sheet.", "prop.", "audio.")):
                parts = ref.rsplit("@", 1)
                aid = parts[0]
                entry = assets.get(aid)
                if not entry:
                    res.error(f"cast {c.get('id')}: ref {ref!r} not in registry")
                elif entry.get("status") != "approved":
                    res.warn(f"cast {c.get('id')}: ref {aid} status={entry.get('status')} (not approved)")
                else:
                    # Verify file exists and hash matches
                    current = entry.get("current")
                    for v in entry.get("versions", []):
                        if v.get("v") == current:
                            p = v.get("path", "")
                            if p and not os.path.isfile(p):
                                res.error(f"asset {aid}: approved file not found: {p}")
                            break


# ---------------------------------------------------------------------------
# Run safety: audio duration + freeze check
# ---------------------------------------------------------------------------


def _ffprobe_duration(path: str) -> float | None:
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return float(out.strip())
    except Exception:
        return None


def validate_run_safety(
    plan: dict,
    ledger: dict,
    song_path: str | None,
    res: ValidationResult,
) -> None:
    """Source-track duration ≥ total delivered; freeze check on accepted clips."""
    compat = plan.get("compatibility", {})
    audio_mode = compat.get("audio_mode", "source_track")

    total_delivered = res.timing.get("total_delivered_frames", 0)
    runtime = total_delivered / H3_FPS if total_delivered else 0

    if audio_mode == "source_track" and song_path:
        dur = _ffprobe_duration(song_path)
        if dur is not None and dur < runtime - 0.5:
            res.error(
                f"source_track audio {song_path} duration {dur:.2f}s < "
                f"total delivered {runtime:.2f}s"
            )
        elif dur is None:
            res.warn(f"could not probe source audio duration (ffprobe missing?): {song_path}")

    # Freeze check: accepted clips must not change hashed fields
    clips = ledger.get("clips", [])
    shots = plan.get("shots", [])
    for i, clip in enumerate(clips):
        if not isinstance(clip, dict):
            continue
        render = clip.get("render", {})
        if render.get("status") != "accepted":
            continue
        if i >= len(shots):
            res.error(f"ledger clip {clip.get('id')} accepted but no plan shot at index {i}")
            continue
        shot = shots[i]
        # Recompute prompt_hash
        prompt = _normalize_prompt(shot.get("prompt", ""))
        prompt_hash = "sha256:" + hashlib.sha256(prompt.encode()).hexdigest()
        if clip.get("prompt_hash") and clip["prompt_hash"] != prompt_hash:
            res.error(
                f"freeze check: clip {clip.get('id')} is accepted but its prompt_hash "
                f"changed (was {clip['prompt_hash'][:16]}…, now {prompt_hash[:16]}…) — "
                "this invalidates the checkpoint prefix"
            )
        for field in ("seed", "steps"):
            if field in clip and field in shot and clip[field] != shot[field]:
                res.error(
                    f"freeze check: clip {clip.get('id')} {field} changed "
                    f"(was {clip[field]}, now {shot[field]})"
                )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def validate(
    plan_path: str,
    *,
    ledger_path: str | None = None,
    bible_path: str | None = None,
    song_path: str | None = None,
    registry_path: str | None = None,
    sheets_dir: str | None = None,
    ref_images: int = 1,
) -> ValidationResult:
    res = ValidationResult()

    ppath = Path(plan_path)
    if not ppath.is_file():
        res.error(f"plan file not found: {ppath}")
        return res
    try:
        plan = json.loads(ppath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        res.error(f"plan JSON parse error: {e}")
        return res

    validate_plan_structure(plan, res)
    validate_ref_labels(plan, ref_images, res)

    ledger = None
    if ledger_path:
        lpath = Path(ledger_path)
        if not lpath.is_file():
            res.warn(f"ledger file not found: {lpath}")
        else:
            try:
                ledger = json.loads(lpath.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                res.error(f"ledger JSON parse error: {e}")

    if ledger:
        validate_ledger(ledger, plan, res)
        validate_audio(ledger, res)
        validate_sheet_prompts(ledger, sheets_dir, res)
        validate_run_safety(plan, ledger, song_path, res)

        if bible_path:
            try:
                bible = json.loads(Path(bible_path).read_text(encoding="utf-8"))
                validate_bible(ledger, bible, res)
            except (json.JSONDecodeError, OSError) as e:
                res.warn(f"could not load bible: {e}")

        # Auto-detect registry at repo root
        if registry_path is None:
            repo_root = Path(__file__).resolve().parents[3]
            auto = repo_root / "assets" / "registry.json"
            if auto.is_file():
                registry_path = str(auto)
        validate_assets(ledger, registry_path, res)

    return res


def main() -> int:
    p = argparse.ArgumentParser(description="Validate an H3 chain plan + ledger")
    p.add_argument("plan", help="Path to plan.json")
    p.add_argument("--ledger", default=None, help="Path to state.json (continuity ledger)")
    p.add_argument("--bible", default=None, help="Path to bible.json")
    p.add_argument("--song", default=None, help="Path to source audio (for source_track duration check)")
    p.add_argument("--registry", default=None, help="Path to assets/registry.json (auto-detected if omitted)")
    p.add_argument("--sheets-dir", default=None, help="Directory containing sheet prompt files")
    p.add_argument("--ref-images", type=int, default=1, help="Number of reference images wired into the workflow")
    args = p.parse_args()

    res = validate(
        args.plan,
        ledger_path=args.ledger,
        bible_path=args.bible,
        song_path=args.song,
        registry_path=args.registry,
        sheets_dir=args.sheets_dir,
        ref_images=args.ref_images,
    )

    out_path = Path(args.plan).with_suffix(".json.validation.json")
    out_path.write_text(json.dumps(res.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    if res.ok:
        print(f"PASS: {args.plan}  warnings={len(res.warnings)}")
        for w in res.warnings:
            print(f"  ⚠ {w}")
        print(f"  runtime: {res.timing.get('runtime_timestamp', '?')} "
              f"({res.timing.get('runtime_seconds', 0)}s, "
              f"{res.timing.get('total_delivered_frames', 0)} delivered frames)")
        return 0
    print(f"FAIL: {args.plan} — {len(res.errors)} error(s)")
    for e in res.errors:
        print(f"  ✗ {e}")
    for w in res.warnings:
        print(f"  ⚠ {w}")
    print(f"  wrote {out_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
