"""Dependency-free checks of the actual retrieval methods and SQLite restoration."""
import ast
import json
import sqlite3
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace


def retrieval_methods(store, client):
    source = ast.parse((Path(__file__).resolve().parents[1] / 'app/retrieval.py').read_text())
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Retrieval')
    cfg = SimpleNamespace(qdrant_url='cloud', collection='test', embedding_model='same-model', chunk_words=140, embedding_batch_size=2)
    model = lambda **kw: kw
    models = SimpleNamespace(Filter=model, FieldCondition=model, MatchValue=model, PointStruct=model,
        VectorParams=model, Distance=SimpleNamespace(COSINE='cosine'))
    namespace = dict(settings=lambda: cfg, digest=lambda value: 'fingerprint', models=models, json=json, uuid=uuid)
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ('embed','index','restore_catalog')]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual retrieval methods>', 'exec'), namespace)
    obj = SimpleNamespace(store=store, client=client, lock=threading.RLock(), model_lock=threading.Lock(),
        ensure_payload_indexes=lambda: None, bm_cache={})
    for n in nodes:
        setattr(obj, n.name, namespace[n.name].__get__(obj))
    return obj


def test_bounded_restore_preserves_all_pages(tmp_path):
    class Store:
        def documents(self): return []
        def save_doc(self, doc): self.docs.append(doc)
        @contextmanager
        def db(self):
            db = sqlite3.connect(tmp_path / 'catalog.sqlite')
            try:
                yield db
                db.commit()
            finally: db.close()
    store = Store(); store.docs = []
    with store.db() as db: db.execute('CREATE TABLE chunks(id TEXT PRIMARY KEY,doc TEXT,body TEXT)')
    pages = [[SimpleNamespace(payload={'chunk_id':str(i),'document_id':'a' if i % 2 else 'b',
        'document_name':'source.pdf','index_fingerprint':'fingerprint','text':'sample'}) for i in range(3)],
        [SimpleNamespace(payload={'chunk_id':'3','document_id':'a','document_name':'source.pdf',
        'index_fingerprint':'fingerprint','text':'last page'})]]
    class Client:
        def collection_exists(self, collection): return True
        def scroll(self, collection, **kwargs):
            assert kwargs['limit'] == 32 and kwargs['with_vectors'] is False
            page = pages.pop(0)
            return page, 'next' if pages else None
    r = retrieval_methods(store, Client())
    assert r.restore_catalog() == 2
    assert {d['id']:d['chunks'] for d in store.docs} == {'a':2, 'b':2}
    with store.db() as db: assert db.execute('SELECT count(*) FROM chunks').fetchone()[0] == 4


def test_small_embedding_batches_publish_every_point():
    captured = []; uploaded = []
    class Embedder:
        def embed(self, texts, batch_size):
            captured.append((len(texts),batch_size))
            for t in texts:
                yield SimpleNamespace(tolist=lambda: [1.,0.])
    class Client:
        def collection_exists(self, collection): return True
        def upsert(self, collection, points, wait): uploaded.extend(points)
        def set_payload(self, collection, payload, points, wait):
            assert payload == {'published':True}
    store = SimpleNamespace(assert_index_config=lambda f: None)
    r = retrieval_methods(store, Client()); r.embedder = Embedder()
    chunks = [{'chunk_id':f'{i:064x}','document_id':'doc','text':'text','context':'context'} for i in range(5)]
    r.index(chunks)
    assert captured == [(2,2),(2,2),(2,2),(2,2),(1,2),(1,2)]
    assert len(uploaded) == 5
    assert all(set(p['vector']) == {'raw','contextual'} for p in uploaded)


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as temp:
        test_bounded_restore_preserves_all_pages(Path(temp))
    test_small_embedding_batches_publish_every_point()
    print('2 memory-profile checks passed')
