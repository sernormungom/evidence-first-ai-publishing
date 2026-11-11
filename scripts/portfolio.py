"""Offline portfolio artifact; only synthetic reader output and selected reports are exported."""
import html
import json
from pathlib import Path
import shutil
import markdown
from preview_authoring import prepare, build
ROOT = Path(__file__).resolve().parents[1]
def main():
    root = ROOT / 'dist/demo'
    if root.exists(): shutil.rmtree(root)
    prepare(root)
    build(root)
    out = ROOT / 'dist/portfolio'
    if out.exists(): shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(root / 'site', out / 'demo')
    reports = out / 'reports'; reports.mkdir()
    for p in sorted((root / 'reviews/examples').glob('*.review.yaml')):
        (reports / (p.stem + '.html')).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Synthetic evidence</title><h1>Illustrative evidence — not approval</h1><pre>' + html.escape(p.read_text()) + '</pre></html>')
    for name in ('case-study','architecture','information-policy'):
        body = markdown.markdown((ROOT / 'docs' / (name + '.md')).read_text(), extensions=['fenced_code'])
        (out / (name + '.html')).write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Portfolio notes</title><a href="index.html">Portfolio</a>' + body + '</html>')
    links = ''.join('<li><a href="reports/' + p.name + '">' + html.escape(p.stem) + '</a></li>' for p in reports.glob('*.html'))
    repo = __import__('yaml').safe_load((ROOT / 'project.yaml').read_text())['repository_url']
    (out / 'index.html').write_text('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Evidence-first AI publishing</title><style>body{font:18px/1.7 system-ui;color:#172033;background:#f5f7fb;max-width:920px;margin:0 auto;padding:5vw}h1{font-size:clamp(2.3rem,6vw,4.4rem);line-height:1.1}a{color:#184eb0}section{border-top:1px solid #cbd5e1;margin-top:3rem;padding-top:1rem}.label{font-size:.85rem;letter-spacing:.12em;text-transform:uppercase}nav a{display:inline-block;margin:0 1rem 1rem 0}pre{overflow:auto}</style></head><body><main><p class="label">AI systems engineering / synthetic demonstration</p><h1>Generation is only the first gate.</h1><p>A source-grounded publishing pipeline that makes evidence, translation drift and acceptance visible.</p><nav><a href="demo/en/index.html">Explore English demo →</a><a href="demo/sv/index.html">Svensk demonstration →</a><a href="REPO">Inspect the code →</a></nav><section><h2>Follow the evidence</h2><p>Two fictional examples demonstrate centralized figures, open decisions and bilingual output. These pages replay saved fixtures without live inference. They establish no entitlement and carry no real approval.</p><ul>REPORTS</ul></section><section><h2>Inspect the engineering</h2><p><a href="case-study.html">Problem and tradeoffs</a> · <a href="architecture.html">Architecture</a> · <a href="information-policy.html">Information policy</a></p><p>Incomplete model output is rejected before replacement. Reader changes invalidate stale evidence. Saved output can be recovered without another provider call.</p></section></main></body></html>'.replace('REPO', html.escape(repo, quote=True)).replace('REPORTS', links))
    errors = []
    from bs4 import BeautifulSoup
    for p in out.rglob('*.html'):
        soup = BeautifulSoup(p.read_text(), 'html.parser')
        for tag, attr in [('a','href'),('script','src'),('link','href')]:
            for node in soup.find_all(tag):
                value = node.get(attr,'').split('#')[0].split('?')[0]
                if value and not value.startswith(('http:', 'https:', 'mailto:', 'data:')) and not (p.parent / value).exists(): errors.append(str(p.relative_to(out)) + ': ' + value)
    if errors: raise SystemExit('Broken artifact links: ' + repr(errors))
    print('Offline portfolio built: ' + str(out))
if __name__ == '__main__': main()
