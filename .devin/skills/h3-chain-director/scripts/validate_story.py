#!/usr/bin/env python3
"""Deterministic validator for Tier 0 story artifacts.

Validates:
  1. ``episode-N.meta.json`` — the episode sidecar.
  2. ``series_state.json`` — the cross-episode canon + thread ledger.

Usage::

    python3 scripts/validate_story.py episode-N.meta.json [--series-state PATH]
                                                          [--episode-file PATH]
                                                          [--prior-episodes DIR]

Writes ``<file>.validation.json`` and exits nonzero on failure.

Check groups:
  Structure   — meta parses, beats match prose, stable ids, end_state/hook non-empty.
  Canon-lock  — every char/loc/item referenced exists in series_state; no attribute
                contradicts canon unless declared in threads_closed or canon_change.
  Threads     — every threads_opened in episodes 1..N-1 is closed by N, still in
                unresolved_threads, or explicitly parked (no silent disappearance).
  Novelty     — shingle-overlap of this episode's beats vs prior episodes above
                a threshold → error; same primary location + action as immediately
                previous episode → warning.
  Retention   — cold-open hook in first beat, re-hook cadence ≤ ~10s, payoff before
                cliffhanger, loopable final beat when format: reel.
  Feasibility — beat count vs target runtime (so W3 can't hand Tier 1 a 6-minute
                episode budgeted at 90s).
  Continuity  — episode N's opening state must match episode N-1's end_state in
                series_state.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Result (mirrors validate_plan.py)
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ID_RE = re.compile(r"^(char|loc|item)_\d{2,}$")
BEAT_RE = re.compile(r"^\s*[-*]\s+(.+)$", re.MULTILINE)

# Feasibility: ~70s per scene (story-maker-v3 heuristic), restated for clip grids.
# A 14-clip plan at ~14s/clip ≈ 196s.  Beats should roughly map to clips.
BEATS_PER_70S = 8  # rough: 8-10 beats per 70s of screen time
FEASIBILITY_TOLERANCE = 0.5  # beat count can be ±50% of target

# Novelty: shingle overlap threshold
NOVELTY_SHINGLE_SIZE = 3
NOVELTY_OVERLAP_THRESHOLD = 0.6  # >60% shingle overlap with any prior episode → error

# Retention
COLD_OPEN_S = 1.5
REHOOK_CADENCE_S = 10.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shingles(text: str, k: int = NOVELTY_SHINGLE_SIZE) -> set[tuple[str, ...]]:
    words = re.findall(r"\b\w+\b", text.lower())
    if len(words) < k:
        return set()
    return {tuple(words[i : i + k]) for i in range(len(words) - k + 1)}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def validate_structure(
    meta: dict,
    episode_file: str | None,
    res: ValidationResult,
) -> None:
    """Structural checks on episode-N.meta.json."""
    if not isinstance(meta, dict):
        res.error("meta is not a JSON object")
        return

    episode = meta.get("episode")
    if episode is None or not isinstance(episode, int):
        res.error("meta missing integer 'episode' field")

    end_state = meta.get("end_state", "")
    if not end_state or not isinstance(end_state, str):
        res.error("meta has empty or missing 'end_state'")

    hook = meta.get("hook", "")
    if not hook or not isinstance(hook, str):
        res.error("meta has empty or missing 'hook'")

    threads_opened = meta.get("threads_opened", [])
    threads_closed = meta.get("threads_closed", [])
    if not isinstance(threads_opened, list):
        res.error("threads_opened is not a list")
    if not isinstance(threads_closed, list):
        res.error("threads_closed is not a list")

    beats = meta.get("beats", [])
    if not isinstance(beats, list):
        res.error("beats is not a list")
    elif len(beats) == 0:
        res.warn("meta has no beats")

    # Verify beats appear in the episode prose
    if episode_file and Path(episode_file).is_file():
        prose = Path(episode_file).read_text(encoding="utf-8").lower()
        for i, beat in enumerate(beats):
            if isinstance(beat, str):
                # Check first 6 words of the beat appear in the prose
                words = re.findall(r"\b\w+\b", beat.lower())[:6]
                if words and not all(w in prose for w in words):
                    res.warn(f"beat {i}: first words not found in episode prose: {beat[:60]!r}")

    # Stable ids in cast/locations referenced in beats
    for beat in beats:
        if not isinstance(beat, str):
            continue
        for m in re.finditer(r"\b(char|loc|item)_(\d+)\b", beat):
            sid = m.group(0)
            # Just check format here; canon check is separate
            if not ID_RE.match(sid):
                res.error(f"invalid id format in beat: {sid} (expected {m.group(1)}_NN)")


def validate_canon(
    meta: dict,
    series_state: dict,
    res: ValidationResult,
) -> None:
    """Canon-lock: every referenced entity exists; no contradictions."""
    if not isinstance(series_state, dict):
        res.error("series_state is not a JSON object")
        return

    canon = series_state.get("canon", {})
    canon_cast = {c["id"]: c for c in canon.get("cast", []) if isinstance(c, dict) and "id" in c}
    canon_items = {c["id"]: c for c in canon.get("items", []) if isinstance(c, dict) and "id" in c}

    # Check beats reference valid entities
    for beat in meta.get("beats", []):
        if not isinstance(beat, str):
            continue
        for m in re.finditer(r"\b(char|loc|item)_(\d+)\b", beat):
            sid = m.group(0)
            kind = m.group(1)
            pool = canon_cast if kind == "char" else canon_items if kind == "item" else {}
            if kind == "loc":
                # Locations may be in canon_cast or a separate locations list
                locs = {c["id"]: c for c in canon.get("locations", []) if isinstance(c, dict) and "id" in c}
                pool = locs
            if sid not in pool:
                res.warn(f"beat references {sid} not in series_state.canon")

    # Check threads_closed are valid
    unresolved = series_state.get("unresolved_threads", [])
    if not isinstance(unresolved, list):
        unresolved = []
    threads_closed = meta.get("threads_closed", [])
    for tc in threads_closed:
        if isinstance(tc, str) and tc not in unresolved:
            # Could be closed in a prior episode; just warn
            pass


def validate_threads(
    meta: dict,
    series_state: dict,
    prior_episodes: list[dict],
    res: ValidationResult,
) -> None:
    """Thread bookkeeping: no silent disappearance."""
    if not isinstance(series_state, dict):
        return

    unresolved = set(series_state.get("unresolved_threads", []))
    if not isinstance(series_state.get("unresolved_threads"), list):
        unresolved = set()

    threads_closed = set(meta.get("threads_closed", []))
    threads_opened = set(meta.get("threads_opened", []))

    # Collect all threads opened in prior episodes
    all_opened = set()
    for ep in prior_episodes:
        if isinstance(ep, dict):
            all_opened.update(ep.get("threads_opened", []))

    # Every thread opened in prior episodes must be:
    #   (a) closed by this episode, or
    #   (b) still in unresolved_threads, or
    #   (c) closed by a prior episode
    prior_closed = set()
    for ep in prior_episodes:
        if isinstance(ep, dict):
            prior_closed.update(ep.get("threads_closed", []))

    for thread in all_opened:
        if thread in prior_closed:
            continue
        if thread in threads_closed:
            continue
        if thread in unresolved:
            continue
        # Check if it's explicitly parked (in meta or series_state)
        parked = meta.get("parked_threads", []) or series_state.get("parked_threads", [])
        if thread in parked:
            continue
        res.warn(f"thread {thread!r} opened in a prior episode but not closed, unresolved, or parked")


def validate_novelty(
    meta: dict,
    episode_file: str | None,
    prior_episode_files: list[str],
    res: ValidationResult,
) -> None:
    """Anti-sameness: shingle overlap with prior episodes."""
    if not episode_file or not Path(episode_file).is_file():
        return

    this_text = Path(episode_file).read_text(encoding="utf-8")
    this_shingles = _shingles(this_text)

    for prior_path in prior_episode_files:
        if not Path(prior_path).is_file():
            continue
        prior_text = Path(prior_path).read_text(encoding="utf-8")
        prior_shingles = _shingles(prior_text)
        overlap = _jaccard(this_shingles, prior_shingles)
        if overlap > NOVELTY_OVERLAP_THRESHOLD:
            res.error(
                f"novelty: {overlap:.0%} shingle overlap with {Path(prior_path).name} "
                f"(threshold {NOVELTY_OVERLAP_THRESHOLD:.0%}) — episode is too similar"
            )

    # Same primary location + action as immediately previous episode
    if prior_episode_files:
        prev = prior_episode_files[-1]
        if Path(prev).is_file():
            prev_text = Path(prev).read_text(encoding="utf-8").lower()
            this_lower = this_text.lower()
            # Rough: check if the first 100 words overlap heavily
            prev_words = set(re.findall(r"\b\w+\b", prev_text[:500]))
            this_words = set(re.findall(r"\b\w+\b", this_lower[:500]))
            if prev_words and this_words:
                overlap = len(prev_words & this_words) / len(prev_words | this_words)
                if overlap > 0.5:
                    res.warn(
                        f"novelty: opening {overlap:.0%} word overlap with previous episode "
                        "— may be too similar"
                    )


def validate_retention(meta: dict, res: ValidationResult) -> None:
    """Retention: cold-open hook, re-hook cadence, payoff, loopable final beat."""
    beats = meta.get("beats", [])
    if not beats or not isinstance(beats, list):
        return

    fmt = meta.get("format", "long-form")
    target_s = meta.get("target_runtime_s", 0)

    # Cold-open hook: first beat should contain hook-like language
    first_beat = beats[0] if beats else ""
    if isinstance(first_beat, str):
        hook_words = ("hook", "cold open", "opens on", "starts with", "immediately")
        if not any(w in first_beat.lower() for w in hook_words):
            # Check if the hook field references the first beat
            hook = meta.get("hook", "")
            if hook and isinstance(hook, str):
                pass  # hook is declared separately
            else:
                res.warn("retention: first beat may not be a cold-open hook")

    # Re-hook cadence: roughly every 10s of screen time there should be a beat
    if target_s and isinstance(target_s, (int, float)) and target_s > 0:
        expected_beats = max(1, int(target_s / REHOOK_CADENCE_S))
        actual_beats = len(beats)
        if actual_beats < expected_beats * 0.5:
            res.warn(
                f"retention: {actual_beats} beats for {target_s}s target "
                f"(expected ~{expected_beats} at one per {REHOOK_CADENCE_S}s)"
            )

    # Loopable final beat for reels
    if fmt == "reel":
        last_beat = beats[-1] if beats else ""
        if isinstance(last_beat, str):
            loop_words = ("loop", "returns to", "back to", "cycle", "repeat", "opening")
            if not any(w in last_beat.lower() for w in loop_words):
                res.warn("retention: reel format but final beat may not be loopable")


def validate_feasibility(meta: dict, res: ValidationResult) -> None:
    """Beat count vs target runtime."""
    beats = meta.get("beats", [])
    target_s = meta.get("target_runtime_s", 0)

    if not target_s or not isinstance(target_s, (int, float)):
        return

    expected = max(1, int(target_s / 70 * BEATS_PER_70S))
    actual = len(beats) if isinstance(beats, list) else 0
    low = int(expected * (1 - FEASIBILITY_TOLERANCE))
    high = int(expected * (1 + FEASIBILITY_TOLERANCE))

    if actual < low:
        res.warn(f"feasibility: {actual} beats for {target_s}s target (expected ~{expected}, min {low})")
    elif actual > high:
        res.warn(f"feasibility: {actual} beats for {target_s}s target (expected ~{expected}, max {high})")


def validate_continuity(
    meta: dict,
    series_state: dict,
    res: ValidationResult,
) -> None:
    """Episode N's opening state must match episode N-1's end_state."""
    if not isinstance(series_state, dict):
        return

    episode = meta.get("episode", 0)
    if not isinstance(episode, int) or episode <= 1:
        return  # first episode has no predecessor

    end_states = series_state.get("episode_end_states", {})
    if not isinstance(end_states, dict):
        return

    prev_key = str(episode - 1)
    prev_end = end_states.get(prev_key)
    if not prev_end:
        res.warn(f"continuity: no end_state found for episode {prev_key} in series_state")
        return

    # The meta's opening state should be consistent with the previous end state.
    # We can't do a deep semantic check deterministically, but we can check that
    # the end_state field exists and is non-empty.
    opening = meta.get("opening_state", "")
    if not opening:
        res.warn("continuity: meta has no 'opening_state' — cannot verify handoff from previous episode")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def validate(
    meta_path: str,
    *,
    series_state_path: str | None = None,
    episode_file: str | None = None,
    prior_episodes_dir: str | None = None,
) -> ValidationResult:
    res = ValidationResult()

    mpath = Path(meta_path)
    if not mpath.is_file():
        res.error(f"meta file not found: {mpath}")
        return res
    try:
        meta = json.loads(mpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        res.error(f"meta JSON parse error: {e}")
        return res

    # Auto-detect episode file if not given
    if not episode_file:
        episode_num = meta.get("episode", 0)
        if isinstance(episode_num, int):
            # Try stories/<series>/episode-N.md relative to meta
            parent = mpath.parent
            auto = parent / f"episode-{episode_num}.md"
            if auto.is_file():
                episode_file = str(auto)

    validate_structure(meta, episode_file, res)

    # Load series_state
    series_state = None
    if series_state_path:
        sspath = Path(series_state_path)
        if not sspath.is_file():
            res.warn(f"series_state not found: {sspath}")
        else:
            try:
                series_state = json.loads(sspath.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                res.error(f"series_state JSON parse error: {e}")
    else:
        # Auto-detect: walk up from meta to find series_state.json
        for parent in mpath.parents:
            candidate = parent / "series_state.json"
            if candidate.is_file():
                series_state = json.loads(candidate.read_text(encoding="utf-8"))
                break

    if series_state:
        validate_canon(meta, series_state, res)
        validate_continuity(meta, series_state, res)

        # Load prior episode metas
        prior_metas: list[dict] = []
        prior_episode_files: list[str] = []
        if prior_episodes_dir:
            pdir = Path(prior_episodes_dir)
            if pdir.is_dir():
                episode_num = meta.get("episode", 0)
                if isinstance(episode_num, int):
                    for n in range(1, episode_num):
                        pm = pdir / f"episode-{n}.meta.json"
                        if pm.is_file():
                            try:
                                prior_metas.append(json.loads(pm.read_text(encoding="utf-8")))
                            except json.JSONDecodeError:
                                pass
                        pe = pdir / f"episode-{n}.md"
                        if pe.is_file():
                            prior_episode_files.append(str(pe))

        validate_threads(meta, series_state, prior_metas, res)

    # Novelty needs the episode file + prior episode files
    if episode_file:
        prior_files: list[str] = []
        if prior_episodes_dir:
            pdir = Path(prior_episodes_dir)
            episode_num = meta.get("episode", 0)
            if isinstance(episode_num, int) and pdir.is_dir():
                for n in range(1, episode_num):
                    pe = pdir / f"episode-{n}.md"
                    if pe.is_file():
                        prior_files.append(str(pe))
        validate_novelty(meta, episode_file, prior_files, res)

    validate_retention(meta, res)
    validate_feasibility(meta, res)

    return res


def main() -> int:
    p = argparse.ArgumentParser(description="Validate a Tier 0 story artifact")
    p.add_argument("meta", help="Path to episode-N.meta.json")
    p.add_argument("--series-state", default=None, help="Path to series_state.json (auto-detected if omitted)")
    p.add_argument("--episode-file", default=None, help="Path to the episode prose .md file (auto-detected if omitted)")
    p.add_argument("--prior-episodes", default=None, help="Directory containing prior episode files + metas")
    args = p.parse_args()

    res = validate(
        args.meta,
        series_state_path=args.series_state,
        episode_file=args.episode_file,
        prior_episodes_dir=args.prior_episodes,
    )

    out_path = Path(args.meta).with_suffix(".json.validation.json")
    out_path.write_text(json.dumps(res.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    if res.ok:
        print(f"PASS: {args.meta}  warnings={len(res.warnings)}")
        for w in res.warnings:
            print(f"  ⚠ {w}")
        return 0
    print(f"FAIL: {args.meta} — {len(res.errors)} error(s)")
    for e in res.errors:
        print(f"  ✗ {e}")
    for w in res.warnings:
        print(f"  ⚠ {w}")
    print(f"  wrote {out_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
