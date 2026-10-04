"""Resume retains finished questions and never queries them again."""
import json
from types import SimpleNamespace
import pytest
from app.config import Settings, settings
from app.utils import Store
from app.workflow import Options
from eval import evaluate

def test_resume_runs_only_remaining_question(tmp_path, monkeypatch):
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('DATA_DIR', str(tmp_path/'data'))
    monkeypatch.setenv('GROQ_API_KEY', 'offline')
    settings.cache_clear()
    output=tmp_path/'results'; output.mkdir()
    records=[{'id':f'q{i}', 'question':f'question{i}', 'document':'source.pdf',
              'source_sha256':'doc', 'type':'single-hop', 'requires_manual_validation':True}
             for i in range(3)]
    old_rows=[{'id':r['id'], 'type':'single-hop', 'failure':'', 'hit@10':1,
               'latency_seconds':2} for r in records[:2]]
    old_responses=[{'id':r['id'], 'answer':'saved', 'abstained':False,
                   'timings':{'total':2}, 'claims':[], 'audit':[], 'evidence':[]}
                  for r in records[:2]]
    evaluate.checkpoint(output, records, old_rows, old_responses)
    store=Store(); store.save_doc({'id':'doc', 'name':'source.pdf', 'searchable':True})
    calls=[]
    def query(question, *args, **kwargs):
        calls.append(question)
        return {'answer':'new', 'abstained':False, 'timings':{'total':1},
                'claims':[], 'audit':[], 'evidence':[], 'hits':[], 'cache_hit':False}
    monkeypatch.setattr(evaluate, 'Retrieval', lambda s: SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(evaluate, 'Graph', lambda *a: SimpleNamespace(close=lambda:None))
    monkeypatch.setattr(evaluate, 'Cache', lambda *a: None)
    monkeypatch.setattr(evaluate, 'Workflow', lambda *a: SimpleNamespace(query=query))
    monkeypatch.setattr(evaluate, 'retrieval_metrics', lambda *a:{'hit@10':1})
    monkeypatch.setattr(evaluate, 'path_validity', lambda *a:None)
    try:
        result=evaluate.run(records, Options(cache=False), output,
                            allow_unreviewed=True, resume=True)
        assert calls == ['question2']
        assert result['questions']==3 and result['resumed_questions']==2
        assert result['telemetry_missing_questions']==2
        saved=[json.loads(x) for x in (output/'responses.jsonl').read_text().splitlines()]
        assert [x['answer'] for x in saved] == ['saved','saved','new']
        assert (output/'responses.jsonl.before-resume').exists()
        # Resume a fully completed checkpoint: no inference is repeated.
        evaluate.run(records, Options(cache=False), output, allow_unreviewed=True, resume=True)
        assert calls == ['question2']
        state=json.loads((output/'checkpoint.json').read_text())
        state['rows'][1]={'id':'q1','type':'single-hop','failure':'runtime_error','error_type':'TypeError'}
        state['responses'][1]={'id':'q1','answer':'','abstained':True,'error_type':'TypeError'}
        evaluate.save_progress(output,state)
        result=evaluate.run(records,Options(cache=False),output,allow_unreviewed=True,
                            resume=True,retry_runtime_errors=True)
        assert calls == ['question2','question1']
        assert result['runtime_errors']==0
        saved=[json.loads(x) for x in (output/'responses.jsonl').read_text().splitlines()]
        assert [x['id'] for x in saved]==['q0','q1','q2']
        assert [x['answer'] for x in saved]==['saved','new','new']
    finally:
        settings.cache_clear()

def test_resume_rejects_wrong_order_without_overwriting(tmp_path):
    records=[{'id':'expected'}]
    evaluate.checkpoint(tmp_path, [{'id':'wrong'}], [{'id':'wrong'}], [{'answer':'saved'}])
    original=(tmp_path/'responses.jsonl').read_bytes()
    with pytest.raises(ValueError, match='IDs/order'):
        evaluate.load_progress(tmp_path, records, 'signature')
    assert (tmp_path/'responses.jsonl').read_bytes()==original

def test_resume_rejects_changed_configuration(tmp_path):
    evaluate.save_progress(tmp_path, {'signature':'original','rows':[],'responses':[]})
    with pytest.raises(ValueError, match='configuration changed'):
        evaluate.load_progress(tmp_path, [], 'changed')

def test_early_abstention_has_no_graph_paths():
    assert evaluate.path_validity({'hits':None}, {}) is None
    assert evaluate.path_validity({}, {}) is None
    assert evaluate.path_validity({'hits':[{'graph_path':None}]}, {}) is None

def test_legacy_checkpoint_between_two_file_writes_keeps_common_prefix(tmp_path):
    (tmp_path/'per_question.jsonl').write_text('{"id":"q1"}\n')
    (tmp_path/'responses.jsonl').write_text('{"id":"q1"}\n{"id":"q2"}\n')
    state=evaluate.load_progress(tmp_path, [{'id':'q1'}, {'id':'q2'}], 'same')
    assert len(state['rows'])==len(state['responses'])==1
    assert 'q2' in (tmp_path/'responses.jsonl.before-resume').read_text()
