"""Duration budget math for story-maker-v3.

Pure, deterministic, no I/O. The Agent 3 validator calls these to enforce that
row/scene/clip durations sum correctly against the target.

Locked budget (see plan):
  - panel_duration: 2-5s per panel (sub-clip within a batch).
  - row_total  = sum of panel durations in a row (max 20s = one LTX session).
  - scene_total = sum of row totals (~40-54s for 3 rows).
  - scene_count = ceil(target_seconds / scene_budget), scene_budget default 70s.
"""

from __future__ import annotations

import math

CLIP_MIN = 9
CLIP_MAX_CLASSIC = 15
CLIP_MAX_BEATS = 20
CLIP_DEFAULT = 10
BATCH_MAX = 20  # batch unit max 20s to avoid VRAM overflow on LTX Director
PANEL_MIN = 2   # storyboard panel durations can be as short as 2s (sub-clips within a batch)
PANEL_MAX = 20
ROW_MAX = 20    # row total (one LTX session) must be <= 20s to avoid VRAM overflow
ROW_PANELS = 3          # one LTX session = 3 chained panels
SCENE_ROWS = 3          # 3 LTX sessions per scene
SCENE_COLS = 3          # visual columns on the album sheet (3 rows x 3 cols)
SCENE_PANELS = ROW_PANELS * SCENE_ROWS   # 9
SCENE_BUDGET_DEFAULT = 70   # seconds; scene_count = ceil(target / scene_budget)

# ---------------------------------------------------------------------------
# Director-set timing constants (Stage C0 — director_sets_sN.json)
# ---------------------------------------------------------------------------
# A "set" = 3 panels shown in sequence (one row of the storyboard).
# Beat sequence: pre_roll → hold → gap → hold → gap → hold
PRE_ROLL_MAX = 2            # seconds of pre-roll before first panel (0-2)
HOLD_MIN = 3                # minimum seconds a panel is held on screen
HOLD_MAX = 5                # maximum seconds a panel is held on screen
GAP_CUT = 0                 # hard cut / smash cut = 0s gap
GAP_MAX = 2                 # maximum gap for non-continuation transitions
GAP_CONTINUATION_MAX = 2    # maximum gap for continuation transitions
SET_MAX = 20                # one set must be <= 20s (LTX batch limit)


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