#!/usr/bin/env python3
"""CLI for the global asset registry.

    python3 scripts/assetctl.py index [--root PATH] [--series NAME] [--dry-run]
    python3 scripts/assetctl.py plan --series NAME --episode N --needs FILE
    python3 scripts/assetctl.py resolve --asset-id ID
    python3 scripts/assetctl.py add --kind K --series S --entity E --variant V --lock L --path P
    python3 scripts/assetctl.py approve --asset-id ID [--by USER]
    python3 scripts/assetctl.py supersede --asset-id ID [--reason R]
    python3 scripts/assetctl.py doctor
    python3 scripts/assetctl.py usage --asset-id ID
    python3 scripts/assetctl.py list [--series NAME] [--status STATUS]

All mutations go through the locked, atomic-write path in
``assets_registry.GlobalAssetRegistry``.  ``--force-regen`` is intentionally
NOT a bare flag: it must name an ``asset_id`` (see ``supersede`` + ``add``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from assets_registry import (  # noqa: E402
    AssetNotFound,
    GlobalAssetRegistry,
    RegistryError,
    VALID_KINDS,
    VALID_STATUSES,
    make_asset_id,
)


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def cmd_index(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    root = args.root or ""
    if not root:
        # Default: walk all series under outputs/story-maker-v3/*/assets
        repo = SKILL_ROOT.parents[2]
        base = repo / "outputs" / "story-maker-v3"
        if not base.is_dir():
            print(f"no legacy outputs found at {base}", file=sys.stderr)
            return 1
        total = []
        for series_dir in sorted(base.iterdir()):
            assets = series_dir / "assets"
            if assets.is_dir():
                entries = reg.index_legacy(assets, series=series_dir.name, dry_run=args.dry_run)
                total.extend(entries)
                print(f"{series_dir.name}: {len(entries)} plates indexed")
        _print_json(total if args.dry_run else [{"asset_id": e["asset_id"], "status": e["status"]} for e in total])
        return 0
    entries = reg.index_legacy(root, series=args.series, dry_run=args.dry_run)
    print(f"{len(entries)} plates indexed")
    _print_json(entries)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    needs = json.loads(Path(args.needs).read_text(encoding="utf-8"))
    result = reg.plan(series=args.series, episode=args.episode, needed=needs)
    _print_json(result)
    print(
        f"reuse={len(result['reuse'])}  generate={len(result['generate'])}  "
        f"projected_cost=${result['projected_cost_usd']}",
        file=sys.stderr,
    )
    return 0 if not result["generate"] else 0  # exit 0 regardless; caller checks counts


def cmd_resolve(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    entry = reg.get(args.asset_id)
    if entry is None:
        print(f"not found: {args.asset_id}", file=sys.stderr)
        return 1
    _print_json(entry)
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    entry = reg.add(
        kind=args.kind,
        series=args.series,
        entity_id=args.entity,
        variant=args.variant,
        appearance_lock=args.lock,
        path=args.path,
        provider=args.provider,
        model=args.model,
        prompt_file=args.prompt_file,
        cost_usd=args.cost,
        notes=args.notes,
        shared=args.shared,
        status=args.status,
    )
    _print_json(entry)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    try:
        entry = reg.approve(args.asset_id, approved_by=args.by)
    except AssetNotFound:
        print(f"not found: {args.asset_id}", file=sys.stderr)
        return 1
    _print_json(entry)
    return 0


def cmd_supersede(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    try:
        entry = reg.supersede(args.asset_id, reason=args.reason)
    except AssetNotFound:
        print(f"not found: {args.asset_id}", file=sys.stderr)
        return 1
    _print_json(entry)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    issues = reg.doctor()
    if issues:
        _print_json(issues)
        print(f"{len(issues)} issue(s) found", file=sys.stderr)
        return 1
    print("OK — all version hashes match files on disk")
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    entry = reg.get(args.asset_id)
    if entry is None:
        print(f"not found: {args.asset_id}", file=sys.stderr)
        return 1
    _print_json(entry.get("usage", []))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    reg = GlobalAssetRegistry()
    entries = reg.list_series(args.series) if args.series else list(reg._data.values())
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]
    summary = [
        {
            "asset_id": e["asset_id"],
            "kind": e["kind"],
            "series": e["series"],
            "variant": e["variant"],
            "status": e["status"],
            "current": e.get("current"),
            "versions": len(e.get("versions", [])),
        }
        for e in entries
    ]
    _print_json(summary)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Global asset registry CLI")
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("index", help="Index legacy plates in place")
    pi.add_argument("--root", default=None, help="legacy assets root (default: auto-detect)")
    pi.add_argument("--series", default=None)
    pi.add_argument("--dry-run", action="store_true")
    pi.set_defaults(func=cmd_index)

    pp = sub.add_parser("plan", help="Classify needed assets as reuse or generate")
    pp.add_argument("--series", required=True)
    pp.add_argument("--episode", type=int, required=True)
    pp.add_argument("--needs", required=True, help="JSON file of needed assets")
    pp.set_defaults(func=cmd_plan)

    pr = sub.add_parser("resolve", help="Show an asset entry")
    pr.add_argument("--asset-id", required=True)
    pr.set_defaults(func=cmd_resolve)

    pa = sub.add_parser("add", help="Add a new asset or version")
    pa.add_argument("--kind", required=True, choices=VALID_KINDS)
    pa.add_argument("--series", required=True)
    pa.add_argument("--entity", required=True, dest="entity")
    pa.add_argument("--variant", default="base")
    pa.add_argument("--lock", required=True, help="appearance lock string")
    pa.add_argument("--path", required=True)
    pa.add_argument("--provider", default="")
    pa.add_argument("--model", default="")
    pa.add_argument("--prompt-file", default="")
    pa.add_argument("--cost", type=float, default=0.0)
    pa.add_argument("--notes", default="")
    pa.add_argument("--shared", action="store_true")
    pa.add_argument("--status", default="draft", choices=VALID_STATUSES)
    pa.set_defaults(func=cmd_add)

    pap = sub.add_parser("approve", help="Promote latest version to approved")
    pap.add_argument("--asset-id", required=True)
    pap.add_argument("--by", default="user")
    pap.set_defaults(func=cmd_approve)

    psu = sub.add_parser("supersede", help="Mark an approved asset as superseded")
    psu.add_argument("--asset-id", required=True)
    psu.add_argument("--reason", default="")
    psu.set_defaults(func=cmd_supersede)

    pd = sub.add_parser("doctor", help="Verify all version hashes match files")
    pd.set_defaults(func=cmd_doctor)

    pu = sub.add_parser("usage", help="Show usage history for an asset")
    pu.add_argument("--asset-id", required=True)
    pu.set_defaults(func=cmd_usage)

    pl = sub.add_parser("list", help="List assets")
    pl.add_argument("--series", default=None)
    pl.add_argument("--status", default=None, choices=VALID_STATUSES)
    pl.set_defaults(func=cmd_list)

    return p


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.func(args)
    except RegistryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
