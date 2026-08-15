#!/usr/bin/env python3
"""Recovery-branch assemble-only submission.

Uses the muted ``ChainManifestLoad → ChainAssemble`` branch (nodes 1707→1708)
to assemble already-rendered segments into a final video WITHOUT re-rendering.

Usage::

    python3 scripts/assemble.py --run-name <run_name> [--output final.mp4]

This is the S12 step of the pipeline. It requires that all clips have been
rendered and checkpointed under ``output/h3_chains/<run_name>/``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
STORY_MAKER = REPO_ROOT / "skills" / "story-maker-v3"

sys.path.insert(0, str(STORY_MAKER))
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import config  # type: ignore  # noqa: E402
from tools.comfyui_tools import curl_json, download_output, wait_for_prompt  # type: ignore  # noqa: E402
from tools.minimax_workflow import ui_workflow_to_api  # type: ignore  # noqa: E402

WORKFLOW_PATH = REPO_ROOT / "workflows" / "comfyui" / "minimax-h3-seamless-chain-global-refs.json"


def get_object_info() -> dict:
    import httpx

    resp = httpx.get(f"{config.COMFYUI_URL}/object_info", timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    p = argparse.ArgumentParser(description="Assemble-only (recovery branch) submission")
    p.add_argument("--run-name", required=True, help="The chain run name to assemble")
    p.add_argument("--output", default=None, help="Output filename (default: <run_name>_final.mp4)")
    p.add_argument("--workflow", default=str(WORKFLOW_PATH))
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    workflow_path = Path(args.workflow)
    if not workflow_path.is_file():
        print(f"workflow not found: {workflow_path}", file=sys.stderr)
        return 1
    ui_workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    # Enable the recovery branch: unmute ChainManifestLoad(1707) + ChainAssemble(1708)
    # and mute the main branch (1706) to avoid duplicate assembly.
    for node in ui_workflow.get("nodes", []):
        if node.get("id") in (1707, 1708):
            node["mode"] = 0  # active
        elif node.get("id") == 1706:
            node["mode"] = 2  # muted

    # Set the run_name on the manifest load node
    for node in ui_workflow.get("nodes", []):
        if node.get("type") == "MiniMaxH3ChainManifestLoad":
            widgets = node.setdefault("widgets_values", [])
            for i, w in enumerate(widgets):
                if isinstance(w, str) and ("run_name" in w or "silver" in w):
                    widgets[i] = args.run_name
                    break
            else:
                widgets.append(args.run_name)

    if args.dry_run:
        # Just dump the patched workflow
        out = Path(f"assemble_{args.run_name}_dryrun.json")
        out.write_text(json.dumps(ui_workflow, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"dry-run: wrote {out}")
        return 0

    object_info = get_object_info()
    api_prompt = ui_workflow_to_api(ui_workflow, object_info)

    resp = curl_json(
        f"{config.COMFYUI_URL}/prompt",
        {"prompt": api_prompt},
        auth=config.COMFYUI_AUTH,
    )
    prompt_id = resp.get("prompt_id")
    if not prompt_id:
        print(f"no prompt_id: {resp}", file=sys.stderr)
        return 1

    print(f"assembling {args.run_name}... prompt_id={prompt_id}")
    outputs = wait_for_prompt(config.COMFYUI_URL, prompt_id, auth=config.COMFYUI_AUTH)

    out_name = args.output or f"{args.run_name}_final.mp4"
    for node_id, node_output in outputs.get("outputs", {}).items():
        for o in node_output.get("gifs", []) + node_output.get("images", []):
            fname = o.get("filename", "")
            subfolder = o.get("subfolder", "")
            if fname:
                local = download_output(
                    fname, subfolder, o.get("type", "output"),
                    config.COMFYUI_URL, config.COMFYUI_AUTH,
                    Path(out_name),
                )
                print(f"downloaded: {local}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
