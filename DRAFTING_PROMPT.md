# Draft an employee article
# Version 4 — content-only output; metadata constructed in code. Shared AUTHORING_GUIDE.md is attached by scripts/draft.py.

Write one original English employee article from the attached article specification,
primary Swedish sources and maintained Example Studio company sources. Follow the attached
shared authoring contract. A specification may contain older guidance; the shared
contract controls presentation, while its factual coverage and source boundaries
must still be respected.

Sources have separate roles. Statutes, the applicable collective agreement and
binding authority rules establish external requirements; distinguish general advice.
Maintained Swedish company sections establish documented Example Studio arrangements. Current
English counterparts assist understanding. Company text does not prove a legal rule.
If the sources disagree, retain the material condition in employee language and
record the conflict for review; do not select or change company policy.

Use only attached source evidence. Never copy or closely paraphrase licensed legacy
explanations. Never invent a reporting channel, insurer, contact, procedure or
attestation. Never reproduce access codes, tokens or redacted values. Company-source
cross-references identify navigation, not additional evidence.

Use only AVAILABLE FIGURE KEYS for amounts, percentages, rates and thresholds.
Preserve placeholders in worked examples. Ordinary counts/deadlines may be words.
If a key or source is missing, do not invent it: record the gap in review notes and
state the action-critical uncertainty in employee language. Exact source IDs and
provisions belong in review evidence. Footnotes are optional for reader-useful
citations; the renderer creates the source panel. No inline legal citation lists,
HR-directed boxes or self-verification tables in the employee article.

Answer all specification questions, with relevant qualifiers, exceptions and modal
strength. Introduce exact Swedish terms from the attached glossary once in English
detail. Keep the short English answer free of glosses. Preserve the distinction
between law, CBA applicability and company practice without repeating provenance
when sources agree.

Output only the employee Markdown body, beginning with ## In short, without a
code fence or introductory commentary. Aim for at most 45 words in that opening,
leaving room below the contract's sixty-word maximum. Give the main answer and its
essential condition; put detailed rules in the following sections rather than
trying to summarize every topic. Do not generate frontmatter: Python copies
the specification's identity, title, questions, source/figure/question references
and replacement mappings, sets authoring_version: 1, status: draft and
reviewed_by: null, and records source fingerprints. If another question is
necessary, propose it in review notes for registration before acceptance.

After the employee article, output exactly this heading:
## Review notes (not for publication)

Start that section with a fenced YAML evidence record, followed by optional prose:

```yaml
claims:
  - claim: "A complete factual claim from the article"
    source: "attached_registered_source_id"
    provision: "Exact statute section, company heading or CBA provision and page"
    supported: true
notes:
  - "Remaining source/application gaps, proposed questions or figure keys"
```

Quote all YAML string values as complete strings, escaping embedded double quotes;
never close a quote before the rest of its value. Keep provision short for the
employee source panel; put detailed reasoning in an optional evidence_detail field.

Cover every factual claim and required answer, including calculations and
exceptions. Each claim cites an attached source. Correct unsupported claims or
exclude them from employee prose; do not mark them supported to make a check pass.
This is writer self-verification, never independent review or HR attestation.
