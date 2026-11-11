#!/usr/bin/env python3
"""
Scaffold a new article: adds it to schema.yaml AND creates the spec stub in
content/, with all required fields pre-filled to valid defaults. This is the
'generate the content schema' step made into one command instead of manual
YAML editing in two places that could drift apart.

    python3 scripts/new_article.py \\
        --folder vacation --file 07-part-time-vacation.md \\
        --title "Vacation for part-time employees" \\
        --owner hr --review on-law-change

If --folder doesn't exist yet in schema.yaml, it's created (you'll be asked
to fill in the folder's own owner via the printed reminder).
"""

import argparse
import pathlib
import sys

import yaml

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema.yaml"
STATUS_VOCAB = {"spec", "draft", "blocked", "live", "retired", "not_started"}
REVIEW_VOCAB = {"annual-jan", "on-cba-change", "on-law-change", "annual-free"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="folder key, e.g. vacation")
    ap.add_argument("--file", required=True, help="e.g. 07-part-time-vacation.md")
    ap.add_argument("--title", required=True)
    ap.add_argument("--owner", required=True, choices=["hr", "finance", "office", "it", "tooling", "ceo"])
    ap.add_argument("--review", required=True, choices=sorted(REVIEW_VOCAB))
    ap.add_argument("--content-type", default="TBD — set after drafting")
    args = ap.parse_args()

    schema = yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))

    folder = schema["folders"].setdefault(
        args.folder, {"title": args.folder.replace("-", " ").title(),
                       "owner": args.owner, "articles": []})
    if "articles" not in folder:
        # folder was a flat not_started stub — upgrade it
        folder["articles"] = []
    if any(a["file"] == args.file for a in folder["articles"]):
        raise SystemExit(f"'{args.file}' already exists in folder '{args.folder}'")

    folder["articles"].append({
        "file": args.file, "status": "spec", "review": args.review, "owner": args.owner,
    })
    SCHEMA.write_text(yaml.dump(schema, allow_unicode=True, sort_keys=False, width=100),
                       encoding="utf-8")

    content_dir = ROOT / "content" / args.folder
    content_dir.mkdir(parents=True, exist_ok=True)
    spec_path = content_dir / args.file
    if spec_path.exists():
        raise SystemExit(f"content file already exists: {spec_path}")

    spec_path.write_text(f"""---
title: "{args.title}"
folder: {folder['title']}
content_type: {args.content_type}
authoring_version: 1
question_refs: []    # IDs in reviews/questions.yaml; state lives in the register
status: spec
status_note: "Ready for drafting."
sources: []          # fill with ids from sources/sources.yaml
sources_snapshot: [] # filled automatically by scripts/harvest.py
figures_used: []      # figure keys this article will need (see figures/figures.yaml)
answers:
  - "TODO: first question an employee would ask that this article must answer"
review_notes_for_drafter: >
  Follow AUTHORING_GUIDE.md. TODO: anything the drafter needs to know that isn't in the sources —
  known gotchas, which CBA clause likely applies, company-specific angles.
reviewed_by: null
---
""", encoding="utf-8")

    print(f"✓ Added to schema.yaml under folder '{args.folder}'")
    print(f"✓ Spec stub created → {spec_path.relative_to(ROOT)}")
    print("\nNext steps:")
    print(f"  1. Fill in 'sources', 'figures_used' and 'answers' in the spec")
    print(f"  2. python3 scripts/harvest.py <source_id>   # if a new source is needed")
    print(f"  3. python3 scripts/draft.py {spec_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
