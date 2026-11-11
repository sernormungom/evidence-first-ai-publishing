#!/usr/bin/env python3
"""
Shared source loader for draft.py, translate.py, validate.py and review sheets.

Two kinds of registered source (sources/sources.yaml):

  official  — statutes, authority guidance, the CBA. Text comes from the
              latest dated text snapshot in sources/snapshots/<id>/.
  company   — Example Studio's own policy sections (type: internal with `paths`).
              Text is read directly from the registered local Markdown files
              under sources/company/policies/ — never copied into snapshots.

Company sections are maintained in Swedish (`maintained_language: sv`); the
English file is a translated counterpart whose `translated_from` stamp is the
fingerprint of the Swedish body. Legacy-background extracts, review notes and
raw exports can never be loaded: local paths must stay inside
sources/company/policies/.

A fingerprint is sha256[:12] of a file's body (text after the frontmatter,
line endings normalised, outer blank lines stripped) — see
sources/company/README.md. Articles record the fingerprint of each company
section they were drafted from (`source_fingerprints:`) so validation can warn
when the company text changes later.
"""
import hashlib
import pathlib
import re
from dataclasses import dataclass, field

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY_DIR = pathlib.PurePosixPath("sources/company/policies")
SNAPSHOT_SUFFIXES = {".txt", ".md"}
FINGERPRINT_KEY = "source_fingerprints"


class SourceError(Exception):
    """A registry entry that can never be loaded (configuration error)."""


@dataclass
class Source:
    id: str
    title: str
    role: str                      # "official" | "company"
    texts: list = field(default_factory=list)   # [(language, label, text)]
    fingerprint: str | None = None  # company: fingerprint of maintained file
    problem: str | None = None      # set when no usable text was found
    notes: list = field(default_factory=list)   # non-fatal remarks

    @property
    def available(self):
        return bool(self.texts) and self.problem is None


# --------------------------------------------------------------------------
# Fingerprints and frontmatter
# --------------------------------------------------------------------------
def split_frontmatter(text):
    """Return (frontmatter dict or {}, body)."""
    text = text.replace("\r\n", "\n")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return yaml.safe_load(parts[1]) or {}, parts[2]
    return {}, text


def body_of(text):
    return split_frontmatter(text)[1].strip("\n")


def fingerprint_text(text):
    return hashlib.sha256(body_of(text).encode("utf-8")).hexdigest()[:12]


def stamp(value):
    """Normalise a recorded fingerprint read from YAML (quoted or not)."""
    return None if value is None else str(value)


def raw_field(text, key):
    """Read a scalar frontmatter field as written, bypassing YAML typing."""
    m = re.search(rf"^{re.escape(key)}:\s*[\"']?([^\"'\s#]+)", split_frontmatter_text(text), re.M)
    return m.group(1) if m else None


def split_frontmatter_text(text):
    text = text.replace("\r\n", "\n")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[1]
    return ""


def fingerprint_file(path):
    return fingerprint_text(pathlib.Path(path).read_text(encoding="utf-8"))


def set_frontmatter_mapping(text, key, mapping):
    """Replace (or add) a top-level `key:` mapping in the frontmatter.

    Edits the frontmatter text in place so other fields keep their order and
    formatting. Values are plain scalars (fingerprints)."""
    if not text.startswith("---"):
        raise ValueError("document has no frontmatter")
    _, fm, rest = text.split("---", 2)
    lines = fm.strip("\n").split("\n")
    out, skipping = [], False
    for line in lines:
        if re.match(rf"^{re.escape(key)}\s*:", line):
            skipping = True
            continue
        if skipping and (line.startswith((" ", "\t")) or not line.strip()):
            continue
        skipping = False
        out.append(line)
    if mapping:
        out.append(f"{key}:")
        # Quoted: an all-digit or "123e4567"-shaped hex value would otherwise
        # be read back by YAML as a number.
        out += [f'  {k}: "{v}"' for k, v in sorted(mapping.items())]
    return "---\n" + "\n".join(out) + "\n---" + rest


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------
def load_registry(root=ROOT):
    path = pathlib.Path(root) / "sources" / "sources.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["sources"]


def is_company(entry):
    return entry.get("type") == "internal" and bool(entry.get("paths"))


def local_path(root, rel):
    """Resolve a registered local path, refusing anything outside policies/."""
    rel = pathlib.PurePosixPath(str(rel))
    if rel.is_absolute() or ".." in rel.parts or rel.parent != POLICY_DIR:
        raise SourceError(f"local source path {rel} must be a file directly in {POLICY_DIR}/ "
                          f"(legacy background, review notes and raw exports are not drafting inputs)")
    return pathlib.Path(root) / rel


def registry_errors(registry, root=ROOT):
    """Mechanical checks of company entries (used by validate.py)."""
    errors = []
    for sid, entry in registry.items():
        if not is_company(entry):
            continue
        paths = entry["paths"]
        maintained = entry.get("maintained_language")
        if maintained not in paths:
            errors.append(f"{sid}: maintained_language '{maintained}' has no path")
        for lang, rel in paths.items():
            try:
                p = local_path(root, rel)
            except SourceError as e:
                errors.append(f"{sid}: {e}")
                continue
            if not p.exists():
                errors.append(f"{sid}: {lang} file {rel} does not exist")
                continue
            fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
            if fm.get("source_id") != sid:
                errors.append(f"{sid}: {rel} declares source_id '{fm.get('source_id')}'")
            if fm.get("language") != lang:
                errors.append(f"{sid}: {rel} declares language '{fm.get('language')}', registered as '{lang}'")
    return errors


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def latest_snapshot(source_id, root=ROOT):
    folder = pathlib.Path(root) / "sources" / "snapshots" / source_id
    if not folder.exists():
        return None
    snaps = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in SNAPSHOT_SUFFIXES)
    return snaps[-1] if snaps else None


def counterpart_status(entry, root, lang):
    """For a derived-language file: (path, is_current, reason)."""
    maintained = pathlib.Path(root) / entry["paths"][entry["maintained_language"]]
    path = local_path(root, entry["paths"][lang])
    if not path.exists():
        return path, False, "file missing"
    recorded = raw_field(path.read_text(encoding="utf-8"), "translated_from")
    if not recorded:
        return path, False, "not reconciled (no translated_from)"
    if recorded != fingerprint_file(maintained):
        return path, False, "stale (Swedish source changed since translation)"
    return path, True, None


def load_company(sid, entry, root, languages):
    src = Source(sid, entry.get("title", sid), "company")
    maintained_lang = entry.get("maintained_language")
    maintained_rel = entry["paths"].get(maintained_lang)
    if not maintained_rel:
        src.problem = f"no path for maintained language '{maintained_lang}'"
        return src
    maintained = local_path(root, maintained_rel)
    if not maintained.exists():
        src.problem = f"maintained file {maintained_rel} is missing"
        return src
    text = maintained.read_text(encoding="utf-8")
    src.fingerprint = fingerprint_text(text)
    src.texts.append((maintained_lang, f"{maintained_rel} (maintained)", body_of(text)))
    for lang in languages:
        if lang == maintained_lang or lang not in entry["paths"]:
            continue
        path, current, reason = counterpart_status(entry, root, lang)
        if current:
            src.texts.append((lang, f"{entry['paths'][lang]} (translation of the {maintained_lang} text)",
                              body_of(path.read_text(encoding="utf-8"))))
        else:
            src.notes.append(f"{lang} counterpart left out: {reason}")
    return src


def load_official(sid, entry, root):
    src = Source(sid, entry.get("title", sid), "official")
    snap = latest_snapshot(sid, root)
    if snap is None:
        if entry.get("type") == "internal":
            src.problem = ("no text: legacy internal placeholder — cite the company_* company "
                           "section instead")
        else:
            src.problem = "no text snapshot — run `make harvest` (or add the manual snapshot)"
        return src
    src.texts.append((None, f"snapshot {snap.name}", snap.read_text(encoding="utf-8")))
    return src


def load_sources(ids, *, root=ROOT, languages=("sv", "en"), registry=None):
    """Load the given source ids. Returns a list of Source in input order.

    `languages`: which company-source languages to include. The maintained
    language is always included; others only when their translation is
    current. Unknown ids are returned with a problem, never silently dropped.
    """
    registry = registry if registry is not None else load_registry(root)
    out = []
    for sid in ids or []:
        entry = registry.get(sid)
        if entry is None:
            out.append(Source(sid, sid, "unknown", problem="not in sources/sources.yaml"))
        elif is_company(entry):
            out.append(load_company(sid, entry, root, languages))
        else:
            out.append(load_official(sid, entry, root))
    return out


def company_fingerprints(sources):
    return {s.id: s.fingerprint for s in sources if s.role == "company" and s.fingerprint}


# --------------------------------------------------------------------------
# Prompt formatting
# --------------------------------------------------------------------------
def format_sources(sources):
    """Render loaded sources as prompt sections with distinct roles."""
    official = [s for s in sources if s.role == "official" and s.available]
    company = [s for s in sources if s.role == "company" and s.available]
    missing = [s for s in sources if not s.available]
    parts = []
    parts.append("## OFFICIAL SOURCES (law, authority guidance, collective agreement)")
    if official:
        for s in official:
            for _, label, text in s.texts:
                parts.append(f"===== OFFICIAL SOURCE: {s.id} — {s.title} ({label}) =====\n{text}")
    else:
        parts.append("(none attached)")
    parts.append("## COMPANY COMPANY SOURCES (Example Studio's own policies and procedures)")
    if company:
        for s in company:
            for lang, label, text in s.texts:
                parts.append(f"===== COMPANY COMPANY SOURCE: {s.id} — {s.title} [{lang}] ({label}) =====\n{text}")
    else:
        parts.append("(none attached)")
    parts.append("## MISSING SOURCES")
    if missing:
        parts += [f"- {s.id}: {s.problem}" for s in missing]
        parts.append("Anything that depends on a missing source must appear as a "
                     "`> **BLOCKED:**` or `> **DECISION NEEDED:**` box — never fill it from memory.")
    else:
        parts.append("(none)")
    return "\n\n".join(parts)


def summary_lines(sources):
    """Human-readable loading summary for the terminal."""
    lines = []
    for s in sources:
        if s.available:
            labels = "; ".join(label for _, label, _ in s.texts)
            size = sum(len(t) for _, _, t in s.texts)
            fp = f", fingerprint {s.fingerprint}" if s.fingerprint else ""
            lines.append(f"  ✓ {s.id} [{s.role}] {labels} — {size} chars{fp}")
        else:
            lines.append(f"  ✗ {s.id}: {s.problem}")
        lines += [f"    ⚠️  {n}" for n in s.notes]
    return lines


# --------------------------------------------------------------------------
# Freshness
# --------------------------------------------------------------------------
def freshness_warnings(article_fm, registry, root=ROOT):
    """Warnings for an article whose company sources changed since drafting."""
    warnings = []
    recorded = {k: stamp(v) for k, v in (article_fm.get(FINGERPRINT_KEY) or {}).items()}
    cited = [sid for sid in article_fm.get("sources") or []
             if sid in registry and is_company(registry[sid])]
    for sid in cited:
        entry = registry[sid]
        try:
            maintained = local_path(root, entry["paths"][entry["maintained_language"]])
        except (KeyError, SourceError):
            continue  # reported by registry_errors
        if not maintained.exists():
            continue
        current = fingerprint_file(maintained)
        if sid not in recorded:
            if article_fm.get("status") in ("draft", "live"):
                warnings.append(f"{sid}: no fingerprint recorded — not drafted against the "
                                f"current company source; re-run `make draft`")
        elif recorded[sid] != current:
            warnings.append(f"{sid}: company source changed since drafting "
                            f"({recorded[sid]} → {current}); review the article against it")
    for sid in recorded:
        if sid not in cited:
            warnings.append(f"{sid}: fingerprint recorded but source no longer cited")
    return warnings


# --------------------------------------------------------------------------
# Policy translations (SV maintained → EN counterpart) and dependants
# --------------------------------------------------------------------------
def dependent_articles(sid, root=ROOT):
    """English canonical articles in content/ whose `sources:` cite `sid`."""
    out = []
    content = pathlib.Path(root) / "content"
    for path in sorted(content.rglob("*.md")):
        if path.name.endswith(".sv.md"):
            continue
        fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        if sid in (fm.get("sources") or []):
            out.append(path.relative_to(content).as_posix())
    return out


def counterpart_problems(registry, root=ROOT):
    """[(sid, lang, reason)] for every derived-language file that is missing,
    unreconciled or stale relative to the maintained Swedish text."""
    out = []
    for sid, entry in registry.items():
        if not is_company(entry):
            continue
        maintained_lang = entry.get("maintained_language")
        try:
            maintained = local_path(root, entry["paths"][maintained_lang])
        except (KeyError, SourceError):
            continue  # reported by registry_errors
        if not maintained.exists():
            continue
        for lang in entry["paths"]:
            if lang == maintained_lang:
                continue
            try:
                _, current, reason = counterpart_status(entry, root, lang)
            except SourceError:
                continue
            if not current:
                out.append((sid, lang, reason))
    return out


def translation_warnings(registry, root=ROOT):
    """V12: human-readable warnings, each naming the dependent articles."""
    warnings = []
    for sid, lang, reason in counterpart_problems(registry, root):
        deps = dependent_articles(sid, root)
        cited = f"; cited by {', '.join(deps)}" if deps else "; no article cites it yet"
        warnings.append(f"{sid}: {lang} counterpart {reason} — run "
                        f"`make translate-policy SOURCE={sid}`{cited}")
    return warnings


# --------------------------------------------------------------------------
# Company figures ↔ company sources
# --------------------------------------------------------------------------
def _number_forms(value):
    """Ways a registry value may be written in Swedish or English text."""
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    s = str(value)
    forms = {s, s.replace(".", ",")}
    if isinstance(value, int) and value >= 1000:
        forms |= {f"{value:,}".replace(",", " "), f"{value:,}"}
    return forms


def company_figure_findings(figures, registry, root=ROOT):
    """V13: check figures that quote the company text stating them.

    A figure maps to its company source with
        company_source: {id: company_vacation, quote: "rätt att spara 5 semesterdagar"}
    The quote must occur in the maintained Swedish text and contain the value.
    Returns (errors, warnings): a quote without the value is a registry error;
    a quote no longer found means the company text changed — a warning for the
    figure reviewer, never resolved automatically."""
    errors, warnings = [], []
    bodies = {}
    for key, fig in figures.items():
        ref = fig.get("company_source")
        if not ref:
            continue
        sid, quote = ref.get("id"), ref.get("quote", "")
        entry = registry.get(sid)
        if not entry or not is_company(entry):
            errors.append(f"{key}: company_source id '{sid}' is not a company source")
            continue
        forms = _number_forms(fig.get("value"))
        if fig.get("value") is not None and not any(f in quote for f in forms):
            errors.append(f"{key}: value {fig.get('value')} does not appear in its quote “{quote}”")
        if sid not in bodies:
            try:
                path = local_path(root, entry["paths"][entry["maintained_language"]])
                bodies[sid] = " ".join(body_of(path.read_text(encoding="utf-8")).split())
            except (KeyError, SourceError, FileNotFoundError):
                bodies[sid] = None
        if bodies[sid] is None:
            continue
        if " ".join(quote.split()) not in bodies[sid]:
            warnings.append(f"{key}: the company text it quotes is no longer in {sid} "
                            f"(“{quote}”) — the company figure may have changed; "
                            f"review the value and update the quote")
    return errors, warnings
