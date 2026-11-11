"""Check localized opt-in units through complete Markdown builds; no providers."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build


class FigureUnitBuildTests(unittest.TestCase):
    def test_localized_units_preserve_existing_bare_and_explicit_attributes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            figures = root / 'figures.yaml'
            figures.write_text(yaml.safe_dump({'figures': {
                'duration': {'value': 6, 'unit': 'months', 'unit_sv': 'månader',
                             'display_unit': True, 'status': 'verified', 'source': 'law'},
                'amount': {'value': 42, 'unit': 'SEK', 'status': 'verified'},
            }}))
            content = root / 'content'
            content.mkdir()
            body = ('---\nstatus: draft\nquestion_refs: []\n---\n'
                    '{{duration}}; {{amount}}; {{amount:unit}}; {{duration:source}}\n')
            for name in ('example.md', 'example.sv.md'):
                (content / name).write_text(body)
            with patch.multiple(build, ROOT=root, FIGURES=figures, CONTENT=content,
                                DIST=root / 'dist'), patch.object(
                                    sys, 'argv', ['build.py', '--allow-unverified']), \
                    contextlib.redirect_stdout(io.StringIO()):
                build.main()
            en = (root / 'dist/example.md').read_text()
            sv = (root / 'dist/example.sv.md').read_text()
            self.assertIn('6 months; 42; 42 SEK; law', en)
            self.assertIn('6 månader; 42; 42 SEK; law', sv)


if __name__ == '__main__':
    unittest.main()
