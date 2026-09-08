"""
The intent-capture hook: the record must not depend on anyone remembering.
"""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    'capture_intent', ROOT / 'hooks' / 'capture-intent.py')
capture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture)


class _Stdin:
    """Feed text to the hook the way a harness would."""

    def __init__(self, text):
        self.text = text

    def __enter__(self):
        self._real = sys.stdin
        sys.stdin = io.StringIO(self.text)
        return self

    def __exit__(self, *exc):
        sys.stdin = self._real


class TestReadPrompt(unittest.TestCase):
    def test_reads_harness_json(self):
        with _Stdin(json.dumps({'prompt': 'build me a thing'})):
            self.assertEqual(capture.read_prompt([]), 'build me a thing')

    def test_accepts_alternate_key_names(self):
        for key in ('user_prompt', 'message', 'text', 'content'):
            with _Stdin(json.dumps({key: 'hello there'})):
                self.assertEqual(capture.read_prompt([]), 'hello there')

    def test_plain_mode_takes_raw_text(self):
        with _Stdin('just words'):
            self.assertEqual(capture.read_prompt(['--plain']), 'just words')

    def test_non_json_falls_back_to_raw(self):
        with _Stdin('not json at all'):
            self.assertEqual(capture.read_prompt([]), 'not json at all')

    def test_unknown_shape_yields_empty(self):
        with _Stdin(json.dumps({'irrelevant': 'x'})):
            self.assertEqual(capture.read_prompt([]), '')


class TestIsIntent(unittest.TestCase):
    def test_keeps_a_real_request(self):
        self.assertTrue(capture.is_intent(
            'I want the pool to forecast on percent change instead of price',
            False))

    def test_skips_slash_commands(self):
        self.assertFalse(capture.is_intent('/compact and keep going please ok',
                                           False))

    def test_skips_very_short_prompts(self):
        self.assertFalse(capture.is_intent('yes do it', False))

    def test_keep_all_overrides_filters(self):
        self.assertTrue(capture.is_intent('yes', True))

    def test_empty_is_never_intent(self):
        self.assertFalse(capture.is_intent('', True))


class TestAppend(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / 'docs' / 'INTENT.md'

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_file_with_header(self):
        capture.append('the first thing I want', self.path)
        text = self.path.read_text()
        self.assertIn('# INTENT', text)
        self.assertIn('this one wins', text)

    def test_quotes_verbatim_under_dated_heading(self):
        capture.append('exactly these words', self.path)
        text = self.path.read_text()
        self.assertIn(f'## {date.today().isoformat()}', text)
        self.assertIn('> exactly these words', text)

    def test_appends_without_rewriting_existing(self):
        capture.append('first thought', self.path)
        capture.append('second thought', self.path)
        text = self.path.read_text()
        self.assertIn('> first thought', text)
        self.assertIn('> second thought', text)
        self.assertEqual(text.count('# INTENT'), 1)
        self.assertEqual(text.count(f'## {date.today().isoformat()}'), 1,
                         'one heading per day, not one per prompt')

    def test_multiline_prompt_stays_verbatim(self):
        capture.append('line one\n\nline three', self.path)
        text = self.path.read_text()
        self.assertIn('> line one', text)
        self.assertIn('> line three', text)


class TestMainNeverBlocks(unittest.TestCase):
    def test_exits_zero_even_on_failure(self):
        """A capture failure must never block the human's actual work."""
        with _Stdin('a prompt long enough to count as real intent here'):
            import os
            os.environ['INTENT_FILE'] = '/nonexistent-dir/x/INTENT.md'
            err = io.StringIO()
            try:
                with redirect_stderr(err), redirect_stdout(io.StringIO()):
                    code = capture.main([])
            finally:
                del os.environ['INTENT_FILE']
        self.assertEqual(code, 0)

    def test_exits_zero_on_garbage_input(self):
        with _Stdin(''):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(capture.main([]), 0)


if __name__ == '__main__':
    unittest.main()
