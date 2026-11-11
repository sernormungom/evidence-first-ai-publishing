import json
import pathlib
import sys
import unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import translation_output as output

class TranslationOutput(unittest.TestCase):
    def setUp(self):
        self.fm = dict(title='English', answers=['Why?'], sources=['law'],
                       status='draft', reviewed_by=None, question_refs=['Q1'])
        self.reply = dict(title='Svenska', answers=['Varför?'],
                          body='## Kort svar\n\nSvar.', notes='')

    def test_code_owns_governance_and_hash(self):
        fm, body, notes = output.assemble(json.dumps(self.reply), self.fm, 'English')
        self.assertEqual(fm['sources'], ['law'])
        self.assertEqual(fm['question_refs'], ['Q1'])
        self.assertIsNone(fm['reviewed_by'])
        self.assertEqual(fm['language'], 'sv')
        self.assertIn('translated_from', fm)
        self.assertIn('## Kort svar', body)

    def test_known_fence_is_repaired_without_model_call(self):
        text = '```json\n' + json.dumps(self.reply) + '\n```'
        self.assertEqual(output.assemble(text, self.fm, 'English')[0]['title'], 'Svenska')

    def test_only_missing_notes_recovers_reader_text_with_explicit_omission(self):
        reply = {k: v for k, v in self.reply.items() if k != 'notes'}
        fm, body, notes = output.assemble(json.dumps(reply), self.fm, 'English')
        self.assertEqual(fm['title'], reply['title'])
        self.assertEqual(fm['answers'], reply['answers'])
        self.assertEqual(body.strip(), reply['body'])
        self.assertIn('no translator ambiguity assessment was supplied', notes)
        for key in ('title', 'answers', 'body'):
            with self.subTest(missing=key), self.assertRaises(ValueError):
                output.assemble(json.dumps({k:v for k,v in reply.items() if k != key}), self.fm, 'English')
        with self.assertRaises(ValueError):
            output.assemble(json.dumps(reply | {'reviewed_by':'Model'}), self.fm, 'English')

    def test_literal_newline_is_recovered_verbatim_but_nul_is_rejected(self):
        text = json.dumps(self.reply).replace('\\n', '\n')
        _, body, _ = output.assemble(text, self.fm, 'English')
        self.assertIn('## Kort svar\n\nSvar.', body)
        bad = json.dumps(self.reply | {'body':'## Kort svar\n\nBad\x00text'})
        with self.assertRaises(ValueError):
            output.assemble(bad, self.fm, 'English')

    def test_injected_metadata_and_missing_questions_are_rejected(self):
        for change in ({'reviewed_by': 'Model'}, {'answers': []}, {'body': '---\nx: y'}):
            with self.subTest(change), self.assertRaises(ValueError):
                output.assemble(json.dumps(self.reply | change), self.fm, 'English')

    def test_truncated_json_is_not_repaired(self):
        with self.assertRaises(ValueError):
            output.assemble(json.dumps(self.reply)[:-4], self.fm, 'English')
