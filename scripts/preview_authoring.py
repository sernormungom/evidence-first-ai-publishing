#!/usr/bin/env python3
"""Build isolated bilingual authoring demonstrations without provider calls."""
import argparse
import pathlib
import shutil
import subprocess
import sys

import yaml
import authoring

ROOT = pathlib.Path(__file__).resolve().parent.parent


def prepare(root):
    root = pathlib.Path(root)
    for folder in ('scripts', 'sources', 'figures', 'reviews', 'content/examples'):
        (root / folder).mkdir(parents=True, exist_ok=True)
    for script in (ROOT / 'scripts').glob('*.py'):
        shutil.copyfile(script, root / 'scripts' / script.name)
    shutil.copytree(ROOT / 'web/assets', root / 'web/assets', dirs_exist_ok=True)
    for filename in ('AUTHORING_GUIDE.md', 'DRAFTING_PROMPT.md', 'TRANSLATION_PROMPT.md', 'glossary.yaml', 'project.yaml'):
        shutil.copyfile(ROOT / filename, root / filename)
    examples = sorted((ROOT / 'examples/authoring').glob('0*.md'))
    for example in examples:
        shutil.copyfile(example, root / 'content/examples' / example.name)
    # Assemble saved synthetic translation content through the same output parser.
    import json
    from source_loader import split_frontmatter
    from translation_output import assemble
    for target in sorted((root / 'content/examples').glob('*.sv.md')):
        en = target.with_name(target.name.replace('.sv.md', '.md')).read_text()
        fm, _ = split_frontmatter(en)
        sv, body = split_frontmatter(target.read_text())
        metadata, translated, notes = assemble(json.dumps(dict(title=sv['title'], answers=sv['answers'], body=body, notes='Synthetic saved response; no inference or attestation.')), fm, en)
        target.write_text('---\n' + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False) + '---' + translated)
    canonical = [p for p in examples if not p.name.endswith('.sv.md')]
    (root / 'schema.yaml').write_text(yaml.safe_dump({'folders': {'examples': {'title': 'Authoring examples', 'title_sv': 'Författarexempel',
        'articles': [{'file': p.name, 'status': 'draft', 'owner': 'hr', 'review': 'annual-free'} for p in canonical]}}}))
    (root / 'sources/sources.yaml').write_text(yaml.safe_dump({'sources': {'demo_rules': {
        'title': 'Synthetic demonstration rules', 'type': 'authority', 'url': None, 'watch': False}}}))
    snap = root / 'sources/snapshots/demo_rules'
    snap.mkdir(parents=True, exist_ok=True)
    (snap / '2026-10-14.txt').write_text('Synthetic demonstration: two days at twenty units per day gives forty units. No company policy is established.\n')
    (root / 'figures/figures.yaml').write_text(yaml.safe_dump({'figures': {
        'example_daily_amount': {'value': 20, 'unit': 'illustrative units per day', 'unit_sv': 'illustrativa enheter per dag', 'source': 'demo_rules', 'status': 'needs_verification'},
        'example_total_amount': {'value': 40, 'unit': 'illustrative units', 'unit_sv': 'illustrativa enheter', 'source': 'demo_rules', 'status': 'needs_verification'}}}))
    (root / 'reviews/questions.yaml').write_text(yaml.safe_dump({'questions': {'00-Q99': {
        'kind': 'decision', 'status': 'open', 'blocking': True, 'owner': 'Demo owner (unassigned)',
        'question': 'HR INTERNAL DEMO TASK: supply the fictional reviewer assignment and supporting document.',
        'evidence': 'Synthetic fixture; no real arrangement exists.'}}}))
    evidence_dir = root / 'reviews/examples'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for p in canonical:
        evidence = {'claims': [{'claim': 'Synthetic format example, not a company policy.', 'source': 'demo_rules',
            'provision': 'Synthetic fixture paragraph', 'supported': True}],
            'question_refs': ['00-Q99'] if p.name.startswith('01') else [],
            'workflow': {'source_review': 'synthetic fixture only', 'bilingual_review': 'synthetic fixture only'}}
        evidence['reader_hash'] = authoring.translation_hash(p.read_text(encoding='utf-8'), 'reader-v1')
        (evidence_dir / (p.stem + '.review.yaml')).write_text(yaml.safe_dump(evidence))
    return root


def build(root):
    for script, args in (('validate.py', []), ('build.py', ['--allow-unverified']), ('build_site.py', [])):
        subprocess.run([sys.executable, str(root / 'scripts' / script), *args], cwd=root, check=True)
    for article in sorted((root / 'content/examples').glob('*.md')):
        if not article.name.endswith('.sv.md'):
            subprocess.run([sys.executable, str(root / 'scripts/make_review_sheet.py'),
                            str(article.relative_to(root))], cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, default=ROOT / 'dist/authoring-example')
    args = parser.parse_args()
    root = prepare(args.output.resolve())
    build(root)
    print(f'Eexample pages: {root}/site/; reviewer reports: {root}/dist/review/')


if __name__ == '__main__':
    main()
