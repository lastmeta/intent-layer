"""
Resolving anchors to real code.

An anchor names a symbol, not a line: `path/to/file.py::function_name` or
`path/to/file.py::Class.method`. Line numbers are computed on demand by
parsing the file, so the map never needs updating when code moves down a
file -- only when the symbol itself is renamed, moved, or deleted, which
is exactly when a human should be looking at it anyway.

Python files are parsed with `ast` (exact). Other languages fall back to a
regex scan for common definition forms, so the pattern is useful in a
mixed-language repository without pretending to be a parser for every
language.
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Anchor:
    """A parsed `path::symbol` reference."""

    path: str
    symbol: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.path}::{self.symbol}" if self.symbol else self.path


@dataclass
class Resolution:
    """What resolving an anchor found (or didn't)."""

    anchor: Anchor
    exists: bool          # the file exists
    found: bool           # the symbol was found (True when no symbol asked)
    line: Optional[int] = None
    reason: str = ''      # why it failed, when it failed

    @property
    def ok(self) -> bool:
        return self.exists and self.found


def parse_anchor(text: str) -> Anchor:
    """Parse `path::symbol` (or a bare path) into an Anchor."""
    text = text.strip()
    if '::' in text:
        path, _, symbol = text.partition('::')
        return Anchor(path.strip(), symbol.strip() or None)
    return Anchor(text)


def _python_symbol_lines(source: str) -> dict:
    """{name: line} for every def/class in a Python file, plus Class.method."""
    lines = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return lines

    def visit(node, prefix=''):
        for child in getattr(node, 'body', []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                qualified = f"{prefix}{child.name}"
                lines.setdefault(child.name, child.lineno)
                lines[qualified] = child.lineno
                if isinstance(child, ast.ClassDef):
                    visit(child, f"{qualified}.")

    visit(tree)
    return lines


def _generic_symbol_line(source: str, symbol: str) -> Optional[int]:
    """Best-effort definition search for non-Python files."""
    name = re.escape(symbol.split('.')[-1])
    patterns = [
        rf'^\s*(?:export\s+)?(?:async\s+)?function\s+{name}\b',       # JS/TS
        rf'^\s*(?:export\s+)?(?:abstract\s+)?class\s+{name}\b',       # JS/TS/etc
        rf'^\s*(?:public|private|protected|static|\s)*[\w<>\[\]]+\s+{name}\s*\(',
        rf'^\s*(?:const|let|var)\s+{name}\s*=\s*(?:async\s*)?\(',     # JS arrow
        rf'^\s*func\s+(?:\([^)]*\)\s*)?{name}\b',                     # Go
        rf'^\s*(?:pub\s+)?fn\s+{name}\b',                             # Rust
        rf'^\s*def\s+{name}\b',                                       # Ruby/Python
    ]
    for lineno, line in enumerate(source.splitlines(), start=1):
        for pattern in patterns:
            if re.search(pattern, line):
                return lineno
    return None


def resolve(anchor: Anchor, root: Path) -> Resolution:
    """Resolve one anchor against the repository at `root`."""
    path = Path(root) / anchor.path
    if not path.exists():
        return Resolution(anchor, False, False, reason='file not found')
    if anchor.symbol is None:
        return Resolution(anchor, True, True, line=1)

    try:
        source = path.read_text()
    except (OSError, UnicodeDecodeError) as e:
        return Resolution(anchor, True, False, reason=f'cannot read file: {e}')

    if path.suffix == '.py':
        line = _python_symbol_lines(source).get(anchor.symbol)
    else:
        line = _generic_symbol_line(source, anchor.symbol)

    if line is None:
        return Resolution(anchor, True, False,
                          reason=f'symbol {anchor.symbol!r} not found in file')
    return Resolution(anchor, True, True, line=line)


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        result = subprocess.run(('git', *args), cwd=str(root), timeout=30,
                                capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def last_commit_touching(root: Path, path: str) -> Optional[str]:
    """`<short sha> <date> <subject>` for the last commit touching a path."""
    out = _git(root, 'log', '-1', '--format=%h %ad %s', '--date=short',
               '--', path)
    return out.strip() if out and out.strip() else None


def search_history(root: Path, symbol: str, limit: int = 3) -> List[str]:
    """
    Find where a symbol went after a rename or move.

    Searches the current tree first (the symbol usually still exists
    somewhere), then git history for commits that removed a line defining
    it -- which is where a stale anchor's answer normally lives.
    """
    findings: List[str] = []
    name = symbol.split('.')[-1]

    out = _git(root, 'grep', '-l', '-E',
               rf'(def|class|function|func|fn)\s+{re.escape(name)}\b')
    if out:
        for path in out.split():
            findings.append(f'defined now in {path}')
            if len(findings) >= limit:
                return findings

    out = _git(root, 'log', '-S', name, '--oneline', '-n', str(limit),
               '--format=%h %ad %s', '--date=short')
    if out:
        for line in out.strip().splitlines():
            if line.strip():
                findings.append(f'changed in {line.strip()}')
    return findings[:limit]
