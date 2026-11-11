# Local authoring examples

These two bilingual examples are synthetic demonstrations, not Example Studio policy or
approved translations of handbook articles. They test a procedure and a calculation
through the real build/review pipeline without inference calls. The tests copy them
into a temporary repository. Human source review and HR approval are still required
for real articles; these are format examples, not attested company guidance.

Run `python3 scripts/preview_authoring.py` (or `make authoring-preview`) to generate
`dist/authoring-example/site/` and reviewer reports locally. Open its `site/en/` or
`site/sv/` index. No maintained content, source or figure registry is changed.
The fixture question is intentionally open: the employee sees concise uncertainty;
the reviewer sees the full task. The unresolved question must still prevent `live`.
