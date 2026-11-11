"""Authoring contract, bilingual build and independent publication gates. No inference."""
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import authoring
import build_site
import questions
from preview_authoring import prepare, build
from source_loader import split_frontmatter


class ContractTests(unittest.TestCase):
    def test_reader_hash_ignores_workflow_but_tracks_reader_inputs(self):
        text = '---\ntitle: Question\nstatus: draft\nstatus_note: Pending\nquestion_refs: [09-Q1]\nsources: [law]\n---\n\n## In short\nAn answer.\n'
        digest = authoring.translation_hash(text, 'reader-v1')
        self.assertEqual(digest, authoring.translation_hash(text.replace('Pending', 'Accepted').replace('status: draft', 'status: live'), 'reader-v1'))
        for changed in (text.replace('An answer.', 'Another answer.'), text.replace('09-Q1', '09-Q3'), text.replace('[law]', '[other]'), text.replace('title: Question', 'title: Another question')):
            self.assertNotEqual(digest, authoring.translation_hash(changed, 'reader-v1'))
        self.assertNotEqual(authoring.translation_hash(text), authoring.translation_hash(text.replace('Pending', 'Accepted')))

    def test_open_questions_block_live_and_unknown_ids_always_fail(self):
        records = {'09-Q1': {'status': 'open', 'blocking': True}}
        self.assertEqual(questions.findings({'status': 'draft', 'question_refs': ['09-Q1']}, records), [])
        self.assertIn('unresolved', questions.findings({'status': 'live', 'question_refs': ['09-Q1']}, records)[0])
        self.assertIn('unresolved', questions.findings({'status': 'Live', 'question_refs': ['09-Q1']}, records)[0])
        self.assertIn('unknown', questions.findings({'question_refs': ['09-Q9']}, records)[0])
        self.assertIn('list', questions.findings({'question_refs': '09-Q1'}, records)[0])

    def test_summary_and_hr_material_are_checked_without_removing_conditions(self):
        body = '## In short\n\n' + 'word ' * 61 + '\n\n## Detail\n> **DECISION NEEDED:** HR to supply a policy.\n'
        problems, _ = authoring.readability({}, body)
        self.assertTrue(any('60' in p for p in problems))
        self.assertTrue(any('reviewer-only' in p for p in problems))
        self.assertEqual(authoring.readability({}, '## In short\n\nIf the conditions apply, use the documented procedure.\n')[0], [])

    def test_length_warning_yields_to_recorded_justification(self):
        body = '## In short\n\nShort answer.\n\n## Detail\n' + 'word ' * 1201
        self.assertTrue(any('1,200' in w for w in authoring.readability({}, body)[1]))
        self.assertEqual(authoring.readability({}, body, length_justified=True)[1], [])

    def test_evidence_cannot_cite_unattached_sources_or_false_support(self):
        fm = {'sources': ['law'], 'question_refs': []}
        valid = '```yaml\nclaims:\n- claim: A rule\n  source: law\n  provision: section one\n  supported: true\n```'
        self.assertEqual(len(authoring.parse_evidence(valid, fm, {})['claims']), 1)
        for invalid in (valid.replace('source: law', 'source: memory'), valid.replace('true', 'false'), 'No evidence'):
            with self.assertRaises(ValueError):
                authoring.parse_evidence(invalid, fm, {})

    def test_question_register_preserves_ids_and_resolutions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / 'reviews').mkdir()
            data = {'questions': {'00-Q1': {'status': 'resolved', 'blocking': True, 'kind': 'decision', 'owner': 'Synthetic reviewer', 'question': 'Fictional decision', 'resolution': 'Fixture resolution'}, '00-Q2': {'status': 'open', 'blocking': True, 'kind': 'decision', 'owner': 'Synthetic reviewer', 'question': 'Fictional open question'}}}
            (root / 'reviews/questions.yaml').write_text(yaml.safe_dump(data))
            records = questions.load_questions(root)
            self.assertEqual(records['00-Q1']['resolution'], 'Fixture resolution')
            self.assertEqual(records['00-Q2']['status'], 'open')


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = prepare(pathlib.Path(self.directory.name))

    def command(self, script, *args):
        return subprocess.run([sys.executable, str(self.root / 'scripts' / script), *args],
                              cwd=self.root, text=True, capture_output=True)

    def test_generators_receive_exact_contract_without_calling_providers(self):
        article = 'content/examples/01-demo-request.md'
        for script in ('draft.py', 'translate.py'):
            result = self.command(script, '--dry-run', article)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.command('draft.py', '--dry-run', 'content/examples/02-demo-calculation.md')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calculation_prompt = (self.root / 'dist/prompts/02-demo-calculation.draft.txt').read_text()
        self.assertIn('Reference value: 20', calculation_prompt)
        self.assertIn('Reference value: 40', calculation_prompt)
        prompts = list((self.root / 'dist/prompts').glob('*.txt'))
        self.assertEqual(len(prompts), 3)
        for path in prompts:
            text = path.read_text()
            self.assertIn((self.root / 'AUTHORING_GUIDE.md').read_text(), text)
            self.assertIn('## GLOSSARY', text)
        (self.root / 'AUTHORING_GUIDE.md').unlink()
        self.assertNotEqual(self.command('draft.py', '--dry-run', article).returncode, 0)

    def test_bilingual_trial_separates_employee_and_hr_and_resolves_links(self):
        with contextlib.redirect_stdout(io.StringIO()):
            build(self.root)
        for asset in ('handbook.css', 'handbook.js'):
            self.assertTrue((self.root / 'site/assets' / asset).is_file())
        for lang in ('en', 'sv'):
            index = json.loads((self.root / f'site/{lang}/search-index.json').read_text())
            self.assertEqual(len(index), 2)
            for name in ('01-demo-request', '02-demo-calculation'):
                page = self.root / f'site/{lang}/examples/{name}.html'
                soup = BeautifulSoup(page.read_text(), 'html.parser')
                self.assertIsNotNone(soup.select_one('.inshort'))
                self.assertEqual(soup.select_one('article h1').get_text(), index[0 if name.startswith('01') else 1]['title'])
                self.assertIsNotNone(soup.select_one('details.sources summary'))
                self.assertIsNone(soup.select_one('details.sources[open]'))
                self.assertNotIn('HR INTERNAL DEMO TASK', soup.get_text())
                self.assertNotIn('demo_rules', soup.get_text())
                self.assertIsNotNone(soup.select_one('a[href$=".html"]'))
            self.assertNotIn('HR INTERNAL DEMO TASK', json.dumps(index))
            self.assertNotIn('Synthetic demonstration only', json.dumps(index))
            self.assertEqual(index[0]['folder'], 'Författarexempel' if lang == 'sv' else 'Authoring examples')
        report = (self.root / 'dist/review/examples/01-demo-request.html').read_text()
        self.assertIn('HR INTERNAL DEMO TASK', report)
        self.assertIn('Structured claim evidence', report)
        self.assertIn('40 illustrative units', (self.root / 'site/en/examples/02-demo-calculation.html').read_text())
        self.assertIn('awaiting verification', (self.root / 'site/en/examples/02-demo-calculation.html').read_text())

    def test_live_gate_uses_register_even_without_a_decision_box(self):
        path = self.root / 'content/examples/01-demo-request.md'
        text = path.read_text().replace('status: draft', 'status: live').replace('reviewed_by: null', 'reviewed_by: Test fixture')
        path.write_text(text)
        result = self.command('validate.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unresolved blocking question 00-Q99', result.stdout)
        result = self.command('build.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unresolved blocking question 00-Q99', result.stderr)

    def test_unknown_reference_and_missing_evidence_fail_validation(self):
        path = self.root / 'content/examples/01-demo-request.md'
        path.write_text(path.read_text().replace('00-Q99', '00-Q98'))
        (self.root / 'reviews/examples/01-demo-request.review.yaml').unlink()
        result = self.command('validate.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unknown question reference', result.stdout)
        self.assertIn('missing structured claim evidence', result.stdout)

    def test_duplicate_question_id_cannot_overwrite_an_open_item(self):
        path = self.root / 'reviews/questions.yaml'
        path.write_text('questions:\n  00-Q99: {status: open}\n  00-Q99: {status: resolved}\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            questions.load_questions(self.root)

    def test_question_register_uses_existing_access_data_checks(self):
        path = self.root / 'reviews/questions.yaml'
        data = yaml.safe_load(path.read_text())
        data['questions']['00-Q99']['question'] = 'Invented fixture https://demo.invalid/?RequestKey=INVENTED'
        path.write_text(yaml.safe_dump(data))
        result = self.command('validate.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('V9 reviews/questions.yaml', result.stdout)

    def test_changed_evidence_does_not_stale_reader_translation(self):
        path = self.root / 'reviews/examples/01-demo-request.review.yaml'
        record = yaml.safe_load(path.read_text())
        record['workflow']['source_review'] = 'accepted for this test fixture'
        path.write_text(yaml.safe_dump(record))
        result = self.command('validate.py')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertNotIn('STALE', result.stdout)

    def test_reader_change_flags_both_translation_and_evidence(self):
        path = self.root / 'content/examples/01-demo-request.md'
        path.write_text(path.read_text().replace('Keep a copy', 'Keep an accurate copy'))
        result = self.command('validate.py')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('STALE', result.stdout)
        self.assertIn('claim evidence predates current reader content', result.stdout)

    def test_stale_translation_cannot_go_live(self):
        path = self.root / 'content/examples/02-demo-calculation.md'
        path.write_text(path.read_text().replace('status: draft', 'status: live').replace('Multiply the illustrative', 'Multiply the example'))
        result = self.command('validate.py')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('V8 examples/02-demo-calculation.sv.md: STALE', result.stdout)

    def test_translation_checks_fields_and_stamps_reader_mode_with_fake_cli(self):
        # Exercise the real generator wrapper with a local fake executable,
        # including its neutral working directory. No provider is contacted.
        en = 'content/examples/01-demo-request.md'
        sv = self.root / 'content/examples/01-demo-request.sv.md'
        original = sv.read_text()
        fake = self.root / 'fake-claude'
        def invoke(response):
            payload = {'subtype': 'success', 'stop_reason': 'end_turn', 'result': response}
            fake.write_text('#!' + sys.executable + '\nimport sys,json\nsys.stdin.read()\nprint(' + repr(json.dumps(payload)) + ')\n')
            fake.chmod(0o755)
            return subprocess.run([sys.executable, str(self.root / 'scripts/translate.py'), en],
                cwd=self.root, text=True, capture_output=True,
                env={**os.environ, 'HANDBOOK_BACKEND': 'cli', 'HANDBOOK_CLI': str(fake)})
        sv_fm, sv_body = split_frontmatter(original)
        response = dict(title=sv_fm['title'], answers=sv_fm['answers'], body=sv_body, notes='')
        bad = json.dumps(response | {'question_refs': ['00-Q98']})
        result = invoke(bad)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sv.read_text(), original)
        result = invoke(json.dumps(response))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        fm, _ = split_frontmatter(sv.read_text())
        self.assertEqual(fm['translation_hash_mode'], 'reader-v1')
        self.assertEqual(fm['translated_from'], authoring.translation_hash((self.root / en).read_text(), 'reader-v1'))

    def test_missing_swedish_page_gets_labeled_english_fallback(self):
        pages = {('en', 'examples/target.html'): True}
        rendered = build_site.article_links('<a href="target.md">Target</a>', 'sv', 'examples/source.html', pages)
        self.assertIn('../../en/examples/target.html', rendered)
        self.assertIn('(English)', rendered)

    def test_broken_links_fail_new_pages_and_warn_for_legacy(self):
        site = self.root / 'site'
        site.mkdir()
        page = site / 'test.html'
        page.write_text('<a href="missing.html">Missing</a>')
        errors, warnings = build_site.check_links(site, {page})
        self.assertEqual(len(errors), 1)
        errors, warnings = build_site.check_links(site, set())
        self.assertEqual(len(warnings), 1)

    def test_obsolete_root_page_redirects_to_current_english_page(self):
        legacy = self.root / 'site/examples/01-demo-request.html'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('Obsolete page with <a href="missing.md">a broken link</a>')
        build(self.root)
        self.assertIn('../en/examples/01-demo-request.html', legacy.read_text())
        self.assertNotIn('Obsolete page', legacy.read_text())

    def test_spec_only_section_remains_visible_as_coming_soon(self):
        path = self.root / 'schema.yaml'
        data = yaml.safe_load(path.read_text())
        data['folders']['pending'] = {'title': 'Pending section', 'articles': [
            {'file': '01-pending.md', 'status': 'spec', 'owner': 'hr', 'review': 'annual-free'}]}
        path.write_text(yaml.safe_dump(data))
        article = self.root / 'content/pending/01-pending.md'
        article.parent.mkdir()
        article.write_text('---\ntitle: Pending\nfolder: Pending section\ncontent_type: example\nstatus: spec\nsources: [demo_rules]\n---\n')
        build(self.root)
        soup = BeautifulSoup((self.root / 'site/en/index.html').read_text(), 'html.parser')
        self.assertIn('Pending section', [item.get_text() for item in soup.select('li.soon')])


if __name__ == '__main__':
    unittest.main()
