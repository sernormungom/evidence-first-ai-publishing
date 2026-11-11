#!/usr/bin/env python3
"""
Handbook build script.

1. Loads figures/figures.yaml (single source of truth for all amounts).
2. Renders every content/**/*.md by replacing {{key}} placeholders with the
   registry value, and {{key:unit}} with value + unit. A figure may opt into
   localized units for bare placeholders with display_unit: true.
3. Refuses to publish articles that reference figures with status
   'needs_verification' or 'placeholder' unless --allow-unverified is passed
   (they are still rendered, but marked DRAFT and listed in the report).
4. Prints a maintenance report: figures not verified within --max-age days.

Usage:
    python3 scripts/build.py [--allow-unverified] [--max-age 400]
"""

import argparse
import datetime as dt
import pathlib
import re
import sys

import yaml
import questions
import authoring

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIGURES = ROOT / "figures" / "figures.yaml"
CONTENT = ROOT / "content"
DIST = ROOT / "dist"

PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)(?::(unit|source|verified))?\s*\}\}")


def fmt_value(v):
    if v is None:
        return "⟨NOT SET⟩"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return f"{v:,}".replace(",", " ") if isinstance(v, int) else str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-unverified", action="store_true")
    ap.add_argument("--max-age", type=int, default=400,
                    help="days since last_verified before a figure is flagged stale")
    args = ap.parse_args()
    records = questions.load_questions(ROOT)
    article_problems = []

    registry = yaml.safe_load(FIGURES.read_text(encoding="utf-8"))
    figures = registry["figures"]
    today = dt.date.today()

    problems, stale = [], []
    for key, fig in figures.items():
        if fig.get("status") != "verified":
            problems.append((key, fig.get("status")))
        lv = fig.get("last_verified")
        if lv:
            age = (today - dt.date.fromisoformat(str(lv))).days
            if age > args.max_age:
                stale.append((key, age))
        else:
            stale.append((key, None))

    DIST.mkdir(exist_ok=True)
    built, drafts = [], []

    for src in sorted(CONTENT.rglob("*.md")):
        text = src.read_text(encoding="utf-8")
        from source_loader import split_frontmatter
        fm, original_body = split_frontmatter(text)
        effective = authoring.effective_metadata(ROOT, src.relative_to(CONTENT), fm)
        if effective != fm:
            text = '---\n' + yaml.safe_dump(effective, allow_unicode=True, sort_keys=False) + '---' + original_body
        fm = effective
        article_problems.extend(f"{src.relative_to(CONTENT)}: {problem}" for problem in questions.findings(fm or {}, records))
        if not args.allow_unverified and (fm or {}).get("status") != "live":
            article_problems.append(f"{src.relative_to(CONTENT)}: status is not live")
        used, missing, unverified = set(), set(), set()

        def sub(m):
            key, attr = m.group(1), m.group(2)
            fig = figures.get(key)
            if fig is None:
                missing.add(key)
                return f"⟨UNKNOWN FIGURE: {key}⟩"
            used.add(key)
            if fig.get("status") != "verified":
                unverified.add(key)
            if attr == "unit" or (attr is None and fig.get("display_unit", False)):
                unit_field = ("unit_sv" if src.name.endswith(".sv.md")
                              and fig.get("unit_sv") else "unit")
                return f"{fmt_value(fig['value'])} {fig.get(unit_field, '')}".strip()
            if attr == "source":
                return fig.get("source", "")
            if attr == "verified":
                return str(fig.get("last_verified", "never"))
            return fmt_value(fig["value"])

        rendered = PLACEHOLDER.sub(sub, text)

        rel = src.relative_to(CONTENT)
        out = DIST / rel
        out.parent.mkdir(parents=True, exist_ok=True)

        banner = ""
        if missing:
            article_problems.append(f"{rel}: unknown figure keys: {', '.join(sorted(missing))}")
            banner = ("> ⛔ **BUILD ERROR** — unknown figure keys: "
                      + ", ".join(sorted(missing)) + "\n\n")
        elif unverified:
            banner = ("> ⚠️ **DRAFT — NOT FOR PUBLICATION.** Uses unverified "
                      "figures: " + ", ".join(sorted(unverified))
                      + ". Verify in figures.yaml first.\n\n")
            drafts.append(str(rel))
        out.write_text(banner + rendered, encoding="utf-8")
        built.append((str(rel), sorted(used)))

    # ---- report ----
    print(f"Built {len(built)} article(s) → {DIST}")
    for rel, used in built:
        print(f"  • {rel}" + (f"   (figures: {', '.join(used)})" if used else ""))
    if drafts:
        print(f"\n⚠️  {len(drafts)} article(s) marked DRAFT (unverified figures):")
        for d in drafts:
            print(f"  • {d}")
    if problems:
        print("\n⚠️  Registry entries not fully verified:")
        for key, status in problems:
            print(f"  • {key}: {status}")
    if stale:
        print(f"\n🕑 Figures older than {args.max_age} days (or never verified):")
        for key, age in stale:
            print(f"  • {key}: {age if age is not None else 'never verified'} days")

    if article_problems:
        sys.exit("Publication/reference checks failed:\n" + "\n".join(article_problems))

    if (problems or drafts) and not args.allow_unverified:
        print("\nExit 1: unverified content present. "
              "Re-run with --allow-unverified to build drafts anyway.")
        sys.exit(1)


if __name__ == "__main__":
    main()
