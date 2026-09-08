"""Anchors resolve to symbols, and line numbers are derived, never stored."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intentmap.resolve import (Anchor, last_commit_touching, parse_anchor,
                               pin_at_head, pin_drift,
                               resolve, search_history)

MODULE = '''"""doc"""
import os


def alpha():
    return 1


class Widget:
    def spin(self):
        return 2


def beta():
    return 3
'''


class TestParseAnchor(unittest.TestCase):
    def test_path_and_symbol(self):
        anchor = parse_anchor('src/a.py::do_thing')
        self.assertEqual(anchor.path, 'src/a.py')
        self.assertEqual(anchor.symbol, 'do_thing')

    def test_bare_path(self):
        self.assertIsNone(parse_anchor('docs/DESC.md').symbol)

    def test_qualified_method(self):
        self.assertEqual(parse_anchor('a.py::Widget.spin').symbol, 'Widget.spin')

    def test_round_trips_to_string(self):
        self.assertEqual(str(parse_anchor('a.py::b')), 'a.py::b')

    def test_no_line_numbers_in_format(self):
        """Anchors address symbols; a line number is not part of the format."""
        anchor = parse_anchor('src/a.py::do_thing')
        self.assertNotIn(':1', str(anchor))
        self.assertFalse(any(ch.isdigit() for ch in anchor.symbol))


class _TempRepo(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'mod.py').write_text(MODULE)

    def tearDown(self):
        self._tmp.cleanup()


class TestResolve(_TempRepo):
    def test_finds_function(self):
        res = resolve(Anchor('src/mod.py', 'alpha'), self.root)
        self.assertTrue(res.ok)

    def test_finds_class_and_method(self):
        self.assertTrue(resolve(Anchor('src/mod.py', 'Widget'), self.root).ok)
        self.assertTrue(resolve(Anchor('src/mod.py', 'Widget.spin'), self.root).ok)

    def test_missing_file_reported(self):
        res = resolve(Anchor('src/gone.py', 'alpha'), self.root)
        self.assertFalse(res.ok)
        self.assertFalse(res.exists)
        self.assertIn('not found', res.reason)

    def test_missing_symbol_reported(self):
        res = resolve(Anchor('src/mod.py', 'nope'), self.root)
        self.assertFalse(res.ok)
        self.assertTrue(res.exists)
        self.assertIn('nope', res.reason)

    def test_bare_path_resolves_when_file_exists(self):
        self.assertTrue(resolve(Anchor('src/mod.py'), self.root).ok)

    def test_non_python_file_falls_back_to_scan(self):
        (self.root / 'src' / 'app.js').write_text(
            'const x = 1;\nfunction handle(a) { return a; }\n')
        res = resolve(Anchor('src/app.js', 'handle'), self.root)
        self.assertTrue(res.ok)
        self.assertEqual(res.line, 2)


class TestResolveLineNumbers(_TempRepo):
    def test_reports_current_line(self):
        self.assertEqual(resolve(Anchor('src/mod.py', 'alpha'), self.root).line, 5)
        self.assertEqual(resolve(Anchor('src/mod.py', 'beta'), self.root).line, 14)

    def test_line_follows_code_when_it_moves(self):
        """The whole reason anchors are symbols: edits above must not rot them."""
        before = resolve(Anchor('src/mod.py', 'beta'), self.root).line
        path = self.root / 'src' / 'mod.py'
        path.write_text('# inserted\n# lines\n' + path.read_text())
        after = resolve(Anchor('src/mod.py', 'beta'), self.root).line
        self.assertEqual(after, before + 2)


class TestHistory(_TempRepo):
    def setUp(self):
        super().setUp()
        env = {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@x',
               'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@x',
               'PATH': '/usr/bin:/bin'}
        run = lambda *a: subprocess.run(a, cwd=self.root, env=env,
                                        capture_output=True)
        run('git', 'init', '-q')
        run('git', 'add', '-A')
        run('git', 'commit', '-q', '-m', 'add module')
        self.git_ok = (self.root / '.git').exists()

    def test_last_commit_touching_path(self):
        if not self.git_ok:
            self.skipTest('git unavailable')
        self.assertIn('add module', last_commit_touching(self.root, 'src/mod.py'))

    def test_search_finds_symbol_after_move(self):
        if not self.git_ok:
            self.skipTest('git unavailable')
        (self.root / 'src' / 'moved.py').write_text('def alpha():\n    return 1\n')
        findings = search_history(self.root, 'alpha')
        self.assertTrue(any('moved.py' in f or 'mod.py' in f for f in findings))

    def test_history_is_quiet_outside_a_repo(self):
        with tempfile.TemporaryDirectory() as plain:
            self.assertIsNone(last_commit_touching(Path(plain), 'x.py'))
            self.assertEqual(search_history(Path(plain), 'alpha'), [])



class TestPinParsing(unittest.TestCase):
    """`path::symbol@commit:start-end` -- a historical fact, not a pointer."""

    def test_parses_commit_and_range(self):
        anchor = parse_anchor('src/a.py::alpha@a1b2c3d:120-165')
        self.assertEqual(anchor.path, 'src/a.py')
        self.assertEqual(anchor.symbol, 'alpha')
        self.assertEqual(anchor.commit, 'a1b2c3d')
        self.assertEqual((anchor.start, anchor.end), (120, 165))
        self.assertTrue(anchor.pinned)

    def test_single_line_pin(self):
        anchor = parse_anchor('src/a.py::alpha@a1b2c3d:42')
        self.assertEqual((anchor.start, anchor.end), (42, 42))

    def test_unpinned_anchor_is_not_pinned(self):
        self.assertFalse(parse_anchor('src/a.py::alpha').pinned)

    def test_round_trips_through_string(self):
        for text in ('src/a.py::alpha@a1b2c3d:120-165',
                     'src/a.py::alpha@a1b2c3d:42',
                     'src/a.py::alpha'):
            self.assertEqual(str(parse_anchor(text)), text)

    def test_pin_does_not_disturb_symbol(self):
        self.assertEqual(parse_anchor('a.py::Widget.spin@abc123:5-9').symbol,
                         'Widget.spin')


class TestPinAtHead(_TempRepo):
    def setUp(self):
        super().setUp()
        env = {'GIT_AUTHOR_NAME': 'T', 'GIT_AUTHOR_EMAIL': 't@x',
               'GIT_COMMITTER_NAME': 'T', 'GIT_COMMITTER_EMAIL': 't@x',
               'PATH': '/usr/bin:/bin'}
        self.env = env
        run = lambda *a: subprocess.run(a, cwd=self.root, env=env,
                                        capture_output=True)
        self.run = run
        run('git', 'init', '-q')
        run('git', 'add', '-A')
        run('git', 'commit', '-q', '-m', 'initial')
        self.git_ok = (self.root / '.git').exists()

    def test_pins_symbol_extent_at_head(self):
        if not self.git_ok:
            self.skipTest('git unavailable')
        pinned = pin_at_head(Anchor('src/mod.py', 'Widget'), self.root)
        self.assertIsNotNone(pinned)
        self.assertTrue(pinned.pinned)
        self.assertEqual(pinned.start, 9)     # class Widget
        self.assertEqual(pinned.end, 11)      # through its method
        self.assertRegex(pinned.commit, r'^[0-9a-f]{4,40}$')

    def test_returns_none_for_missing_symbol(self):
        if not self.git_ok:
            self.skipTest('git unavailable')
        self.assertIsNone(pin_at_head(Anchor('src/mod.py', 'gone'), self.root))


class TestPinDrift(TestPinAtHead):
    """The heart of it: unchanged pinned lines mean no doc update needed."""

    def _commit(self, message):
        self.run('git', 'add', '-A')
        self.run('git', 'commit', '-q', '-m', message)

    def test_no_drift_when_pinned_lines_untouched(self):
        if not self.git_ok:
            self.skipTest('git unavailable')
        pinned = pin_at_head(Anchor('src/mod.py', 'beta'), self.root)
        # Edit a DIFFERENT part of the same file, shifting beta downward
        path = self.root / 'src' / 'mod.py'
        path.write_text('# a new header comment\n\n' + path.read_text())
        self._commit('unrelated edit above')

        drift = pin_drift(pinned, self.root)
        self.assertTrue(drift.checked)
        self.assertFalse(drift.needs_review,
                         'moving lines must not count as changing them')

    def test_drift_when_pinned_lines_change(self):
        if not self.git_ok:
            self.skipTest('git unavailable')
        pinned = pin_at_head(Anchor('src/mod.py', 'beta'), self.root)
        path = self.root / 'src' / 'mod.py'
        path.write_text(path.read_text().replace('return 3', 'return 999'))
        self._commit('change beta itself')

        drift = pin_drift(pinned, self.root)
        self.assertTrue(drift.checked)
        self.assertTrue(drift.needs_review)
        self.assertTrue(any('change beta itself' in c for c in drift.commits))

    def test_unpinned_anchor_reports_unchecked(self):
        drift = pin_drift(Anchor('src/mod.py', 'beta'), self.root)
        self.assertFalse(drift.checked)
        self.assertFalse(drift.needs_review)

    def test_unchecked_outside_a_git_repo(self):
        with tempfile.TemporaryDirectory() as plain:
            Path(plain, 'x.py').write_text('def a():\n    pass\n')
            drift = pin_drift(parse_anchor('x.py::a@abc1234:1-2'), Path(plain))
            self.assertFalse(drift.checked)
            self.assertFalse(drift.needs_review)

if __name__ == '__main__':
    unittest.main()
