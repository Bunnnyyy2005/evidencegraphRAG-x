"""Single-worker FastAPI application. Run from the repository root."""
import asyncio
import hashlib
import hmac
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import settings
from .utils import Store, LLM
from .retrieval import Retrieval
from .graph import Graph
from .cache import Cache
from .workflow import Workflow, Options
from .ingest import ingest, enrich_document

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
# Avoid provider HTTP debug logging that may expose secret query parameters.
logging.getLogger('httpx').setLevel(logging.WARNING)

class Services:
    def __init__(self):
        self.store = Store()
        self.llm = LLM(self.store)
        self.retrieval = Retrieval(self.store)
        self.graph = Graph(self.store,self.llm)
        self.cache = Cache(self.store)
        self.workflow = Workflow(self.store,self.retrieval,self.graph,self.llm,self.cache)
        self.jobs = ThreadPoolExecutor(max_workers=1,thread_name_prefix='ingest')
        self.graph_jobs = ThreadPoolExecutor(max_workers=1,thread_name_prefix='graph')
        self.pending = set()

    def submit(self, doc_id: str):
        if doc_id not in self.pending:
            self.pending.add(doc_id)
            future = self.jobs.submit(ingest,doc_id,self.store,self.retrieval,self.graph,self.submit_graph)
            future.add_done_callback(lambda _:self.pending.discard(doc_id))

    def submit_graph(self, doc_id: str, chunks: list[dict]):
        self.graph_jobs.submit(enrich_document,doc_id,chunks,self.store,self.graph)

@lru_cache
def services():
    return Services()

@asynccontextmanager
async def lifespan(app):
    svc = services()
    try:
        await asyncio.to_thread(svc.retrieval.restore_catalog)
    except Exception as exc:
        svc.store.failure('retrieval', exc)
    # Persisted interrupted uploads are resumed, not left permanently "processing".
    for doc in svc.store.documents():
        if doc['stage'] in ('Queued','Parsing','Chunking','Embedding','Indexing','Searchable','Searchable — graph queued','Graph extraction'):
            if (svc.store.root/'uploads'/f'{doc["id"]}.pdf').exists():
                if doc.get('searchable'):
                    svc.submit_graph(doc['id'],svc.store.chunks([doc['id']]))
                else:
                    svc.submit(doc['id'])
    yield
    svc.jobs.shutdown(wait=True)
    svc.graph_jobs.shutdown(wait=True)
    svc.retrieval.close()
    svc.graph.close()
    svc.llm.client.close()

app = FastAPI(title='EvidenceGraph-X',lifespan=lifespan)
static = Path(__file__).resolve().parents[1]/'static'
app.mount('/static',StaticFiles(directory=static),name='static')

def auth(authorization: str = Header(default='')):
    token = settings().api_token
    if token and not hmac.compare_digest(authorization,f'Bearer {token}'):
        raise HTTPException(401,'A valid API token is required')

@app.get('/')
def home():
    return FileResponse(static/'index.html')

@app.get('/health')
def health():
    cfg = settings()
    return {'status':'ok','llm_configured':bool(cfg.groq_api_key),'qdrant':'cloud' if cfg.qdrant_url else 'local',
            'graph_configured':bool(cfg.neo4j_uri and cfg.graph_enabled),'cache_configured':bool(cfg.redis_url),
            'note':'Configuration summary only. Run python -m eval.evaluate --check-services for connectivity.'}

@app.post('/upload',dependencies=[Depends(auth)],status_code=202)
async def upload(file: UploadFile = File(...)):
    svc = services()
    if len(svc.pending)>=5:
        raise HTTPException(429,'Ingestion queue is full; retry after current uploads finish.')
    if not (file.filename or '').lower().endswith('.pdf'):
        raise HTTPException(400,'Only PDF uploads are supported')
    data = bytearray()
    while part := await file.read(1024*1024):
        data.extend(part)
        if len(data)>settings().max_upload_mb*1024*1024:
            raise HTTPException(413,'PDF exceeds upload limit')
    await file.close()
    if not bytes(data[:1024]).lstrip().startswith(b'%PDF-'):
        raise HTTPException(400,'Invalid PDF signature')
    doc_id = hashlib.sha256(data).hexdigest()
    old = svc.store.document(doc_id)
    if old and old['stage'] != 'Failed':
        path = svc.store.root/'uploads'/f'{doc_id}.pdf'
        if not path.exists():
            path.write_bytes(data)
            old['original_pdf_available'] = True
            svc.store.save_doc(old)
        return old
    name = re.sub(r'[\x00-\x1f\[\]]','_', (file.filename or 'document.pdf').replace('\\','/').split('/')[-1])[:180]
    path = svc.store.root/'uploads'/f'{doc_id}.pdf'
    path.write_bytes(data)
    doc = {'id':doc_id,'name':name,'stage':'Queued','searchable':False,'bytes':len(data)}
    svc.store.save_doc(doc)
    svc.submit(doc_id)
    return doc

@app.get('/documents',dependencies=[Depends(auth)])
def documents():
    return services().store.documents()

def get_doc(doc_id):
    if not re.fullmatch('[a-f0-9]{64}',doc_id):
        raise HTTPException(404,'Document not found')
    doc = services().store.document(doc_id)
    if doc is None:
        raise HTTPException(404,'Document not found')
    return doc

@app.get('/document/{doc_id}/status',dependencies=[Depends(auth)])
def status(doc_id: str):
    return get_doc(doc_id)

@app.get('/document/{doc_id}',dependencies=[Depends(auth)])
def document(doc_id: str):
    doc = get_doc(doc_id)
    path = services().store.root/'uploads'/f'{doc_id}.pdf'
    if not path.exists():
        raise HTTPException(404,'Original PDF is no longer stored on this host')
    return FileResponse(path,media_type='application/pdf',filename=doc['name'])

class Query(BaseModel):
    question: str = Field(min_length=3,max_length=2000)
    document_ids: list[str] = Field(default_factory=list,max_length=30)

@app.post('/query',dependencies=[Depends(auth)])
def query(body: Query):
    # Ablation switches are intentionally a local Python API, not a public bypass of verification.
    for doc_id in body.document_ids:
        get_doc(doc_id)
    return services().workflow.query(body.question,body.document_ids)

@app.get('/metrics',dependencies=[Depends(auth)])
def metrics():
    from eval.latency import summarize
    return summarize(services().store.events())

if __name__=='__main__':
    import uvicorn
    uvicorn.run('app.main:app',host=settings().host,port=settings().port,workers=1)
