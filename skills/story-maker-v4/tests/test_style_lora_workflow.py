"""Structural tests for the MiniMax H3 R2V + style-LoRA workflow graph.

The renderer loads this graph via ``MINIMAX_H3_WORKFLOW``, so a broken link
table would only surface as a ComfyUI error hours into a render.
"""

from __future__ import annotations

import json
import os

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
WORKFLOW_PATH = os.path.join(
    _REPO_ROOT, "workflows", "comfyui", "minimax-h3-r2v-style-lora.json"
)


def _load() -> dict:
    with open(WORKFLOW_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _by_id(wf: dict) -> dict[int, dict]:
    return {n["id"]: n for n in wf["nodes"]}


def test_workflow_exists_and_links_are_consistent():
    wf = _load()
    link_by_id = {l[0]: l for l in wf["links"]}
    nodes = _by_id(wf)

    for node in wf["nodes"]:
        for inp in node.get("inputs") or []:
            link_id = inp.get("link")
            if link_id is None:
                continue
            assert link_id in link_by_id, f"node {node['id']} input {inp['name']} dangling"
            _, origin_id, _, target_id, _, _ = link_by_id[link_id]
            assert target_id == node["id"]
            assert origin_id in nodes
        for out in node.get("outputs") or []:
            for link_id in out.get("links") or []:
                assert link_id in link_by_id, f"node {node['id']} output dangling"
                assert link_by_id[link_id][1] == node["id"]


def test_lora_chain_sits_between_unet_and_attention_patch():
    wf = _load()
    nodes = _by_id(wf)
    link_by_id = {l[0]: l for l in wf["links"]}

    loras = [n for n in wf["nodes"] if n["type"] == "LoraLoaderModelOnly"]
    assert len(loras) == 3, "three switchable style-LoRA slots are expected"

    unet = next(n for n in wf["nodes"] if n["type"] == "UNETLoader")
    sage = next(n for n in wf["nodes"] if n["type"] == "PathchSageAttentionKJ")

    # Walk back from the attention patch through the LoRA chain to the UNET.
    seen: list[int] = []
    current = link_by_id[sage["inputs"][0]["link"]][1]
    while nodes[current]["type"] == "LoraLoaderModelOnly":
        seen.append(current)
        current = link_by_id[nodes[current]["inputs"][0]["link"]][1]
    assert current == unet["id"]
    assert sorted(seen) == sorted(n["id"] for n in loras)


def test_scheduler_still_reads_the_unpatched_unet():
    # Matches Minimax_h3_4_step_lora.json: sigmas come from the raw UNET, not
    # from the LoRA-patched model.
    wf = _load()
    nodes = _by_id(wf)
    link_by_id = {l[0]: l for l in wf["links"]}
    scheduler = next(n for n in wf["nodes"] if n["type"] == "BasicScheduler")
    model_link = next(i for i in scheduler["inputs"] if i["name"] == "model")["link"]
    assert nodes[link_by_id[model_link][1]]["type"] == "UNETLoader"


def test_lora_filenames_match_the_setup_script():
    wf = _load()
    setup = os.path.join(
        _REPO_ROOT, "workflows", "setup", "minimax-h3-r2v-style-lora.sh"
    )
    with open(setup, encoding="utf-8") as fh:
        script = fh.read()
    for node in wf["nodes"]:
        if node["type"] != "LoraLoaderModelOnly":
            continue
        filename, strength = node["widgets_values"][:2]
        assert filename in script, f"{filename} is not installed by the setup script"
        assert 0.0 <= float(strength) <= 1.5
