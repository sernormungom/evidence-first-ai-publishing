# Evidence-first AI publishing

A source-grounded AI publishing pipeline with independent review gates, bilingual freshness checks, bounded provider calls and recoverable execution.

This portfolio is an anonymized adaptation of an employee-information publishing project. All examples, sources, questions and reviewer evidence here are synthetic. No original articles, company records or inference transcripts are included.

## Try it

Requires Python 3.14 and Make:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
make demo
python3 -m http.server 8000 --directory dist/portfolio
```

Open http://localhost:8000. Demo builds use saved synthetic fixtures, make no inference calls and need no credentials. The Swedish fixtures were assembled through the translation output pipeline; they are not attested translations.

[Case study](docs/case-study.md) · [Architecture](docs/architecture.md) · [Information policy](docs/information-policy.md)

## What to inspect

- Source loader: maintained sources, path boundaries and fingerprints.
- Draft and translation wrappers: incomplete-output rejection and saved-response recovery.
- Review bundles and section ledger: independent acceptance, input hashes and bounded attempts.
- Validator: unresolved decisions, unverified figures and missing attestation block publication.
- Static site: bilingual search, source panels and labeled language fallbacks.

```sh
make test
make demo-check
make validate
make disclosure-check
```

`make publish` deliberately rejects the default draft examples. Positive publication scenarios run in temporary test repositories. Fixture evidence is illustrative; matching hashes and model acceptance are not human approval.

## Optional live inference

The API and CLI backends remain available. Set HANDBOOK_MODEL to a provider-supported model and configure ANTHROPIC_API_KEY, or HANDBOOK_BACKEND=cli with a signed-in Claude CLI. Use DRY_RUN=1 first. Live calls may cost money and are never performed by the demo or CI. Captures remain ignored local files.

## Hosting and maintenance

The workflow checks pull requests and main, then deploys only `dist/portfolio` to GitHub Pages on main. Set Pages to GitHub Actions after creating the personal repository. Use short-lived branches; manually sanitize future code transfers instead of merging original history.

Source is published for inspection. No new open-source license is granted. Existing applicable notices must be preserved. No production adoption, savings or accuracy claims are made by the fixture demo.
