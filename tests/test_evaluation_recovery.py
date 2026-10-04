"""Offline regressions for event collisions, quota waits, and saved partial results."""
import json
from types import SimpleNamespace
import pytest
from app.config import Settings, settings
from app.utils import Store, LLM, RateLimitError
from eval import evaluate

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    settings.cache_clear()
    yield Store()
    settings.cache_clear()

def test_event_metadata_collision_preserves_database_category(store):
    store.event('failure', {'category': 'provider', 'ts': -1, 'error_type': 'RateLimitError'})
    event = store.events()[0]
    assert event['category'] == 'failure'
    assert event['ts'] > 0
    assert event['error_type'] == 'RateLimitError'

def test_evaluation_retries_short_quota_wait(store, monkeypatch):
    waits, calls = [], []
    monkeypatch.setattr(evaluate, 'time', SimpleNamespace(
        monotonic=lambda: 100, sleep=waits.append))
    def request(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RateLimitError('test-model', 2)
        return 'result'
    monkeypatch.setattr(LLM, 'json', request)
    llm = evaluate.EvaluationLLM(store, rate_limit_retries=2)
    try:
        assert llm.json('instruction', {}, str) == 'result'
        assert len(calls) == 2
        assert waits == [2.2]
    finally:
        llm.client.close()

def test_evaluation_never_waits_through_long_quota(store, monkeypatch):
    waits = []
    monkeypatch.setattr(evaluate, 'time', SimpleNamespace(monotonic=lambda: 100, sleep=waits.append))
    def request(*args, **kwargs):
        raise RateLimitError('test-model', 3600)
    monkeypatch.setattr(LLM, 'json', request)
    llm = evaluate.EvaluationLLM(store, rate_limit_retries=2, max_rate_wait=60)
    try:
        with pytest.raises(RateLimitError):
            llm.json('instruction', {}, str)
        assert waits == []
    finally:
        llm.client.close()

def test_evaluation_quota_retry_bound(store, monkeypatch):
    calls = []
    monkeypatch.setattr(evaluate, 'time', SimpleNamespace(monotonic=lambda: 100, sleep=lambda _: None))
    def request(*args, **kwargs):
        calls.append(1)
        raise RateLimitError('test-model', 2)
    monkeypatch.setattr(LLM, 'json', request)
    llm = evaluate.EvaluationLLM(store, rate_limit_retries=2)
    try:
        with pytest.raises(RateLimitError):
            llm.json('instruction', {}, str)
        assert len(calls) == 3
    finally:
        llm.client.close()

def test_partial_question_results_are_saved(tmp_path):
    evaluate.checkpoint(tmp_path, [{'id': 'q1'}, {'id': 'q2'}],
                        [{'id': 'q1', 'failure': ''}], [{'answer': 'saved'}])
    assert json.loads((tmp_path/'responses.jsonl').read_text()) == {'id': 'q1', 'answer': 'saved'}
    assert json.loads((tmp_path/'per_question.jsonl').read_text())['id'] == 'q1'
