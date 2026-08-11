#!/usr/bin/env python3
"""
fix_get_set_nodes.py - Rewire KJNodes-style GetNode/SetNode bus patterns
into direct connections, so the workflow no longer requires any GetNode/SetNode pack.

PROBLEM:
  Many third-party workflows (SCAIL-2, ComfyUI-WanAnimatePreprocess wrappers, etc.) use
  KJNodes SetNode as a "named bus" and GetNode to read from that bus by name. KJNodes
  itself does NOT export these as Python node classes - they are a UI feature only. When
  the workflow JSON is loaded, the Set/Get nodes show as "Missing Node Type" and the
  entire downstream graph (WanSCAILToVideo, BasicScheduler, VHS_VideoCombine, etc.)
  silently loses its inputs.

DETECTION:
  - Workflow has GetNode / SetNode nodes
  - /object_info on the running ComfyUI does not contain "GetNode" or "SetNode" classes
  - KJNodes (kijai/ComfyUI-KJNodes) __init__.py does not import GetNode/SetNode classes
  - ComfyUI-Easy-Use (yolain/ComfyUI-Easy-Use) removed easy getNode/easy setNode in 2026

FIX:
  For each (SetNode name, GetNode name) pair:
    1. Find the upstream source of the SetNode (the node that feeds it)
    2. Replicate each GetNode output link, replacing source (GetNode) with the
       SetNode upstream source
    3. Delete all SetNode and GetNode nodes + their internal links
    4. Renumber link IDs sequentially

USAGE:
  python3 fix_get_set_nodes.py <workflow.json> [-o <output.json>]
  python3 fix_get_set_nodes.py <workflow.json> -i   # overwrite in place
"""
import sys
import json
import argparse


def rewire(wf):
    set_nodes_list = [n for n in wf["nodes"] if n["type"] == "SetNode"]
    get_nodes_list = [n for n in wf["nodes"] if n["type"] == "GetNode"]
    set_nodes = {n["widgets_values"][0]: n for n in set_nodes_list}
    links_by_id = {l[0]: l for l in wf["links"]}
    upstream_source = {link[0]: (link[1], link[2]) for link in wf["links"]}

    new_links = []
    skipped = []
    for gn in get_nodes_list:
        name = gn["widgets_values"][0]
        if name not in set_nodes:
            skipped.append(
                f"GetNode id={gn['id']} name='{name}' - no SetNode pair"
            )
            continue
        upstream_lid = set_nodes[name]["inputs"][0].get("link")
        if upstream_lid is None:
            skipped.append(
                f"SetNode '{name}' has no upstream link - skipping GetNode {gn['id']}"
            )
            continue
        src_node, src_slot = upstream_source[upstream_lid]
        upstream_type = set_nodes[name]["inputs"][0].get("type")
        for out_port in gn.get("outputs", []):
            for link_id in (out_port.get("links") or []):
                link = links_by_id[link_id]
                _, _, _, dst, dst_slot, _ = link
                new_links.append(
                    [link_id, src_node, src_slot, dst, dst_slot, upstream_type]
                )

    if skipped:
        print(
            f"WARN: Skipped {len(skipped)} GetNode entries:",
            file=sys.stderr,
        )
        for s in skipped:
            print(f"   {s}", file=sys.stderr)

    removed_nodes = {
        n["id"] for n in wf["nodes"] if n["type"] in ("GetNode", "SetNode")
    }
    removed_links = {
        link[0]
        for link in wf["links"]
        if link[1] in removed_nodes or link[3] in removed_nodes
    }

    new_nodes = [n for n in wf["nodes"] if n["id"] not in removed_nodes]
    new_links_full = [
        l for l in wf["links"] if l[0] not in removed_links
    ] + new_links

    seen = set()
    deduped = []
    for l in new_links_full:
        key = (l[1], l[2], l[3], l[4])
        if key not in seen:
            seen.add(key)
            deduped.append(l)
    new_links_full = deduped

    old_id_to_new = {}
    for new_id, l in enumerate(new_links_full, start=1):
        old_id_to_new[l[0]] = new_id
        l[0] = new_id

    for n in new_nodes:
        for inp in n.get("inputs", []):
            if inp.get("link") in old_id_to_new:
                inp["link"] = old_id_to_new[inp["link"]]

    new_wf = dict(wf)
    new_wf["nodes"] = new_nodes
    new_wf["links"] = new_links_full
    new_wf["last_node_id"] = max(n["id"] for n in new_nodes)
    new_wf["last_link_id"] = max(l[0] for l in new_links_full)
    return new_wf, {
        "original_nodes": len(wf["nodes"]),
        "fixed_nodes": len(new_wf["nodes"]),
        "original_links": len(wf["links"]),
        "fixed_links": len(new_wf["links"]),
        "removed_nodes": len(removed_nodes),
        "added_rewires": len(new_links),
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("workflow", help="Input workflow JSON path")
    p.add_argument("-o", "--output", help="Output path (default: <input>.fixed.json)")
    p.add_argument(
        "-i", "--in_place", action="store_true", help="Overwrite input file"
    )
    args = p.parse_args()

    with open(args.workflow) as f:
        wf = json.load(f)

    has_gs = any(n["type"] in ("GetNode", "SetNode") for n in wf["nodes"])
    if not has_gs:
        print(f"No GetNode/SetNode found in {args.workflow} - nothing to do")
        sys.exit(0)

    new_wf, stats = rewire(wf)
    out = (
        args.workflow
        if args.in_place
        else (args.output or args.workflow.replace(".json", ".fixed.json"))
    )
    with open(out, "w") as f:
        json.dump(new_wf, f, indent=2)

    print(f"OK Rewrote {args.workflow} -> {out}")
    print(
        f"   Nodes: {stats['original_nodes']} -> {stats['fixed_nodes']} "
        f"(removed {stats['removed_nodes']} Get/Set)"
    )
    print(
        f"   Links: {stats['original_links']} -> {stats['fixed_links']} "
        f"(added {stats['added_rewires']} rewires)"
    )
