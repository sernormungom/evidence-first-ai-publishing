#!/usr/bin/env python3
"""
Refresh the English counterpart of Example Studio company sections from the Swedish
maintained text (Swedish → English). Separate from scripts/translate.py,
which translates employee articles English → Swedish.

    python3 scripts/translate_policy.py company_vacation [company_business_trips …]
    python3 scripts/translate_policy.py --stale          # every stale/missing counterpart
    python3 scripts/translate_policy.py --dry-run company_vacation
    python3 scripts/translate_policy.py --force company_vacation   # even if current

Mode `update` (preferred): when the Swedish version the English was stamped
from is found in git history, the model gets previous + current Swedish and
their diff, and changes only the matching English passages. Otherwise mode
`full` translates the section, reusing correct existing English wording.

The English file is written only when the response is complete and passes
structure checks (same headings, redaction markers, links and
cross-references as the Swedish). It is then stamped
`translated_from: <fingerprint of the Swedish body>`. A missing API key, a
truncated or declined response, or a failed check leaves the existing English
file untouched and unstamped. Policy literal figures are kept; numbers that
appear in one language only are reported, not blocked.

Requires ANTHROPIC_API_KEY, or HANDBOOK_BACKEND=cli to use the Claude Code
CLI instead. Neither is needed for --dry-run.
"""
import difflib
import os
import re
import subprocess
import sys

import claude_api
import source_loader as sl

ROOT = sl.ROOT
PROMPT = ROOT / "POLICY_TRANSLATION_PROMPT.md"
NOTES_MARKER = "=== TRANSLATOR NOTES ==="
HEADING_RE = re.compile(r"^(#{1,6})\s+\S", re.M)
LINK_RE = re.compile(r"\]\(([^)\s]+)\)|(https?://[^\s)\]]+)")
XREF_RE = re.compile(r"^(?:See|Se) \*[^*]+\* (?:(?:in|i) \[[^\]]+\]\([^)\s]+\)|below|above|nedan|ovan)\.$", re.M)
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
def previous_swedish(rel_path, stamp, root=ROOT):
    """Find the Swedish body whose fingerprint equals the English stamp."""
    if not stamp:
        return None
    try:
        commits = subprocess.run(["git", "log", "--format=%H", "-n", "200", "--", rel_path],
                                 cwd=root, capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    for commit in commits:
        shown = subprocess.run(["git", "show", f"{commit}:{rel_path}"], cwd=root,
                               capture_output=True, text=True)
        if shown.returncode == 0 and sl.fingerprint_text(shown.stdout) == stamp:
            return sl.body_of(shown.stdout)
    return None


def build_request(sid, entry, root=ROOT, force=False):
    """Return a dict describing the work for one section, or None if current."""
    sv_rel, en_rel = entry["paths"]["sv"], entry["paths"]["en"]
    sv_path, en_path = sl.local_path(root, sv_rel), sl.local_path(root, en_rel)
    sv_text = sv_path.read_text(encoding="utf-8")
    sv_fm, _ = sl.split_frontmatter(sv_text)
    sv_body = sl.body_of(sv_text)
    fingerprint = sl.fingerprint_text(sv_text)
    en_body, stamp = None, None
    if en_path.exists():
        en_text = en_path.read_text(encoding="utf-8")
        en_body = sl.body_of(en_text)
        stamp = sl.raw_field(en_text, "translated_from")
    if stamp == fingerprint and not force:
        return None
    old_sv = previous_swedish(sv_rel, stamp, root) if en_body else None
    mode = "update" if old_sv is not None else "full"
    return {"sid": sid, "sv_fm": sv_fm, "sv_body": sv_body, "fingerprint": fingerprint,
            "en_path": en_path, "en_body": en_body, "old_sv": old_sv, "mode": mode}


def user_message(req, glossary):
    parts = [f"## MODE\n{req['mode']}",
             f"## CURRENT SWEDISH SECTION ({req['sid']})\n{req['sv_body']}"]
    if req["mode"] == "update":
        diff = "\n".join(difflib.unified_diff(req["old_sv"].split("\n"), req["sv_body"].split("\n"),
                                              "previous.sv.md", "current.sv.md", lineterm=""))
        parts += [f"## PREVIOUS SWEDISH SECTION\n{req['old_sv']}",
                  f"## DIFF (previous → current Swedish)\n{diff}"]
    parts.append("## CURRENT ENGLISH COUNTERPART\n" + (req["en_body"] or "(none — no English file yet)"))
    parts.append(f"## GLOSSARY\n{glossary}")
    parts.append("Produce the English section now, following every hard rule.")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
def structure(text):
    links = set()
    for m in LINK_RE.finditer(text):
        target = m.group(1) or m.group(2)
        links.add(target.replace(".sv.md", ".md"))
    return {
        "headings": [len(m.group(1)) for m in HEADING_RE.finditer(text)],
        "redactions": sorted(re.findall(r"\[REDACTED: [^\]]+\]", text)),
        "links": links,
        "cross-references": len(XREF_RE.findall(text)),
    }


def check_translation(sv_body, en_body):
    """Return (blocking problems, non-blocking warnings)."""
    problems, warnings = [], []
    if not en_body.startswith("# "):
        problems.append("does not start with a '# ' title line")
    sv, en = structure(sv_body), structure(en_body)
    for key in ("headings", "redactions", "cross-references"):
        if sv[key] != en[key]:
            problems.append(f"{key} differ from the Swedish ({_short(sv[key])} vs {_short(en[key])})")
    if sv["links"] - en["links"]:
        problems.append(f"links missing from the English: {_short(sv['links'] - en['links'])}")
    for link in sorted(en["links"] - sv["links"]):
        warnings.append(f"link {link} is in the English only")
    sv_nums, en_nums = numbers(sv_body), numbers(en_body)
    for n in sorted(sv_nums - en_nums):
        warnings.append(f"number {n} appears in the Swedish but not in the English")
    for n in sorted(en_nums - sv_nums):
        warnings.append(f"number {n} appears in the English but not in the Swedish")
    return problems, warnings


THOUSANDS_RE = re.compile(r"(?<![\d.,])\d{1,3}(?:[ \u00a0,]\d{3})+(?![\d])")


def numbers(text):
    """Numbers in a text, normalised so formatting differences do not count:
    thousands separators ("1 000", "1,000"), decimal comma, leading zeros in
    times ("09.00", "9:00")."""
    text = THOUSANDS_RE.sub(lambda m: re.sub(r"[ \u00a0,]", "", m.group(0)), text)
    text = re.sub(r"(\d{1,2}):(\d{2})", r"\1.\2", text)
    out = set()
    for n in NUMBER_RE.findall(text):
        n = n.replace(",", ".")
        whole, _, frac = n.partition(".")
        out.add((whole.lstrip("0") or "0") + ("." + frac if frac else ""))
    return out


def _short(value):
    s = str(sorted(value) if isinstance(value, set) else value)
    return s if len(s) < 80 else s[:77] + "…"


def english_file(req, en_body):
    title = en_body.split("\n", 1)[0][2:].strip()
    fm = req["sv_fm"]
    lines = ["---", f"source_id: {fm['source_id']}", f"section: {fm['section']}",
             f"title: {title}", "language: en", f'translated_from: "{req["fingerprint"]}"', "---", ""]
    return "\n".join(lines) + "\n" + en_body.strip() + "\n"


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def rel(path):
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def translate(req, prompt, glossary, dry_run):
    name = req["en_path"].name
    msg = user_message(req, glossary)
    print(f"{req['sid']}: {req['mode']} mode → {rel(req['en_path'])}")
    if dry_run:
        out = ROOT / "dist" / "prompts" / f"{req['en_path'].stem}.policy-translate.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"=== SYSTEM ===\n{prompt}\n\n=== USER ===\n{msg}\n", encoding="utf-8")
        print(f"   dry run: prompt ({len(prompt) + len(msg)} chars) → {rel(out)}")
        return True
    resp = claude_api.create_message(system=prompt, user_msg=msg, max_tokens=16000, timeout=900)
    note = claude_api.usage_note(resp)
    if note:
        print(f"   {note}")
    problem = claude_api.incomplete_reason(resp)
    if problem:
        print(f"   ❌ Not written: {problem}. {name} is unchanged and keeps its old stamp.")
        return False
    body, _, notes = claude_api.response_text(resp).partition(NOTES_MARKER)
    body = claude_api.unwrap_fences(body.strip())
    problems, warnings = check_translation(req["sv_body"], body)
    if problems:
        print(f"   ❌ Not written — the translation failed its checks; {name} is unchanged:")
        print("\n".join(f"      - {p}" for p in problems))
        return False
    tmp = req["en_path"].with_name(name + ".tmp")
    tmp.write_text(english_file(req, body), encoding="utf-8")
    os.replace(tmp, req["en_path"])
    print(f"   ✓ written and stamped translated_from: {req['fingerprint']}")
    for w in warnings:
        print(f"   ⚠️  {w}")
    notes_path = ROOT / "dist" / "company-translation" / f"{req['en_path'].stem}.notes.md"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(f"# Translator notes — {req['sid']} ({req['mode']})\n\n"
                          + "\n".join(f"- ⚠️ {w}" for w in warnings) + "\n\n" + notes.strip() + "\n",
                          encoding="utf-8")
    print(f"   notes → {rel(notes_path)}")
    deps = sl.dependent_articles(req["sid"])
    if deps:
        print(f"   Articles citing {req['sid']} — review them against the changed policy "
              f"(validate.py V11 lists those drafted from the old text):")
        print("\n".join(f"      - content/{d}" for d in deps))
    return True


def main():
    args = sys.argv[1:]
    dry_run, force, stale = "--dry-run" in args, "--force" in args, "--stale" in args
    ids = [a for a in args if not a.startswith("--")]
    registry = sl.load_registry()
    if stale:
        ids += sorted({sid for sid, lang, _ in sl.counterpart_problems(registry) if lang == "en"})
    if not ids:
        if stale:
            print("All English counterparts are current.")
            return
        sys.exit(__doc__)
    for sid in ids:
        entry = registry.get(sid)
        if not entry or not sl.is_company(entry) or "en" not in entry["paths"]:
            sys.exit(f"{sid}: not a company source with an English path in sources/sources.yaml")
    if not dry_run:
        claude_api.require_credentials()  # fail before any work, nothing written

    prompt = PROMPT.read_text(encoding="utf-8")
    glossary = (ROOT / "glossary.yaml").read_text(encoding="utf-8")
    ok = True
    for sid in dict.fromkeys(ids):
        req = build_request(sid, registry[sid], force=force)
        if req is None:
            print(f"{sid}: English counterpart is current — nothing to do (use --force to redo).")
            continue
        ok &= translate(req, prompt, glossary, dry_run)
    if not dry_run:
        print("\nRunning validator …")
        subprocess.run([sys.executable, "scripts/validate.py"], cwd=ROOT)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
