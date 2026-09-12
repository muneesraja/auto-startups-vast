#!/usr/bin/env python3
"""Review + accept a render run — the human/agent sign-off after rendering.

    python3 scripts/review_run.py --run-dir <run>            # report only
    python3 scripts/review_run.py --run-dir <run> --accept   # accept all good clips
    python3 scripts/review_run.py --run-dir <run> --reject s2/g1

Report mode prints the per-clip table (status, output hash, verification)
plus a pointer at qc.md and the review frames under clips/<scene>/review/.

``--accept`` verifies every clip in ``rendered`` state (ffprobe + stream +
duration checks via tools.video_verify) and promotes it to ``accepted``;
when every manifest generation is accepted the run's status.json advances
to ``complete``, otherwise ``qc_pending``.

``--reject s1/g1`` marks a clip failed so the next render_all run re-renders
it (and, via fingerprint chaining, everything downstream of it).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools import render_state  # noqa: E402
from tools.episode_spec import (  # noqa: E402
    set_index_production,
    set_production_status,
)
from tools.video_verify import verify_clip  # noqa: E402


def _manifest_gens(run_dir: str) -> list[tuple[str, str, float]]:
    """(scene_id, gen_id, expected_seconds) from the manifest or storyboards."""
    mpath = os.path.join(run_dir, "render_manifest.json")
    if os.path.isfile(mpath):
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
        return [
            (e["scene_id"], e["gen_id"], float(e.get("duration_seconds") or 0))
            for e in manifest.get("generations", [])
        ]
    from tools import validators

    out = []
    for name in sorted(os.listdir(run_dir)):
        if not (name.startswith("storyboard_") and name.endswith(".md")):
            continue
        sid = name[len("storyboard_"):-3]
        sb = validators.parse_storyboard(
            open(os.path.join(run_dir, name), encoding="utf-8").read()
        )
        for g in sb.get("generations", []):
            if g.get("is_bridge"):
                continue
            out.append((sid, g["gen_id"], (g.get("end") or 0) - (g.get("start") or 0)))
    return out


def _update_index(run_dir: str, stage: str) -> None:
    spec_path = os.path.join(run_dir, "episode_spec.json")
    if not os.path.isfile(spec_path):
        return
    try:
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        set_index_production(
            os.path.dirname(run_dir), spec.get("episode", 0), stage,
            run_dir=run_dir,
        )
    except Exception:
        pass


def main() -> int:
    p = argparse.ArgumentParser(description="Review/accept a render run")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--accept", action="store_true",
                   help="verify rendered clips and mark them accepted")
    p.add_argument("--reject", default="",
                   help="clip key (s1/g1) to mark failed for re-render")
    args = p.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    state = render_state.load_state(run_dir)
    gens = _manifest_gens(run_dir)
    if not gens:
        raise SystemExit(f"no manifest or storyboards under {run_dir}")

    if args.reject:
        key = args.reject.strip()
        sid, _, gid = key.partition("/")
        if not sid or not gid or (sid, gid, 0) not in [
            (s, g, 0) for s, g, _ in gens
        ]:
            raise SystemExit(f"unknown clip key: {key}")
        render_state.set_status(
            run_dir, state, sid, gid, "failed",
            error="rejected at review",
        )
        set_production_status(run_dir, "qc_pending")
        _update_index(run_dir, "qc_pending")
        print(f"{key}: rejected — re-run render_all to re-render it "
              f"and its downstream dependents")
        return 0

    # Report table.
    print(f"{'clip':<10} {'status':<10} {'verify':<8} {'output_sha256':<14}")
    all_accepted = True
    problems: list[str] = []
    for sid, gid, dur in gens:
        key = f"{sid}/{gid}"
        rec = state.get("clips", {}).get(key, {})
        status = rec.get("status", "pending")
        clip_path = rec.get("clip_path") or ""
        full = os.path.join(run_dir, clip_path) if clip_path else ""
        verdict = "-"
        if status in ("rendered", "accepted") and os.path.isfile(full):
            problem = verify_clip(full, dur)
            verdict = "ok" if not problem else problem
            if problem:
                problems.append(f"{key}: {problem}")
        if status != "accepted":
            all_accepted = False
        print(f"{key:<10} {status:<10} {verdict:<8} "
              f"{(rec.get('output_sha256') or '')[:12]:<14}")

    qc = os.path.join(run_dir, "qc.md")
    if os.path.isfile(qc):
        print(f"\nqc report: {qc}")
    review_glob = os.path.join(run_dir, "clips", "*", "review")
    print(f"review frames under: {review_glob}")

    if not args.accept:
        if problems:
            print("\nproblems:", *problems, sep="\n  ")
            return 1
        return 0

    # Acceptance pass.
    for sid, gid, dur in gens:
        key = f"{sid}/{gid}"
        rec = state.get("clips", {}).get(key, {})
        if rec.get("status") != "rendered":
            continue
        clip_path = rec.get("clip_path") or ""
        full = os.path.join(run_dir, clip_path)
        problem = verify_clip(full, dur) if os.path.isfile(full) else "missing"
        if problem:
            render_state.set_status(
                run_dir, state, sid, gid, "failed",
                error=f"review verify: {problem}",
            )
            print(f"{key}: failed verification ({problem}) — marked failed")
        else:
            render_state.set_status(run_dir, state, sid, gid, "accepted")
            print(f"{key}: accepted")

    remaining = [
        f"{sid}/{gid}" for sid, gid, _ in gens
        if state.get("clips", {}).get(f"{sid}/{gid}", {}).get("status")
        != "accepted"
    ]
    stage = "complete" if not remaining else "qc_pending"
    set_production_status(run_dir, stage)
    _update_index(run_dir, stage)
    if remaining:
        print(f"production → qc_pending; unaccepted: {', '.join(remaining)}")
        return 1
    print("production → complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
