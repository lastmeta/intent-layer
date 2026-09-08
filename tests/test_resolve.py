"""Anchors resolve to symbols, and line numbers are derived, never stored."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intentmap.resolve import (Anchor, last_commit_touching, parse_anchor,
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


if __name__ == '__main__':
    unittest.main()
