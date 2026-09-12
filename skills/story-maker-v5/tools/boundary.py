"""Generation boundary policy for story-maker-v5.

Single source of truth for whether a generation is conditioned on the
previous generation's rendered tail (``ref_videos``) or opens fresh.

Rules:
  * The first generation of the episode never gets a tail ref.
  * Within a scene, generation ``gK`` (K > 1) is a *fresh cut* iff its first
    shot declares ``transition: hard_cut``. Otherwise it is a continuation
    and receives the previous generation's rendered tail.
  * For the first generation of scene N > 1, the scene boundary is decided
    by the previous scene's ``handoff.transition`` — ``hard_cut`` means a
    fresh cut (no tail); anything else (or a missing handoff) means the
    tail is attached. The next scene's own g1 shot-1 ``transition`` is a
    secondary signal: ``hard_cut`` there also marks a fresh cut, and a
    ``hard_cut`` handoff paired with a ``continuous`` shot 1 is a
    contradiction flagged by the storyboard validator.

Used by ``scripts/render_all.py`` (render-time attachment) and
``tools/validators.py`` (the ``<Video 1>`` declaration contract). No I/O —
all functions take already-parsed data.
"""

from __future__ import annotations

from typing import Any

FRESH_CUT = "fresh_cut"
CONTINUATION = "continuation"
FIRST = "first"


def _first_shot_transition(gen: dict[str, Any]) -> str:
    shots = gen.get("shots") or []
    if not shots:
        return ""
    return (shots[0].get("transition") or "").strip().lower()


def gen_boundary(sb: dict[str, Any], gen_id: str) -> str:
    """Boundary type for a generation within its scene's storyboard.

    Returns FIRST for the scene's first non-bridge generation (the caller
    must still apply the scene-boundary rule for scenes after the first),
    FRESH_CUT when the generation's first shot declares ``hard_cut``,
    CONTINUATION otherwise.
    """
    gens = [g for g in sb.get("generations", []) if not g.get("is_bridge")]
    idx = next((i for i, g in enumerate(gens) if g.get("gen_id") == gen_id), None)
    if idx is None or idx == 0:
        return FIRST
    return FRESH_CUT if _first_shot_transition(gens[idx]) == "hard_cut" else CONTINUATION


def scene_boundary(prev_storyboard: dict[str, Any] | None, next_storyboard: dict[str, Any] | None) -> str:
    """Boundary type between two scenes.

    Fresh cut iff the previous scene's handoff declares ``hard_cut`` or the
    next scene's g1 shot 1 declares ``hard_cut``. Any other combination is a
    continuation. With no data, default to CONTINUATION (current renderer
    behaviour).
    """
    handoff = ((prev_storyboard or {}).get("handoff") or {}).get("transition", "")
    if str(handoff).strip().lower() == "hard_cut":
        return FRESH_CUT
    if next_storyboard:
        gens = [g for g in next_storyboard.get("generations", []) if not g.get("is_bridge")]
        if gens and _first_shot_transition(gens[0]) == "hard_cut":
            return FRESH_CUT
    return CONTINUATION


def needs_tail_ref(
    scene_ids: list[str],
    scene_id: str,
    sb: dict[str, Any],
    gen_id: str,
    prev_storyboard: dict[str, Any] | None = None,
) -> bool:
    """True when the renderer should attach the previous generation's tail.

    Args:
        scene_ids: Scene ids in render order (scenes.md order).
        scene_id: The scene containing ``gen_id``.
        sb: Parsed storyboard for ``scene_id``.
        gen_id: The generation being rendered.
        prev_storyboard: Parsed storyboard of the previous scene (needed
            only when ``gen_id`` is the scene's first generation).
    """
    boundary = gen_boundary(sb, gen_id)
    if boundary in (FRESH_CUT,):
        return False
    if boundary == CONTINUATION:
        return True
    # FIRST generation of the scene — apply the scene-boundary rule.
    if scene_id == scene_ids[0]:
        return False
    return scene_boundary(prev_storyboard, sb) != FRESH_CUT


def boundary_consistency_errors(
    sb: dict[str, Any],
    next_storyboard: dict[str, Any] | None,
) -> tuple[list[str], list[str]]:
    """Check handoff vs next-scene g1 shot-1 transition for contradictions.

    Returns (errors, warnings). A ``hard_cut`` handoff paired with a
    ``continuous`` next-shot-1 (or vice versa) is an error; other mismatches
    are warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    handoff = ((sb or {}).get("handoff") or {}).get("transition", "")
    handoff = str(handoff).strip().lower()
    if not next_storyboard or not handoff:
        return errors, warnings
    next_gens = [g for g in next_storyboard.get("generations", []) if not g.get("is_bridge")]
    if not next_gens:
        return errors, warnings
    next_t = _first_shot_transition(next_gens[0])
    sid = sb.get("scene_id") or "?"
    nid = next_storyboard.get("scene_id") or "?"
    handoff_is_cut = handoff == "hard_cut"
    shot_is_cut = next_t == "hard_cut"
    shot_is_cont = next_t == "continuous"
    if handoff_is_cut and shot_is_cont:
        errors.append(
            f"scene {sid}: handoff.transition is hard_cut but scene {nid} "
            f"g1 shot 1 is 'continuous' — the boundary cannot be both a "
            f"deliberate cut and an unbroken take; fix one"
        )
    elif not handoff_is_cut and shot_is_cut:
        errors.append(
            f"scene {sid}: handoff.transition is '{handoff}' (continuation) "
            f"but scene {nid} g1 shot 1 is 'hard_cut' — the boundary cannot "
            f"be both; fix one"
        )
    elif handoff_is_cut and next_t not in ("", "hard_cut"):
        warnings.append(
            f"scene {sid}: handoff.transition is hard_cut but scene {nid} "
            f"g1 shot 1 uses '{next_t}' — the boundary renders as a fresh "
            f"cut (no tail ref); consider 'hard_cut' on the shot for clarity"
        )
    return errors, warnings
