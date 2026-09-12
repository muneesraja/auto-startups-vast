#!/usr/bin/env python3
"""Minimax H3 renderer + concat (the slow "hands" stage). No LLM calls.

Sequential single-pass render with tail-video conditioning, driven by the
approved render manifest:

  - The manifest is required and must validate (``status: approved``, all
    sheet/prompt/audio/scenes/storyboard hashes match). ``--no-manifest`` is
    a loudly-warned escape hatch for dev smoke renders only.
  - Scene order comes from scenes.md; durations come from the manifest.
  - Boundary policy (tools/boundary.py): a generation whose first shot
    declares ``hard_cut`` — or whose scene follows a ``hard_cut`` handoff —
    opens fresh and gets no tail ref. Everything else is conditioned on the
    previous generation's rendered tail.
  - Resume is dependency-aware via render_state.json: a clip is skipped only
    when its file exists AND the recorded fingerprint of its inputs (sheet,
    prompt, audio, predecessor output, render config) still matches.
    Re-rendering a clip invalidates every downstream clip automatically.
  - ``prompt_id`` is persisted immediately after queueing; on restart a
    submitted-but-unfinished job is re-polled rather than re-submitted.
  - Downloads land in ``*.part`` and are promoted only after ffprobe
    verification.

  python3 scripts/render_all.py --output-dir <run> [--only-scenes s1,s2]
      [--force-rerender-from s2/g1] [--tail-ref-seconds 3]

Long-running (hours). Fire-and-forget; the SKILL.md launches it in the
background.

Set ``NTFY_URL`` in the environment (e.g. ``ntfy.sh/topic``) to receive a
push notification after each generation, each scene, and the final film.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

import config  # noqa: E402
from tools import boundary, image_pipeline as ip, render_state, validators  # noqa: E402
from tools.audio_refs import find_audio_refs  # noqa: E402
from tools.episode_spec import set_index_production, set_production_status  # noqa: E402
from tools.minimax_workflow import (  # noqa: E402
    _collect_video_outputs,
    minimax_workflow_path,
    render_generation,
)
from tools.comfyui_tools import download_output, wait_for_prompt  # noqa: E402
from tools.video_concat import concat_videos  # noqa: E402
from tools.video_frames import (  # noqa: E402
    extract_first_frame,
    extract_last_frame,
    extract_tail,
)
from tools.video_verify import verify_clip  # noqa: E402


def _sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _exists(path: str) -> bool:
    return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0


def _ntfy(message: str) -> None:
    """Send a push notification to ``NTFY_URL`` if it is set in the env."""
    ntfy_url = os.environ.get("NTFY_URL", os.environ.get("NTFY_TOPIC"))
    if not ntfy_url:
        return
    try:
        subprocess.run(
            ["curl", "-d", message, ntfy_url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except Exception:
        pass


def _find_sheet(run_dir: str, scene_id: str, gen_id: str) -> str:
    """Find the per-generation storyboard sheet image (canonical convention)."""
    for ext in ("webp", "png", "jpg", "jpeg"):
        sheet_path = os.path.join(run_dir, f"storyboard_sheet_{scene_id}_{gen_id}.{ext}")
        if _exists(sheet_path):
            return sheet_path
    raise FileNotFoundError(
        f"storyboard sheet missing: {run_dir}/storyboard_sheet_{scene_id}_{gen_id}.<ext> "
        "(per-generation sheets are canonical)"
    )


def _manifest_entry(manifest: dict | None, scene_id: str, gen_id: str) -> dict | None:
    if not manifest:
        return None
    for e in manifest.get("generations", []):
        if e.get("scene_id") == scene_id and e.get("gen_id") == gen_id:
            return e
    return None


def _check_manifest_entry(entry: dict, scene_id: str, gid: str,
                          sheet_sha: str, prompt_sha: str,
                          audio_shas: list[str]) -> None:
    """Defense-in-depth: inputs at render time must equal the approved inputs."""
    tag = f"{scene_id}/{gid}"
    if entry.get("sheet_sha256") and entry["sheet_sha256"] != sheet_sha:
        raise RuntimeError(
            f"Stale sheet for {tag}: checksum mismatch with manifest "
            f"(expected {entry['sheet_sha256'][:10]}, got {sheet_sha[:10]}). "
            "Re-run scripts/build_manifest.py --approve before rendering."
        )
    if entry.get("video_prompt_sha256") and entry["video_prompt_sha256"] != prompt_sha:
        raise RuntimeError(
            f"Stale video prompt for {tag}: checksum mismatch with manifest "
            f"(expected {entry['video_prompt_sha256'][:10]}, got {prompt_sha[:10]}). "
            "Re-run scripts/build_manifest.py --approve before rendering."
        )
    manifest_audio = [a.get("sha256") for a in (entry.get("audio_refs") or []) if a.get("sha256")]
    if entry.get("audio_ref_sha256") and entry["audio_ref_sha256"] not in manifest_audio:
        manifest_audio.append(entry["audio_ref_sha256"])
    if sorted(manifest_audio) != sorted(audio_shas):
        raise RuntimeError(
            f"Audio references for {tag} differ from the approved manifest. "
            "Re-run scripts/build_manifest.py --approve before rendering."
        )


def _write_review_frames(clip_path: str, clips_dir: str, gid: str) -> None:
    """Drop first/last-frame PNGs for agent/user inspection after the run."""
    review_dir = os.path.join(clips_dir, "review")
    try:
        extract_first_frame(clip_path, os.path.join(review_dir, f"{gid}_first.png"))
        extract_last_frame(clip_path, os.path.join(review_dir, f"{gid}_last.png"))
    except Exception:
        pass  # review artifacts are best-effort


def _resume_submitted(
    prompt_id: str, part_path: str, out_path: str,
    expected_seconds: float, tag: str,
) -> str | None:
    """Re-poll a prompt_id persisted by a previous run; returns out_path on
    success or None when the job cannot be recovered (caller re-renders)."""
    try:
        outputs = wait_for_prompt(prompt_id, max_wait=7200, poll_interval=10)
    except Exception as exc:
        print(f"  clip {tag}: could not recover queued job {prompt_id}: {exc}")
        return None
    videos = _collect_video_outputs(outputs)
    if not videos:
        print(f"  clip {tag}: job {prompt_id} finished with no video output")
        return None
    f = videos[0]
    if not download_output(
        f["filename"], part_path,
        subfolder=f.get("subfolder", ""), is_video=True,
        file_type=f.get("type", "output"),
    ):
        print(f"  clip {tag}: resume download failed for {prompt_id}")
        return None
    problem = verify_clip(part_path, expected_seconds)
    if problem:
        print(f"  clip {tag}: resumed output failed verification ({problem})")
        try:
            os.unlink(part_path)
        except OSError:
            pass
        return None
    os.replace(part_path, out_path)
    return out_path


def _render_clip(
    run_dir: str, scene_id: str, gen: dict, clips_dir: str, *,
    seed: int, megapixels: float | None, aspect: str | None,
    extra_video_refs: list[str] | None,
    manifest_entry: dict | None,
    config_fp: str,
    prev_output_sha: str | None,
    state: dict,
    force: bool,
) -> tuple[str, str]:
    """Render one generation clip with fingerprint-aware resume.

    Returns (clip_path, output_sha256).
    """
    gid = gen["gen_id"]
    tag = f"{scene_id}/{gid}"
    out_path = os.path.join(clips_dir, f"{gid}.mp4")
    part_path = out_path + ".part"

    sheet_path = _find_sheet(run_dir, scene_id, gid)
    prompt_file = ip.video_prompt_path(run_dir, scene_id, gid)
    prompt = ip.read_prompt(prompt_file)
    if not prompt:
        raise FileNotFoundError(f"video prompt missing: {prompt_file}")

    audio_refs = find_audio_refs(run_dir, scene_id, gid)
    audio_paths = [r["path"] for r in audio_refs]
    audio_shas = [_sha256(p) for p in audio_paths]
    sheet_sha = _sha256(sheet_path)
    prompt_sha = _sha256(prompt_file)

    if manifest_entry is not None:
        _check_manifest_entry(
            manifest_entry, scene_id, gid, sheet_sha, prompt_sha, audio_shas
        )

    fp = render_state.input_fingerprint(
        sheet_sha=sheet_sha,
        prompt_sha=prompt_sha,
        audio_shas=audio_shas,
        prev_output_sha=prev_output_sha,
        config_fingerprint=config_fp,
    )
    rec = render_state.clip_record(state, scene_id, gid)

    # Reuse: file exists AND inputs fingerprint unchanged AND not forced.
    if not force and render_state.is_reusable(rec, out_path, fp):
        print(f"  clip {tag}: inputs unchanged, reuse")
        out_sha = rec.get("output_sha256") or _sha256(out_path)
        rec["output_sha256"] = out_sha
        return out_path, out_sha

    if force and _exists(out_path):
        print(f"  clip {tag}: forced re-render")

    # Resume a job queued by a previous (interrupted) run.
    duration = (gen["end"] or 0.0) - (gen["start"] or 0.0)
    old_prompt_id = rec.get("prompt_id")
    if (
        old_prompt_id
        and rec.get("status") in ("submitted", "rendering")
        and not _exists(out_path)
        and not force
    ):
        print(f"  clip {tag}: resuming queued job {old_prompt_id} ...")
        recovered = _resume_submitted(old_prompt_id, part_path, out_path, duration, tag)
        if recovered:
            out_sha = _sha256(out_path)
            render_state.set_status(
                run_dir, state, scene_id, gid, "rendered",
                prompt_id=old_prompt_id, input_fingerprint=fp,
                output_sha256=out_sha,
                clip_path=os.path.relpath(out_path, run_dir),
            )
            _write_review_frames(out_path, clips_dir, gid)
            return out_path, out_sha
        # Fall through to a fresh render.

    print(
        f"  clip {tag}: rendering ({duration:.1f}s, "
        f"tail_ref={'yes' if extra_video_refs else 'no'}, "
        f"audio_refs={len(audio_paths)}) ..."
    )

    def _on_queued(pid: str) -> None:
        render_state.set_status(
            run_dir, state, scene_id, gid, "submitted",
            prompt_id=pid, input_fingerprint=fp,
            attempts=(rec.get("attempts") or 0) + 1,
        )

    render_state.set_status(
        run_dir, state, scene_id, gid, "rendering", input_fingerprint=fp
    )
    t0 = time.time()
    result = render_generation(
        sheet_path=sheet_path,
        prompt=prompt,
        duration_seconds=duration,
        output_path=part_path,
        seed=seed,
        megapixels=megapixels,
        aspect=aspect,
        extra_reference_video_paths=extra_video_refs,
        extra_reference_audio_paths=audio_paths or None,
        on_queued=_on_queued,
    )
    if result.get("status") != "success":
        render_state.set_status(
            run_dir, state, scene_id, gid, "failed",
            error=result.get("message", "unknown"),
        )
        _ntfy(f"[story-maker-v5] {tag} render failed: {result.get('message', result)}")
        raise RuntimeError(f"clip {tag} failed: {result.get('message', result)}")

    problem = verify_clip(part_path, duration)
    if problem:
        render_state.set_status(
            run_dir, state, scene_id, gid, "failed",
            error=f"verification failed: {problem}",
        )
        try:
            os.unlink(part_path)
        except OSError:
            pass
        raise RuntimeError(f"clip {tag} failed verification: {problem}")
    os.replace(part_path, out_path)

    out_sha = _sha256(out_path)
    render_state.set_status(
        run_dir, state, scene_id, gid, "rendered",
        prompt_id=result.get("prompt_id"),
        input_fingerprint=fp,
        output_sha256=out_sha,
        clip_path=os.path.relpath(out_path, run_dir),
        elapsed_seconds=result.get("elapsed_seconds"),
        expected_frames=result.get("frames"),
    )
    print(f"    done in {result.get('elapsed_seconds')}s -> {out_path}")
    _ntfy(f"[story-maker-v5] {tag} render complete -> {out_path}")
    _write_review_frames(out_path, clips_dir, gid)
    return out_path, out_sha


def _extract_tail_ref(
    clip_path: str, clip_sha: str, ref_seconds: float, refs_dir: str,
    scene_id: str, gen_id: str, rec: dict,
) -> str | None:
    """Extract the tail of a clip for use as a ref_video by the next generation.

    Re-extracts whenever the source clip changed — a stale tail must never be
    silently reused after its clip is re-rendered.
    """
    tail_name = f"tail_{scene_id}_{gen_id}.mp4"
    tail_path = os.path.join(refs_dir, tail_name)
    tail_meta = rec.get("tail") or {}
    if _exists(tail_path) and tail_meta.get("source_sha256") == clip_sha:
        return tail_path
    if not extract_tail(clip_path, ref_seconds, tail_path):
        print(f"  WARNING: tail extraction failed for {scene_id}/{gen_id}, skipping ref")
        return None
    rec["tail"] = {"path": os.path.relpath(tail_path), "source_sha256": clip_sha}
    return tail_path


def render_scene(
    run_dir: str, scene_id: str, sb: dict, *, seed: int,
    megapixels: float | None, aspect: str | None,
    tail_ref_seconds: float = 3.0,
    prev_tail_ref: str | None = None,
    prev_output_sha: str | None = None,
    manifest: dict | None = None,
    config_fp: str = "",
    state: dict | None = None,
    force_from: set[str] | None = None,
) -> tuple[str, str | None, str | None]:
    """Render all generations for one scene sequentially with tail refs.

    Returns (scene_mp4_path, last_gen_tail_path, last_gen_output_sha).
    """
    state = state if state is not None else {"clips": {}}
    gens = sb["generations"]
    if not gens:
        raise SystemExit(f"storyboard_{scene_id}.md has no generations")

    clips_dir = os.path.join(run_dir, "clips", scene_id)
    os.makedirs(clips_dir, exist_ok=True)
    refs_dir = os.path.join(clips_dir, "refs")

    clip_paths: list[str] = []
    tail_ref = prev_tail_ref  # carries over from previous scene's last gen
    out_sha = prev_output_sha
    is_first_gen = True

    for gen in gens:
        gid = gen["gen_id"]

        # Skip bridge generations (no longer supported, but may exist in old storyboards)
        if gen.get("is_bridge"):
            print(f"  skip {scene_id}/{gid}: bridge generations are no longer supported")
            continue

        # Boundary policy: a generation whose first shot is a hard_cut opens
        # fresh — no tail ref even though one may be available.
        fresh_cut = boundary.gen_boundary(sb, gid) == boundary.FRESH_CUT
        attach_tail = bool(tail_ref) and not fresh_cut
        if tail_ref and fresh_cut:
            print(f"  clip {scene_id}/{gid}: hard_cut boundary — opening fresh (no tail ref)")
        extra_video_refs = [tail_ref] if attach_tail else None

        key = render_state.clip_key(scene_id, gid)
        clip_path, out_sha = _render_clip(
            run_dir, scene_id, gen, clips_dir,
            seed=seed, megapixels=megapixels, aspect=aspect,
            extra_video_refs=extra_video_refs,
            manifest_entry=_manifest_entry(manifest, scene_id, gid),
            config_fp=config_fp,
            prev_output_sha=out_sha if attach_tail else None,
            state=state,
            force=bool(force_from and key in force_from),
        )
        clip_paths.append(clip_path)
        is_first_gen = False

        # Extract tail for the next generation
        rec = render_state.clip_record(state, scene_id, gid)
        tail_ref = _extract_tail_ref(
            clip_path, out_sha, tail_ref_seconds, refs_dir, scene_id, gid, rec,
        )
    render_state.save_state(run_dir, state)

    scene_mp4 = os.path.join(run_dir, f"scene_{scene_id}.mp4")
    print(f"  concat {len(clip_paths)} clips -> {scene_mp4}")
    res = concat_videos(clip_paths, scene_mp4)
    if res.get("status") != "success":
        _ntfy(f"[story-maker-v5] scene {scene_id} concat failed: {res.get('message')}")
        raise RuntimeError(f"scene concat failed for {scene_id}: {res.get('message')}")
    _ntfy(f"[story-maker-v5] scene {scene_id} complete -> {scene_mp4}")
    return scene_mp4, tail_ref, out_sha


def _write_qc_report(
    run_dir: str, scene_ids: list[str], storyboards: dict, state: dict,
) -> str:
    """Write ``<run_dir>/qc.md`` — a review report of what the run produced."""
    lines = [
        "# Render QC Report",
        "",
        f"- run_dir: {run_dir}",
        f"- generated_at: {state.get('updated_at')}",
        "",
        "| clip | status | duration | output_sha256 | error |",
        "|---|---|---|---|---|",
    ]
    n_done = n_failed = n_pending = 0
    for sid in scene_ids:
        for gen in storyboards[sid].get("generations", []):
            if gen.get("is_bridge"):
                continue
            gid = gen["gen_id"]
            rec = state.get("clips", {}).get(f"{sid}/{gid}", {})
            status = rec.get("status", "pending")
            dur = (gen.get("end") or 0.0) - (gen.get("start") or 0.0)
            out_sha = (rec.get("output_sha256") or "")[:10]
            err = rec.get("error", "")
            lines.append(f"| {sid}/{gid} | {status} | {dur:.1f}s | {out_sha} | {err} |")
            if status in ("rendered", "accepted"):
                n_done += 1
            elif status == "failed":
                n_failed += 1
            else:
                n_pending += 1
    lines += [
        "",
        f"- rendered/accepted: {n_done}",
        f"- failed: {n_failed}",
        f"- pending/other: {n_pending}",
        "",
    ]

    # Seam metrics (best-effort — needs ffmpeg + Pillow/numpy).
    try:
        from tools import seam_report
        report = seam_report.build_report(run_dir)
        seams = [s for s in report.get("seams", [])]
        if seams:
            lines += [
                "## Seams",
                "",
                "| seam | boundary | mean_abs_diff | luma_delta | hist_dist | contact |",
                "|---|---|---|---|---|---|",
            ]
            for s in seams:
                m = s.get("metrics", {})
                # A hard_cut boundary legitimately jumps; a continuation seam
                # with a big diff is the one worth a human look.
                bnd = "fresh_cut"
                if s["scene_a"] == s["scene_b"]:
                    gsb = storyboards.get(s["scene_a"]) or {}
                    gid_b = os.path.basename(s["clip_b"])[:-4]
                    if boundary.gen_boundary(gsb, gid_b) != boundary.FRESH_CUT:
                        bnd = "continuation"
                else:
                    pa = storyboards.get(s["scene_a"]) or {}
                    pb = storyboards.get(s["scene_b"]) or {}
                    if boundary.scene_boundary(pa, pb) != boundary.FRESH_CUT:
                        bnd = "continuation"
                lines.append(
                    f"| {s['seam_id']} | {bnd} | {m.get('mean_abs_diff', '-')} | "
                    f"{m.get('mean_luma_delta', '-')} | {m.get('histogram_distance', '-')} | "
                    f"{s.get('contact_sheet') or '-'} |"
                )
            lines.append("")
    except Exception:
        pass  # seam metrics are advisory; never fail the run on them

    qc_path = os.path.join(run_dir, "qc.md")
    with open(qc_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return qc_path


def _natural_scene_key(sid: str) -> tuple[int, str]:
    m = re.search(r"(\d+)", sid)
    return (int(m.group(1)) if m else 10**9, sid)


def _ordered_scene_ids(run_dir: str) -> list[str]:
    """Scene order from scenes.md; falls back to natural filename order."""
    scenes_path = os.path.join(run_dir, "scenes.md")
    if os.path.isfile(scenes_path):
        scenes = validators.parse_scenes(open(scenes_path, encoding="utf-8").read())
        ids = [
            s["scene_id"] for s in scenes.get("scenes", [])
            if os.path.isfile(os.path.join(run_dir, f"storyboard_{s['scene_id']}.md"))
        ]
        if ids:
            return ids
    return sorted(
        (
            m.group(1)
            for f in os.listdir(run_dir)
            if (m := re.fullmatch(r"storyboard_([^.]+)\.md", f))
        ),
        key=_natural_scene_key,
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Render Minimax H3 generations + concat (sequential with tail refs)")
    p.add_argument("--output-dir", required=True, help="run output dir")
    p.add_argument("--only-scenes", default="", help="comma-separated scene ids to render (partial run — no final_film.mp4 is written)")
    p.add_argument("--manifest", default=None, help="path to render_manifest.json (default: <run>/render_manifest.json)")
    p.add_argument("--no-manifest", action="store_true",
                   help="DEV ONLY: render without an approved manifest (no hash enforcement)")
    p.add_argument("--force-rerender-from", default="",
                   help="scene/gen (e.g. s2/g1): re-render that clip and everything after it")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--megapixels", type=float, default=None,
                   help=f"output size in MP (default {config.MINIMAX_MEGAPIXELS}; e.g. 0.6 -> 1056x608)")
    p.add_argument("--aspect", default=None, help=f"aspect ratio (default {config.MINIMAX_ASPECT})")
    p.add_argument("--tail-ref-seconds", type=float, default=3.0,
                   help="seconds of tail to extract as ref video for the next generation (default 3.0)")
    args = p.parse_args()

    run_dir = os.path.abspath(args.output_dir)
    only = {s.strip() for s in args.only_scenes.split(",") if s.strip()}

    # --- Manifest: the approved render contract ---
    manifest_path = args.manifest or os.path.join(run_dir, "render_manifest.json")
    manifest = None
    if args.no_manifest:
        print("WARNING: --no-manifest — rendering without hash enforcement "
              "or approval checks (dev smoke only)")
    else:
        if not os.path.isfile(manifest_path):
            raise SystemExit(
                f"no render manifest at {manifest_path} — run "
                "scripts/build_manifest.py --run-dir <run> --approve after "
                "GATE 2 review (or pass --no-manifest for a dev smoke render)"
            )
        res = validators.validate_render_manifest(manifest_path, run_dir=run_dir)
        for e in res.errors:
            print(f"  manifest error: {e}")
        for w in res.warnings:
            print(f"  manifest warn: {w}")
        if not res.ok:
            raise SystemExit("render manifest failed validation — refusing to render")
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        print(f"Loaded approved render manifest: {manifest_path}")

    # --- Scene order (scenes.md, not filename sort — s10 must follow s9) ---
    scene_ids = _ordered_scene_ids(run_dir)
    if only:
        scene_ids = [s for s in scene_ids if s in only]
    if not scene_ids:
        raise SystemExit(f"no storyboard_*.md scenes found in {run_dir}")

    # Parse all storyboards once (boundary policy needs neighbors).
    storyboards = {
        sid: validators.parse_storyboard(
            open(os.path.join(run_dir, f"storyboard_{sid}.md"), encoding="utf-8").read()
        )
        for sid in scene_ids
    }

    # --- Render state + config fingerprint ---
    state = render_state.load_state(run_dir)
    workflow_path = minimax_workflow_path()
    workflow_sha = _sha256(str(workflow_path)) if workflow_path.is_file() else None
    config_fp = render_state.config_fingerprint(
        seed=args.seed, megapixels=args.megapixels, aspect=args.aspect,
        workflow_sha=workflow_sha,
    )

    # --- --force-rerender-from: invalidate that clip and all downstream ---
    force_from: set[str] | None = None
    if args.force_rerender_from:
        target = args.force_rerender_from.strip()
        order = [
            render_state.clip_key(sid, g["gen_id"])
            for sid in scene_ids
            for g in storyboards[sid]["generations"]
            if not g.get("is_bridge")
        ]
        if target not in order:
            raise SystemExit(
                f"--force-rerender-from {target!r} not found in render order "
                f"({', '.join(order)})"
            )
        force_from = set(order[order.index(target):])
        print(f"Forcing re-render of {len(force_from)} clip(s) from {target}")

    def _set_stage(stage: str) -> None:
        set_production_status(run_dir, stage)
        spec_path = os.path.join(run_dir, "episode_spec.json")
        if os.path.isfile(spec_path):
            try:
                with open(spec_path, encoding="utf-8") as f:
                    spec = json.load(f)
                set_index_production(
                    os.path.dirname(run_dir), spec.get("episode", 0),
                    stage, run_dir=run_dir,
                )
            except Exception:
                pass

    _set_stage("rendering")

    # Sequential single-pass: render scenes in order, passing tail refs across
    # scenes — unless the boundary between them is a declared hard_cut.
    scene_mp4s: list[str] = []
    prev_tail_ref: str | None = None
    prev_out_sha: str | None = None
    prev_sb: dict | None = None
    for i, sid in enumerate(scene_ids):
        print(f"== scene {sid} ==")
        cur_sb = storyboards[sid]
        if i > 0 and prev_tail_ref:
            fresh = (
                boundary.scene_boundary(prev_sb, cur_sb) == boundary.FRESH_CUT
            )
            if fresh:
                print(f"  scene boundary into {sid}: hard_cut — opening fresh (no tail ref)")
                prev_tail_ref = None
                prev_out_sha = None
        scene_mp4, prev_tail_ref, prev_out_sha = render_scene(
            run_dir, sid, cur_sb, seed=args.seed,
            megapixels=args.megapixels, aspect=args.aspect,
            tail_ref_seconds=args.tail_ref_seconds,
            prev_tail_ref=prev_tail_ref,
            prev_output_sha=prev_out_sha,
            manifest=manifest,
            config_fp=config_fp,
            state=state,
            force_from=force_from,
        )
        scene_mp4s.append(scene_mp4)
        prev_sb = cur_sb

    qc = _write_qc_report(run_dir, scene_ids, storyboards, state)
    print(f"qc report -> {qc}")
    _set_stage("qc_pending")

    if only:
        print(f"Partial render ({', '.join(scene_ids)}): skipping final_film.mp4")
        return 0

    final = os.path.join(run_dir, "final_film.mp4")
    if len(scene_mp4s) == 1:
        shutil.copy(scene_mp4s[0], final)
        print(f"final_film.mp4 -> {final}")
        _ntfy(f"[story-maker-v5] final film complete -> {final}")
    else:
        res = concat_videos(scene_mp4s, final)
        if res.get("status") != "success":
            _ntfy(f"[story-maker-v5] final concat failed: {res.get('message')}")
            raise SystemExit(f"final concat failed: {res.get('message')}")
        print(f"final_film.mp4 -> {final}")
        _ntfy(f"[story-maker-v5] final film complete -> {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
