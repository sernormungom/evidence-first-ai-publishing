import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claude_api as ca
from section_call import review_result

class ReviewResults(unittest.TestCase):
    def test_pair_label_alias_preserves_verdict_and_rejects_unknown_coverage(self):
        entry = dict(article='a.md + .sv.md', verdict='changes_requested',
                     positive_evidence=[dict(claim='x', source='law', locator='s1', check='matches')],
                     findings=[])
        result = review_result(json.dumps(dict(articles=[entry])), ['a.md'])['articles'][0]
        self.assertEqual(result['article'], 'a.md')
        self.assertEqual(result['reported_article'], entry['article'])
        self.assertEqual(result['verdict'], 'changes_requested')
        self.assertEqual(result['positive_evidence'], entry['positive_evidence'])
        for entries, expected in [([entry], ['b.md']),
                                  ([entry, entry], ['a.md', 'b.md'])]:
            with self.subTest(entries=entries, expected=expected), self.assertRaises(ValueError):
                review_result(json.dumps(dict(articles=entries)), expected)

    def test_missing_article_or_evidence_cannot_be_accepted(self):
        entry = dict(article='a.md', verdict='accept', positive_evidence=[{'claim':'x', 'source':'law', 'locator':'section1', 'check':'matches'}], findings=[])
        self.assertEqual(review_result(json.dumps({'articles':[entry]}), ['a.md'])['articles'][0]['verdict'], 'accept')
        for entries in ([], [entry, entry], [entry | {'positive_evidence': []}]):
            with self.subTest(entries), self.assertRaises(ValueError):
                review_result(json.dumps({'articles':entries}), ['a.md'])

    def test_fix_alias_is_recovered_without_changing_verdict_or_evidence(self):
        finding = dict(id='F1', severity='minor', location='Detail', problem='Example', evidence='law', fix='Add example')
        entry = dict(article='a.md', verdict='accept', positive_evidence=[dict(claim='x', source='law', locator='s1', check='matches')], findings=[finding])
        result = review_result(json.dumps(dict(articles=[entry])), ['a.md'])
        self.assertEqual(result['articles'][0]['verdict'], 'accept')
        self.assertEqual(result['articles'][0]['findings'][0]['suggested_fix'], 'Add example')

    def test_material_finding_cannot_receive_accept_verdict(self):
        finding = dict(id='F1', severity='major', location='Opening', problem='Wrong pay', evidence='law', suggested_fix='Correct pay')
        entry = dict(article='a.md', verdict='accept', positive_evidence=[{'claim':'x', 'source':'law', 'locator':'section1', 'check':'matches'}], findings=[finding])
        with self.assertRaises(ValueError):
            review_result(json.dumps({'articles':[entry]}), ['a.md'])

class ProviderCapture(unittest.TestCase):
    def test_failure_is_captured_once_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(ca.os.environ, {'HANDBOOK_CAPTURE_DIR':tmp}), mock.patch.object(ca, 'BACKEND', 'cli'), mock.patch.object(ca, '_create_message_cli', side_effect=SystemExit('quota')) as call:
            with self.assertRaises(SystemExit):
                ca.create_message(system='system', user_msg='input', effort='medium')
            call.assert_called_once()
            request = json.loads(next(Path(tmp).glob('*.request.json')).read_text())
            self.assertEqual(request['effort'], 'medium')
            self.assertEqual(request['automatic_retries'], 0)
            self.assertEqual(len(list(Path(tmp).glob('*.error.json'))), 1)

    def test_effort_is_passed_to_cli(self):
        with mock.patch.object(ca, 'require_credentials', return_value='/fake/claude'):
            cmd = ca.cli_command('system', 'medium')
        self.assertEqual(cmd[cmd.index('--effort') + 1], 'medium')

class AcceptanceFreshness(unittest.TestCase):
    def test_changed_pair_does_not_invalidate_other_articles_in_batch(self):
        import hashlib
        import section_metrics as metrics
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / '.section-runs/demo'
            (directory / 'capture').mkdir(parents=True)
            names = ['content/demo/a.md', 'content/demo/b.md']
            for name in names:
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text('English ' + name)
                (root / name.replace('.md', '.sv.md')).write_text('Swedish ' + name)
            raw = '.section-runs/demo/raw-review.md'
            (root / raw).write_text('Original reviewer prose retained')
            calls = []
            for kind in ('source', 'bilingual'):
                inputs = names if kind == 'source' else names + [n.replace('.md', '.sv.md') for n in names]
                outcome = {'independent_acceptance': {n:'accept' for n in names}}
                artifact = f'.section-runs/demo/{kind}.json'
                (root / artifact).write_text(json.dumps(outcome))
                calls.append(dict(id=len(calls)+1, kind=kind, articles=names, outcome='completed',
                    artifacts={artifact:hashlib.sha256((root / artifact).read_bytes()).hexdigest(), raw:hashlib.sha256((root / raw).read_bytes()).hexdigest()},
                    inputs={n:hashlib.sha256((root / n).read_bytes()).hexdigest() for n in inputs}))
            (directory / 'manifest.json').write_text(json.dumps(dict(section='demo', calls=calls, events=[])))
            with mock.patch.object(metrics, 'ROOT', root):
                self.assertEqual(metrics.summarize(directory)['independently_accepted_pairs'], names)
                (root / names[0]).write_text('Changed reader claim')
                report = metrics.summarize(directory)
                self.assertEqual(report['independently_accepted_pairs'], [names[1]])
                self.assertIsNone(report['equivalent_api_cost_usd'])
                self.assertEqual(report['human_interruptions'], 0)

class CompleteBundles(unittest.TestCase):
    def test_complete_bodies_and_source_tail_are_preserved_and_specs_rejected(self):
        import review_bundle as bundle
        import source_loader as sl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            name = 'content/demo/a.md'
            article = root / name
            article.parent.mkdir(parents=True)
            article.write_text('---\nstatus: draft\nsources: [law]\nfigures_used: []\nquestion_refs: [G-Q1, G-Q2]\n---\n## In short\nComplete article tail.')
            (root / 'reviews').mkdir()
            (root / 'reviews/questions.yaml').write_text('''questions:
  G-Q1:
    kind: decision
    status: resolved
    blocking: true
    question: Who approves?
    answer: The manager at Example Studio, never the client.
    resolution:
      record: A confirmed manager decision.
      source: Maintained decision evidence.
  G-Q2:
    kind: decision
    status: open
    blocking: true
    question: Which current schedule applies?
  G-Q3:
    kind: decision
    status: open
    blocking: true
    question: Unrelated private evidence must not be attached.
''')
            (root / 'AUTHORING_GUIDE.md').write_text('Guide')
            roles = root / 'skills/handbook-section/references/roles.md'
            roles.parent.mkdir(parents=True)
            roles.write_text('## Source reviewer\nReturn compact JSON.\n## Bilingual reviewer\nCheck pairs.\n## Coordinator disposition\nRecord.')
            (root / 'figures').mkdir()
            (root / 'figures/figures.yaml').write_text('figures: {}')
            source = sl.Source('law', 'Law', 'official', texts=[(None, 'snapshot', 'Complete source tail.')])
            with mock.patch.object(bundle, 'ROOT', root), mock.patch.object(sl, 'load_sources', return_value=[source]):
                text, metadata = bundle.build([name], 'source')
                self.assertIn('Complete article tail.', text)
                self.assertIn('Complete source tail.', text)
                self.assertIn('The manager at Example Studio, never the client.', text)
                self.assertIn('Maintained decision evidence.', text)
                self.assertIn('Which current schedule applies?', text)
                self.assertNotIn('Unrelated private evidence', text)
                self.assertFalse(metadata['truncated'])
                article.write_text(article.read_text().replace('status: draft', 'status: spec'))
                with self.assertRaises(ValueError):
                    bundle.build([name], 'source')

class StageUsage(unittest.TestCase):
    def test_stage_usage_counts_actual_artifacts_once_and_preserves_unknown_cost(self):
        import section_metrics as metrics
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            request='capture/one.request.json';response='capture/one.response.json'
            (root/'capture').mkdir()
            (root/request).write_text(json.dumps({'effort':'medium'}))
            (root/response).write_text(json.dumps({'stop_reason':'end_turn',
                'usage':{'input_tokens':2,'cache_creation_input_tokens':3,'cache_read_input_tokens':4,
                         'output_tokens':10,'output_tokens_details':{'thinking_tokens':6}},
                '_cli':{'cost_usd':0.2}}))
            outcome={'provider_artifacts':[request,response,response]}
            (root/'outcome.json').write_text(json.dumps(outcome))
            digest=hashlib.sha256((root/'outcome.json').read_bytes()).hexdigest()
            manifest={'calls':[{'kind':'draft','artifacts':{'outcome.json':digest}},
                               {'kind':'draft','artifacts':{}}]}
            with mock.patch.object(metrics,'ROOT',root):
                stage=metrics.stage_usage(manifest)['draft']
            self.assertEqual(stage['attempts'],2)
            self.assertEqual(stage['provider_completions'],1)
            self.assertEqual(stage['input_tokens'],9)
            self.assertEqual(stage['output_tokens'],10)
            self.assertEqual(stage['thinking_tokens'],6)
            self.assertEqual(stage['efforts'],['medium'])
            self.assertEqual(stage['reported_partial_cost_usd'],0.2)
            self.assertIsNone(stage['equivalent_api_cost_usd'])
