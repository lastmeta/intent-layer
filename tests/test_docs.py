"""
The documents are part of the system, so they get tested too.

These are deliberately structural, not stylistic: they check that INTENT
stays verbatim and append-only, that DESC stays a flat current list whose
ids match the map, and that DESC reads as prose rather than as a data file.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
INTENT = ROOT / 'docs' / 'INTENT.md'
DESC = ROOT / 'docs' / 'DESC.md'


class TestIntentFile(unittest.TestCase):
    def test_exists(self):
        self.assertTrue(INTENT.exists(), 'docs/INTENT.md must exist')

    def test_has_dated_verbatim_entries(self):
        text = INTENT.read_text()
        self.assertRegex(text, r'##\s+\d{4}-\d{2}-\d{2}',
                         'entries must be dated so the record is append-only')

    def test_entries_are_quoted_verbatim(self):
        self.assertIn('\n> ', INTENT.read_text(),
                      'verbatim intent is quoted, not paraphrased')

    def test_declares_itself_authoritative(self):
        text = INTENT.read_text().lower()
        self.assertTrue('authority' in text or 'wins' in text,
                        'INTENT must state that it outranks derived docs')


class TestDescFile(unittest.TestCase):
    def setUp(self):
        self.text = DESC.read_text()

    def test_exists_and_has_overview(self):
        self.assertTrue(DESC.exists())
        self.assertIn('# DESC', self.text)

    def test_states_it_is_derived_from_intent(self):
        self.assertIn('INTENT.md', self.text)

    def test_requirements_are_identified(self):
        ids = re.findall(r'\*\*(R-\d+)\*\*', self.text)
        self.assertGreater(len(ids), 5)
        self.assertEqual(len(ids), len(set(ids)), 'ids must be unique')

    def test_ids_match_the_map(self):
        sys.path.insert(0, str(ROOT))
        from intentmap.model import load_map
        map_ids = {r.id for r in load_map(ROOT / 'map' / 'intent-map.yaml')}
        desc_ids = set(re.findall(r'\*\*(R-\d+)\*\*', self.text))
        self.assertEqual(desc_ids, map_ids,
                         'every described requirement must be mapped, and '
                         'every mapped requirement described')

    def test_keeps_no_version_history(self):
        """It is a current document; the history lives in git and INTENT."""
        lowered = self.text.lower()
        for banned in ('changelog', 'previously,', 'used to be', 'v1:', 'v2:'):
            self.assertNotIn(banned, lowered)


class TestDescReadsAsProse(unittest.TestCase):
    def setUp(self):
        self.text = DESC.read_text()

    def test_statements_are_sentences(self):
        statements = re.findall(r'\*\*R-\d+\*\*\s*—\s*(.+?)(?=\n\n)',
                                self.text, re.S)
        self.assertGreater(len(statements), 5)
        for statement in statements:
            flat = ' '.join(statement.split())
            self.assertTrue(flat.endswith('.'),
                            f'statement should be a sentence: {flat[:60]}...')
            self.assertGreater(len(flat.split()), 5,
                               f'statement too terse to read as prose: {flat}')

    def test_contains_no_code_anchors(self):
        """Anchors belong in the map; DESC must stay readable prose."""
        self.assertNotIn('::', self.text)
        self.assertNotIn('.py', self.text)


if __name__ == '__main__':
    unittest.main()
