"""LTX render parameter lookups for assistant-director clips.

Maps constrained AD enums → concrete ComfyUI floats (image lock strength, CFG).
"""

from __future__ import annotations

from typing import Literal

MotionClass = Literal[
    "talking",
    "walking",
    "horse_riding",
    "forest_exploration",
    "large_reveal",
    "fast_action",
    "general",
]

Guidance = Literal["balanced", "prompt_follow", "strong"]

MOTION_CLASSES: tuple[str, ...] = (
    "talking",
    "walking",
    "horse_riding",
    "forest_exploration",
    "large_reveal",
    "fast_action",
    "general",
)

GUIDANCE_LEVELS: tuple[str, ...] = ("balanced", "prompt_follow", "strong")

# LTXVImgToVideoInplace strength (low-res image lock vs motion freedom)
I2V_STRENGTH_BY_MOTION_CLASS: dict[str, float] = {
    "talking": 0.80,
    "walking": 0.70,
    "horse_riding": 0.65,
    "forest_exploration": 0.70,
    "large_reveal": 0.60,
    "fast_action": 0.55,
    "general": 0.70,
}

CFG_BY_GUIDANCE: dict[str, float] = {
    "balanced": 1.0,
    "prompt_follow": 1.2,
    "strong": 1.5,
}

DEFAULT_MOTION_CLASS: MotionClass = "general"
DEFAULT_GUIDANCE: Guidance = "balanced"
DEFAULT_I2V_STRENGTH = I2V_STRENGTH_BY_MOTION_CLASS[DEFAULT_MOTION_CLASS]
DEFAULT_CFG = CFG_BY_GUIDANCE[DEFAULT_GUIDANCE]
DEFAULT_LAST_FRAME_STRENGTH = 0.85

# Aliases the AD / older plans may emit
_MOTION_ALIASES: dict[str, str] = {
    "talking": "talking",
    "dialogue": "talking",
    "emotional": "talking",
    "emotion": "talking",
    "walking": "walking",
    "walk": "walking",
    "horse_riding": "horse_riding",
    "horse-riding": "horse_riding",
    "horse riding": "horse_riding",
    "riding": "horse_riding",
    "forest_exploration": "forest_exploration",
    "forest-exploration": "forest_exploration",
    "forest exploration": "forest_exploration",
    "exploration": "forest_exploration",
    "large_reveal": "large_reveal",
    "large-reveal": "large_reveal",
    "large reveal": "large_reveal",
    "reveal": "large_reveal",
    "fast_action": "fast_action",
    "fast-action": "fast_action",
    "fast action": "fast_action",
    "action": "fast_action",
    "general": "general",
    "default": "general",
}

_GUIDANCE_ALIASES: dict[str, str] = {
    "balanced": "balanced",
    "default": "balanced",
    "natural": "balanced",
    "prompt_follow": "prompt_follow",
    "prompt-follow": "prompt_follow",
    "prompt follow": "prompt_follow",
    "follow": "prompt_follow",
    "strong": "strong",
    "high": "strong",
}


def normalize_motion_class(raw: str | None) -> str:
    key = str(raw or "").strip().lower().replace("_", " ").replace("-", " ")
    compact = key.replace(" ", "_")
    if compact in I2V_STRENGTH_BY_MOTION_CLASS:
        return compact
    spaced = " ".join(key.split())
    if spaced in _MOTION_ALIASES:
        return _MOTION_ALIASES[spaced]
    if compact in _MOTION_ALIASES:
        return _MOTION_ALIASES[compact]
    return DEFAULT_MOTION_CLASS


def normalize_guidance(raw: str | None) -> str:
    key = str(raw or "").strip().lower().replace("_", " ").replace("-", " ")
    compact = key.replace(" ", "_")
    if compact in CFG_BY_GUIDANCE:
        return compact
    spaced = " ".join(key.split())
    if spaced in _GUIDANCE_ALIASES:
        return _GUIDANCE_ALIASES[spaced]
    if compact in _GUIDANCE_ALIASES:
        return _GUIDANCE_ALIASES[compact]
    return DEFAULT_GUIDANCE


def resolve_i2v_strength(motion_class: str | None, override: float | None = None) -> float:
    if override is not None:
        return max(0.4, min(0.95, float(override)))
    return I2V_STRENGTH_BY_MOTION_CLASS[normalize_motion_class(motion_class)]


def resolve_cfg(guidance: str | None, override: float | None = None) -> float:
    if override is not None:
        return max(1.0, min(1.5, float(override)))
    return CFG_BY_GUIDANCE[normalize_guidance(guidance)]


def resolve_last_frame_strength(
    i2v_strength: float,
    *,
    override: float | None = None,
    floor: float = DEFAULT_LAST_FRAME_STRENGTH,
) -> float:
    """Keep FLF endpoint lock at least as strong as a raised first-frame lock."""
    if override is not None:
        return max(0.5, min(1.0, float(override)))
    return max(float(floor), float(i2v_strength) + 0.05)


def resolve_clip_render_params(
    clip: dict | None = None,
    *,
    prefer_stored: bool = True,
) -> dict:
    """Resolve AD enums (or stored floats) into render knobs.

    prefer_stored=True (render): reuse clip.i2v_strength / cfg when present.
    prefer_stored=False (normalize): always recompute from motion_class / guidance.
    """
    clip = clip or {}
    motion_class = normalize_motion_class(clip.get("motion_class"))
    guidance = normalize_guidance(clip.get("guidance"))
    strength_override = (
        float(clip["i2v_strength"])
        if prefer_stored and clip.get("i2v_strength") is not None
        else None
    )
    cfg_override = (
        float(clip["cfg"]) if prefer_stored and clip.get("cfg") is not None else None
    )
    lf_override = (
        float(clip["last_frame_strength"])
        if prefer_stored and clip.get("last_frame_strength") is not None
        else None
    )
    i2v_strength = resolve_i2v_strength(motion_class, override=strength_override)
    cfg = resolve_cfg(guidance, override=cfg_override)
    last_frame_strength = resolve_last_frame_strength(
        i2v_strength, override=lf_override
    )
    return {
        "motion_class": motion_class,
        "guidance": guidance,
        "i2v_strength": i2v_strength,
        "cfg": cfg,
        "last_frame_strength": last_frame_strength,
    }
