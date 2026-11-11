#!/usr/bin/env python3
"""
Validation gate. Run in CI on every PR. Exit non-zero on any violation.

Enforces the mechanical rules so human reviewers never have to:
  V1. Frontmatter complete (title, folder, content_type, status, sources).
  V2. No literal money/percent amounts in article prose — must be {{figure}}
      placeholders. (Blockquote lines '>' are exempt: that's where DECISION
      boxes quote historical numbers; they may not exist in 'live' articles.)
  V3. Every {{key}} used exists in figures/figures.yaml.
  V4. Every source id in frontmatter exists in sources/sources.yaml.
  V5. schema.yaml <-> content/ consistency: no orphan files, no ghost entries.
  V6. An article may only have status 'live' if reviewed_by is set AND all
      its figures are status: verified AND it contains no DECISION/BLOCKED
      boxes and no unreviewed-number exemptions.
  V9. No access data (door/insurance codes, access-key links, Outlook
      safelinks) in Example Studio company sources or their review notes. Raw exports
      (sources/company/example-guide*, sources/company/raw/) are git-ignored and
      not scanned.
  V10. Example Studio company sources in the registry resolve to existing files in
      sources/company/policies/ whose source_id and language match.
  V11. (warning) An article was drafted from a company section that has
      changed since (recorded source_fingerprints no longer match).
  V12. (warning) A company section's English counterpart is missing,
      unreconciled or stale against the Swedish maintained text; names the
      articles that cite the section.
  V13. Company figures (figures.yaml `company_source`) quote text containing
      their value (error); warning when the quoted company text has changed.
  Company sources themselves may contain literal figures — V2 checks
  articles in content/ only.

Usage: python3 scripts/validate.py
"""

import pathlib
import re
import sys

import yaml

import source_loader
import authoring
import questions

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

REQUIRED_FM = ["title", "folder", "content_type", "status", "sources"]
STATUS_VOCAB = {"spec", "draft", "blocked", "live", "retired", "not_started"}
PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)(?::[a-z]+)?\s*\}\}")
# money/percent literals: "SEK 300", "300 SEK", "25 kr", "12 %", "0.43%"
MONEY = re.compile(r"(SEK\s*\d|(?<![:.\d])\d[\d\s.,]*\s*(SEK|kr\b)|\d[\d.,]*\s*%)")
STATUTE = re.compile(r"\(\d{4}:\d+\)")  # e.g. (1977:480) — always allowed
DECISION_BOX = re.compile(
    r"\*\*(DECISION NEEDED|BESLUT (KRÄVS|BEHÖVS)|BLOCKED|"
    r"COMPANY (POLICY|PROCESS|ROUTINE)|MIGRATION NOTE|VERIFY)", re.I)

errors, warnings = [], []


def split_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    return yaml.safe_load(parts[1]), parts[2]


def main():
    errors.clear()
    warnings.clear()
    figures = yaml.safe_load((ROOT / "figures" / "figures.yaml").read_text(encoding="utf-8"))["figures"]
    sources = yaml.safe_load((ROOT / "sources" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    schema = yaml.safe_load((ROOT / "schema.yaml").read_text(encoding="utf-8"))["folders"]
    try:
        records = questions.load_questions(ROOT)
    except (ValueError, yaml.YAMLError) as exc:
        errors.append(f"V14 {exc}")
        records = {}

    # V5: schema <-> disk consistency (English canonical only; .sv.md are
    # derived siblings checked separately in V8)
    # NOTE: use as_posix() — schema.yaml keys are always forward-slash, but
    # relative_to() renders with the OS separator (backslash on Windows).
    schema_files = {}
    for folder_key, folder in schema.items():
        for art in folder.get("articles", []) if isinstance(folder, dict) else []:
            schema_files[f"{folder_key}/{art['file']}"] = art
    disk_files = {p.relative_to(CONTENT).as_posix() for p in CONTENT.rglob("*.md")
                  if not p.name.endswith(".sv.md")}
    sv_files = {p.relative_to(CONTENT).as_posix() for p in CONTENT.rglob("*.sv.md")}
    for f in sorted(disk_files - set(schema_files)):
        errors.append(f"V5 {f}: file exists but is not in schema.yaml")
    for f in sorted(set(schema_files) - disk_files):
        errors.append(f"V5 {f}: in schema.yaml but file does not exist")
    for en in sorted(disk_files):
        en_fm, _ = split_frontmatter((CONTENT / en).read_text(encoding='utf-8'))
        if (en_fm or {}).get('status') == 'live' and en.replace('.md', '.sv.md') not in sv_files:
            errors.append(f"V8 {en}: live article has no generated Swedish counterpart")

    # V8: Swedish siblings — must have a canonical, and must not be stale
    for sv in sorted(sv_files):
        en = sv.replace(".sv.md", ".md")
        if en not in disk_files:
            errors.append(f"V8 {sv}: Swedish version has no English canonical '{en}'")
            continue
        sv_fm, _ = split_frontmatter((CONTENT / sv).read_text(encoding="utf-8"))
        recorded = (sv_fm or {}).get("translated_from")
        mode = (sv_fm or {}).get("translation_hash_mode")
        if mode not in (None, "reader-v1"):
            errors.append(f"V8 {sv}: unknown translation_hash_mode {mode}")
        actual = authoring.translation_hash((CONTENT / en).read_text(encoding="utf-8"), mode)
        if not recorded:
            errors.append(f"V8 {sv}: missing 'translated_from' hash — regenerate "
                          f"with scripts/translate.py, never write .sv.md by hand")
        elif recorded != actual:
            en_fm, _ = split_frontmatter((CONTENT / en).read_text(encoding='utf-8'))
            message = (f"V8 {sv}: STALE — English canonical changed since "
                       f"translation (recorded {recorded}, now {actual}). "
                       f"Re-run scripts/translate.py {en}")
            (errors if (en_fm or {}).get('status') == 'live' else warnings).append(message)

    for path in sorted(CONTENT.rglob("*.md")):
        rel = path.relative_to(CONTENT).as_posix()
        fm, body = split_frontmatter(path.read_text(encoding="utf-8"))

        if fm is None:
            errors.append(f"V1 {rel}: missing/invalid frontmatter"); continue
        fm = authoring.effective_metadata(ROOT, rel, fm)
        for field in REQUIRED_FM:
            if field not in fm:
                errors.append(f"V1 {rel}: missing frontmatter field '{field}'")
        status = str(fm.get("status", "")).lower()
        for problem in questions.findings(fm, records):
            errors.append(f"V14 {rel}: {problem}")
        if fm.get("authoring_version") not in (None, authoring.VERSION):
            errors.append(f"V15 {rel}: unsupported authoring_version")
        if status in ("draft", "live"):
            try:
                justified = bool(authoring.load_review(ROOT, rel).get("length_justification"))
            except (ValueError, yaml.YAMLError):
                justified = False
            problems, advice = authoring.readability(fm, body, "sv" if path.name.endswith('.sv.md') else "en", justified)
            for problem in problems:
                if fm.get("authoring_version") == authoring.VERSION:
                    errors.append(f"V15 {rel}: {problem}")
            if fm.get("authoring_version") != authoring.VERSION and problems:
                advice = ["legacy article — " + "; ".join(problems)] + advice
            if advice:
                warnings.append(f"    V15 {rel}: " + "; ".join(advice))
            if fm.get("authoring_version") == authoring.VERSION and not path.name.endswith(".sv.md"):
                try:
                    record = authoring.load_review(ROOT, rel)
                    if not record.get("claims"):
                        raise ValueError("missing structured claim evidence")
                    for claim in record["claims"]:
                        if not isinstance(claim, dict) or claim.get("source") not in fm.get("sources", []) or not claim.get("claim") or not claim.get("provision") or claim.get("supported") is not True:
                            raise ValueError("claim evidence is incomplete or cites an unattached source")
                    if record.get("question_refs", []) != fm.get("question_refs", []):
                        raise ValueError("review and article question references differ")
                    if record.get("reader_hash") != authoring.translation_hash(path.read_text(encoding="utf-8"), "reader-v1"):
                        message = f"V15 {rel}: claim evidence predates current reader content — recheck it"
                        (errors if status == "live" else warnings).append(message)
                except (ValueError, yaml.YAMLError) as exc:
                    errors.append(f"V15 {rel}: {exc}")
        if status and status not in STATUS_VOCAB:
            errors.append(f"V0 {rel}: status '{fm.get('status')}' is not in the "
                          f"controlled vocabulary {sorted(STATUS_VOCAB)} — "
                          f"put explanatory text in 'status_note' instead")

        # V11 company-source freshness (English canonical only; the Swedish
        # sibling inherits it through V8)
        if not path.name.endswith(".sv.md"):
            for w in source_loader.freshness_warnings(fm, sources):
                warnings.append(f"    V11 {rel}: {w}")

        # V4 source ids
        for sid in fm.get("sources", []):
            if sid not in sources:
                errors.append(f"V4 {rel}: unknown source id '{sid}'")

        # V3 placeholders
        used_keys = set(PLACEHOLDER.findall(body))
        for key in sorted(used_keys):
            if key not in figures:
                errors.append(f"V3 {rel}: unknown figure key '{{{{{key}}}}}'")

        # V2 literal amounts in prose (blockquotes exempt)
        has_decision_box = False
        for i, line in enumerate(body.splitlines(), 1):
            if DECISION_BOX.search(line):
                has_decision_box = True
            if line.lstrip().startswith(">"):
                continue
            probe = STATUTE.sub("", PLACEHOLDER.sub("", line))
            if MONEY.search(probe):
                errors.append(f"V2 {rel}:{i}: literal amount in prose — use a "
                              f"figure placeholder. Line: {line.strip()[:80]}")

        # V6 'live' gate
        if status == "live":
            if not fm.get("reviewed_by"):
                errors.append(f"V6 {rel}: status 'live' but reviewed_by is empty")
            for key in used_keys:
                if figures.get(key, {}).get("status") != "verified":
                    errors.append(f"V6 {rel}: live article uses unverified figure '{key}'")
            if has_decision_box:
                errors.append(f"V6 {rel}: live article still contains a DECISION/BLOCKED/VERIFY box")

        # V7 reader-first structure: drafted/live articles must open with the
        # answer section ("## In short" / "## Kort svar" for .sv.md).
        if status in ("draft", "live"):
            want = "kort svar" if path.name.endswith(".sv.md") else "in short"
            first_heading = next((ln for ln in body.splitlines()
                                  if ln.startswith("## ")), "")
            if want not in first_heading.lower():
                msg = f"V7 {rel}: first section must be '## {want.title()}' (answer-first for readers)"
                (errors if status == "live" else warnings).append(
                    msg if status == "live" else "    " + msg)

        # schema.yaml is the master status; frontmatter must match exactly now
        # that both use the same controlled vocabulary.
        sch = schema_files.get(rel)
        if sch and status and sch.get("status") != status:
            warnings.append(f"    {rel}: schema says status '{sch.get('status')}' "
                            f"but frontmatter says '{status}' — update schema.yaml "
                            f"(the source of truth) via PR")

    # V10: company-source registry entries resolve to valid local files.
    for e in source_loader.registry_errors(sources):
        errors.append(f"V10 sources.yaml {e}")

    # V12: English counterparts of company sections follow the Swedish text.
    for w in source_loader.translation_warnings(sources):
        warnings.append(f"    V12 {w}")

    # V13: company figures stay tied to the company text that states them.
    fig_errors, fig_warnings = source_loader.company_figure_findings(figures, sources)
    errors.extend(f"V13 figures.yaml {e}" for e in fig_errors)
    warnings.extend(f"    V13 figures.yaml {w}" for w in fig_warnings)

    # V9: access data must never reach tracked company sources or notes.
    from sensitive import find_sensitive
    company = ROOT / "sources" / "company"
    company_files = [f for f in company.rglob("*.md")
                     if not f.name.startswith("example-guide") and "raw" not in f.relative_to(company).parts]
    company_files += sorted((ROOT / "reviews").glob("company-*.md"))
    company_files += sorted((ROOT / "reviews").rglob("*.review.yaml"))
    company_files += sorted((ROOT / "reviews").rglob("*.translation.md"))
    if (ROOT / 'reviews/questions.yaml').exists():
        company_files.append(ROOT / 'reviews/questions.yaml')
    for f in company_files:
        for line_no, kind in find_sensitive(f.read_text(encoding="utf-8")):
            errors.append(f"V9 {f.relative_to(ROOT)}:{line_no}: {kind} — replace the value "
                          f"with [REDACTED: {kind}] (see sources/company/README.md)")

    if warnings:
        print(f"⚠️  {len(warnings)} warning(s):")
        print("\n".join(warnings))
    if errors:
        print(f"\n❌ {len(errors)} validation error(s):")
        print("\n".join("  " + e for e in errors))
        sys.exit(1)
    print(f"\n✅ Validation passed: {len(disk_files)} article(s) checked.")


if __name__ == "__main__":
    main()
