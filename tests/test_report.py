"""Checking, coverage, orphans, and the human-readable report."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intentmap.model import Requirement
from intentmap.report import (check, find_orphan_symbols, format_check,
                              format_show)


class _Repo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'mod.py').write_text(
            'def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n')
        (self.root / 'tests').mkdir()
        (self.root / 'tests' / 'test_mod.py').write_text(
            'class TestAlpha:\n    def test_it(self):\n        pass\n')

    def tearDown(self):
        self._tmp.cleanup()


class TestCheck(_Repo):
    def test_all_anchors_resolve(self):
        reqs = [Requirement('R-1', 'alpha works', ['src/mod.py::alpha'],
                            ['tests/test_mod.py::TestAlpha'])]
        result = check(reqs, self.root)
        self.assertTrue(result.ok)
        self.assertEqual(result.broken, [])

    def test_broken_anchor_detected(self):
        reqs = [Requirement('R-1', 'gone', ['src/mod.py::vanished'])]
        result = check(reqs, self.root)
        self.assertFalse(result.ok)
        self.assertEqual(len(result.broken), 1)

    def test_broken_report_names_requirement_and_anchor(self):
        reqs = [Requirement('R-9', 'gone', ['src/mod.py::vanished'])]
        text = format_check(reqs, check(reqs, self.root), self.root)
        self.assertIn('R-9', text)
        self.assertIn('vanished', text)
        self.assertIn('FAILED', text)

    def test_passing_report_says_ok(self):
        reqs = [Requirement('R-1', 'x', ['src/mod.py::alpha'],
                            ['tests/test_mod.py::TestAlpha'])]
        self.assertIn('OK', format_check(reqs, check(reqs, self.root), self.root))


class TestCoverage(_Repo):
    def setUp(self):
        super().setUp()
        self.reqs = [
            Requirement('R-1', 'proven', ['src/mod.py::alpha'],
                        ['tests/test_mod.py::TestAlpha']),
            Requirement('R-2', 'implemented only', ['src/mod.py::beta']),
            Requirement('R-3', 'claimed only'),
        ]
        self.result = check(self.reqs, self.root)

    def test_unproven_listed(self):
        self.assertEqual(self.result.unproven, ['R-2', 'R-3'])

    def test_unanchored_listed(self):
        self.assertEqual(self.result.unanchored, ['R-3'])

    def test_summary_counts(self):
        text = format_check(self.reqs, self.result, self.root)
        self.assertIn('3 requirements', text)
        self.assertIn('2 with implementation', text)
        self.assertIn('1 with tests', text)


class TestUnprovenMarking(_Repo):
    def test_unproven_requirement_is_flagged_not_silent(self):
        reqs = [Requirement('R-1', 'no test for this', ['src/mod.py::alpha'])]
        text = format_show(reqs, self.root)
        self.assertIn('UNPROVEN', text)

    def test_proven_requirement_says_proven(self):
        reqs = [Requirement('R-1', 'tested', ['src/mod.py::alpha'],
                            ['tests/test_mod.py::TestAlpha'])]
        text = format_show(reqs, self.root)
        self.assertIn('proven', text)
        self.assertNotIn('UNPROVEN', text)


class TestOrphans(_Repo):
    def test_finds_unclaimed_symbol(self):
        reqs = [Requirement('R-1', 'x', ['src/mod.py::alpha'])]
        orphans = find_orphan_symbols(reqs, self.root, ['src'])
        self.assertIn('src/mod.py::beta', orphans)
        self.assertNotIn('src/mod.py::alpha', orphans)

    def test_no_orphans_when_all_claimed(self):
        reqs = [Requirement('R-1', 'x', ['src/mod.py::alpha', 'src/mod.py::beta'])]
        self.assertEqual(find_orphan_symbols(reqs, self.root, ['src']), [])

    def test_private_symbols_skipped(self):
        (self.root / 'src' / 'mod.py').write_text('def _helper():\n    pass\n')
        self.assertEqual(find_orphan_symbols([], self.root, ['src']), [])


class TestFormatShow(_Repo):
    def setUp(self):
        super().setUp()
        self.reqs = [Requirement('R-1', 'alpha must work',
                                 ['src/mod.py::alpha'],
                                 ['tests/test_mod.py::TestAlpha'],
                                 note='a note')]

    def test_shows_statement_id_and_anchors(self):
        text = format_show(self.reqs, self.root)
        self.assertIn('R-1', text)
        self.assertIn('alpha must work', text)
        self.assertIn('implements:', text)
        self.assertIn('proves:', text)

    def test_resolves_anchor_to_line_number(self):
        self.assertIn('src/mod.py:1', format_show(self.reqs, self.root))

    def test_marks_broken_anchor_inline(self):
        reqs = [Requirement('R-1', 'x', ['src/mod.py::vanished'])]
        self.assertIn('BROKEN', format_show(reqs, self.root))

    def test_filters_to_one_requirement(self):
        reqs = self.reqs + [Requirement('R-2', 'other thing')]
        text = format_show(reqs, self.root, only='R-2')
        self.assertIn('R-2', text)
        self.assertNotIn('alpha must work', text)


if __name__ == '__main__':
    unittest.main()
