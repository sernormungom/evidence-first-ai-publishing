#!/usr/bin/env python3
"""
Automated article drafting.

    python3 scripts/draft.py content/vacation/02-earning-vacation.md
    python3 scripts/draft.py --dry-run content/vacation/02-earning-vacation.md

Reads the spec and loads every source it lists through scripts/source_loader.py:
official sources from their latest text snapshot, Example Studio company sections from
their local Markdown (Swedish maintained text, plus the English counterpart
when it is current). Sends DRAFTING_PROMPT.md + spec + sources to the Claude
API, and writes:
  - the draft back into the spec file (status → draft), with
    `source_fingerprints:` recording the company-section versions used
  - structured evidence/notes to reviews/<folder>/<stem>.review.yaml
  - a generated review sheet and browser copy (used by reviewers)

--dry-run builds the exact prompt, writes it to dist/prompts/, prints the
source summary and exits — no API call, no credentials needed.

Then a human runs the ordinary flow:
    git checkout -b draft/vacation-02 && git add -A && git commit && gh pr create

Requires: pip install requests pyyaml, and ANTHROPIC_API_KEY — or
HANDBOOK_BACKEND=cli to use the signed-in Claude Code CLI instead.
Model pinned for reproducibility (HANDBOOK_MODEL).
"""

import pathlib
import os
import argparse
import json
import subprocess
import sys

import yaml

import claude_api
from claude_api import unwrap_fences
import source_loader
import authoring
import questions

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('article')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--response-file', help='Replay a saved complete API-shaped JSON response; no provider call')
    args = parser.parse_args()
    if args.dry_run and args.response_file:
        parser.error('Use either dry-run or response replay')
    dry_run = args.dry_run
    spec_path = (ROOT / args.article).resolve()
    spec_text = spec_path.read_text(encoding="utf-8")
    fm, _ = source_loader.split_frontmatter(spec_text)
    spec_fm = fm

    prompt = ((ROOT / "DRAFTING_PROMPT.md").read_text(encoding="utf-8")
              + "\n\n# SHARED AUTHORING CONTRACT\n" + authoring.contract(ROOT))
    figures = yaml.safe_load((ROOT / "figures" / "figures.yaml").read_text(encoding="utf-8"))["figures"]
    wanted_keys = fm.get("figures_used") or []
    unknown = set(wanted_keys) - set(figures)
    if unknown:
        sys.exit(f"Unknown figures_used keys: {', '.join(sorted(unknown))}")
    records = questions.load_questions(ROOT)
    ref_errors = questions.findings(fm, records)
    if ref_errors:
        sys.exit("Invalid question references: " + "; ".join(ref_errors))
    if wanted_keys:
        fig_keys = "\n".join(
            f"- {{{{{k}}}}}: {figures[k].get('description')} [{figures[k].get('status')}]. "
            f"Reference value: {figures[k].get('value')} {figures[k].get('unit', '')}; retain the placeholder in employee prose."
            for k in wanted_keys if k in figures
        )
        fig_keys += ("\n\n(These are the keys this article's spec expects. If you "
                     "need one that doesn't exist, propose it by name in Review "
                     "notes — do not invent a number inline.)")
    else:
        fig_keys = ("No figures_used listed in the spec. If the article needs "
                    "amounts, propose figure keys by name in Review notes — do "
                    "not invent a number inline.")

    try:
        sources = source_loader.load_sources(fm.get("sources") or [], languages=("sv", "en"))
    except source_loader.SourceError as e:
        sys.exit(f"Source registry error: {e}")
    print("Sources:")
    print("\n".join(source_loader.summary_lines(sources)))
    if not any(s.available for s in sources):
        sys.exit("No sources available at all — run scripts/harvest.py first. "
                 "Refusing to draft from model memory.")
    if any(not s.available for s in sources):
        print("   Missing sources must be recorded in review evidence; "
              "action-critical uncertainty must remain in employee language.")

    user_msg = (
        f"## ARTICLE SPEC\n{spec_text}\n\n"
        f"## AVAILABLE FIGURE KEYS\n{fig_keys}\n\n"
        f"## GLOSSARY\n{(ROOT / 'glossary.yaml').read_text(encoding='utf-8')}\n\n"
        f"## REFERENCED QUESTIONS (review context, not employee prose)\n"
        + questions.review_context_yaml(records, fm.get("question_refs", [])) + "\n\n"
        + source_loader.format_sources(sources)
        + "\n\nDraft the article now, following every hard rule. Then perform "
          "the self-verification pass."
    )
    fingerprints = source_loader.company_fingerprints(sources)

    if dry_run:
        out = ROOT / "dist" / "prompts" / (spec_path.stem + ".draft.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"=== SYSTEM ===\n{prompt}\n\n=== USER ===\n{user_msg}\n", encoding="utf-8")
        print(f"\nDry run: prompt ({len(prompt) + len(user_msg)} chars) → {out.relative_to(ROOT)}")
        if fingerprints:
            print(f"Would record {source_loader.FINGERPRINT_KEY}: {fingerprints}")
        return

    if args.response_file:
        print(f'Replaying {args.response_file}; no provider invocation or new usage.')
        resp = json.loads((ROOT / args.response_file).read_text(encoding='utf-8'))
    else:
        print(f"Drafting {fm['title']!r} with {claude_api.describe_backend()} …")
        resp = claude_api.create_message(system=prompt, user_msg=user_msg, max_tokens=16000, timeout=900,
                                         effort=os.environ.get("HANDBOOK_DRAFT_EFFORT", "medium"))
        note = claude_api.usage_note(resp)
        if note:
            print(f"   {note}")
    problem = claude_api.incomplete_reason(resp)
    if problem:
        sys.exit(f"❌ Not written: {problem}. The spec is unchanged — split the spec "
                 f"into smaller articles or retry.")
    out = claude_api.response_text(resp)

    # Split article from review notes / self-verification
    marker = "## Review notes"
    article, _, review = out.partition(marker)
    review = (marker + review) if review else "## Review notes\n(none produced)"

    article = unwrap_fences(article.strip()) + "\n"
    if article.startswith('## In short'):
        # Preferred content-only format: identity and governance come from code.
        generated_fm = dict(spec_fm)
        generated_fm.update(authoring_version=authoring.VERSION, status='draft', reviewed_by=None)
        article = '---\n' + yaml.safe_dump(generated_fm, allow_unicode=True, sort_keys=False) + '---\n\n' + article
    # The spec is the only copy of the article's requirements — never replace
    # it with output we cannot parse. A draft must be a Markdown file whose
    # frontmatter still carries the spec's identity.
    fm, _ = source_loader.split_frontmatter(article)
    if not article.startswith("---") or not isinstance(fm, dict) or "title" not in fm:
        reviews_dir = ROOT / "reviews"
        reviews_dir.mkdir(exist_ok=True)
        rejected = reviews_dir / (spec_path.stem + ".rejected-draft.md")
        rejected.write_text(article, encoding="utf-8")
        sys.exit(f"❌ Not written: the response is not a Markdown file with frontmatter "
                 f"(it must start with '---'). {spec_path.name} is unchanged; the response "
                 f"was kept for inspection at {rejected.relative_to(ROOT)}.")
    # Validate the complete new-format response before replacing the specification.
    if fm.get("authoring_version") == authoring.VERSION:
        try:
            if fm.get('status') != 'draft' or fm.get('reviewed_by') is not None:
                raise ValueError('Generation must produce an unattested draft')
            for field in ('folder', 'sources', 'figures_used', 'replaces_legacy_article', 'replaces_legacy_articles'):
                if fm.get(field) != spec_fm.get(field):
                    raise ValueError(f'Generator changed specification field {field}')
            # Reader questions/identity are the specification contract. Build their
            # metadata in code; do not retry an article for predictable copy drift.
            generated_status_note = fm.get('status_note')
            fm = {key: value for key, value in spec_fm.items()
                  if key not in ('review_notes_for_drafter', 'reader_design')}
            fm.update(authoring_version=authoring.VERSION, status='draft', reviewed_by=None)
            fm['status_note'] = (spec_fm.get('status_note') or generated_status_note or
                                 'Draft guidance awaiting review.')
            article = '---\n' + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False) + '---\n\n' + source_loader.body_of(article) + '\n'
            evidence = authoring.parse_evidence(review, fm, records)
            available = {source.id for source in sources if source.available}
            if any(claim['source'] not in available for claim in evidence['claims']):
                raise ValueError('Claim evidence cites a source whose text was unavailable')
            problems, _ = authoring.readability(fm, source_loader.body_of(article))
            if problems:
                raise ValueError("; ".join(problems))
        except (ValueError, yaml.YAMLError) as exc:
            rejected = ROOT / 'reviews' / (spec_path.stem + '.rejected-draft.md')
            rejected.parent.mkdir(parents=True, exist_ok=True)
            rejected.write_text(out, encoding='utf-8')
            sys.exit(f"Not written: {exc}. The specification is unchanged.")
    else:
        rejected = ROOT / 'reviews' / (spec_path.stem + '.rejected-draft.md')
        rejected.parent.mkdir(parents=True, exist_ok=True)
        rejected.write_text(out, encoding='utf-8')
        sys.exit("Not written: generator omitted authoring_version: 1. The specification is unchanged.")
    article = source_loader.set_frontmatter_mapping(
        article, source_loader.FINGERPRINT_KEY, fingerprints)
    evidence["reader_hash"] = authoring.translation_hash(article, "reader-v1")
    spec_path.write_text(article, encoding="utf-8")
    evidence_path = authoring.review_path(ROOT, spec_path.relative_to(ROOT / 'content'))
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(yaml.safe_dump(evidence, allow_unicode=True, sort_keys=False), encoding="utf-8")
    reviews_dir = ROOT / "reviews"
    reviews_dir.mkdir(exist_ok=True)
    print(f"✓ Draft written to {spec_path.relative_to(ROOT)}")
    print(f"✓ Review evidence + notes → {evidence_path.relative_to(ROOT)}")

    # Chain straight into validation + review-sheet generation — one command,
    # not four — so a non-technical drafter can't forget a step.
    print("\nRunning validator …")
    val = subprocess.run([sys.executable, "scripts/validate.py"], cwd=ROOT)
    print("\nGenerating review sheet …")
    subprocess.run([sys.executable, "scripts/make_review_sheet.py",
                    str(spec_path.relative_to(ROOT))], cwd=ROOT)

    if val.returncode != 0:
        print("\n⚠️  Validation FAILED — fix the errors above before opening a "
              "PR (the draft was still written; correct it locally before translating).")
        sys.exit(val.returncode)
    else:
        print("\n✓ All checks passed. Next: commit, push, open a PR — the "
              "review sheet is your PR description.")


if __name__ == "__main__":
    main()
