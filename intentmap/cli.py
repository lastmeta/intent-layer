"""
Command line: `python -m intentmap <command>`.

    check     resolve every anchor; exit 1 if any is broken   (CI / pre-commit)
    show      print the description with its anchors resolved to line numbers
    where     print the current location of one anchor
    orphans   requirements with no anchors; symbols no requirement claims
    stats     one-line coverage summary
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .model import MapError, load_map
from .report import (check, find_orphan_symbols, format_check, format_show)
from .resolve import (last_commit_touching, parse_anchor, pin_at_head,
                      resolve, search_history)

DEFAULT_MAP = 'map/intent-map.yaml'


def _load(args):
    root = Path(args.root).resolve()
    map_path = Path(args.map)
    if not map_path.is_absolute():
        map_path = root / map_path
    return root, load_map(map_path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='intentmap',
        description='Keep a plain-language description anchored to the code '
                    'that implements it and the tests that prove it.')
    parser.add_argument('--map', default=DEFAULT_MAP,
                        help=f'map file (default: {DEFAULT_MAP})')
    parser.add_argument('--root', default='.',
                        help='repository root the anchors are relative to')
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('check', help='verify every anchor resolves (exit 1 if not)')

    p_pin = sub.add_parser(
        'pin', help='print an anchor pinned to the current commit and lines')
    p_pin.add_argument('anchor', help='path::symbol')

    sub.add_parser('drift',
                   help='which pinned line ranges have changed since pinning')

    p_show = sub.add_parser('show', help='print the description with anchors')
    p_show.add_argument('id', nargs='?', help='show only this requirement')

    p_where = sub.add_parser('where', help='locate one anchor right now')
    p_where.add_argument('anchor', help='path::symbol')

    p_orphans = sub.add_parser('orphans', help='unbuilt claims, unclaimed code')
    p_orphans.add_argument('--source', action='append', default=None,
                           help='source dir to scan (repeatable)')

    sub.add_parser('stats', help='one-line coverage summary')

    args = parser.parse_args(argv)

    try:
        root, requirements = _load(args)
    except MapError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.command == 'check':
        result = check(requirements, root)
        print(format_check(requirements, result, root))
        return 0 if result.ok else 1

    if args.command == 'pin':
        anchor = parse_anchor(args.anchor)
        pinned = pin_at_head(anchor, root)
        if pinned is None:
            print(f"cannot pin {anchor}: symbol not found, or not a git "
                  f"repository", file=sys.stderr)
            return 1
        print(pinned)
        return 0

    if args.command == 'drift':
        result = check(requirements, root)
        pinned_total = sum(len(ds) for ds in result.drifts.values())
        for req_id, drifts in result.drifts.items():
            for drift in drifts:
                if drift.needs_review:
                    print(f"{req_id}: {drift.anchor}")
                    for commit in drift.commits[:3]:
                        print(f"    touched by: {commit}")
                elif not drift.checked:
                    print(f"{req_id}: {drift.anchor}\n    unchecked "
                          f"({drift.reason})")
        if not result.drifted:
            print(f"no drift -- {pinned_total} pinned range(s) unchanged "
                  f"since they were pinned")
        return 0

    if args.command == 'show':
        if args.id and not any(r.id == args.id for r in requirements):
            print(f"error: no requirement {args.id}", file=sys.stderr)
            return 2
        print(format_show(requirements, root, only=args.id), end='')
        return 0

    if args.command == 'where':
        anchor = parse_anchor(args.anchor)
        res = resolve(anchor, root)
        if res.ok:
            print(f"{anchor.path}:{res.line}"
                  f"{'  ' + anchor.symbol if anchor.symbol else ''}")
            commit = last_commit_touching(root, anchor.path)
            if commit:
                print(f"last commit: {commit}")
            return 0
        print(f"not found: {anchor} ({res.reason})", file=sys.stderr)
        if anchor.symbol:
            for finding in search_history(root, anchor.symbol):
                print(f"  history: {finding}", file=sys.stderr)
        return 1

    if args.command == 'orphans':
        result = check(requirements, root)
        unbuilt = [r for r in result.unanchored]
        if unbuilt:
            print("requirements with no implementation anchor:")
            for req_id in unbuilt:
                print(f"  {req_id}")
        sources = args.source or ['.']
        symbols = find_orphan_symbols(requirements, root, sources)
        if symbols:
            print(f"\nsymbols no requirement claims ({len(symbols)}):")
            for symbol in symbols:
                print(f"  {symbol}")
        if not unbuilt and not symbols:
            print("no orphans in either direction")
        return 0

    if args.command == 'stats':
        result = check(requirements, root)
        total = len(requirements)
        print(f"{total} requirements | "
              f"{total - len(result.unanchored)} implemented | "
              f"{total - len(result.unproven)} proven | "
              f"{len(result.broken)} broken anchors")
        return 0

    return 2


if __name__ == '__main__':
    raise SystemExit(main())
