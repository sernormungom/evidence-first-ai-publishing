#!/usr/bin/env python3
"""
Generate/refresh the Swedish version of an English canonical article.

    python3 scripts/translate.py content/business-trips/03-subsistence-allowance.md
    python3 scripts/translate.py --dry-run content/business-trips/03-subsistence-allowance.md

Sources are loaded through scripts/source_loader.py — Swedish only: official
snapshots plus the Swedish maintained text of any Example Studio company section the
article cites (Example Studio's own Swedish terms). --dry-run writes the prompt to
dist/prompts/ and exits without calling the API.

Writes the sibling  <name>.sv.md  with frontmatter:
    language: sv
    translated_from: <reader-content fingerprint; translation_hash_mode: reader-v1>

The hash is how validate.py detects stale translations: if the English
reader content changes, the recorded hash no longer matches and the Swedish version is
flagged until retranslated. Never edit .sv.md by hand — fix the English and
re-run this script.

Requires: pip install requests pyyaml, and ANTHROPIC_API_KEY — or
HANDBOOK_BACKEND=cli to use the signed-in Claude Code CLI instead.
"""

import os
import argparse
import json
import re
import pathlib
import subprocess
import sys
from collections import Counter

import yaml

import claude_api
import source_loader
import authoring
import translation_output

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent


def content_hash(text: str) -> str:
    return authoring.translation_hash(text, "reader-v1")



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('article')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--response-file', help='Replay a complete saved provider response through identical checks; no inference')
    parser.add_argument('--feedback-file', default=os.environ.get('HANDBOOK_TRANSLATION_FEEDBACK_FILE'),
                        help='Independent correction feedback under reviews/; also HANDBOOK_TRANSLATION_FEEDBACK_FILE')
    args = parser.parse_args()
    if args.dry_run and args.response_file:
        parser.error('Use either dry-run or response replay')
    dry_run = args.dry_run
    en_path = (ROOT / args.article).resolve()
    if en_path.suffix != ".md" or en_path.name.endswith(".sv.md"):
        sys.exit("Give the ENGLISH canonical .md file (not the .sv.md sibling).")
    en_text = en_path.read_text(encoding="utf-8")
    fm, _ = source_loader.split_frontmatter(en_text)

    prompt = ((ROOT / "TRANSLATION_PROMPT.md").read_text(encoding="utf-8")
              + "\n\n# SHARED AUTHORING CONTRACT\n" + authoring.contract(ROOT))
    glossary = (ROOT / "glossary.yaml").read_text(encoding="utf-8")
    try:
        sources = source_loader.load_sources(fm.get("sources") or [], languages=("sv",))
    except source_loader.SourceError as e:
        sys.exit(f"Source registry error: {e}")
    print("Sources:")
    print("\n".join(source_loader.summary_lines(sources)))
    if not any(s.available for s in sources):
        print("⚠️  No Swedish sources available — translation will be "
              "glossary-grounded only. Run scripts/harvest.py first for best results.")

    user_msg = (f"## ENGLISH CANONICAL ARTICLE\n{en_text}\n\n"
                f"## GLOSSARY\n{glossary}\n\n"
                f"# SWEDISH SOURCES\n\n" + source_loader.format_sources(sources)
                + "\n\nProduce the Swedish version now, following every hard rule.")
    if args.feedback_file:
        feedback_path = (ROOT / args.feedback_file).resolve()
        if not feedback_path.is_relative_to((ROOT / 'reviews').resolve()):
            parser.error('Translation feedback must be a file under reviews/')
        user_msg += ("\n\n## INDEPENDENT TRANSLATION CORRECTION FEEDBACK\n"
                     "Apply this feedback while translating the complete canonical article. "
                     "Do not put review commentary in the employee text.\n"
                     + feedback_path.read_text(encoding='utf-8'))

    if dry_run:
        out = ROOT / "dist" / "prompts" / (en_path.stem + ".translate.txt")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"=== SYSTEM ===\n{prompt}\n\n=== USER ===\n{user_msg}\n", encoding="utf-8")
        print(f"\nDry run: prompt ({len(prompt) + len(user_msg)} chars) → {out.relative_to(ROOT)}")
        return

    if args.response_file:
        print(f'Replaying {args.response_file}; no provider invocation or new usage.')
        resp = json.loads((ROOT / args.response_file).read_text(encoding='utf-8'))
    else:
        print(f"Translating {fm['title']!r} → Swedish with {claude_api.describe_backend()} …")
        resp = claude_api.create_message(system=prompt, user_msg=user_msg, max_tokens=16000, timeout=900,
                                         effort=os.environ.get("HANDBOOK_TRANSLATION_EFFORT", "medium"))
        note = claude_api.usage_note(resp)
        if note:
            print(f"   {note}")
    problem = claude_api.incomplete_reason(resp)
    if problem:
        sys.exit(f"❌ Not written: {problem}. The existing Swedish version (if any) "
                 f"is unchanged and keeps its old translated_from stamp.")
    out = claude_api.response_text(resp)

    # Metadata is constructed from canonical English, never regenerated.
    try:
        translated_fm, translated_body, review = translation_output.assemble(out, fm, en_text)
    except (ValueError, yaml.YAMLError) as exc:
        rejected = authoring.review_path(ROOT, en_path.relative_to(ROOT / 'content')).with_suffix('.rejected-translation.txt')
        rejected.parent.mkdir(parents=True, exist_ok=True)
        rejected.write_text(out, encoding='utf-8')
        sys.exit(f"Not written: {exc}; raw response retained at {rejected.relative_to(ROOT)}.")
    marker = "## Review notes\n"
    pattern = r"\{\{\s*[a-z0-9_]+(?::[a-z]+)?\s*\}\}"
    if Counter(re.findall(pattern, translated_body)) != Counter(re.findall(pattern, source_loader.body_of(en_text))):
        sys.exit("Not written: Swedish changed figure placeholders; existing translation is unchanged.")
    if translated_fm.get("language") != "sv":
        sys.exit("Not written: Swedish must set language: sv.")
    if fm.get("authoring_version") == authoring.VERSION:
        problems, _ = authoring.readability(translated_fm, translated_body, "sv")
        if problems:
            sys.exit("Not written: " + "; ".join(problems))

    h = translated_fm["translated_from"]
    article = "---\n" + yaml.safe_dump(translated_fm, allow_unicode=True, sort_keys=False) + "---" + translated_body

    sv_path = en_path.with_name(en_path.stem + ".sv.md")
    tmp = sv_path.with_name(sv_path.name + ".tmp")
    tmp.write_text(article + "\n", encoding="utf-8")
    os.replace(tmp, sv_path)  # atomic: never a half-written translation
    if review:
        rev_path = (authoring.review_path(ROOT, en_path.relative_to(ROOT / 'content')).with_name(en_path.stem + '.translation.md')
                    if fm.get('authoring_version') == authoring.VERSION else ROOT / "reviews" / (en_path.stem + ".sv.md"))
        rev_path.parent.mkdir(parents=True, exist_ok=True)
        rev_path.write_text(marker + review, encoding="utf-8")
        print(f"✓ Translator's review notes → {rev_path.relative_to(ROOT)}")
    print(f"✓ Swedish version → {sv_path.relative_to(ROOT)} (translated_from: {h})")

    checked = subprocess.run([sys.executable, "scripts/validate.py"], cwd=ROOT)
    if checked.returncode:
        sys.exit(checked.returncode)


if __name__ == "__main__":
    main()
