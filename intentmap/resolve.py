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
    """
    A parsed `path::symbol` reference, optionally pinned to a commit.

    The optional pin -- `path::symbol@<commit>:<start>-<end>` -- records
    the line range that satisfied the requirement *in that commit*. That
    is a historical fact, so it never needs rewriting as the file moves
    around it; it only becomes interesting when those specific lines
    themselves change, which `pin_drift` detects.
    """

    path: str
    symbol: Optional[str] = None
    commit: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None

    @property
    def pinned(self) -> bool:
        return self.commit is not None and self.start is not None

    def __str__(self) -> str:
        text = f"{self.path}::{self.symbol}" if self.symbol else self.path
        if self.pinned:
            span = (f"{self.start}-{self.end}" if self.end and self.end != self.start
                    else str(self.start))
            text += f"@{self.commit}:{span}"
        return text


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


_PIN_RE = re.compile(r'@(?P<commit>[0-9a-fA-F]{4,40}):'
                     r'(?P<start>\d+)(?:-(?P<end>\d+))?$')


def parse_anchor(text: str) -> Anchor:
    """
    Parse an anchor reference.

        path/to/file.py
        path/to/file.py::symbol
        path/to/file.py::symbol@a1b2c3d:120-165     (commit-pinned)
    """
    text = text.strip()
    commit = start = end = None

    pin = _PIN_RE.search(text)
    if pin:
        commit = pin.group('commit')
        start = int(pin.group('start'))
        end = int(pin.group('end') or start)
        text = text[:pin.start()]

    if '::' in text:
        path, _, symbol = text.partition('::')
        return Anchor(path.strip(), symbol.strip() or None, commit, start, end)
    return Anchor(text.strip(), None, commit, start, end)


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


@dataclass
class Drift:
    """Whether a pinned line range has changed since it was pinned."""

    anchor: Anchor
    checked: bool          # the pin could actually be evaluated
    changed: bool          # those lines changed since the pinned commit
    commits: List[str] = None   # commits that touched them
    reason: str = ''

    @property
    def needs_review(self) -> bool:
        return self.checked and self.changed


def pin_drift(anchor: Anchor, root: Path) -> Drift:
    """
    Has the pinned line range changed since the commit it was pinned at?

    This is what makes a pin worth having: it answers "do the docs
    actually need updating?" rather than nagging on every edit to the
    file. Unchanged lines mean the description still describes reality,
    however much the rest of the file moved.

    Implemented with `git log -L<start>,<end>:<file>`, which follows the
    range through history rather than comparing raw line numbers.
    """
    if not anchor.pinned:
        # nothing to compare against without a pin
        return Drift(anchor, False, False, [], 'not pinned')

    out = _git(root, 'log', '--format=%h %ad %s', '--date=short',
               f'-L{anchor.start},{anchor.end}:{anchor.path}',
               f'{anchor.commit}..HEAD')
    if out is None:
        return Drift(anchor, False, False, [],
                     'git unavailable, or commit/path unknown to this repo')

    commits = [line.strip() for line in out.splitlines()
               if line.strip() and not line.startswith(('diff', '---', '+++',
                                                        '@@', '+', '-', ' '))]
    return Drift(anchor, True, bool(commits), commits)


def pin_at_head(anchor: Anchor, root: Path) -> Optional[Anchor]:
    """
    Build a pin for `anchor` at the current commit: resolve the symbol,
    measure its extent, and stamp it with HEAD. Used by `intentmap pin`
    to create pins and to refresh one after a deliberate change.
    """
    res = resolve(anchor, root)
    if not res.ok or res.line is None:
        return None

    head = _git(root, 'rev-parse', '--short', 'HEAD')
    if not head:
        return None

    path = Path(root) / anchor.path
    end = res.line
    if path.suffix == '.py' and anchor.symbol:
        try:
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                      ast.ClassDef))
                        and node.name == anchor.symbol.split('.')[-1]
                        and node.lineno == res.line):
                    end = getattr(node, 'end_lineno', res.line) or res.line
                    break
        except (OSError, SyntaxError, UnicodeDecodeError):
            pass

    return Anchor(anchor.path, anchor.symbol, head.strip(), res.line, end)
