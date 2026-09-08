"""
Checking the map against reality, and reporting what it says.

Three questions this answers:
  check    -- is every anchor still real? (exit non-zero if not)
  show     -- what does the system claim to do, and what proves it?
  orphans  -- what is claimed but unbuilt, and built but unclaimed?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .model import Requirement
from .resolve import (Drift, Resolution, last_commit_touching, parse_anchor,
                      pin_drift, resolve, search_history)


@dataclass
class CheckResult:
    """Outcome of checking every anchor in the map."""

    resolutions: Dict[str, List[Resolution]] = field(default_factory=dict)
    drifts: Dict[str, List[Drift]] = field(default_factory=dict)
    unproven: List[str] = field(default_factory=list)
    unanchored: List[str] = field(default_factory=list)
    unexplained: List[str] = field(default_factory=list)

    @property
    def broken(self) -> List[Resolution]:
        return [r for rs in self.resolutions.values() for r in rs if not r.ok]

    @property
    def drifted(self) -> List[Drift]:
        """Pinned line ranges that have changed since they were pinned."""
        return [d for ds in self.drifts.values() for d in ds if d.needs_review]

    @property
    def drifted_ids(self) -> List[str]:
        return [req_id for req_id, ds in self.drifts.items()
                if any(d.needs_review for d in ds)]

    @property
    def ok(self) -> bool:
        """Broken anchors fail the check; drift is flagged, not fatal."""
        return not self.broken


def check(requirements: List[Requirement], root: Path,
          with_drift: bool = True) -> CheckResult:
    """
    Resolve every anchor; collect breakages, drift, and coverage gaps.

    Drift is reported separately from breakage because they mean
    different things: a broken anchor is wrong *now*, while drift means
    the pinned lines changed and a human should decide whether the
    description still holds.
    """
    result = CheckResult()
    for req in requirements:
        anchors = [parse_anchor(a) for a in req.implementation + req.tests]
        result.resolutions[req.id] = [resolve(a, root) for a in anchors]
        if with_drift:
            result.drifts[req.id] = [pin_drift(a, root)
                                     for a in anchors if a.pinned]
        if not req.is_proven:
            result.unproven.append(req.id)
        if not req.is_anchored:
            result.unanchored.append(req.id)
        if not req.has_prose:
            result.unexplained.append(req.id)
    return result


def format_check(requirements: List[Requirement], result: CheckResult,
                 root: Path) -> str:
    """Human-readable check report, with repair hints for broken anchors."""
    by_id = {r.id: r for r in requirements}
    out: List[str] = []

    if result.broken:
        out.append(f"BROKEN ANCHORS ({len(result.broken)})")
        out.append("")
        for req_id, resolutions in result.resolutions.items():
            for res in resolutions:
                if res.ok:
                    continue
                out.append(f"  {req_id}: {res.anchor}")
                out.append(f"      {res.reason}")
                commit = last_commit_touching(root, res.anchor.path)
                if commit:
                    out.append(f"      last commit touching that path: {commit}")
                if res.anchor.symbol:
                    for finding in search_history(root, res.anchor.symbol):
                        out.append(f"      history: {finding}")
                out.append("")

    if result.drifted:
        out.append(f"PINNED LINES CHANGED -- review these ({len(result.drifted)})")
        out.append("")
        for req_id, drifts in result.drifts.items():
            for drift in drifts:
                if not drift.needs_review:
                    continue
                out.append(f"  {req_id}: {drift.anchor}")
                for commit in drift.commits[:3]:
                    out.append(f"      touched by: {commit}")
                out.append("      -> confirm the statement still holds, then "
                           "re-pin: intentmap pin " + str(drift.anchor).split('@')[0])
                out.append("")

    total = len(requirements)
    anchored = total - len(result.unanchored)
    proven = total - len(result.unproven)
    explained = total - len(result.unexplained)
    out.append(f"{total} requirements | {anchored} with implementation | "
               f"{proven} with tests | {explained} explained")

    if result.unanchored:
        out.append(f"  no implementation anchor: {', '.join(result.unanchored)}")
    if result.unproven:
        out.append(f"  UNPROVEN (no test): {', '.join(result.unproven)}")
    if result.unexplained:
        out.append(f"  no 'how' prose: {', '.join(result.unexplained)}")
    if result.drifted_ids:
        out.append(f"  pinned lines changed: {', '.join(result.drifted_ids)}")

    out.append("")
    out.append("OK -- every anchor resolves" if result.ok
               else "FAILED -- see broken anchors above")
    return "\n".join(out)


def format_show(requirements: List[Requirement], root: Path,
                only: Optional[str] = None, with_lines: bool = True) -> str:
    """
    The description as a report: every requirement, what implements it,
    what proves it, and whether those anchors currently resolve.
    """
    out: List[str] = []
    for req in requirements:
        if only and req.id != only:
            continue
        status = 'proven' if req.is_proven else 'UNPROVEN'
        out.append(f"{req.id} [{status}]")
        for line in _wrap(req.statement, 74):
            out.append(f"  {line}")

        # The map's prose: how the code delivers this, and what bites.
        if req.how:
            out.append("")
            for line in _wrap(f"how: {req.how}", 74):
                out.append(f"  {line}")
        if req.depends:
            for dep in req.depends:
                for line in _wrap(f"depends on: {dep}", 74):
                    out.append(f"  {line}")
        if req.gotchas:
            for line in _wrap(f"gotcha: {req.gotchas}", 74):
                out.append(f"  {line}")
        if req.note:
            for line in _wrap(f"note: {req.note}", 74):
                out.append(f"  {line}")
        if req.how or req.depends or req.gotchas or req.note:
            out.append("")

        for label, anchors in (('implements', req.implementation),
                               ('proves', req.tests)):
            for text in anchors:
                anchor = parse_anchor(text)
                res = resolve(anchor, root) if with_lines else None
                if res is None:
                    out.append(f"    {label}: {anchor}")
                elif res.ok:
                    where = f":{res.line}" if res.line else ""
                    out.append(f"    {label}: {anchor.path}{where}"
                               f"{' :: ' + anchor.symbol if anchor.symbol else ''}")
                else:
                    out.append(f"    {label}: {anchor}  <-- BROKEN ({res.reason})")
        if not req.implementation:
            out.append("    implements: (nothing anchored)")
        if not req.tests:
            out.append("    proves: (nothing anchored)")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def find_orphan_symbols(requirements: List[Requirement], root: Path,
                        source_dirs: List[str],
                        skip_private: bool = True) -> List[str]:
    """
    Public Python symbols in `source_dirs` that no requirement claims.

    This is the direction that catches code nobody asked for -- the
    counterpart to requirements nobody built.
    """
    import ast

    claimed = set()
    for req in requirements:
        for text in req.implementation + req.tests:
            anchor = parse_anchor(text)
            if anchor.symbol:
                claimed.add((anchor.path, anchor.symbol.split('.')[0]))

    orphans: List[str] = []
    for directory in source_dirs:
        base = Path(root) / directory
        if not base.exists():
            continue
        for path in sorted(base.rglob('*.py')):
            if '__pycache__' in path.parts:
                continue
            rel = str(path.relative_to(root))
            try:
                tree = ast.parse(path.read_text())
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                    continue
                if skip_private and node.name.startswith('_'):
                    continue
                if (rel, node.name) not in claimed:
                    orphans.append(f"{rel}::{node.name}")
    return orphans


def _wrap(text: str, width: int) -> List[str]:
    words, lines, current = text.split(), [], ''
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or ['']
