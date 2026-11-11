"""Source extraction regressions; no network or paid API calls."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harvest import extract_text


class SourceText(unittest.TestCase):
    def test_html_declared_encoding_preserves_swedish(self):
        html = '<meta charset="utf-8"><p>Föräldraledighet och sjuklön</p>'
        self.assertEqual(extract_text(html.encode("utf-8")),
                         "Föräldraledighet och sjuklön")

    def test_http_success_rejection_body_is_not_source_text(self):
        for title in ["Request Rejected", "Access Denied"]:
            with self.subTest(title=title), self.assertRaises(ValueError):
                extract_text(f"<title>{title}</title><body>Contact support.</body>")
