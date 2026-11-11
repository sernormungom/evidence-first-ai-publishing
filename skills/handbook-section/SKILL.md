---
name: handbook-section
description: Write or resume a schema.yaml handbook section with bounded generation, compact independent reviews, deterministic repairs and durable recovery. Draft authoring only; no publication or company decisions.
---

# Handbook section

The invoking session coordinates from the repository root. Read `AGENTS.md`,
`AUTHORING_GUIDE.md`, the requested schema folder and its existing plan/evidence.
Inspect Git changes; preserve unrelated work and completed reviews. Use the user's
provider preference (currently Claude) and existing authorized backend/model.
Invoking this skill does not authorize a new destination or spending route.

## Choose scope and bounds

For new synthetic sections, default to **agile drafts**: fewer
reviews and lower editorial polish. Research the complete section, consolidate
legacy topics around employee questions, then prepare specs, sources and figures.
The coordinator plans directly; no planner model call when local research suffices.
Read complete applicable provisions/exceptions. Company wording establishes company
arrangements, not legal rules; do not copy licensed legacy explanations.

Use one independent source batch before Swedish and one independent bilingual
batch after complete pairs exist. Both include reader usability and positive
claim evidence. Minor style defects do not trigger corrections. Fix material
errors in pay, eligibility, calculations, mandatory timing, safety, modality or
company promises. Allow at most one correction review per gate, covering changed
source claims or the complete regenerated Swedish file. Deliver unresolved
articles as unaccepted drafts; never interpret missing verdicts as acceptance.

Group genuine company decisions and missing inputs in `reviews/questions.yaml`;
reuse existing IDs/resolutions. Continue work that does not depend on them. The
user's tolerance of draft imperfections is not permission to choose company policy
or attest legal correctness. Retain `draft` and `reviewed_by: null`.

Existing section plans, approvals, provider restrictions and tighter counters take
precedence when resuming. Do not reset review passes or repeat accepted articles.

## Prepare and generate

Use the current accepted section example and shared guide, without extra writer,
readability or final-auditor sessions. Read [role briefs](references/roles.md) only
for the role being launched. Fresh independent reviewers receive complete articles,
relevant actual evidence and prior findings; no session transcripts or run histories.

1. Register question/figure references, then run `make draft ARTICLE=... PYTHON=python3`.
   English defaults to medium effort (`HANDBOOK_DRAFT_EFFORT`); escalate only for a
   concrete source ambiguity, recording the passage and evidence first.
   Code constructs canonical metadata from the spec. The coordinator makes ordinary
   English corrections and rechecks evidence; avoid another full drafting call.
   Reuse a completed rejected response with `make recover-draft ARTICLE=...
   RESPONSE=...`; preserve the original and record the local repair.
2. Build source input with `scripts/review_bundle.py --kind source --output
   .section-runs/SECTION/source.prompt.md ARTICLE...`; inspect completeness and size.
   Run a fresh read-only review. Batch corrections; finish English before translation.
3. Generate Swedish through `make translate`, never by editing employee Swedish.
   The translator returns title/questions/body/notes; code copies metadata and stamps
   the reader hash. Replay complete output with `make recover-translation` when
   only known formatting failed; never edit Swedish wording in a recovery copy. Default `HANDBOOK_TRANSLATION_EFFORT=medium`; do not raise effort
   without a concrete ambiguity and its affected passage/evidence.
4. Build a bilingual bundle with `--kind bilingual`, attaching prior findings with
   `--prior FILE`. Review every full pair using accepted English evidence. Correct
   English-origin ambiguity in English; regenerate only affected Swedish and review
   the whole regenerated file. Source semantic edits require relevant source review.

Bundle preparation never silently truncates sources. Use complete provision
selections with parent/date/hash/range provenance when full documents are excessive.
Review outputs must cover every requested article with concise evidence and findings.
Coordinator judgment remains necessary; schema validity is not semantic acceptance.

## Account, recover and measure

Initialize once (default ceiling `2 × articles + 5` calls), then resume status:

```bash
python3 skills/handbook-section/scripts/section_run.py init SECTION
python3 skills/handbook-section/scripts/section_run.py status SECTION
```

Empty folders begin with planning; scaffold articles and `enroll SECTION --article
FILENAME` without resetting counters. Budgets are ceilings, not spending targets.
Keep prompts, raw responses and usage in ignored `.section-runs/SECTION/`.

Use `scripts/section_call.py SECTION --kind KIND --input PROMPT --approval
'AUTHORIZATION REFERENCE' ARTICLE...` with the authorized `HANDBOOK_BACKEND` and
`HANDBOOK_MODEL`. It records start/finish, captures provider artifacts and separates
provider completion, pipeline acceptance and independent verdicts. Generation
inputs should be audited `--dry-run` exports; reviews use complete bundles.
For a manually captured call, use ledger `start`/`finish` explicitly; never count
both wrapper and nested invocation as separate provider calls.

The pipeline performs zero automatic retries or continuations; CLI text generation
is capped at one turn. Known enclosing fences and copied metadata are mechanical
repairs; literal JSON string whitespace is decoded verbatim and `fix` may alias
`suggested_fix` without changing reviewer findings. A reported canonical path plus
the literal ` + .sv.md` pair suffix can map to that requested path; preserve its
original label and verdict. Use `section_call.py SECTION
--recover-review ID` to reparse a finished review with unchanged inputs. Never automatically alter meaning, figures, claims, evidence or summary
length. Capture rejected responses before deciding whether another call is needed.
For a complete translation missing only `notes`, code may add an explicit omission
notice; infer no ambiguity assessment and preserve all reader fields verbatim.
Stop on quota/unknown failures; inspect pending process/output/Git changes before
retrying. Never silently switch providers, reset a counter or duplicate a call.

Use `scripts/section_metrics.py SECTION` for attempts, reported tokens/equivalent
API cost and cost per currently accepted pair. Include all failures in cost; unknown
cost stays unknown, and subscription billing is not equivalent API cost. Record
human interruptions with ledger `event --kind human_interruption --note TEXT
--artifact FILE` and in section evidence; do not infer zero. Provider
completion and a green build never establish independent acceptance or HR attestation.

## Deliver

Run `make validate preview site PYTHON=python3`, article review sheets and
`git diff --check`. Run pipeline tests when
code changed. Broaden checks for failures/changed behavior, not by default. Inspect
rendered English/Swedish, links, source disclosure and absence of reviewer material.
Report unavailable browser/mobile checks honestly. Keep reviewer work outside prose.

Handoff: article outcomes, material unresolved issues/company questions, checks,
attempts/usage/cost, evidence links and exact next step. Do not commit, publish,
deploy, resolve company decisions or claim attestation without authorization.
