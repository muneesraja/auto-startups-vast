"""Duration budget math for story-maker-v3 (Minimax H3 backend).

Pure, deterministic, no I/O. The Agent 3 validator calls these to enforce that
generation/scene durations sum correctly against the target.

Locked budget:
  - generation: one Minimax H3 render from one storyboard sheet reference.
    Duration 5-15s (model hard limit is 15s per generation).
  - Shots NEVER straddle a generation boundary: a shot that does not fit in the
    remaining seconds of the current generation moves to the next one.
  - scene_total = sum of generation durations = scene target_seconds.
  - scene_count = ceil(target_seconds / scene_budget), scene_budget default 70s.
  - Continuity between adjacent generations is handled at render time by
    conditioning each generation on the previous generation's rendered tail
    (3s). No bridge generations are needed.
"""

from __future__ import annotations

import math

# Minimax H3 generation limits (seconds).
GEN_MIN = 5.0
GEN_MAX = 15.0
MINIMAX_FPS = 24

# Storyboard sheet grid limits (panels per generation sheet).
PANELS_MIN = 6   # minimum grid: 2x3, 3x2, or larger
PANELS_MAX = 12

SCENE_BUDGET_DEFAULT = 70   # seconds; scene_count = ceil(target / scene_budget)

# Float comparison slop for authored timecodes.
TIME_EPS = 0.05


def parse_target_duration(value: str | int | float) -> int:
    """Parse a target duration into integer seconds.

    Accepts ``"5m"``, ``"5min"``, ``"300"``, ``300``. Fractions of a second are
    rounded to the nearest whole second.
    """
    if isinstance(value, (int, float)):
        return max(1, int(round(value)))
    text = str(value).strip().lower()
    if not text:
        raise ValueError("empty target duration")
    mult = 1
    for suffix, m in (("min", 60), ("m", 60), ("s", 1)):
        if text.endswith(suffix):
            mult = m
            text = text[: -len(suffix)]
            break
    try:
        return max(1, int(round(float(text) * mult)))
    except ValueError as e:
        raise ValueError(f"unparseable target duration: {value!r}") from e


def scene_count_for_target(target_seconds: int, scene_budget: int = SCENE_BUDGET_DEFAULT) -> int:
    """Number of scenes to fill ``target_seconds`` at ``scene_budget`` each."""
    if scene_budget <= 0:
        raise ValueError("scene_budget must be > 0")
    return max(1, math.ceil(target_seconds / scene_budget))


def generation_count_for_scene(target_seconds: float) -> int:
    """Minimum number of Minimax generations needed to cover a scene."""
    if target_seconds <= 0:
        return 0
    return max(1, math.ceil(target_seconds / GEN_MAX))


def minimax_frames(seconds: float, fps: int = MINIMAX_FPS) -> int:
    """Snap a duration to Minimax H3's frame grid.

    Mirrors the workflow's math node: ``max(5, round(s*fps))`` then bump up to
    the next count where ``frames % 17 == 5`` (Minimax temporal latent chunks).
    """
    n = max(5, int(round(seconds * fps)))
    return n + (5 - (n % 17)) % 17


def within_tolerance(actual: float, target: float, tolerance_percent: int = 15) -> bool:
    """True when ``actual`` is within ``tolerance_percent``% of ``target``."""
    if target <= 0:
        return actual == 0
    slack = target * tolerance_percent / 100.0
    return abs(actual - target) <= slack
