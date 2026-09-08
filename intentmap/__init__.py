"""
Intent Map -- keep a plain-language description of what a system must do
anchored to the code that does it and the tests that prove it.

    from intentmap import load_map, check

    requirements = load_map(Path('map/intent-map.yaml'))
    result = check(requirements, Path('.'))
    assert result.ok

Or from the command line: `python -m intentmap check`.
"""

from .model import MapError, Requirement, load_map, parse_map
from .report import CheckResult, check, find_orphan_symbols, format_check, format_show
from .resolve import Anchor, Resolution, parse_anchor, resolve, search_history

__version__ = '0.1.0'

__all__ = [
    'MapError', 'Requirement', 'load_map', 'parse_map',
    'CheckResult', 'check', 'find_orphan_symbols', 'format_check', 'format_show',
    'Anchor', 'Resolution', 'parse_anchor', 'resolve', 'search_history',
]
