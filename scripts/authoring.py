"""Shared authoring contract, reader fingerprints and structured review evidence."""
import hashlib
import json
import pathlib
import re

import yaml

from source_loader import split_frontmatter


VERSION = 1
READER_FIELDS = ("title", "folder", "answers", "question_refs", "legal_basis", "sources", "figures_used")
EDITORIAL = re.compile(r"\*\*(?:DECISION NEEDED|BESLUT (?:KRÄVS|BEHÖVS)|BLOCKED|VERIFY|MIGRATION NOTE)", re.I)


def contract(root):
    """Fail closed: an installed generator must not silently omit its contract."""
    return (pathlib.Path(root) / "AUTHORING_GUIDE.md").read_text(encoding="utf-8")


def translation_hash(text, mode=None):
    fm, body = split_frontmatter(text)
    if mode != "reader-v1":
        return hashlib.sha256(text.encode()).hexdigest()[:12]
    data = {key: (fm or {}).get(key) for key in READER_FIELDS}
    data["body"] = body.replace("\r\n", "\n").strip()
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def review_path(root, relative_article):
    rel = pathlib.Path(relative_article)
    stem = rel.name.removesuffix(".sv.md").removesuffix(".md")
    return pathlib.Path(root) / "reviews" / rel.parent / (stem + ".review.yaml")


def effective_metadata(root, relative_article, fm):
    """A reader-hash translation inherits governance from canonical English."""
    rel = pathlib.Path(relative_article)
    result = dict(fm or {})
    if rel.name.endswith(".sv.md") and result.get("translation_hash_mode") == "reader-v1":
        canonical = pathlib.Path(root) / "content" / rel.parent / rel.name.replace(".sv.md", ".md")
        if canonical.exists():
            en, _ = split_frontmatter(canonical.read_text(encoding="utf-8"))
            for field in ("status", "reviewed_by"):
                result[field] = (en or {}).get(field)
    return result


def load_review(root, relative_article):
    path = review_path(root, relative_article)
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a review mapping")
    return data


def parse_evidence(notes, fm, records):
    match = re.search(r"```ya?ml\s*\n(.*?)\n```", notes, re.S)
    if not match:
        raise ValueError("Missing structured YAML evidence in Review notes")
    data = yaml.safe_load(match[1])
    if not isinstance(data, dict) or not isinstance(data.get("claims"), list) or not data["claims"]:
        raise ValueError("Review evidence must include a nonempty claims list")
    for claim in data["claims"]:
        if not isinstance(claim, dict) or not all(claim.get(k) for k in ("claim", "source", "provision")):
            raise ValueError("Each claim needs claim, source and provision")
        if claim["source"] not in fm.get("sources", []):
            raise ValueError(f"Claim cites unattached source {claim['source']}")
        if claim.get("supported") is not True:
            raise ValueError("Unsupported claims must be corrected or excluded from employee prose")
    refs = fm.get("question_refs", [])
    if not isinstance(refs, list) or any(not isinstance(q, str) or q not in records for q in refs):
        raise ValueError("Article has an unregistered question reference")
    data["question_refs"] = refs
    commentary = notes[match.end():].strip()
    if commentary:
        data["writer_commentary"] = commentary
    data["workflow"] = {"source_review": "pending", "bilingual_review": "pending"}
    return data


def readability(fm, body, lang="en", length_justified=False):
    """Errors for version-one articles, advisory messages for legacy drafts.

    length_justified: the review record carries a length_justification."""
    problems, warnings = [], []
    heading = "Kort svar" if lang == "sv" else "In short"
    match = re.search(rf"^## {heading}\s*\n(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not match:
        problems.append(f"missing opening '## {heading}'")
    else:
        first = re.search(r"^## .+$", body, re.M)
        if first and first.start() != match.start():
            problems.append(f"first section must be '## {heading}'")
        words = re.findall(r"\S+", match[1])
        if len(words) > 60:
            problems.append(f"opening answer has {len(words)} words; maximum is 60")
        if len(re.findall(r"^\s*[-*+]\s", match[1], re.M)) > 3:
            problems.append("opening answer has more than three bullets")
    if EDITORIAL.search(body) or re.search(r"^## (?:Review notes|Self-verification)", body, re.M | re.I):
        problems.append("reviewer-only material belongs in the review record")
    if re.search(r"\((?:Semesterlagen|Sjuklönelagen|LAS\b|Innovationsavtalet|Socialförsäkringsbalken)[^)]*(?:§|section|clause|\d)[^)]*\)", body):
        warnings.append("move inline statutory citations to evidence or Markdown footnotes")
    if len(re.findall(r"\S+", body)) > 1200 and not length_justified:
        warnings.append("article exceeds 1,200 words; justify necessary detail in its review record")
    return problems, warnings
