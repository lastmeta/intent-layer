"""The command line: one command, honest exit codes, any repository."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intentmap.cli import main

GOOD_MAP = """
- id: R-1
  statement: alpha must work
  implementation:
    - src/mod.py::alpha
  tests:
    - tests/test_mod.py::TestAlpha
"""

BROKEN_MAP = """
- id: R-1
  statement: vanished must work
  implementation:
    - src/mod.py::vanished
"""


class _CliRepo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'mod.py').write_text('def alpha():\n    return 1\n')
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / 'test_mod.py').write_text('class TestAlpha:\n    pass\n')
        (self.root / 'map').mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def write_map(self, text):
        (self.root / 'map' / 'intent-map.yaml').write_text(text)

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(['--root', str(self.root), *args])
        return code, out.getvalue() + err.getvalue()


class TestCheckExitCode(_CliRepo):
    def test_zero_when_anchors_resolve(self):
        self.write_map(GOOD_MAP)
        code, text = self.run_cli('check')
        self.assertEqual(code, 0)
        self.assertIn('OK', text)

    def test_nonzero_when_anchor_is_broken(self):
        self.write_map(BROKEN_MAP)
        code, text = self.run_cli('check')
        self.assertEqual(code, 1)
        self.assertIn('BROKEN', text)

    def test_nonzero_when_map_is_malformed(self):
        self.write_map('- id: nope\n  statement: x\n')
        self.assertEqual(self.run_cli('check')[0], 2)


class TestShowCommand(_CliRepo):
    def test_prints_description_with_anchors(self):
        self.write_map(GOOD_MAP)
        code, text = self.run_cli('show')
        self.assertEqual(code, 0)
        self.assertIn('alpha must work', text)
        self.assertIn('src/mod.py:1', text)

    def test_unknown_id_errors(self):
        self.write_map(GOOD_MAP)
        self.assertEqual(self.run_cli('show', 'R-99')[0], 2)


class TestWhereCommand(_CliRepo):
    def test_locates_symbol(self):
        self.write_map(GOOD_MAP)
        code, text = self.run_cli('where', 'src/mod.py::alpha')
        self.assertEqual(code, 0)
        self.assertIn('src/mod.py:1', text)

    def test_missing_symbol_exits_nonzero(self):
        self.write_map(GOOD_MAP)
        self.assertEqual(self.run_cli('where', 'src/mod.py::gone')[0], 1)


class TestStatsAndOrphans(_CliRepo):
    def test_stats_summarizes(self):
        self.write_map(GOOD_MAP)
        code, text = self.run_cli('stats')
        self.assertEqual(code, 0)
        self.assertIn('1 requirements', text)

    def test_orphans_reports_unclaimed_symbol(self):
        self.write_map(GOOD_MAP)
        (self.root / 'src' / 'extra.py').write_text('def nobody_asked():\n    pass\n')
        code, text = self.run_cli('orphans', '--source', 'src')
        self.assertEqual(code, 0)
        self.assertIn('nobody_asked', text)


class TestExternalRoot(_CliRepo):
    def test_works_on_a_repository_it_does_not_live_in(self):
        """Adoption must not require restructuring the target repo."""
        self.write_map(GOOD_MAP)
        code, _ = self.run_cli('check')
        self.assertEqual(code, 0)
        self.assertFalse((self.root / 'intentmap').exists())

    def test_custom_map_path(self):
        (self.root / 'elsewhere.yaml').write_text(GOOD_MAP)
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(['--root', str(self.root), '--map', 'elsewhere.yaml',
                         'check'])
        self.assertEqual(code, 0)


class TestDriftCommand(_CliRepo):
    def test_reports_no_drift_for_unpinned_map(self):
        self.write_map(GOOD_MAP)
        code, text = self.run_cli('drift')
        self.assertEqual(code, 0)
        self.assertIn('no drift', text)

    def test_unresolvable_pin_is_unchecked_not_clean(self):
        """Outside git, a pin cannot be evaluated -- say so, don't imply OK."""
        self.write_map(GOOD_MAP.replace('src/mod.py::alpha',
                                        'src/mod.py::alpha@abc1234:1-2'))
        code, text = self.run_cli('drift')
        self.assertEqual(code, 0)
        self.assertIn('unchecked', text)


class TestPinCommand(_CliRepo):
    def test_pin_outside_git_fails_cleanly(self):
        self.write_map(GOOD_MAP)
        code, text = self.run_cli('pin', 'src/mod.py::alpha')
        self.assertEqual(code, 1)
        self.assertIn('cannot pin', text)

    def test_pin_missing_symbol_fails(self):
        self.write_map(GOOD_MAP)
        self.assertEqual(self.run_cli('pin', 'src/mod.py::gone')[0], 1)


if __name__ == '__main__':
    unittest.main()
