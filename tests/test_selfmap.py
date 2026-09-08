"""
The project's own map must pass its own check.

This is the test that makes the pattern trustworthy: if Intent Map cannot
keep its own map honest, it has no business asking anyone else to.
"""

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from intentmap.model import load_map
from intentmap.report import check

MAP_FILE = ROOT / 'map' / 'intent-map.yaml'

# The standard library only -- see R-14.
STDLIB_OK = {
    'ast', 're', 'subprocess', 'argparse', 'sys', 'os', 'pathlib',
    'dataclasses', 'typing', '__future__',
}


class TestSelfMap(unittest.TestCase):
    def setUp(self):
        self.requirements = load_map(MAP_FILE)
        self.result = check(self.requirements, ROOT)

    def test_map_parses(self):
        self.assertGreater(len(self.requirements), 10)

    def test_every_anchor_resolves(self):
        broken = [f'{r.anchor} ({r.reason})' for r in self.result.broken]
        self.assertEqual(broken, [], f'broken anchors: {broken}')

    def test_every_requirement_is_implemented(self):
        self.assertEqual(self.result.unanchored, [],
                         'every requirement needs an implementation anchor')

    def test_every_requirement_is_proven(self):
        self.assertEqual(self.result.unproven, [],
                         'every requirement needs a test anchor')


class TestNoThirdPartyImports(unittest.TestCase):
    def test_package_imports_stdlib_only(self):
        offenders = []
        for path in sorted((ROOT / 'intentmap').glob('*.py')):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split('.')[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:  # relative import within the package
                        continue
                    names = [(node.module or '').split('.')[0]]
                else:
                    continue
                for name in names:
                    if name and name not in STDLIB_OK:
                        offenders.append(f'{path.name}: {name}')
        self.assertEqual(offenders, [],
                         f'third-party imports found: {offenders}')

    def test_no_yaml_dependency(self):
        """The map parser is deliberately hand-rolled so adoption is free."""
        for path in (ROOT / 'intentmap').glob('*.py'):
            self.assertNotIn('import yaml', path.read_text())


if __name__ == '__main__':
    unittest.main()
