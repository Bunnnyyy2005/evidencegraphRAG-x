"""Small, paired, resumable architecture pilot. No API calls with --prepare."""
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

TYPES = ('single-hop', 'multi-hop', 'unanswerable')
VARIANTS = {
    'hybrid': dict(graph=False, reranker=False, cache=False),
    'reranked': dict(graph=False, reranker=True, cache=False),
    'graph': dict(graph=True, reranker=True, cache=False),
}



class EvaluationQuotaPause(BaseException):
    """Escape application fallback handlers without counting quota failures as answers."""


def quota_safe_llm(base, rate_limit_error):
    import threading
    import time

    class QuotaSafeLLM(base):
        def __init__(self, store, request_interval=0, rate_limit_retries=0, max_rate_wait=60):
            super().__init__(store)
            self.interval = max(0, request_interval)
            self.retries = max(0, rate_limit_retries)
            self.max_wait = max(0, max_rate_wait)
            self.next_request = 0
            self.request_lock = threading.Lock()

        def json(self, *args, **kwargs):
            # Serialize evaluation inference, including calls from retrieval worker threads.
            with self.request_lock:
                for attempt in range(self.retries + 1):
                    pause = self.next_request - time.monotonic()
                    if pause > 0:
                        time.sleep(pause)
                    self.next_request = time.monotonic() + self.interval
                    try:
                        return super().json(*args, **kwargs)
                    except rate_limit_error as exc:
                        if attempt == self.retries or exc.retry_after > self.max_wait:
                            raise EvaluationQuotaPause(
                                f'Groq quota: wait at least {exc.retry_after}s before resuming. '
                                'Current question was not saved; earlier completed questions are preserved.'
                            ) from exc
                        print(f'Groq quota: waiting {exc.retry_after}s (bounded retry)', flush=True)
                        time.sleep(exc.retry_after + 0.2)
    return QuotaSafeLLM


def select_records(records, per_type=2, seed=42):
    """Balance question types and spread each type across documents, deterministically."""
    rng = random.Random(seed)
    chosen = []
    for kind in TYPES:
        groups = {}
        for row in records:
            if row['type'] == kind:
                groups.setdefault(row['document'], []).append(row)
        names = sorted(groups)
        rng.shuffle(names)
        for rows in groups.values():
            rng.shuffle(rows)
        available = sum(map(len, groups.values()))
        if available < per_type:
            raise ValueError(f'Need {per_type} {kind} questions; found {available}')
        picked = 0
        while picked < per_type:
            for name in names:
                if groups[name] and picked < per_type:
                    chosen.append(groups[name].pop())
                    picked += 1
    rng.shuffle(chosen)
    return chosen


def has_progress(output):
    # Any legacy result must go through load_progress validation; never overwrite it.
    return any((output / name).exists() for name in
               ('checkpoint.json', 'per_question.jsonl', 'responses.jsonl'))


def resources(responses, events):
    import numpy as np
    usages = [r.get('usage', {}) for r in responses]
    times = [r['timings']['total'] for r in responses if r.get('timings', {}).get('total') is not None]
    complete_tokens = sum(u.get('tokens_available') is True for u in usages)
    complete_cost = sum(u.get('cost_available') is True and u.get('estimated_paid_usd') is not None for u in usages)
    failures = [e for e in events if e.get('category') == 'failure']
    return {
        'responses': len(responses), 'complete_token_records': complete_tokens,
        'observed_input_tokens': sum(u.get('prompt_tokens', 0) for u in usages),
        'observed_output_tokens': sum(u.get('completion_tokens', 0) for u in usages),
        'estimated_paid_usd': sum(u['estimated_paid_usd'] for u in usages) if usages and complete_cost == len(usages) else None,
        'latency_mean_seconds': float(np.mean(times)) if times else None,
        'latency_p50_seconds': float(np.percentile(times, 50)) if times else None,
        'latency_p95_seconds': float(np.percentile(times, 95)) if times else None,
        'failure_events': len(failures),
        'rate_limit_events': sum(e.get('error_type') == 'RateLimitError' for e in failures),
        'graph_retrieval_responses': sum('graph_retrieval' in r.get('timings', {}) for r in responses),
        'interpretation': 'Service failures present; do not claim a clean architecture comparison' if failures else 'Pilot only; human answer review required',
    }


def main():
    from . import evaluate
    from .evaluate import dataset, run
    from app.config import settings
    from app.utils import Store, LLM, RateLimitError
    from app.workflow import Options
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare', action='store_true')
    p.add_argument('--per-type', type=int, default=2)
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--dataset', type=Path)
    p.add_argument('--output', type=Path, default=Path('eval/results/controlled_pilot'))
    p.add_argument('--variants', nargs='+', choices=list(VARIANTS), default=['hybrid', 'reranked'])
    p.add_argument('--allow-unreviewed', action='store_true')
    p.add_argument('--request-interval', type=float, default=15)
    args = p.parse_args()
    if args.per_type < 1 or args.request_interval < 0:
        p.error('per-type must be positive and request-interval nonnegative')
    cfg = settings()
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    selected_path = root / 'selected.jsonl'
    if args.prepare:
        records = select_records(dataset(args.dataset) if args.dataset else dataset(), args.per_type, args.seed)
        if selected_path.exists():
            raise ValueError('Selection already exists. Keep it for paired runs, or choose a new --output.')
        selected_path.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        print(f'Prepared {len(records)} questions; no API calls. Review: {selected_path}')
        print('Documents: ' + ', '.join(sorted({r['document'] for r in records})))
        print('Review question, gold_answer and PDF pages; only then set requires_manual_validation=false.')
        return
    if not selected_path.exists():
        raise ValueError('Run with --prepare first.')
    records = dataset(selected_path)
    docs = {d['name']: d for d in Store().documents()}
    for r in records:
        d = docs.get(r['document'], {})
        if not d.get('searchable') or d.get('id') != r['source_sha256']:
            raise ValueError('Missing searchable annotated PDF edition: ' + r['document'])
        if 'graph' in args.variants and (not cfg.graph_enabled or d.get('stage') != 'Graph ready'):
            raise ValueError('Graph comparison requires Graph ready for every selected document: ' + r['document'])
    # Explicit list prices, NOT a bill. Unknown models retain configured prices or remain unmeasured.
    price_table = {'openai/gpt-oss-20b': (0.075, 0.30), 'openai/gpt-oss-120b': (0.15, 0.60)}
    for prefix, model in [('small', cfg.small_model), ('large', cfg.llm_model)]:
        if model in price_table and cfg.llm_base_url.rstrip('/') == 'https://api.groq.com/openai/v1':
            for direction, price in zip(('input', 'output'), price_table[model]):
                key = f'{prefix}_{direction}_usd_million'
                if getattr(cfg, key) is None:
                    setattr(cfg, key, price)
    # Lock all non-secret configuration, corpus revision and selection for safe reuse.
    config = cfg.model_dump(mode='json')
    config = {k: v for k, v in config.items() if k not in {'groq_api_key','qdrant_api_key','judge_api_key','api_token','neo4j_password','redis_url','neo4j_uri'}}
    fingerprint = hashlib.sha256(json.dumps([config, records, Store().version(), args.request_interval], sort_keys=True).encode()).hexdigest()
    manifest = root / 'manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())['fingerprint'] != fingerprint:
        raise ValueError('Configuration, labels or corpus changed. Use a new output folder and prepare again.')
    manifest.write_text(json.dumps({'fingerprint': fingerprint, 'config': config,
        'request_interval': args.request_interval, 'pricing_source': 'https://console.groq.com/docs/models',
        'pricing_checked': '2026-10-04', 'cost_scope': 'Estimated inference list price, excludes hosting, ingestion and judge; not actual free-tier charges'}, indent=2), encoding='utf-8')
    comparison = {}
    for name in args.variants:
        target = root / name
        original_llm = evaluate.EvaluationLLM
        evaluate.EvaluationLLM = quota_safe_llm(LLM, RateLimitError)
        try:
            summary = run(records, Options(**VARIANTS[name]), target,
                allow_unreviewed=args.allow_unreviewed, resume=has_progress(target),
                request_interval=args.request_interval, rate_limit_retries=2, max_rate_wait=60)
        except EvaluationQuotaPause as exc:
            print(str(exc), flush=True)
            print('Evaluation paused. Repeat the exact command after cooldown; no account rotation required.', flush=True)
            return
        finally:
            evaluate.EvaluationLLM = original_llm
        state = json.loads((target / 'checkpoint.json').read_text(encoding='utf-8'))
        response_rows = state['responses']
        comparison[name] = {'metrics': summary, 'resources': resources(response_rows, state.get('events', []))}
        with (target / 'answer_review.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['id','question','reference','answer','correct_0_or_1','citation_supported_0_or_1','notes'])
            writer.writeheader()
            for q, a in zip(records, response_rows):
                writer.writerow({'id': q['id'], 'question': q['question'], 'reference': q['gold_answer'], 'answer': a.get('answer', '')})
        (root / 'comparison.json').write_text(json.dumps(comparison, indent=2), encoding='utf-8')
        if comparison[name]['resources']['failure_events'] or summary['runtime_errors']:
            print(f'Stopped after {name}: failures recorded. Inspect checkpoint.json; fix before starting further variants.')
            break
    print('Results:', root / 'comparison.json')
    print('Latency includes deliberate quota pacing. Do not compare directly with dashboard latency.')
    print('Complete answer_review.csv against PDFs before claiming answer accuracy. Keep pilot separate from final held-out tests.')


if __name__ == '__main__':
    main()
