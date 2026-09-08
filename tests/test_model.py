"""Map parsing: the format is the contract."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intentmap.model import MapError, Requirement, load_map, parse_map

SAMPLE = """
# a comment
- id: R-1
  statement: >
    The system must do the thing,
    across two lines.
  implementation:
    - src/a.py::do_thing
    - src/b.py::Helper.assist
  tests:
    - tests/test_a.py::TestThing

- id: R-2
  statement: A short one-line statement.
  note: worth remembering
"""


class TestParseMap(unittest.TestCase):
    def setUp(self):
        self.reqs = parse_map(SAMPLE)

    def test_parses_every_entry(self):
        self.assertEqual([r.id for r in self.reqs], ['R-1', 'R-2'])

    def test_folds_block_statement(self):
        self.assertEqual(self.reqs[0].statement,
                         'The system must do the thing, across two lines.')

    def test_keeps_implementation_and_test_anchors(self):
        self.assertEqual(self.reqs[0].implementation,
                         ['src/a.py::do_thing', 'src/b.py::Helper.assist'])
        self.assertEqual(self.reqs[0].tests, ['tests/test_a.py::TestThing'])

    def test_inline_statement_and_note(self):
        self.assertEqual(self.reqs[1].statement, 'A short one-line statement.')
        self.assertEqual(self.reqs[1].note, 'worth remembering')

    def test_missing_anchors_are_empty_not_absent(self):
        self.assertEqual(self.reqs[1].implementation, [])
        self.assertEqual(self.reqs[1].tests, [])

    def test_records_line_numbers_for_errors(self):
        self.assertGreater(self.reqs[0].line, 0)


class TestIdValidation(unittest.TestCase):
    def test_stable_id_required(self):
        with self.assertRaises(MapError):
            parse_map('- id: nope\n  statement: x\n')

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(MapError) as ctx:
            parse_map('- id: R-1\n  statement: x\n\n- id: R-1\n  statement: y\n')
        self.assertIn('duplicate', str(ctx.exception))

    def test_statement_required(self):
        with self.assertRaises(MapError):
            parse_map('- id: R-1\n  implementation:\n    - a.py::b\n')

    def test_unknown_key_rejected(self):
        with self.assertRaises(MapError):
            parse_map('- id: R-1\n  statement: x\n  mystery: y\n')

    def test_id_survives_restatement(self):
        """The identifier is the anchor point, not the wording."""
        first = parse_map('- id: R-1\n  statement: Old wording.\n')[0]
        second = parse_map('- id: R-1\n  statement: Totally new wording.\n')[0]
        self.assertEqual(first.id, second.id)
        self.assertNotEqual(first.statement, second.statement)


class TestRequirementFlags(unittest.TestCase):
    def test_proven_and_anchored(self):
        req = Requirement('R-1', 'x', ['a.py::b'], ['t.py::T'])
        self.assertTrue(req.is_proven)
        self.assertTrue(req.is_anchored)

    def test_unproven_when_no_tests(self):
        self.assertFalse(Requirement('R-1', 'x', ['a.py::b']).is_proven)

    def test_unanchored_when_no_implementation(self):
        self.assertFalse(Requirement('R-1', 'x', [], ['t.py::T']).is_anchored)


class TestLoadMap(unittest.TestCase):
    def test_round_trip_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'm.yaml'
            path.write_text(SAMPLE)
            self.assertEqual([r.id for r in load_map(path)], ['R-1', 'R-2'])

    def test_missing_file_names_the_path(self):
        with self.assertRaises(MapError) as ctx:
            load_map(Path('/nonexistent/map.yaml'))
        self.assertIn('map.yaml', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
