"""Offline contract tests with deterministic doubles only at service/model boundaries."""
import json
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.config import Settings, settings
from app.utils import Store
from app.ingest import make_chunks, parse_pdf
from app.retrieval import rrf, Retrieval
from app.graph import traversal_query
from app.cache import Cache, cosine
from app.verification import Claim, Answer, Verdict, valid_citations, verify
from app.workflow import Workflow, Options, Grade, Route, Transform
from eval.evaluate import retrieval_metrics, dataset

@pytest.fixture
def store(tmp_path,monkeypatch):
    # Never load live cloud credentials from the project's .env in offline tests.
    monkeypatch.setitem(Settings.model_config, 'env_file', None)
    monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('QDRANT_URL','')
    monkeypatch.setenv('REDIS_URL','');monkeypatch.setenv('NEO4J_URI','')
    settings.cache_clear();s=Store();yield s;settings.cache_clear()

@pytest.fixture
def chunk():
    return {'chunk_id':'a'*64,'document_id':'d'*64,'document_name':'source.pdf','page_number':2,
            'section':'Results','section_id':'s','parent_id':'p','text':'Alpha reduces latency to 8 ms.',
            'parent_text':'Alpha reduces latency to 8 ms.','context':'Results: Alpha reduces latency to 8 ms.',
            'metadata':{'kind':'paragraph'},'bbox':None}

def test_config():
    assert Settings(_env_file=None).port==7860
    with pytest.raises(ValidationError):Settings(graph_hops=3,_env_file=None)

def test_hierarchy(store):
    b={'page_number':4,'section':'Results','text':'First sentence. Second sentence.',
       'metadata':{'kind':'paragraph'},'bbox':[0,0,10,10]}
    c=make_chunks([b],'a'*64,'paper.pdf')[0]
    assert c['parent_id'] and c['section_id'] and c['page_number']==4
    assert c['text']!=c['context'] and 'Results' in c['context']
    assert c['bbox']==b['bbox']

def test_table_atomic(store):
    b={'page_number':1,'section':'Table','text':'| x | y |\n'+'| 1 | 2 |\n'*200,'metadata':{'kind':'table'},'bbox':None}
    assert len(make_chunks([b],'a'*64,'t.pdf'))==1

def test_real_pdf_parser(store,tmp_path):
    import pymupdf
    d=pymupdf.open();p=d.new_page();p.insert_text((50,50),'1 Results\nThe measured latency is eight milliseconds.')
    path=tmp_path/'test.pdf';d.save(path);d.close()
    blocks,parser=parse_pdf(path)
    assert parser=='pymupdf' and all(b['page_number']==1 for b in blocks)
    assert any('eight' in b['text'] for b in blocks)

def test_rrf():
    result=rrf([{'chunk_id':'a'},{'chunk_id':'b'}],[{'chunk_id':'b'}])
    assert result[0]['chunk_id']=='b'
    assert rrf([{'chunk_id':'a'},{'chunk_id':'a'}])[0]['score']==1/61

def test_sparse_isolated_documents(store,chunk):
    other={**chunk,'chunk_id':'b'*64,'document_id':'e'*64,'text':'Beta supports 4 streams.'}
    store.save_chunks(chunk['document_id'],[chunk]);store.save_chunks(other['document_id'],[other])
    r=Retrieval(store)
    assert r.sparse('latency',[chunk['document_id']])[0]['chunk_id']==chunk['chunk_id']
    assert r.sparse('latency',[other['document_id']])==[]

def test_qdrant_api_with_deterministic_vectors(store,chunk):
    r=Retrieval(store);r.embed=lambda texts:[[1.,0.,0.] for _ in texts]
    r.index([chunk]);hits=r.dense('alpha',[chunk['document_id']])
    assert hits[0]['chunk_id']==chunk['chunk_id']
    assert r.dense('alpha',['z'*64])==[]
    assert r.dense('alpha',[chunk['document_id']],metadata={'page_number':3})==[]
    r.close()

def test_graph_query_parameters():
    q=traversal_query(2)
    assert '$names' in q and '$documents' in q and '*1..2' in q
    with pytest.raises(ValueError):traversal_query(9)

def test_cloud_payload_indexes_repair_existing_collection(store,monkeypatch):
    monkeypatch.setenv('QDRANT_URL','https://example.invalid')
    settings.cache_clear()
    created=[]
    r=Retrieval(store)
    r.client=SimpleNamespace(
        collection_exists=lambda name:True,
        get_collection=lambda name:SimpleNamespace(payload_schema={'document_id':object()}),
        create_payload_index=lambda name,field,schema,**kwargs:created.append((field,schema,kwargs)))
    r.ensure_payload_indexes();r.ensure_payload_indexes()
    assert [field for field,_,_ in created]==['published','page_number','section','document_name']
    assert created[0][1].value=='bool'
    assert all(kwargs['wait'] for _,_,kwargs in created)

def test_citations(chunk):
    assert valid_citations(Claim(text='A claim',citations=[chunk['chunk_id']]),[chunk])
    assert not valid_citations(Claim(text='A claim',citations=['invented']),[chunk])

def test_verifier_removes_unsupported(store,chunk):
    llm=SimpleNamespace(store=store,json=lambda *a,**k:Verdict(label='PARTIAL_SUPPORT',reason='Number missing'))
    accepted,audit=verify(Answer(claims=[Claim(text='Latency is 1 ms.',citations=[chunk['chunk_id']])]),[chunk],llm)
    assert not accepted and audit[0]['status']=='PARTIAL_SUPPORT'

def test_verifier_outage_fails_closed(store,chunk):
    def fail(*args,**kwargs):raise RuntimeError('Unavailable')
    accepted,audit=verify(Answer(claims=[Claim(text='A',citations=[chunk['chunk_id']])]),[chunk],SimpleNamespace(store=store,json=fail))
    assert not accepted and audit[0]['status']=='INSUFFICIENT_EVIDENCE'

def test_cache_invalidation(store):
    cache=Cache(store)
    assert cache.scope('v1',['a'],{})!=cache.scope('v2',['a'],{})
    assert cache.scope('v1',['a'],{})!=cache.scope('v1',['b'],{})
    assert cache.get('a','b',[]) is None
    assert cosine([1,0],[1,0])==1

def test_workflow_retry_and_abstention(store,chunk):
    store.save_doc({'id':chunk['document_id'],'name':'source.pdf','searchable':True,'stage':'Graph ready'})
    class FakeLLM:
        def json(self,instruction,payload,schema,**kwargs):
            if schema is Route:return Route(category='factoid',reason='Test route')
            if schema is Transform:return Transform(queries=['rewritten query'])
            if schema is Grade:return Grade(sufficient=False,score=.1,reason='Insufficient')
            raise AssertionError('Generation must not run on insufficient evidence')
    class FakeRetrieval:
        count=0
        def hybrid(self,*args,**kwargs):self.count+=1;return [chunk]
    r=FakeRetrieval();w=Workflow(store,r,SimpleNamespace(),FakeLLM(),Cache(store))
    result=w.query('A question?',[],Options(graph=False,reranker=False,cache=False))
    assert result['abstained'] and result['retry']==1 and r.count==2
    assert result['category']=='factoid'

def test_workflow_success(store,chunk):
    store.save_doc({'id':chunk['document_id'],'name':'source.pdf','searchable':True})
    class FakeLLM:
        def json(self,instruction,payload,schema,**kwargs):
            if schema is Route:return Route(category='factoid',reason='Test')
            if schema is Grade:return Grade(sufficient=True,score=.9,reason='Supported')
            if schema is Answer:return Answer(claims=[Claim(text='Alpha reduces latency to 8 ms.',citations=[chunk['chunk_id']])])
            if schema is Verdict:return Verdict(label='ENTAILMENT',reason='Exact evidence')
            raise AssertionError(schema)
    r=SimpleNamespace(hybrid=lambda *a,**k:[chunk])
    result=Workflow(store,r,SimpleNamespace(),FakeLLM(),Cache(store)).query('What is latency?',[],Options(graph=False,reranker=False,cache=False))
    assert not result['abstained'] and '[source.pdf, p.2]' in result['answer']

def test_metrics_duplicate_page_not_double_counted(chunk):
    r=retrieval_metrics([chunk,chunk],{'document':'source.pdf','pages':[2,3]})
    assert r['recall@5']==.5 and r['mrr']==1

def test_gold_distribution():
    rows=dataset()
    assert len(rows)==120
    assert [sum(r['type']==t for r in rows) for t in ('single-hop','multi-hop','unanswerable')]==[48,48,24]
    assert all(r['pages'] or r['type']=='unanswerable' for r in rows)
    assert all(r['requires_manual_validation'] for r in rows)

def test_api_validation(store,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app,services
    services.cache_clear()
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
        assert client.post('/upload',files={'file':('x.pdf',b'not a PDF','application/pdf')}).status_code==400
        assert client.post('/query',json={'question':'x'}).status_code==422
        assert client.get('/document/not-a-hash').status_code==404
        assert client.post('/query',json={'question':'No documents yet?'}).json()['abstained']
    services.cache_clear()

def test_no_secrets_config_example(store,tmp_path):
    from pathlib import Path
    cfg=Settings(_env_file=Path(__file__).resolve().parents[1]/'.env.example')
    assert not cfg.groq_api_key and cfg.small_input_usd_million is None

def test_reranker_failure_preserves_ranking(store,chunk,monkeypatch):
    def fail(*args,**kwargs):raise RuntimeError('Unavailable')
    import flashrank
    monkeypatch.setattr(flashrank,'Ranker',fail)
    r=Retrieval(store);hits,ran=r.rerank('latency',[chunk])
    assert not ran and hits==[chunk]
    assert any(e.get('stage')=='reranking' for e in store.events())

def test_unknown_citation_is_removed_and_logged(store,chunk):
    llm=SimpleNamespace(store=store)
    accepted,audit=verify(Answer(claims=[Claim(text='Unsupported',citations=['unknown'])]),[chunk],llm)
    assert not accepted and audit[0]['status']=='INSUFFICIENT_EVIDENCE'
    assert any(e.get('stage')=='citation' for e in store.events())

def test_off_scope_never_retrieves(store,chunk):
    store.save_doc({'id':chunk['document_id'],'name':'source.pdf','searchable':True})
    llm=SimpleNamespace(json=lambda *args,**kwargs:Route(category='off-scope',reason='Unrelated'))
    result=Workflow(store,SimpleNamespace(),SimpleNamespace(),llm,Cache(store)).query('Write a song?',[],Options(cache=False))
    assert result['abstained'] and result['category']=='off-scope'

def test_regression_gate_refuses_unmeasured(tmp_path):
    from eval.evaluate import compare_baseline
    path=tmp_path/'baseline.json';path.write_text(json.dumps({'status':'EXPLORATORY — HUMAN LABEL AUDIT PENDING'}))
    with pytest.raises(ValueError,match='audited'):compare_baseline({'status':'EXPLORATORY'},str(path),.02)

def test_api_token_protects_documents(store,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app,services
    monkeypatch.setenv('API_TOKEN','test-only-secret');settings.cache_clear();services.cache_clear()
    with TestClient(app) as client:
        assert client.get('/documents').status_code==401
        assert client.get('/documents',headers={'Authorization':'Bearer test-only-secret'}).status_code==200
        assert client.get('/health').status_code==200
    services.cache_clear()

def test_stage1_publishes_before_graph_work(store,chunk,monkeypatch):
    import app.ingest as module
    doc_id=chunk['document_id']
    store.save_doc({'id':doc_id,'name':'source.pdf','stage':'Queued','searchable':False})
    block={'page_number':1,'section':'Results','text':'Original evidence text.',
           'metadata':{'kind':'paragraph'},'bbox':None}
    monkeypatch.setattr(module,'parse_pdf',lambda path:([block],'test-parser'))
    queued=[]
    index=SimpleNamespace(index=lambda chunks,progress:progress())
    module.ingest(doc_id,store,index,SimpleNamespace(),graph_submit=lambda doc,chunks:queued.append((doc,chunks)))
    assert store.document(doc_id)['searchable']
    assert store.document(doc_id)['stage']=='Searchable — graph queued'
    assert queued and store.chunks([doc_id])
