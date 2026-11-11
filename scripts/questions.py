"""Authoritative question records and generated reviewer projections."""
import pathlib
import re

import yaml
from source_loader import split_frontmatter


QUESTION_ID = re.compile(r"^(?:G|\d{2})-(?:Q|FV|F)\d+$|^W-\d+$")


class UniqueLoader(yaml.SafeLoader):
    """A duplicate ID/status must not silently replace an unresolved item."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate question-register key {key} at line {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_questions(root):
    path = pathlib.Path(root) / "reviews/questions.yaml"
    if not path.exists():
        return {}
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)
    if not isinstance(data, dict) or not isinstance(data.get("questions"), dict):
        raise ValueError("reviews/questions.yaml: expected a questions mapping")
    records = data["questions"]
    for qid, record in records.items():
        if not isinstance(qid, str) or not QUESTION_ID.fullmatch(qid):
            raise ValueError(f"Invalid question ID: {qid}")
        if not isinstance(record, dict) or record.get("status") not in ("open", "resolved"):
            raise ValueError(f"{qid}: status must be open or resolved")
        if record.get("kind") not in ("decision", "figure", "company_figure", "wording"):
            raise ValueError(f"{qid}: invalid kind")
        if not isinstance(record.get("question"), str) or not record["question"].strip():
            raise ValueError(f"{qid}: missing question")
        if not isinstance(record.get("blocking"), bool):
            raise ValueError(f"{qid}: blocking must be true or false")
        if record["status"] == "resolved" and not record.get("resolution"):
            raise ValueError(f"{qid}: a resolution record is required")
    return records


def findings(fm, records):
    refs = fm.get("question_refs", [])
    if not isinstance(refs, list) or any(not isinstance(q, str) for q in refs):
        return ["question_refs must be a list of IDs"]
    result = []
    if len(set(refs)) != len(refs):
        result.append("question_refs contains duplicate IDs")
    for qid in refs:
        if qid not in records:
            result.append(f"unknown question reference {qid}")
        elif str(fm.get("status", "")).lower() == "live" and records[qid]["status"] == "open" and records[qid]["blocking"]:
            result.append(f"live article references unresolved blocking question {qid}")
    return result


def referenced(fm, records, open_only=False):
    return [(qid, records[qid]) for qid in fm.get("question_refs", [])
            if qid in records and (not open_only or records[qid]["status"] == "open")]


def review_context_yaml(records, ids):
    """Supply complete referenced decisions, including resolved answers, to models."""
    missing = set(ids) - set(records)
    if missing:
        raise ValueError('Unknown question references: ' + ', '.join(sorted(missing)))
    return yaml.safe_dump({qid: records[qid] for qid in sorted(set(ids))},
                          allow_unicode=True, sort_keys=False)


def cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def article_references(root):
    """Derive affected articles rather than maintain a duplicate list."""
    result = {}
    content = pathlib.Path(root) / "content"
    for path in content.rglob("*.md"):
        if path.name.endswith('.sv.md'):
            continue
        text = path.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(text)
        refs = (fm or {}).get('question_refs', [])
        if not (fm or {}).get('authoring_version'):
            refs = set(refs) | set(re.findall(r'\b(?:G|\d{2})-(?:Q|FV|F)\d+\b', text))
        for qid in refs:
            result.setdefault(qid, []).append(path.relative_to(content).as_posix())
    return result


def meeting_markdown(records, ids=None, root=None):
    """Full HR evidence stays here, never in the employee source panel."""
    selected = [(qid, record) for qid, record in records.items()
                if (ids is None or qid in ids) and record["status"] == "open"]
    lines = ["# Open questions — generated review copy", "",
             "Authority: reviews/questions.yaml. Edit that register, not this copy.", ""]
    affected = article_references(root) if root is not None else {}
    for kind, title in (("decision", "Company decisions"), ("figure", "Figure verification"),
                        ("company_figure", "Company figure confirmation"), ("wording", "Wording confirmations")):
        rows = [(qid, q) for qid, q in selected if q["kind"] == kind]
        lines += [f"## {title}", "", "| ID | Owner (proposed unless assigned) | Question | Evidence / documents | Referencing articles | Answer | Decision-maker / date |",
                  "|---|---|---|---|---|---|---|"]
        for qid, q in rows:
            evidence = q.get("evidence", "")
            if q.get("documents"):
                evidence += " Documents: " + str(q["documents"])
            lines.append("| " + " | ".join(cell(v) for v in
                         (qid, q.get("owner"), q["question"], evidence, ', '.join(affected.get(qid, [])), q.get("answer"), q.get("decided_by"))) + " |")
        lines.append("")
    return "\n".join(lines)
