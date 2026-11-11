#!/usr/bin/env python3
"""
Generate the review sheet for an article — used as the PR description, so
the reviewer does everything inside one GitHub page with checkboxes.

    python3 scripts/make_review_sheet.py content/vacation/02-earning-vacation.md

The sheet contains, in plain language:
  1. The questions this article must answer (from the spec) — tick each.
  2. Every figure used: value, source link, verification status.
  2b. Every source used: official snapshot date or local company file, and
      whether a company section changed since the draft.
  3. Every DECISION/BLOCKED box that needs the reviewer's answer.
  4. Structured claim evidence and workflow, or legacy Markdown review notes.
  5. A single attestation checkbox that gates the merge.
"""

import pathlib
import re
import sys

import yaml

import source_loader
import authoring
import questions
import markdown

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)(?::[a-z]+)?\s*\}\}")
BOX = re.compile(r"^> \*\*(.+?):?\*\*(.*)$")


def main():
    path = ROOT / sys.argv[1]
    text = path.read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---")[1])
    body = text.split("---", 2)[2]
    records = questions.load_questions(ROOT)
    relative_article = path.relative_to(ROOT / "content")
    evidence = authoring.load_review(ROOT, relative_article)
    figures = yaml.safe_load((ROOT / "figures" / "figures.yaml").read_text(encoding="utf-8"))["figures"]

    lines = [f"# Review sheet — {fm['title']}", ""]
    replaces = fm.get("replaces_legacy_articles") or fm.get("replaces_legacy_article") or ["—"]
    if isinstance(replaces, str):
        replaces = [replaces]
    lines += [f"*Folder: {fm['folder']} · Replaces: {', '.join(replaces)}*", ""]

    lines += ["## 1. Does the article answer these questions?",
              "*Read the rendered article (link in the PR checks) and tick each:*", ""]
    for q in fm.get("answers", ["(spec has no answers list — add one)"]):
        lines.append(f"- [ ] {q}")

    lines += ["", "## 2. Are these figures right for us?", "",
              "| Figure | Value | Status | Check against |", "|---|---|---|---|"]
    for key in sorted(set(PLACEHOLDER.findall(body))):
        f = figures.get(key)
        if f is None:
            lines.append(f"| {key} | ⚠️ not in figures registry | — | — |")
            continue
        src = f.get("source", "")
        link = f"[source]({src})" if str(src).startswith("http") else src
        lines.append(f"| {key} | {f.get('value')} {f.get('unit','')} "
                     f"| {f.get('status')} | {link} |")

    registry = source_loader.load_registry()
    recorded = {k: source_loader.stamp(v) for k, v in (fm.get(source_loader.FINGERPRINT_KEY) or {}).items()}
    lines += ["", "## 2b. Sources the draft used", "",
              "| Source | Kind | Text used | Status |", "|---|---|---|---|"]
    for s in source_loader.load_sources(fm.get("sources") or [], registry=registry):
        if s.role == "company":
            used = ", ".join(f"`{label.split(' ')[0]}`" for _, label, _ in s.texts) or "—"
            if not s.available:
                status = f"⚠️ {s.problem}"
            elif s.id not in recorded:
                status = "⚠️ not drafted from this version (no fingerprint)"
            elif recorded[s.id] != s.fingerprint:
                status = f"⚠️ changed since draft ({recorded[s.id]} → {s.fingerprint})"
            else:
                status = f"current ({s.fingerprint})"
            kind = "Example Studio company section (Swedish maintained)"
        else:
            entry = registry.get(s.id, {})
            url = entry.get("url")
            used = s.texts[0][1] if s.texts else "—"
            status = f"[{entry.get('type', '?')}]({url})" if url else entry.get("type", "?")
            status = status if s.available else f"⚠️ {s.problem}"
            kind = s.title
        lines.append(f"| {s.id} | {kind} | {used} | {status} |")

    boxes = [m.group(0) for line in body.splitlines()
             if (m := BOX.match(line.strip()))]
    lines += ["", "## 3. Decisions needed from you", ""]
    refs = fm.get("question_refs", [])
    if refs:
        lines += [questions.meeting_markdown(records, refs, ROOT), ""]
        for qid, record in questions.referenced(fm, records):
            if record['status'] == 'resolved':
                lines += [f"Resolved {qid}: {record.get('answer') or record.get('resolution')}",
                          "Recheck the employee answer against this resolution; status alone does not update prose.", ""]
    if boxes:
        lines += [f"- [ ] {b.lstrip('> ').strip()}" for b in boxes]
        lines += ["", "*Answer each in a PR comment; the drafter (or the bot) "
                  "updates the article. The validator blocks 'live' status "
                  "while any box remains.*"]
    elif not refs:
        lines.append("*(No registered question references or legacy boxes. This does not establish that company policy is complete.)*")

    review_notes = ROOT / "reviews" / (path.stem + ".md")
    lines += ["", "## 4. Drafter's self-verification", ""]
    if not evidence:
        lines += [review_notes.read_text(encoding="utf-8")] if review_notes.exists() else \
                 ["*(no self-verification file found — ask the drafter)*"]
    if evidence:
        current = authoring.translation_hash(text, "reader-v1")
        freshness = "current" if evidence.get("reader_hash") == current else "CHANGED — recheck evidence against the current article"
        lines += ["", f"Evidence content fingerprint: {freshness}. Expected reader_hash: `{current}`."]
        lines += ["", "### Structured claim evidence", "", "| Claim | Source | Provision / heading / page |",
                  "|---|---|---|"]
        for claim in evidence.get("claims", []):
            lines.append("| " + " | ".join(questions.cell(claim.get(k)) for k in ("claim", "source", "provision")) + " |")
        lines += ["", "### Workflow (not attestation)", "", "```yaml",
                  yaml.safe_dump(evidence.get("workflow", {}), allow_unicode=True).strip(), "```"]
        lines += ["", "### Writer notes", ""]
        lines += ["- " + str(note) for note in evidence.get('notes', [])]
        if evidence.get('writer_commentary'):
            lines += [str(evidence['writer_commentary'])]
        translation_notes = authoring.review_path(ROOT, relative_article).with_name(path.stem + '.translation.md')
        if translation_notes.exists():
            lines += ['', '### Translator notes', '', translation_notes.read_text(encoding='utf-8')]
    lines += ["", "## Reader check (included in source and bilingual review)", "",
              "- [ ] Find the answer and next action without reading reviewer work.",
              "- [ ] Short answer retains conditions that change the employee's action or entitlement.",
              "- [ ] Useful example, clear exceptions, terms explained once and working links.",
              "- [ ] Compare the whole regenerated Swedish text with English and sources.",
              "", "Mechanical checks and writer evidence do not prove semantic accuracy or HR approval."]

    lines += ["", "---", "## 5. Attestation (required to merge)", "",
              "- [ ] **I confirm the article is accurate for Example Studio "
              "as of today, to the best of my knowledge, based on the checks "
              "above.** — *reviewer name will be recorded in `reviewed_by`*"]

    out = (authoring.review_path(ROOT, relative_article).with_name(path.stem + '.sheet.md')
           if fm.get('authoring_version') == authoring.VERSION else ROOT / "reviews" / (path.stem + ".sheet.md"))
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # A browser-readable reviewer copy; never place reviewer data under site/.
    review_dir = ROOT / "dist" / "review" / relative_article.parent
    review_dir.mkdir(parents=True, exist_ok=True)
    html_body = markdown.markdown("\n".join(lines), extensions=["tables", "fenced_code"])
    import html
    # Article-local links in the generated sheet resolve to employee preview pages.
    from bs4 import BeautifulSoup
    from urllib.parse import urlsplit
    soup = BeautifulSoup(html_body, "html.parser")
    for link in soup.find_all("a", href=True):
        parsed = urlsplit(link["href"])
        if not parsed.scheme and parsed.path.endswith(".md") and "/" not in parsed.path:
            link["href"] = "../../../site/en/" + relative_article.parent.as_posix() + "/" + parsed.path[:-3] + ".html"
    (review_dir / (path.stem + ".html")).write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        + '<title>' + html.escape(fm['title']) + ' — review</title>'
        + '<style>body{max-width:1100px;margin:2rem auto;padding:1rem;font:16px/1.6 sans-serif}table{border-collapse:collapse;width:100%}td,th{padding:.5rem;border:1px solid #ccc;vertical-align:top}pre{white-space:pre-wrap}</style>'
        + str(soup) + '</html>', encoding="utf-8")
    (ROOT / "dist" / "review" / "questions.md").write_text(questions.meeting_markdown(records, root=ROOT), encoding="utf-8")
    print(f"✓ Review sheet → {out.relative_to(ROOT)}  "
          f"(paste as PR description, or let CI post it)")


if __name__ == "__main__":
    main()
