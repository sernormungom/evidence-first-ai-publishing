"""Exercise the shared website shell against a small bilingual article tree."""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import build_site


class SiteDesignTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = pathlib.Path(directory.name)
        self.site = self.root / "site"
        schema = {"folders": {
            "vacation": {"title": "Vacation", "title_sv": "Semester"},
            "work": {"title": "Work", "title_sv": "Arbete"},
        }}
        (self.root / "schema.yaml").write_text(yaml.safe_dump(schema))
        (self.root / "sources").mkdir()
        (self.root / "sources/sources.yaml").write_text("sources: {}\n")
        self.write_article("vacation/01-leave.md", "Request leave")
        self.write_article("vacation/01-leave.sv.md", "Ansök om semester", translated_from="outdated")
        self.write_article("work/01-work.md", "Work safely")
        self.write_article("work/01-work.sv.md", "Arbeta säkert")
        self.write_article("work/02-english-only.md", "English only")
        with patch.multiple(build_site, ROOT=self.root, DIST=self.root / "dist",
                            SITE=self.site, CONTENT=self.root / "content"), \
                patch.object(build_site, "introduction_html", return_value='<article class="introduction"><h2>Welcome</h2><p>Maintained introduction.</p></article>'), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            build_site.main()

    def write_article(self, relative, title, **extra):
        metadata = {"title": title, "status": "draft", "answers": [title], **extra}
        answer = "Kort svar" if relative.endswith(".sv.md") else "In short"
        text = ("---\n" + yaml.safe_dump(metadata) + "---\n\n"
                f"## {answer}\nA practical answer.\n\n"
                "## Details\nDo this first.\n\n| Item | Value |\n| --- | --- |\n| Example | Detail |\n")
        for folder in ("dist", "content"):
            path = self.root / folder / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)

    def soup(self, relative):
        return BeautifulSoup((self.site / relative).read_text(), "html.parser")

    def test_shared_assets_search_and_home_paths_resolve_at_both_depths(self):
        for lang in ("en", "sv"):
            for relative in (f"{lang}/index.html", f"{lang}/vacation/01-leave.html"):
                soup = self.soup(relative)
                parent = (self.site / relative).parent
                for tag, attr in (("link[rel=stylesheet]", "href"), ("script[src]", "src")):
                    target = (parent / soup.select_one(tag)[attr]).resolve()
                    self.assertTrue(target.is_file(), target)
                home = (parent / soup.select_one("a.brand")["href"]).resolve()
                self.assertEqual(home, self.site / lang / "index.html")
                for search in soup.select(".searchbox"):
                    index = (parent / search["data-index"]).resolve()
                    self.assertEqual(index, self.site / lang / "search-index.json")
                    self.assertTrue(json.loads(index.read_text()))
                    self.assertEqual(search.select_one("label")["for"], search.select_one("input")["id"])
                    self.assertTrue(search.select_one('[role="status"]'))
                self.assertEqual(soup.select_one(".skip-link")["href"], "#main")
                self.assertEqual(len(soup.select("main h1")), 1)
                ids = [node["id"] for node in soup.select("[id]")]
                self.assertEqual(len(ids), len(set(ids)))

    def test_sidebar_contains_later_topics_and_marks_only_the_current_article(self):
        for lang, label in (("en", "Vacation"), ("sv", "Semester")):
            relative = f"{lang}/vacation/01-leave.html"
            soup = self.soup(relative)
            current = soup.select('.sidebar [aria-current="page"]')
            self.assertEqual(len(current), 1)
            self.assertEqual(current[0].find_parent("details").summary.get_text(), label)
            self.assertTrue(current[0].find_parent("details").has_attr("open"))
            self.assertEqual(len(soup.select(".topic-group[open]")), 1)
            for link in soup.select(".sidebar a"):
                target = ((self.site / relative).parent / link["href"]).resolve()
                self.assertTrue(target.is_file())
                self.assertTrue(target.is_relative_to(self.site / lang))
            self.assertTrue(soup.select_one('.sidebar a[href="../work/01-work.html"]'))
            if lang == "sv":
                self.assertFalse(soup.select_one('.sidebar a[href*="english-only"]'))

    def test_language_switches_and_notices_are_preserved(self):
        english = self.soup("en/vacation/01-leave.html")
        swedish = self.soup("sv/vacation/01-leave.html")
        self.assertEqual(english.select_one("header .lang")["href"], "../../sv/vacation/01-leave.html")
        self.assertEqual(swedish.select_one("header .lang")["href"], "../../en/vacation/01-leave.html")
        fallback = self.soup("en/work/02-english-only.html")
        self.assertEqual(fallback.select_one("header .lang")["href"], "../../sv/index.html")
        self.assertTrue(english.select_one(".draftnote"))
        self.assertTrue(swedish.select_one(".stalenote"))
        self.assertEqual(swedish.select_one(".inshort h2").get_text(), "Kort svar")
        self.assertEqual(english.select_one(".inshort h2").get_text(), "In short")
        for soup in (english, swedish):
            table = soup.select_one('.table-scroll[tabindex="0"][role="region"] table')
            self.assertTrue(table)
            self.assertEqual(table.select_one("th").get_text(), "Item")

    def test_homepage_keeps_all_article_links_and_moves_introduction_after_topics(self):
        for lang in ("en", "sv"):
            soup = self.soup(f"{lang}/index.html")
            self.assertEqual(len(soup.select(".searchbox")), 2)
            self.assertFalse(soup.select(".sidebar"))
            sections = soup.select_one("main").find_all(recursive=False)
            self.assertLess(sections.index(soup.select_one(".browse-section")),
                            sections.index(soup.select_one(".introduction")))
            indexed_urls = {a["url"] for a in json.loads((self.site / lang / "search-index.json").read_text())}
            self.assertEqual({a["href"] for a in soup.select(".folders a")}, indexed_urls)
            for link in soup.select(".folders a"):
                self.assertTrue((self.site / lang / link["href"]).is_file())


if __name__ == "__main__":
    unittest.main()
