import unittest
from eval.controlled import select_records, resources, has_progress


def test_balanced_reproducible_selection():
    rows = [dict(id=f'{t}-{d}-{i}', type=t, document=d)
            for t in ('single-hop', 'multi-hop', 'unanswerable')
            for d in ('a', 'b', 'c') for i in range(3)]
    selected = select_records(rows)
    assert selected == select_records(rows)
    assert len({r['id'] for r in selected}) == 6
    for t in ('single-hop', 'multi-hop', 'unanswerable'):
        assert len({r['document'] for r in selected if r['type'] == t}) == 2
    with unittest.TestCase().assertRaises(ValueError):
        select_records(rows, 10)


def test_incomplete_cost_not_reported_as_zero_and_failures_flagged():
    r = resources([{'usage': {'prompt_tokens': 8, 'completion_tokens': 2, 'tokens_available': False},
                    'timings': {'total': 2}}], [{'category': 'failure', 'error_type': 'RateLimitError'}])
    assert r['estimated_paid_usd'] is None
    assert r['complete_token_records'] == 0
    assert r['rate_limit_events'] == 1
    assert r['latency_p95_seconds'] == 2

if __name__ == "__main__":
    test_balanced_reproducible_selection()
    test_incomplete_cost_not_reported_as_zero_and_failures_flagged()
    print("2 controlled evaluation checks passed")


def test_first_run_and_resume_detection():
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as temp:
        p = Path(temp) / 'hybrid'
        assert not has_progress(p)
        p.mkdir()
        assert not has_progress(p)
        for name in ('checkpoint.json', 'per_question.jsonl', 'responses.jsonl'):
            f = p / name
            f.write_text('{}')
            assert has_progress(p)
            f.unlink()
        assert not has_progress(p)


def test_quota_pause_escapes_fallback_and_bounds_calls():
    from eval.controlled import quota_safe_llm, EvaluationQuotaPause
    class RateError(Exception):
        retry_after = 900
    class FakeLLM:
        calls = 0
        def __init__(self, store):
            pass
        def json(self):
            self.calls += 1
            raise RateError()
    client = quota_safe_llm(FakeLLM, RateError)(None, rate_limit_retries=2, max_rate_wait=60)
    try:
        try:
            client.json()
        except Exception:
            raise AssertionError('Application fallback must not swallow quota pause')
    except EvaluationQuotaPause:
        pass
    else:
        raise AssertionError('Expected quota pause')
    assert client.calls == 1
