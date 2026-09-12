#!/usr/bin/env python3
"""V5 asset registry CLI — thin wrapper over the h3 GlobalAssetRegistry.

    python3 scripts/assetctl.py --run-dir <run> list [--status draft]
    python3 scripts/assetctl.py --run-dir <run> approve --entity char_01 [--kind character_plate]
    python3 scripts/assetctl.py --run-dir <run> approve-all        # GATE 1 promotion
    python3 scripts/assetctl.py --run-dir <run> supersede --entity char_01 --reason ...
    python3 scripts/assetctl.py --run-dir <run> doctor
    python3 scripts/assetctl.py --run-dir <run> show --entity char_01

``--run-dir`` locates the story's shared assets dir (``<run>/../assets``,
overridable with ``--assets-dir``). The registry file lives at
``<assets-dir>/asset_registry.json``; a V1 flat registry is migrated to the
h3 schema on first open (backup: ``asset_registry.v1.bak.json``).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT))

from tools.asset_registry_v2 import RegistryV2  # noqa: E402


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _registry(args: argparse.Namespace) -> RegistryV2:
    run_dir = os.path.abspath(args.run_dir)
    assets_dir = args.assets_dir or os.path.join(
        os.path.dirname(run_dir), "assets"
    )
    return RegistryV2(run_dir, assets_dir, allow_draft=True)


def cmd_list(args: argparse.Namespace) -> int:
    reg = _registry(args)
    entries = [
        e for e in reg.data.values() if e.get("series") == reg.series
    ]
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]
    if args.kind:
        entries = [e for e in entries if e.get("kind") == args.kind]
    _print_json(
        [
            {
                "asset_id": e["asset_id"],
                "kind": e["kind"],
                "entity_id": e["entity_id"],
                "variant": e["variant"],
                "status": e["status"],
                "versions": len(e.get("versions", [])),
                "origin": e.get("origin"),
            }
            for e in sorted(entries, key=lambda x: x["asset_id"])
        ]
    )
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    reg = _registry(args)
    e = reg._find(args.kind, args.entity)
    if e is None:
        print(f"not found: {args.kind}/{args.entity}", file=sys.stderr)
        return 1
    _print_json(e)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    reg = _registry(args)
    e = reg._find(args.kind, args.entity)
    if e is None:
        print(f"not found: {args.kind}/{args.entity}", file=sys.stderr)
        return 1
    _print_json(reg.approve(e["asset_id"], approved_by=args.by))
    return 0


def cmd_approve_all(args: argparse.Namespace) -> int:
    reg = _registry(args)
    promoted = reg.approve_all_drafts(approved_by=args.by)
    print(f"approved {len(promoted)} asset(s)")
    _print_json(promoted)
    # GATE 1 → assets_approved status transition.
    from tools.episode_spec import set_index_production, set_production_status

    run_dir = os.path.abspath(args.run_dir)
    set_production_status(run_dir, "assets_approved")
    spec_path = os.path.join(run_dir, "episode_spec.json")
    if os.path.isfile(spec_path):
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        set_index_production(
            os.path.dirname(run_dir), spec.get("episode", 0),
            "assets_approved", run_dir=run_dir,
        )
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    reg = _registry(args)
    e = reg._find(args.kind, args.entity)
    if e is None:
        print(f"not found: {args.kind}/{args.entity}", file=sys.stderr)
        return 1
    _print_json(reg._reg.supersede(e["asset_id"], reason=args.reason))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    reg = _registry(args)
    issues = reg.doctor()
    if issues:
        _print_json(issues)
        print(f"{len(issues)} issue(s) found", file=sys.stderr)
        return 1
    print("OK — registry clean")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="V5 asset registry CLI")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--assets-dir", default=None)
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list")
    pl.add_argument("--status", default=None)
    pl.add_argument("--kind", default=None)
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("show")
    ps.add_argument("--entity", required=True)
    ps.add_argument("--kind", default="character_plate")
    ps.set_defaults(func=cmd_show)

    pa = sub.add_parser("approve")
    pa.add_argument("--entity", required=True)
    pa.add_argument("--kind", default="character_plate")
    pa.add_argument("--by", default="user")
    pa.set_defaults(func=cmd_approve)

    paa = sub.add_parser("approve-all", help="Promote all drafts (GATE 1)")
    paa.add_argument("--by", default="gate-1")
    paa.set_defaults(func=cmd_approve_all)

    psu = sub.add_parser("supersede")
    psu.add_argument("--entity", required=True)
    psu.add_argument("--kind", default="character_plate")
    psu.add_argument("--reason", default="")
    psu.set_defaults(func=cmd_supersede)

    pd = sub.add_parser("doctor")
    pd.set_defaults(func=cmd_doctor)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
