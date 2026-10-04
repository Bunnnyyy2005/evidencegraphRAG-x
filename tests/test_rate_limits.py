"""Quota failures must not cause a request for every remaining PDF chunk."""
from types import SimpleNamespace
import httpx
import pytest
from app.config import Settings, settings
from app.utils import Store, LLM, RateLimitError, rate_limit_delay
from app.graph import Graph, Extraction
from app.verification import Answer, verify

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('GRAPH_REQUEST_INTERVAL', '0')
    monkeypatch.setenv('GROQ_API_KEY', 'offline-test-key')
    monkeypatch.setenv('NEO4J_URI', '')
    settings.cache_clear()
    yield Store()
    settings.cache_clear()


def test_quota_blocks_repeat_requests_but_not_other_model(store):
    calls=[]
    def send(request):
        calls.append(request)
        return httpx.Response(429,headers={'retry-after':'185'},json={'error':{'message':'quota'}},request=request)
    llm=LLM(store);llm.client.close();llm.client=httpx.Client(transport=httpx.MockTransport(send))
    try:
        for _ in range(3):
            with pytest.raises(RateLimitError) as exc:
                llm.json('Extract', {'text':'A works at B'}, Extraction)
            assert exc.value.retry_after > 0
        assert len(calls)==1
        with pytest.raises(RateLimitError):
            llm.json('Extract', {'text':'A works at B'}, Extraction, large=True)
        assert len(calls)==2
    finally:llm.client.close()


def test_provider_duration_fallback():
    response=httpx.Response(429,json={'error':{'message':'Please try again in 3m5.328s.'}})
    assert rate_limit_delay(response)==pytest.approx(185.328)


def test_graph_stops_on_quota_and_preserves_searchable_status(store):
    calls=[]
    def extract(*args,**kwargs):
        calls.append(1)
        if len(calls)==2:raise RateLimitError('offline-model',185)
        return Extraction(entities=[],relations=[])
    graph=Graph(store,SimpleNamespace(json=extract))
    graph.driver=SimpleNamespace(verify_connectivity=lambda:None)
    graph.run=lambda *args,**kwargs:[]
    chunks=[{'document_id':'doc','chunk_id':str(i),'text':'sample'} for i in range(5)]
    result=graph.enrich(chunks)
    assert len(calls)==2
    assert result['processed']==1 and result['deferred']==4
    assert result['status']=='Searchable — graph paused (LLM rate limit)'


def test_verifier_quota_does_not_accept_claim(store):
    def blocked(*args,**kwargs):raise RateLimitError('offline-model',185)
    answer=Answer(claims=[{'text':'A works at B','citations':['a']}])
    claims,audit=verify(answer,[{'chunk_id':'a','text':'A works at B'}],SimpleNamespace(store=store,json=blocked))
    assert claims==[]
    assert 'quota/rate limit' in audit[0]['reason']
