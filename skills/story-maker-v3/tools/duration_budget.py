"""Duration budget math for story-maker-v3.

Pure, deterministic, no I/O. The Agent 3 validator calls these to enforce that
row/scene/clip durations sum correctly against the target.

Locked budget (see plan):
  - clip_duration: 9-15s classic (default 10); 16-20s only for a genuine beats[] arc.
  - row_total  = sum of clip durations in a row (~30-40s for 4 clips).
  - scene_total = sum of row totals (~60-80s for 2 rows).
  - scene_count = ceil(target_seconds / scene_budget), scene_budget default 70s.
"""

from __future__ import annotations

import math

CLIP_MIN = 9
CLIP_MAX_CLASSIC = 15
CLIP_MAX_BEATS = 20
CLIP_DEFAULT = 10
ROW_PANELS = 4          # one LTX session = 4 chained panels
SCENE_ROWS = 2          # 2 LTX sessions per scene
SCENE_COLS = 2          # visual columns on the album sheet (4 rows x 2 cols)
SCENE_PANELS = ROW_PANELS * SCENE_ROWS   # 8
SCENE_BUDGET_DEFAULT = 70   # seconds; scene_count = ceil(target / scene_budget)


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


def snap_clip_duration(seconds: int | float, *, allow_beats: bool = False) -> int:
    """Snap a clip duration to the allowed integer band.

    Classic Prompt-Relay clips are clamped to [9, 15]. When ``allow_beats`` is
    true (Agent 5 flagged a genuine beats[] arc) the band extends to [9, 20].
    Below-min durations are bumped to the minimum; over-max are clamped to max.
    """
    n = int(round(seconds))
    hi = CLIP_MAX_BEATS if allow_beats else CLIP_MAX_CLASSIC
    if n < CLIP_MIN:
        return CLIP_MIN
    if n > hi:
        return hi
    return n


def scene_count_for_target(target_seconds: int, scene_budget: int = SCENE_BUDGET_DEFAULT) -> int:
    """Number of scenes to fill ``target_seconds`` at ``scene_budget`` each."""
    if scene_budget <= 0:
        raise ValueError("scene_budget must be > 0")
    return max(1, math.ceil(target_seconds / scene_budget))


def row_total(clip_durations: list[int]) -> int:
    """Sum of clip durations in one row (one LTX session)."""
    return sum(int(d) for d in clip_durations)


def scene_total(row_totals: list[int]) -> int:
    """Sum of row totals in one scene (two LTX sessions)."""
    return sum(int(d) for d in row_totals)


def within_tolerance(actual: int, target: int, tolerance_percent: int = 15) -> bool:
    """True when ``actual`` is within ``tolerance_percent``% of ``target``."""
    if target <= 0:
        return actual == 0
    slack = target * tolerance_percent / 100.0
    return abs(actual - target) <= slack