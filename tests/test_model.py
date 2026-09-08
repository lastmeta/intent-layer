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


class TestProseFields(unittest.TestCase):
    """The map explains; it does not merely point."""

    MAP = """
- id: R-1
  statement: The thing must work.
  how: >
    It works because the widget spins the sprocket, which is what
    "working" means here.
  depends:
    - "R-2: the sprocket exists"
  gotchas: >
    Spinning backwards looks identical but is not.
  implementation:
    - src/a.py::spin
"""

    def setUp(self):
        self.req = parse_map(self.MAP)[0]

    def test_how_is_parsed_and_folded(self):
        self.assertIn('widget spins the sprocket', self.req.how)

    def test_depends_is_a_list(self):
        self.assertEqual(self.req.depends, ['R-2: the sprocket exists'])

    def test_gotchas_parsed(self):
        self.assertIn('backwards', self.req.gotchas)

    def test_has_prose_flag(self):
        self.assertTrue(self.req.has_prose)

    def test_requirement_without_how_is_unexplained(self):
        req = parse_map('- id: R-9\n  statement: bare.\n')[0]
        self.assertFalse(req.has_prose)


class TestMultiFileMap(unittest.TestCase):
    """One file for a small project; a mirrored tree for a large one."""

    def test_directory_of_maps_merges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'map'
            (root / 'models').mkdir(parents=True)
            (root / 'core.yaml').write_text('- id: R-1\n  statement: Core works.\n')
            (root / 'models' / 'training.yaml').write_text(
                '- id: R-2\n  statement: Training works.\n')
            reqs = load_map(root)
            self.assertEqual(sorted(r.id for r in reqs), ['R-1', 'R-2'])

    def test_records_source_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'map'
            root.mkdir(parents=True)
            (root / 'core.yaml').write_text('- id: R-1\n  statement: x.\n')
            self.assertTrue(load_map(root)[0].source.endswith('core.yaml'))

    def test_duplicate_ids_across_files_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'map'
            root.mkdir(parents=True)
            (root / 'a.yaml').write_text('- id: R-1\n  statement: x.\n')
            (root / 'b.yaml').write_text('- id: R-1\n  statement: y.\n')
            with self.assertRaises(MapError) as ctx:
                load_map(root)
            self.assertIn('duplicate', str(ctx.exception))

    def test_empty_directory_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MapError):
                load_map(Path(tmp))


if __name__ == '__main__':
    unittest.main()
