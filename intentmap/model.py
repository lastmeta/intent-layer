"""
The map file: parsing, validating, and addressing.

An entry looks like this (map/intent-map.yaml):

    - id: R-4
      statement: >
        Each requirement must be anchored to the code that implements it
        by file path plus function or class name.
      implementation:
        - intentmap/resolve.py::Anchor
        - intentmap/resolve.py::parse_anchor
      tests:
        - tests/test_resolve.py::TestParseAnchor
      note: optional free text

Anchors are `path::symbol` -- never line numbers, which change on every
edit and would rot the map continuously. `symbol` may be a bare function
or class name, or `Class.method`.

The parser is a deliberately small YAML subset (this file list, block
scalars, comments) so the tool has zero third-party dependencies and can
be dropped into any repository as-is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


class MapError(Exception):
    """Raised when the map file cannot be parsed or is structurally invalid."""


@dataclass
class Requirement:
    """
    One requirement and everything the map claims about it.

    The prose fields are the map's real content. Because anchors point at
    code instead of copying it, the map has room to explain -- `how` the
    anchored code produces the described behavior, what it `depends` on,
    and the `gotchas` a maintainer needs. These are expected to be
    retuned continually as understanding improves.
    """

    id: str
    statement: str
    implementation: List[str] = field(default_factory=list)
    tests: List[str] = field(default_factory=list)
    how: Optional[str] = None        # how the code produces the behavior
    depends: List[str] = field(default_factory=list)  # what it relies on
    gotchas: Optional[str] = None    # what will bite you
    note: Optional[str] = None
    line: int = 0  # line in the map file, for error messages
    source: str = ''  # which map file this came from (multi-file maps)

    @property
    def has_prose(self) -> bool:
        """Does the map explain this requirement, not just point at it?"""
        return bool(self.how)

    @property
    def is_proven(self) -> bool:
        """A requirement is proven when at least one test claims it."""
        return bool(self.tests)

    @property
    def is_anchored(self) -> bool:
        """A requirement is anchored when code claims to implement it."""
        return bool(self.implementation)


_ID_RE = re.compile(r'^[A-Za-z][A-Za-z0-9]*-\d+$')
_KEYS = {'id', 'statement', 'implementation', 'tests', 'how', 'depends',
         'gotchas', 'note'}


def _clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        value = value[1:-1]
    return value.strip()


def parse_map(text: str) -> List[Requirement]:
    """
    Parse the map file into requirements.

    Supports the subset the map format actually uses: a top-level list of
    entries, scalar values, `>` and `|` block scalars, list values, and
    `#` comments.
    """
    requirements: List[Requirement] = []
    current: Optional[dict] = None
    current_line = 0
    pending_key: Optional[str] = None
    block_lines: List[str] = []
    block_key: Optional[str] = None
    block_fold = True

    def flush_block():
        nonlocal block_key, block_lines
        if block_key is not None:
            joiner = ' ' if block_fold else '\n'
            current[block_key] = joiner.join(
                line.strip() for line in block_lines).strip()
            block_key, block_lines = None, []

    def flush_entry():
        nonlocal current
        if current is not None:
            flush_block()
            missing = {'id', 'statement'} - set(current)
            if missing:
                raise MapError(
                    f"entry near line {current_line} is missing: "
                    f"{', '.join(sorted(missing))}")
            if not _ID_RE.match(current['id']):
                raise MapError(
                    f"line {current_line}: id {current['id']!r} must look "
                    f"like 'R-4' (prefix, dash, number)")
            unknown = set(current) - _KEYS - {'_line'}
            if unknown:
                raise MapError(
                    f"line {current_line}: unknown key(s) "
                    f"{', '.join(sorted(unknown))}")
            requirements.append(Requirement(
                id=current['id'],
                statement=current['statement'],
                implementation=current.get('implementation', []),
                tests=current.get('tests', []),
                how=current.get('how'),
                depends=current.get('depends', []),
                gotchas=current.get('gotchas'),
                note=current.get('note'),
                line=current_line))
            current = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()

        # Inside a block scalar: keep taking indented lines
        if block_key is not None:
            if stripped and not raw.startswith((' ', '\t')):
                flush_block()
            elif not stripped or raw.startswith('    '):
                block_lines.append(stripped)
                continue
            else:
                flush_block()

        if not stripped or stripped.startswith('#'):
            continue

        if stripped.startswith('- ') and not raw.startswith('    -'):
            # New entry (its first key rides along on the dash line)
            flush_entry()
            current = {}
            current_line = lineno
            stripped = stripped[2:].strip()
            pending_key = None

        if current is None:
            raise MapError(f"line {lineno}: content outside any entry: {stripped!r}")

        if stripped.startswith('- '):
            if pending_key is None:
                raise MapError(f"line {lineno}: list item with no key above it")
            current.setdefault(pending_key, []).append(_clean(stripped[2:]))
            continue

        if ':' not in stripped:
            raise MapError(
                f"line {lineno}: expected 'key: value', got {stripped!r} "
                f"(list items must fit on one line -- use a '>' block scalar "
                f"for anything longer)")

        key, _, value = stripped.partition(':')
        key, value = key.strip(), value.strip()
        pending_key = key

        if value in ('>', '|', '>-', '|-'):
            block_key = key
            block_fold = value.startswith('>')
            block_lines = []
        elif value == '':
            current.setdefault(key, [])  # list follows
        else:
            current[key] = _clean(value)

    flush_entry()

    seen = {}
    for req in requirements:
        if req.id in seen:
            raise MapError(
                f"duplicate id {req.id} (lines {seen[req.id]} and {req.line})")
        seen[req.id] = req.line

    return requirements


def load_map(path: Path) -> List[Requirement]:
    """
    Load a map: either one file, or a directory of map files.

    A small project keeps one document. A large one points this at a
    directory and organizes the map files to mirror its source tree --
    same seams, same names -- so the map splits where the code splits.
    Ids must be unique across the whole map either way.
    """
    path = Path(path)
    if path.is_dir():
        return _load_map_dir(path)

    try:
        text = path.read_text()
    except OSError as e:
        raise MapError(f"cannot read map file {path}: {e}") from e
    try:
        requirements = parse_map(text)
    except MapError as e:
        raise MapError(f"{path}: {e}") from e
    for req in requirements:
        req.source = str(path)
    return requirements


def _load_map_dir(directory: Path) -> List[Requirement]:
    """Load every *.yaml under a map directory, recursively, in path order."""
    files = sorted(p for p in directory.rglob('*.yaml') if p.is_file())
    if not files:
        raise MapError(f"no .yaml map files found under {directory}")

    requirements: List[Requirement] = []
    seen: dict = {}
    for file in files:
        for req in load_map(file):
            if req.id in seen:
                raise MapError(
                    f"duplicate id {req.id} in {file} "
                    f"(already defined in {seen[req.id]})")
            seen[req.id] = req.source
            requirements.append(req)
    return requirements
