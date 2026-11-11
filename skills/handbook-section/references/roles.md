# Compact role handoffs

Use fresh role sessions, with the minimum relevant files. Repository paths are
references to inspect, not evidence that the contents were read. Avoid copying the
authoring contract into multiple maintained prompts; attach/reference its current
contents as supported by the runner. A role cannot approve its own work.

## Planner (one call, only if needed)

Provide section schema, existing plan/specs, sanitized maintained sources, source
registry, relevant question records and figure/glossary context. Ask for:

- Article mapping and employee questions, including sensible consolidation.
- Relevant complete source provisions, currentness and concrete source gaps.
- Shared calculations/terms, company conflicts and dependencies.
- A short execution plan with article ownership, source/bilingual gates and budget.

Do not let the planner rewrite registry decisions or resolve company questions.
Coordinator checks the plan and registers actual missing inputs before generation.

## Writer / translator

Use existing `make draft ARTICLE=... PYTHON=python3` and `make translate` commands,
with explicitly authorized backend/model configuration. They already supply the
generation prompts and authoring guide. Do not launch a second model merely to
run these commands. Capture actual payloads, output, usage and failures using an
applicable existing runner/capture mechanism; the ledger is not that mechanism.
Check rejected-draft artifacts and inner failures before deciding to retry.

For translation corrections, use the pipeline's supported feedback mechanism;
inspect `make help` and the current translation script rather than inventing flags.

## Source reviewer (fresh, independent, read-only)

Provide complete current English articles, relevant primary/company sources,
figures and evidence records, the accepted section plan, guide and prior findings.
First pass: all material claims, action-critical omissions, calculations, timing,
company/legal boundaries and reader usability. Later passes: findings, changes and
new risks, retaining unchanged positive evidence. Read the original PDF pages when
layout or tables affect interpretation; state reliance on prior checks honestly.

Return compact JSON with `articles`, one entry per requested article:

```json
{
  "articles": [{
    "article": "content/folder/01-example.md",
    "verdict": "accept",
    "positive_evidence": [{
      "claim": "Specific material claim checked",
      "source": "registered_source_id",
      "locator": "provision/page and dated snapshot",
      "check": "Why it supports the claim; calculation where applicable"
    }],
    "findings": []
  }]
}
```

Use the exact requested canonical English path in `article`, including for pairs.
Use `changes_requested` for unresolved material defects; minor findings may accompany
`accept` under the agile profile. Each finding contains an ID,
severity (`blocker`, `major`, `minor`), location, problem, evidence and suggested
fix. Include previous finding dispositions on correction passes. Positive evidence
must cover actual material claim groups; a clean verdict or matching hash alone
does not establish review. Coordinator validates article coverage and evidence,
then updates authoritative review records; keep detailed proof outside prose.

## Bilingual reviewer (fresh, independent, read-only)

Provide every full English/Swedish pair, glossary, relevant figure values,
accepted source evidence and prior translation findings. Reuse English research;
do not repeat the source audit without a concrete concern. Review all paragraphs
for omissions/additions, numbers/units, qualifiers, modality, terms, next actions,
links, metadata, reader usability and English fallback labels. For each article,
use the same compact result shape, with paired EN/SV passages in material positive
evidence and findings. Add `english_correction_required: true` when the defect
originates in English. Review whole Swedish files again after any regeneration.
Canonical `.md` links render within the current language when a translated target
exists (`scripts/build_site.py:article_links`); an English filename alone does not
establish an English destination. Check the resolved target before flagging it.

## Coordinator disposition

Read results, do not infer acceptance from process exit codes. Record accepted
minor style imperfections explicitly; material unresolved findings leave the article unaccepted as a draft.
Do not ask for repeated editorial approval under the agile profile. Source semantic edits need renewed relevant source review. Preserve
independent results and input hashes before updating evidence freshness. No final
auditor call by default; deterministic checks and actual output inspection remain.
