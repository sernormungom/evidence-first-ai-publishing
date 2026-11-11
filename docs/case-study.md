# From generated prose to reviewable evidence

The engineering problem was to make generated employee information maintainable: sources change, amounts become stale, translations drift, and successful model output can still be wrong.

The reusable solution combines versioned source inputs, centralized figures, structured claim evidence, independent source and bilingual review, and a strict publication gate. Reader prose stays separate from reviewer assignments and operational logs.

## Engineering decisions

- Keep generation separate from acceptance. Completion, mechanical validation, independent review and human attestation answer different questions.
- Hash reader inputs rather than workflow bookkeeping. A reviewer-note change should not force another translation; a changed entitlement should.
- Bound calls and record attempts before execution. Failures and interrupted runs remain inspectable instead of disappearing into automatic retries.
- Recover complete saved responses without paying for another generation. Reject partial output before replacing existing files.
- Use a static bilingual site. Search and navigation need no runtime service or inference credentials.

## Demonstrated contribution

This repository presents the pipeline implementation and its quality-control design as portfolio work. The precise division of contributions in the original project is not documented here; no sole-authorship claim is made.

## Evidence and limitations

The two fictional procedures exercise calculation placeholders, open questions, source panels and translation freshness. Automated tests exercise rejection and recovery paths in isolated directories. Reviewer records are fixtures, not real approvals. Model hallucination, source correctness and judgment still require competent review. The demo makes no empirical quality or cost claims.
