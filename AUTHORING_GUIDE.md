# Write for the employee

Version: 1. This is the shared authoring contract for planners, writers,
translators and reviewers. The generation scripts attach it automatically.
It adapts the Vacation reader feedback without treating that feedback as a
legal audit or approval of existing articles.

## The page

- Title and headings answer questions an employee would ask.
- Start with `## In short` (`## Kort svar` in Swedish): one to three sentences
  or at most three bullets, no more than sixty words. This IS the opening
  answer; do not repeat it in a second summary. Use plain English without
  Swedish glosses in the English summary.
- Keep a condition in the answer if leaving it out would change the reader's
  entitlement or next action. Clear language does not mean unconditional promises.
- Give practical steps first, then relevant exceptions and examples. A short
  procedure may need only a few hundred words. Aim to stay below twelve hundred
  reader-visible words; explain a necessary exception in the review record's
  `length_justification`.
- Explain a Swedish legal term once, at first use in the detail. Preserve exact
  terms and distinctions; do not repeat glosses throughout the article.
- Use one worked example for each calculation rule that needs explanation.
  Amounts, rates and thresholds use registered figure placeholders, including
  illustrative amounts. Preserve calculation bases, units, exceptions and rounding.
- Put precise claim-to-source evidence in the review record. Use Markdown footnotes
  if a reader needs a specific citation. The build supplies an expandable source
  panel; do not repeat a table proving that several sources agree.
- Use ordinary Markdown, not hand-built disclosure HTML. Every cross-reference
  must resolve to an actual page; missing Swedish targets are explicitly labeled
  English links or reported as missing, never fabricated translations.

## Uncertainty and evidence

Research the complete section before drafting. Use attached primary and maintained
company sources, never licensed legacy explanations. Law, CBA, authority guidance
and company arrangements have different evidential roles. A company claim does
not establish a legal rule. Preserve disagreements; do not choose company policy.

Write only employee-facing uncertainty in the article: what is unconfirmed,
what that means for this answer and the documented next step/contact, if known.
Do not invent a contact or instruction. Mention a genuine gap once where useful,
not in every paragraph. Never move an action-critical qualification out of view.

Full HR questions, requested documents and source conflicts belong in
`reviews/questions.yaml`. Preserve IDs and resolutions. Reference relevant IDs in
the article's `question_refs`; register a genuinely new question before generating
an article that refers to it. Evidence/figure verification is distinct from an HR
decision. Generated meeting sheets derive affected articles from references and
are copies, not another authority. Resolving a record requires rechecking those
articles and updating English/Swedish through the normal review process; a status
change alone does not rewrite employee guidance.

Do not write DECISION/BLOCKED/VERIFY boxes, HR assignments, self-verification or
workflow updates in a version-one employee article. Detailed evidence belongs in
its generated `reviews/<folder>/<stem>.review.yaml` record. Translator notes use
`<stem>.translation.md` in the same directory; review sheets are generated copies.
Keep progress in the review record;
the article's `status_note` is a stable explanation, not a running task log.
After editing English, recheck claim evidence and update its `reader_hash` using
the expected fingerprint printed by `make review`; never stamp unchecked evidence.
Existing articles retain their legacy warnings until explicitly migrated.

## Generation and review

New article frontmatter includes `authoring_version: 1` and `question_refs: []`.
Keep the controlled status vocabulary: `spec`, `draft`, `blocked`, `live`,
`retired`, `not_started`. Generation sets `draft` and leaves `reviewed_by` null.
The separate review notes contain the structured evidence required by the drafting
prompt. Neither successful generation nor a matching hash is an attestation.

Finish English content, reader-facing metadata and reader review before Swedish
generation. Generate Swedish through the pipeline; never hand-edit employee
translations. Both languages must preserve content, question IDs, figure keys,
qualifiers and modal strength. Review the whole file after every regeneration.

Source review and bilingual review remain independent and read-only. Include a
reader check in those reviews: can an employee find the answer, act on it and see
the applicable exception without reading HR work? Return positive claim evidence,
not just a clean verdict. Use the approved bounded review loops and record accepted
exceptions honestly. Do not add a separate readability agent by default.

Planners specify reader questions, coverage, sources, ownership, dependencies and
review gates, and reference this contract rather than copying it. Before writing
another article, compare the section's accepted example. Local demonstration
examples in `examples/authoring/` are synthetic fixtures, never company policy.
