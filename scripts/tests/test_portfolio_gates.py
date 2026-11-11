"""Exercise real commands against isolated synthetic inputs; never invoke a provider."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from preview_authoring import prepare
from source_loader import split_frontmatter
import harvest
class PortfolioGates(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=prepare(Path(self.tmp.name))
 def run_script(self,name,*args):
  return subprocess.run([sys.executable,str(self.root/'scripts'/name),*args],cwd=self.root,capture_output=True,text=True)
 def test_saved_output_recovery_and_rejection_preserve_spec(self):
  article='content/examples/02-demo-calculation.md';p=self.root/article; original=p.read_text();fm,body=split_frontmatter(original)
  response=self.root/'response.json'
  for stop,text in [('max_tokens',body),('refusal',body),('end_turn','Unstructured response')]:
   response.write_text(json.dumps(dict(stop_reason=stop,content=[dict(type='text',text=text)])))
   result=self.run_script('draft.py','--response-file','response.json',article)
   self.assertNotEqual(result.returncode,0,result.stdout);self.assertEqual(p.read_text(),original)
  text=body+'\n## Review notes\n```yaml\nclaims:\n- claim: Synthetic calculation only.\n  source: demo_rules\n  provision: Synthetic fixture paragraph\n  supported: true\nnotes: []\n```\n'
  response.write_text(json.dumps(dict(stop_reason='end_turn',content=[dict(type='text',text=text)])))
  result=self.run_script('draft.py','--response-file','response.json',article)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn('no provider invocation',result.stdout)
 def test_strict_publication_success_and_independent_rejections(self):
  for p in (self.root/'content/examples').glob('*.md'):
   fm,body=split_frontmatter(p.read_text());fm.update(status='live',reviewed_by='Synthetic test attestation only')
   p.write_text('---\n'+yaml.safe_dump(fm,allow_unicode=True)+'---\n'+body)
  figures_path=self.root/'figures/figures.yaml';figures=yaml.safe_load(figures_path.read_text())
  for f in figures['figures'].values(): f['status']='verified'
  figures_path.write_text(yaml.safe_dump(figures))
  q=self.root/'reviews/questions.yaml';records=yaml.safe_load(q.read_text());records['questions']['00-Q99']['status']='resolved';records['questions']['00-Q99']['resolution']='Synthetic resolution for test only';q.write_text(yaml.safe_dump(records))
  result=self.run_script('validate.py');self.assertEqual(result.returncode,0,result.stdout)
  self.assertEqual(self.run_script('build.py').returncode,0)
  for mode in ['question','figure','attestation']:
   with self.subTest(mode=mode):
    paths=[q,figures_path,self.root/'content/examples/02-demo-calculation.md'];saved=[p.read_text() for p in paths]
    if mode=='question':q.write_text(q.read_text().replace('status: resolved','status: open'))
    if mode=='figure':figures_path.write_text(figures_path.read_text().replace('status: verified','status: needs_verification'))
    if mode=='attestation':paths[2].write_text(paths[2].read_text().replace('reviewed_by: Synthetic test attestation only','reviewed_by: null'))
    self.assertNotEqual(self.run_script('validate.py').returncode,0)
    for p,text in zip(paths,saved):p.write_text(text)
 def test_harvest_compares_source_body_not_snapshot_header(self):
  registry=self.root/'sources/sources.yaml';registry.write_text(yaml.safe_dump({'sources':{'test':{'title':'Synthetic source','url':'https://example.invalid/rule'}}}))
  response=type('Response',(),{'content':b'<p>Same fictional source.</p>','raise_for_status':lambda self:None})()
  with patch.object(harvest,'ROOT',self.root),patch.object(harvest,'REGISTRY',registry),patch.object(harvest,'SNAPSHOTS',self.root/'sources/snapshots'),patch.object(harvest.sys,'argv',['harvest.py']),patch.object(harvest.requests,'get',return_value=response):
   harvest.main();harvest.main()
   response.content=b'<p>Changed fictional source.</p>'
   with self.assertRaises(SystemExit) as caught:harvest.main()
   self.assertEqual(caught.exception.code,2)
