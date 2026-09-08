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
from .resolve import (Resolution, last_commit_touching, parse_anchor,
                      resolve, search_history)


@dataclass
class CheckResult:
    """Outcome of checking every anchor in the map."""

    resolutions: Dict[str, List[Resolution]] = field(default_factory=dict)
    unproven: List[str] = field(default_factory=list)
    unanchored: List[str] = field(default_factory=list)

    @property
    def broken(self) -> List[Resolution]:
        return [r for rs in self.resolutions.values() for r in rs if not r.ok]

    @property
    def ok(self) -> bool:
        return not self.broken


def check(requirements: List[Requirement], root: Path) -> CheckResult:
    """Resolve every anchor; collect breakages and coverage gaps."""
    result = CheckResult()
    for req in requirements:
        resolutions = [resolve(parse_anchor(a), root)
                       for a in req.implementation + req.tests]
        result.resolutions[req.id] = resolutions
        if not req.is_proven:
            result.unproven.append(req.id)
        if not req.is_anchored:
            result.unanchored.append(req.id)
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

    total = len(requirements)
    anchored = total - len(result.unanchored)
    proven = total - len(result.unproven)
    out.append(f"{total} requirements | {anchored} with implementation | "
               f"{proven} with tests")

    if result.unanchored:
        out.append(f"  no implementation anchor: {', '.join(result.unanchored)}")
    if result.unproven:
        out.append(f"  UNPROVEN (no test): {', '.join(result.unproven)}")

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
        if req.note:
            for line in _wrap(f"note: {req.note}", 74):
                out.append(f"  {line}")

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
