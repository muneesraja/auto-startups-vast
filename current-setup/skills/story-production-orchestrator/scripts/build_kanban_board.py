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


def verify_preflight(story_path: str) -> dict:
    """Verify all pre-flight conditions. Returns dict of status per check."""
    checks = {}

    # 1. Profiles
    out = run(["hermes", "kanban", "assignees"])
    required = ["stv-director", "stv-t2i-writer", "stv-i2i-writer",
                "stv-motion-writer", "stv-reviewer", "stv-ops"]
    checks["profiles"] = all(p in out for p in required)

    # 2. ComfyUI URL
    comfyui_url = os.environ.get("COMFYUI_URL") or run(
        ["bash", "-c", "grep COMFYUI_URL ~/.hermes/.env | head -1 | cut -d= -f2- | tr -d '\"'"]
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
    checks["manifest_exists"] = (story_path_p / "story_manifest.json").exists()

    return checks


def init_board(slug: str):
    """Create the kanban board (idempotent)."""
    # First, init the kanban DB if needed
    run(["hermes", "kanban", "init"], check=False)
    # Then create the board (may already exist, that's OK)
    run(["hermes", "kanban", "boards", "create", slug, "--switch"], check=False)


def build_v01_hybrid_board(story_path: str, slug: str) -> dict:
    """Build 4-task v0.1 hybrid board."""
    tasks = {}

    # T1: Run monolith
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

    # T2: QC
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
        
        "--max-runtime", "30m",
        "--body", t2_body,
    ])
    tasks["T2"] = parse_task_id(out)

    # T3: User gate
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
        
        "--max-runtime", "1440m",  # 24h
        "--body", t3_body,
    ])
    tasks["T3"] = parse_task_id(out)

    # T4: Cleanup
    t4_body = f"""## Task: Cleanup + archive
**Mode:** v0.1-hybrid
**Story:** {slug}
**Blocked on:** T3

### Instructions
1. Verify final_film.mp4 exists and is non-zero size
2. Move artifacts to {story_path}/final/
3. Generate summary report with cost + timings
4. Mark task complete with final film path in metadata
"""
    out = run([
        "hermes", "kanban", "create", "T4: Cleanup + archive",
        "--assignee", "stv-ops",
        "--skill", "comfyui-ops",
        "--workspace", f"dir:{story_path}",
        
        "--max-runtime", "15m",
        "--body", t4_body,
    ])
    tasks["T4"] = parse_task_id(out)

    return tasks


def build_v10_native_board(story_path: str, slug: str) -> dict:
    """Build 12-task v1.0 native board."""
    tasks = {}

    # (Similar structure but with 12 tasks per SKILL.md §4)
    # For brevity, generating abbreviated body templates

    task_specs = [
        ("T1", "stv-ops", "comfyui-ops", "Init project + verify ComfyUI/models"),
        ("T2", "stv-director", "story-direction", "Story expansion → story_manifest.json v3"),
        ("T3", "stv-t2i-writer", "flux-t2i-prompting", "Generate character sheets (T2I Flux 2)"),
        ("T4", "user", None, "★ APPROVAL GATE: character sheets ★"),
        ("T5", "stv-t2i-writer", "flux-t2i-prompting", "Draft FF prompts (one per shot)"),
        ("T6", "stv-i2i-writer", "flux-edit-prompting", "Draft LF edit-mode prompts"),
        ("T7", "stv-motion-writer", "ltx-motion-prompting", "Draft motion prompts + segment_duration"),
        ("T8", "stv-reviewer", "qc-image-review", "Pre-flight text audit (FROZEN/SUBTLE/RADICAL)"),
        ("T9", "stv-ops", "comfyui-ops", "Render Phase 1: FF + LF stills"),
        ("T10", "stv-reviewer", "qc-image-review", "Per-image vision QC gate"),
        ("T11", "stv-ops", "comfyui-ops", "Render Phase 2/3: FFLF video"),
        ("T12", "stv-ops", "comfyui-ops", "Final stitch: ffmpeg concat"),
    ]

    for tid, assignee, skill, desc in task_specs:
        body = f"""## Task: {desc}
**Mode:** v1.0-native
**Story:** {slug}
**Assignee:** {assignee}
"""
        if skill:
            body += f"**Skill:** {skill}\n"
        body += f"\n### Workdir\n{story_path}\n"

        args = [
            "hermes", "kanban", "create", f"{tid}: {desc}",
            "--assignee", assignee,
            "--workspace", f"dir:{story_path}",
            
            "--max-runtime", "60m",
            "--body", body,
        ]
        if skill:
            args.insert(args.index("--max-runtime"), "--skill")
            args.insert(args.index("--max-runtime"), skill)

        out = run(args)
        tasks[tid] = parse_task_id(out)

    return tasks


def link_tasks(tasks: dict, links: list):
    """Create parent-child links. links is list of (parent, child) tuples."""
    for parent_tid, child_tid in links:
        parent_id = tasks[parent_tid]
        child_id = tasks[child_tid]
        run([
            "hermes", "kanban", "link", parent_id, child_id,
        ])


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
        checks = verify_preflight(str(story_path))
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
        links = [("T1", "T2"), ("T2", "T3"), ("T3", "T4")]
    else:  # v1.0-native
        tasks = build_v10_native_board(str(story_path), slug)
        links = [
            ("T1", "T2"), ("T2", "T3"), ("T3", "T4"),
            ("T4", "T5"), ("T5", "T6"), ("T6", "T7"),
            ("T7", "T8"), ("T8", "T9"), ("T9", "T10"),
            ("T10", "T11"), ("T11", "T12"),
        ]
    print(f"  Created {len(tasks)} tasks")

    # Link
    print("=== Linking parent-child ===")
    link_tasks(tasks, links)
    print(f"  Created {len(links)} parent-child links")
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
    print(f"   Links: {len(links)}")
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
