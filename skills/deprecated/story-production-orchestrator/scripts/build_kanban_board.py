#!/usr/bin/env python3
"""
build_kanban_board.py — Create a Kanban board for story production.

Two modes:
- v0.1-hybrid (default): 4-task board wrapping the v1.4.0 monolith
- v1.0-native: 12-task board with full v2.0 decomposition

Usage:
    python3 build_kanban_board.py <story-path> --mode v0.1-hybrid
    python3 build_kanban_board.py <story-path> --mode v1.0-native \\
        --directors-coach off
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Add the scripts directory to sys.path to find verify_profiles
scripts_dir = Path(__file__).parent.resolve()
if str(scripts_dir) not in sys.path:
    sys.path.insert(0, str(scripts_dir))
from verify_profiles import verify_profiles


def run(cmd: list, check: bool = True) -> str:
    """Run a shell command, return stdout."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: {cmd} failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def parse_task_id(create_output: str) -> str:
    """Extract task ID from 'hermes kanban create' output. Returns 't_xxx' or raises."""
    import re
    m = re.search(r"(t_[0-9a-f]+)", create_output)
    if not m:
        raise ValueError(f"Could not extract task ID from: {create_output!r}")
    return m.group(1)


def slugify(text: str) -> str:
    """Convert story name to URL-safe slug."""
    return text.lower().replace(" ", "-").replace("_", "-")


def verify_preflight(story_path: str, mode: str) -> dict:
    """Verify all pre-flight conditions. Returns dict of status per check."""
    checks = {}

    # 1. Profiles verification using verify_profiles script
    checks["profiles_configured"] = verify_profiles(verbose=True)

    # 2. ComfyUI URL
    comfyui_url = os.environ.get("COMFYUI_URL") or run(
        ["bash", "-c", "grep COMFYUI_URL ~/.hermes/.env | head -1 | cut -d= -f2- | tr -d '\"'"],
        check=False
    )
    checks["comfyui_url"] = bool(comfyui_url)

    # 3. OpenRouter key
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if not or_key:
        try:
            with open(Path.home() / ".hermes" / ".env") as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        or_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except FileNotFoundError:
            pass
    checks["openrouter_key"] = bool(or_key)

    # 4. Story path
    story_path_p = Path(story_path)
    checks["story_path_exists"] = story_path_p.exists()
    checks["story_md_exists"] = (story_path_p / "Story.md").exists()
    
    # In v1.0-native, the manifest is created by T2 (stv-director), so it does not need to exist yet.
    if mode == "v0.1-hybrid":
        checks["manifest_exists"] = (story_path_p / "story_manifest.json").exists()

    return checks


def init_board(slug: str):
    """Create the kanban board (idempotent)."""
    # First, init the kanban DB if needed
    run(["hermes", "kanban", "init"], check=False)
    # Then create the board (may already exist, that's OK)
    run(["hermes", "kanban", "boards", "create", slug, "--switch"], check=False)


def build_v01_hybrid_board(story_path: str, slug: str) -> dict:
    """Build 4-task v0.1 hybrid board using atomic parent creation."""
    tasks = {}

    # T1
    t1_body = f"""## Task: Run v1.4.0 monolithic pipeline
**Mode:** v0.1-hybrid (monolith wrap)
**Story:** {slug}
**Workdir:** {story_path}

### Instructions
1. Load `story-to-video-filmmaking` skill (v1.4.0)
2. Run: `python3 ~/.hermes/skills/creative/story-to-video-filmmaking/scripts/filmmaking_orchestrator.py \\
   --prompts {story_path}/filmmaking_prompt.json \\
   --url $COMFYUI_URL \\
   --auth "$COMFYUI_AUTH" \\
   --output-dir {story_path}`
3. If --skip-existing, use it (for in-flight projects)
4. Wait for completion, report output paths

### Output
- FF/LF stills in {story_path}/ff/ and {story_path}/lf/
- Video clips in {story_path}/video/
- Filmmaking prompt used: {story_path}/filmmaking_prompt.json

### ComfyUI
- URL: $COMFYUI_URL
- Auth: from env (NOT GrowthLabs2026!)
- Use `curl_json`, NOT urllib (Cloudflare 403 on tunnel)
"""
    out = run([
        "hermes", "kanban", "create", "T1: Run monolith (v1.4.0)",
        "--assignee", "stv-ops",
        "--skill", "story-to-video-filmmaking",
        "--workspace", f"dir:{story_path}",
        "--max-runtime", "60m",
        "--body", t1_body,
    ])
    tasks["T1"] = parse_task_id(out)

    # T2
    t2_body = f"""## Task: Per-image QC gate
**Mode:** v0.1-hybrid
**Story:** {slug}
**Blocked on:** T1

### Instructions
1. Load `qc-image-review` skill
2. For each FF PNG in {story_path}/ff/, run:
   `python3 ~/.hermes/skills/creative/qc-image-review/scripts/openrouter_qc.py \\
   --images <ff_png> <ref_sheet> \\
   --gate ff_gate \\
   --shot-id <shot_id> \\
   --output <qc_result.json>`
3. For each LF PNG, run with `--gate lf_gate --images <lf_png> <ff_png> <ref_sheet>`
4. If any QC fails: mark task BLOCKED, escalate to user
5. If all pass: report "All N/N shots passed QC"

### Output
- qc_results/ directory with per-shot JSON
- Summary in task completion metadata
"""
    out = run([
        "hermes", "kanban", "create", "T2: Per-image QC",
        "--assignee", "stv-reviewer",
        "--skill", "qc-image-review",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T1"],
        "--max-runtime", "30m",
        "--body", t2_body,
    ])
    tasks["T2"] = parse_task_id(out)

    # T3
    t3_body = f"""## Task: User approval gate (final film)
**Mode:** v0.1-hybrid
**Story:** {slug}
**Blocked on:** T2

### Instructions
1. Concatenate all videos: `ffmpeg -f concat -safe 0 -i {story_path}/concat_list.txt -c copy {story_path}/final_film.mp4`
2. **BLOCK** this task with `kanban block` — wait for user review
3. Present final film path to user
4. User approves → unblock, T4 runs
5. User rejects → spawn retake sub-tasks
"""
    out = run([
        "hermes", "kanban", "create", "T3: User approval gate",
        "--assignee", "user",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T2"],
        "--initial-status", "blocked",
        "--max-runtime", "1440m",  # 24h
        "--body", t3_body,
    ])
    tasks["T3"] = parse_task_id(out)

    # T4
    t4_body = f"""## Task: Cleanup + archive
**Mode:** v0.1-hybrid
**Story:** {slug}
**Blocked on:** T3

### Instructions
1. Verify final_film.mp4 exists and is non-zero size
2. Move artifacts to {story_path}/final/
3. Generate summary report with cost + timings
"""
    out = run([
        "hermes", "kanban", "create", "T4: Cleanup + archive",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T3"],
        "--max-runtime", "15m",
        "--body", t4_body,
    ])
    tasks["T4"] = parse_task_id(out)

    return tasks


def build_v10_native_board(story_path: str, slug: str) -> dict:
    """Build 14-task v1.0 native board."""
    tasks = {}

    # T1: Init project + verify infrastructure
    t1_body = f"""## Task: T1 — Init project and verify infrastructure
**Story:** {slug}
**Workdir:** {story_path}

### Setup
1. Source the profile environment: `source ~/.hermes/profiles/stv-ops/.env` (if exists) or `.env` in workspace.
2. Run preflight auth script: `bash /root/repos/auto-startups-vast/skills/comfyui-ops/scripts/quickstart_auth.sh`

### Helpers
- Use `comfyui_api.py` for `/system_stats`
- No other helpers needed

### Success Criteria
1. ComfyUI `/system_stats` returns JSON containing loaded models
2. Story directory exists: {story_path}/
3. Story.md exists: {story_path}/Story.md
4. Characters directory created: {story_path}/characters/
5. Write roster.json: {story_path}/.roster.json with ComfyUI URL, loaded models, profile status

### Stop
When roster.json is written and all checks pass, complete. Do NOT run any rendering.
"""
    out = run([
        "hermes", "kanban", "create", "T1: Init project + verify ComfyUI/models",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        "--max-runtime", "30m",
        "--body", t1_body,
    ])
    tasks["T1"] = parse_task_id(out)

    # T2: Story expansion → story_manifest.json v3
    t2_body = f"""## Task: T2 — Expand Story.md to story_manifest.json v3
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. {story_path}/story_manifest.json exists with valid v3 schema
2. Shot count matches target duration (e.g. 2 min ≈ 15-20 shots at 5-8s each)
3. Every shot has: shot_id, scene, shot_type, characters_present, facial_expression, duration_seconds, continues_from, qc_reference_strategy
4. character_sheets section lists each character with description + variant list

### Profile→Skill Map (ALWAYS use these exact names when creating tasks)
| Profile | Skill name (EXACT) |
|---|---|
| stv-director | story-direction |
| stv-t2i-writer | flux-t2i-prompting |
| stv-i2i-writer | flux-edit-prompting |
| stv-motion-writer | ltx-motion-prompting |
| stv-reviewer | qc-image-review |
| stv-ops | comfyui-ops |

### Stop
When story_manifest.json passes validation, complete. Do NOT write prompts or render anything.
"""
    out = run([
        "hermes", "kanban", "create", "T2: Story expansion → story_manifest.json v3",
        "--assignee", "stv-director",
        "--skill", "story-direction",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T1"],
        "--max-runtime", "45m",
        "--body", t2_body,
    ])
    tasks["T2"] = parse_task_id(out)

    # T3: Render character reference sheets from manifest
    t3_body = f"""## Task: T3 — Render character reference sheets from manifest
**Story:** {slug}
**Workdir:** {story_path}

### Setup
1. Source the environment: `source ~/.hermes/profiles/stv-ops/.env`
2. Verify ComfyUI connectivity.

### Helpers
- Use `generate_scene.py` for single-shot Flux 2 Dev Turbo rendering
- Use `curl_json()`, `wait_for_prompt()`, `download_output()` from `comfyui_api.py`
- Do NOT write any new helper scripts. Do NOT modify existing ones.

### Input
- {story_path}/story_manifest.json → characters section for descriptions
- Model: flux2-dev-turbo-fp8mixed.safetensors (NOT flux1-dev)
- Style from manifest: e.g. "3D model" per user request

### Success Criteria
- {story_path}/characters/<char>_reference_sheet.png exists for every character (one per character)

### Stop
When reference sheets are successfully rendered, complete. No re-renders.

### Failure Budget
If you hit 80 turns without finishing, BLOCK with reason "T3 budget exhausted".
"""
    out = run([
        "hermes", "kanban", "create", "T3: Render character sheets",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T2"],
        "--max-runtime", "90m",
        "--max-retries", "3",
        "--body", t3_body,
    ])
    tasks["T3"] = parse_task_id(out)

    # T4: ★ APPROVAL GATE: character sheets ★
    t4_body = f"""## Task: T4 — APPROVAL GATE: Character sheet review
**Story:** {slug}
**Workdir:** {story_path}

The orchestrator will present character sheet paths to the user.
User reviews the character reference sheets located in {story_path}/characters/.
Run: `hermes kanban unblock {tasks["T3"]}` (or the T4 task ID) to proceed when you approve them.
"""
    out = run([
        "hermes", "kanban", "create", "T4: ★ APPROVAL GATE: character sheets ★",
        "--assignee", "user",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T3"],
        "--initial-status", "blocked",
        "--max-runtime", "1440m",
        "--body", t4_body,
    ])
    tasks["T4"] = parse_task_id(out)

    # T5: Draft FF prompts
    t5_body = f"""## Task: T5 — Draft FF prompts
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Read {story_path}/story_manifest.json and character sheets.
2. Write/update {story_path}/filmmaking_prompt.json to define `first_frame_prompt` for each shot.

### Stop
When all first_frame_prompts are written, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T5: Draft FF prompts",
        "--assignee", "stv-t2i-writer",
        "--skill", "flux-t2i-prompting",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T4"],
        "--max-runtime", "40m",
        "--body", t5_body,
    ])
    tasks["T5"] = parse_task_id(out)

    # T6: Draft LF edit-mode prompts
    t6_body = f"""## Task: T6 — Draft LF edit prompts
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Read {story_path}/filmmaking_prompt.json and FF prompts.
2. Write/update {story_path}/filmmaking_prompt.json to define `last_frame_prompt` for each shot (using Edit-Instruction format).

### Stop
When all last_frame_prompts are written, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T6: Draft LF edit prompts",
        "--assignee", "stv-i2i-writer",
        "--skill", "flux-edit-prompting",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T5"],
        "--max-runtime", "40m",
        "--body", t6_body,
    ])
    tasks["T6"] = parse_task_id(out)

    # T7: Draft motion prompts + segment_duration
    t7_body = f"""## Task: T7 — Draft motion prompts
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Read {story_path}/filmmaking_prompt.json.
2. Update {story_path}/filmmaking_prompt.json to define `motion_prompt` and `overrides.segment_duration` per shot.

### Stop
When all motion prompts and segment durations are written, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T7: Draft motion prompts",
        "--assignee", "stv-motion-writer",
        "--skill", "ltx-motion-prompting",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T6"],
        "--max-runtime", "40m",
        "--body", t7_body,
    ])
    tasks["T7"] = parse_task_id(out)

    # T8: Pre-flight text audit
    t8_body = f"""## Task: T8 — Pre-flight text audit
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Perform audit on {story_path}/filmmaking_prompt.json.
2. Verify no frozen last-frame prompts, and check token counts.
3. Output audit report and verify correctness.

### Stop
When the pre-flight text audit is successfully completed and passed, mark done.
"""
    out = run([
        "hermes", "kanban", "create", "T8: Pre-flight text audit",
        "--assignee", "stv-reviewer",
        "--skill", "qc-image-review",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T7"],
        "--max-runtime", "30m",
        "--body", t8_body,
    ])
    tasks["T8"] = parse_task_id(out)

    # T9: Director final review of all prompts
    t9_body = f"""## Task: T9 — Director final review
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Verify shot rhythm, 180° line, and that no coverage gaps exist in the prompt JSON.
2. Confirm readiness for rendering.

### Stop
When director approves the prompts, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T9: Director final review",
        "--assignee", "stv-director",
        "--skill", "story-direction",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T8"],
        "--max-runtime", "45m",
        "--body", t9_body,
    ])
    tasks["T9"] = parse_task_id(out)

    # T10: Render FF + LF stills
    t10_body = f"""## Task: T10 — Render FF + LF stills
**Story:** {slug}
**Workdir:** {story_path}

### Setup
1. Source profile environment: `source ~/.hermes/profiles/stv-ops/.env`
2. Verify ComfyUI connection.

### Success Criteria
1. Render all First Frame and Last Frame stills using Flux 2 Dev Turbo.
2. Save stills to {story_path}/ff/ and {story_path}/lf/.

### Stop
When all stills are rendered, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T10: Render FF + LF stills",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T9"],
        "--max-runtime", "120m",
        "--max-retries", "3",
        "--body", t10_body,
    ])
    tasks["T10"] = parse_task_id(out)

    # T11: Per-image vision QC gate
    t11_body = f"""## Task: T11 — Per-image vision QC
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Perform image quality control and consistency review on all rendered stills.
2. Escalate any failures, report passing shots.

### Stop
When all checks are completed, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T11: Per-image vision QC gate",
        "--assignee", "stv-reviewer",
        "--skill", "qc-image-review",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T10"],
        "--max-runtime", "60m",
        "--body", t11_body,
    ])
    tasks["T11"] = parse_task_id(out)

    # T12: Render FFLF videos
    t12_body = f"""## Task: T12 — Render FFLF video
**Story:** {slug}
**Workdir:** {story_path}

### Setup
1. Source profile environment: `source ~/.hermes/profiles/stv-ops/.env`

### Success Criteria
1. Render video segments using LTX 2.3.
2. Save video segments to {story_path}/video/.

### Stop
When video rendering is complete, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T12: Render FFLF video",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T11"],
        "--max-runtime", "120m",
        "--max-retries", "3",
        "--body", t12_body,
    ])
    tasks["T12"] = parse_task_id(out)

    # T13: Continuity chain
    t13_body = f"""## Task: T13 — Continuity chain
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Extract tail frames from rendered video segments.
2. Re-render continuation shots to ensure visual transition continuity.

### Stop
When continuity passes, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T13: Continuity chain",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T12"],
        "--max-runtime", "90m",
        "--body", t13_body,
    ])
    tasks["T13"] = parse_task_id(out)

    # T14: Final stitch: ffmpeg concat
    t14_body = f"""## Task: T14 — Final ffmpeg stitch
**Story:** {slug}
**Workdir:** {story_path}

### Success Criteria
1. Concatenate all final video segments into a single cohesive film: {story_path}/final_film.mp4.
2. Clean up temporary directories and produce the final status report.

### Stop
When final film is stitched and verified, complete.
"""
    out = run([
        "hermes", "kanban", "create", "T14: Final stitch: ffmpeg concat",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        "--parent", tasks["T13"],
        "--max-runtime", "20m",
        "--body", t14_body,
    ])
    tasks["T14"] = parse_task_id(out)

    return tasks


def main():
    parser = argparse.ArgumentParser(description="Build Kanban board for story production")
    parser.add_argument("story_path", help="Path to story directory")
    parser.add_argument("--mode", choices=["v0.1-hybrid", "v1.0-native"],
                       default="v0.1-hybrid", help="Orchestrator mode (default: v0.1-hybrid)")
    parser.add_argument("--directors-coach", choices=["off", "pre-review", "per-shot"],
                       default="off", help="Director's coach level (v1.0 only)")
    parser.add_argument("--slug", help="Custom slug (default: derived from path)")
    parser.add_argument("--skip-preflight", action="store_true",
                       help="Skip pre-flight checks (NOT recommended)")
    args = parser.parse_args()

    story_path = Path(args.story_path).resolve()
    slug = args.slug or slugify(story_path.name)

    print(f"Story path: {story_path}")
    print(f"Slug: {slug}")
    print(f"Mode: {args.mode}")
    print()

    # Pre-flight
    if not args.skip_preflight:
        print("=== Pre-flight checks ===")
        checks = verify_preflight(str(story_path), args.mode)
        for check, status in checks.items():
            icon = "✅" if status else "❌"
            print(f"  {icon} {check}")
        if not all(checks.values()):
            print("\n❌ Pre-flight failed. Fix above issues or use --skip-preflight (not recommended).")
            sys.exit(1)
        print()

    # Init board
    print(f"=== Initializing board '{slug}' ===")
    init_board(slug)
    print()

    # Build tasks
    print(f"=== Building {args.mode} board ===")
    if args.mode == "v0.1-hybrid":
        tasks = build_v01_hybrid_board(str(story_path), slug)
    else:  # v1.0-native
        tasks = build_v10_native_board(str(story_path), slug)
    print(f"  Created {len(tasks)} tasks (linked atomically via parents)")
    print()

    # Dispatch
    print("=== Dispatching ===")
    run(["hermes", "kanban", "dispatch"])
    print()

    # Summary
    print("=" * 60)
    print(f"✅ Board '{slug}' created and dispatched")
    print(f"   Mode: {args.mode}")
    print(f"   Tasks: {len(tasks)}")
    print(f"   Board ID: {slug}")
    print()
    print("Monitor with:")
    print(f"  hermes kanban boards switch {slug}    # make this board active")
    print(f"  hermes kanban list                   # list tasks on active board")
    print(f"  hermes kanban tail <task-id>         # follow task events")
    print()
    if args.mode == "v0.1-hybrid":
        print("Note: T3 is the human approval gate. Watch for that one.")
    else:
        print("Note: T4 is the human approval gate (character sheets). Watch for that one.")


if __name__ == "__main__":
    main()
