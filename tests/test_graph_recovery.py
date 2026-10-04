from types import SimpleNamespace
import pytest
from app.config import Settings, settings
from app.graph import Graph, Extraction
from app.utils import Store, RateLimitError

@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    monkeypatch.setenv('NEO4J_URI', '')
    monkeypatch.setenv('GRAPH_REQUEST_INTERVAL', '0')
    monkeypatch.setenv('GRAPH_RATE_LIMIT_RETRIES', '2')
    settings.cache_clear()
    yield Store()
    settings.cache_clear()

def test_resume_skips_committed_chunks_across_graph_instances(store):
    completed=set(); calls=[]
    def run(query, **kw):
        if 'RETURN c.id AS id' in query:
            return [{'id': cid} for cid in completed]
        if 'SET c.graph_checkpoint' in query:
            completed.add(kw['chunk'])
        return []
    def first(*args):
        calls.append(args[1]['text'])
        if len(calls)==2:
            raise RateLimitError('test', 3600)
        return Extraction(entities=[], relations=[])
    chunks=[{'document_id':'d','chunk_id':str(i),'text':f'text {i}'} for i in range(3)]
    g=Graph(store,SimpleNamespace(json=first));g.run=run
    g.driver=SimpleNamespace(verify_connectivity=lambda:None)
    assert g.enrich(chunks)['processed']==1
    assert completed=={'0'}
    resumed=[]
    def second(*args):
        resumed.append(args[1]['text'])
        return Extraction(entities=[],relations=[])
    g=Graph(store,SimpleNamespace(json=second));g.run=run
    g.driver=SimpleNamespace(verify_connectivity=lambda:None)
    result=g.enrich(chunks)
    assert resumed==['text 1','text 2']
    assert result['status']=='Graph ready' and result['processed']==3

def test_short_quota_retry_is_bounded_and_respects_delay(store, monkeypatch):
    waits=[];calls=[]
    monkeypatch.setattr('app.graph.time.sleep', waits.append)
    def blocked(*args):
        calls.append(1)
        raise RateLimitError('test',2)
    g=Graph(store,SimpleNamespace(json=blocked))
    with pytest.raises(RateLimitError):g._extract_json('prompt',{},Extraction)
    assert len(calls)==3 and waits==[2,2]

def test_graph_resume_endpoint_uses_saved_chunks_without_ingesting(store, monkeypatch):
    import app.main as main
    from fastapi.testclient import TestClient
    doc_id='a'*64
    store.save_doc({'id':doc_id,'name':'test.pdf','searchable':True,'stage':'Searchable — graph paused (LLM rate limit)'})
    chunk={'chunk_id':'b'*64,'document_id':doc_id,'text':'saved'}
    store.save_chunks(doc_id,[chunk])
    queued=[]
    svc=SimpleNamespace(store=store,graph=SimpleNamespace(driver=object()),
                        submit_graph=lambda doc, chunks:queued.append((doc,chunks)) or True)
    monkeypatch.setattr(main,'services',lambda:svc)
    monkeypatch.setenv('API_TOKEN','test-secret');settings.cache_clear()
    client=TestClient(main.app)
    path=f'/document/{doc_id}/resume-graph'
    assert client.post(path).status_code==401
    response=client.post(path,headers={'Authorization':'Bearer test-secret'})
    assert response.status_code==202
    assert queued==[(doc_id,[chunk])]
    assert store.document(doc_id)['searchable'] is True
