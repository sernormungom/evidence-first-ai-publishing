#!/usr/bin/env python3
"""Summarize captured section usage; acceptance is read from hashed review evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def stage_usage(manifest):
    """Attribute retained provider artifacts to stages without counting recovery twice."""
    stages = {}
    for call in manifest['calls']:
        stage = stages.setdefault(call['kind'], dict(attempts=0, provider_completions=0,
            input_tokens=0, output_tokens=0, thinking_tokens=0,
            reported_partial_cost_usd=0, metered_results=0, efforts=set(), seen=set()))
        stage['attempts'] += 1
        for name, digest in call.get('artifacts', {}).items():
            path = ROOT / name
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                continue
            try:
                outcome = json.loads(path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(outcome, dict):
                continue
            for artifact in outcome.get('provider_artifacts', []):
                path = ROOT / artifact
                if not path.exists():
                    continue
                if artifact.endswith('.request.json'):
                    request = json.loads(path.read_text())
                    stage['efforts'].add(request.get('effort') or 'provider_default')
                if not artifact.endswith('.response.json') or artifact in stage['seen']:
                    continue
                stage['seen'].add(artifact)
                response = json.loads(path.read_text())
                if response.get('stop_reason') in ('end_turn', 'stop_sequence'):
                    stage['provider_completions'] += 1
                usage = response.get('usage') or {}
                stage['input_tokens'] += sum(usage.get(k, 0) for k in (
                    'input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
                stage['output_tokens'] += usage.get('output_tokens', 0)
                stage['thinking_tokens'] += (usage.get('output_tokens_details') or {}).get('thinking_tokens', 0)
                cost = (response.get('_cli') or {}).get('cost_usd')
                if cost is not None:
                    stage['metered_results'] += 1
                    stage['reported_partial_cost_usd'] += cost
    for stage in stages.values():
        stage.pop('seen')
        stage['efforts'] = sorted(stage['efforts'])
        stage['equivalent_api_cost_usd'] = (stage['reported_partial_cost_usd']
            if stage['metered_results'] == stage['attempts'] else None)
    return stages


def summarize(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    requests = list((directory / 'capture').glob('*.request.json'))
    responses = list((directory / 'capture').glob('*.response.json'))
    usage = Counter()
    costs = []
    thinking = 0
    for path in responses:
        record = json.loads(path.read_text())
        for key, value in (record.get('usage') or {}).items():
            if isinstance(value, (int, float)):
                usage[key] += value
        thinking += ((record.get('usage') or {}).get('output_tokens_details') or {}).get('thinking_tokens', 0)
        costs.append((record.get('_cli') or {}).get('cost_usd'))
    current = {'source': set(), 'bilingual': set()}
    for call in manifest['calls']:
        kind = call['kind']
        if kind not in current:
            continue
        # A later attempted review supersedes the prior verdict, including failures.
        current[kind].difference_update(call['articles'])
        artifacts = dict(call.get('artifacts', {}))
        for recovery in call.get('recoveries', []):
            artifacts.update(recovery['artifacts'])
        for artifact, digest in artifacts.items():
            path = ROOT / artifact
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                continue
            try:
                outcome = json.loads(path.read_text())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(outcome, dict):
                continue
            # Any changed English/SV input invalidates the reviewer acceptance.
            for article, verdict in (outcome.get('independent_acceptance') or {}).items():
                names = [article]
                if kind == 'bilingual':
                    names.append(article.removesuffix('.md') + '.sv.md')
                if verdict == 'accept' and all(
                    name in call['inputs'] and (ROOT / name).exists() and
                    hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == call['inputs'][name]
                    for name in names):
                    current[kind].add(article)
    accepted = current['source'] & current['bilingual']
    stages = stage_usage(manifest)
    import source_loader
    accepted_english_words = sum(len(source_loader.body_of((ROOT / name).read_text()).split()) for name in current['source'])
    complete_cost = len(responses) == len(requests) == len(manifest['calls']) and all(c is not None for c in costs)
    total = sum(costs) if complete_cost else None
    repetitions = Counter((c['kind'], a) for c in manifest['calls'] for a in c['articles'])
    return dict(section=manifest['section'], attempts=len(manifest['calls']),
                provider_requests=len(requests), provider_responses=len(responses),
                stages=stages,
                source_accepted_english_words_approx=accepted_english_words,
                draft_output_tokens_per_source_accepted_word=(stages.get('draft', {}).get('output_tokens', 0) / accepted_english_words if accepted_english_words else None),
                usage=dict(usage),
                total_reported_input_tokens=sum(usage[k] for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens')),
                reported_thinking_output_tokens=thinking, equivalent_api_cost_usd=total,
                reported_partial_cost_usd=sum(c for c in costs if c is not None),
                reported_partial_cost_per_accepted_pair_usd=(sum(c for c in costs if c is not None) / len(accepted) if accepted else None),
                source_accepted_articles=sorted(current['source']),
                bilingual_accepted_articles=sorted(current['bilingual']),
                independently_accepted_pairs=sorted(accepted),
                cost_per_accepted_pair_usd=total / len(accepted) if total is not None and accepted else None,
                extra_article_stage_attempts=sum(max(0, n-1) for n in repetitions.values()),
                human_interruptions=(sum(e['kind'] == 'human_interruption' for e in manifest['events'])
                                     if 'events' in manifest else None),
                pending=[c['id'] for c in manifest['calls'] if c['outcome'] == 'pending'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('section')
    args = parser.parse_args()
    print(json.dumps(summarize(ROOT / '.section-runs' / args.section), indent=2))

if __name__ == '__main__':
    main()
