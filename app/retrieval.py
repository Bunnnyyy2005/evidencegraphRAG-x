"""CPU dense embeddings, raw/contextual Qdrant vectors, BM25, RRF and cross-encoder."""
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
import numpy as np
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi
from .config import settings
from .utils import tokens, digest


def rrf(*rankings: list[dict], k: int = 60) -> list[dict]:
    scores, items = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, item in enumerate(ranking, 1):
            cid = item['chunk_id']
            if cid in seen:
                continue
            seen.add(cid)
            scores[cid] = scores.get(cid, 0) + 1 / (k+rank)
            items[cid] = {**items.get(cid, {}), **item}
    return [dict(items[cid], score=score) for cid, score in sorted(scores.items(), key=lambda x: -x[1])]

class Retrieval:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.model_lock = threading.Lock()
        self.bm_cache = {}
        self._indexed_collection = None

    @cached_property
    def embedder(self):
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=settings().embedding_model, threads=settings().embedding_threads,
                             cache_dir=str(self.store.root / 'models'))

    def embed(self, texts: list[str]) -> list[list[float]]:
        with self.model_lock:
            return [v.tolist() for v in self.embedder.embed(texts, batch_size=settings().embedding_batch_size)]

    @cached_property
    def client(self):
        cfg = settings()
        return QdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None, timeout=30) if cfg.qdrant_url else QdrantClient(path=str(self.store.root / 'qdrant'))

    def index(self, chunks: list[dict], progress=lambda: None) -> None:
        cfg = settings()
        fingerprint = digest(f'{cfg.collection}|{cfg.embedding_model}|{cfg.chunk_words}|v1')
        self.store.assert_index_config(fingerprint)
        for offset in range(0, len(chunks), cfg.embedding_batch_size):
            batch = chunks[offset:offset+cfg.embedding_batch_size]
            raw = self.embed([c['text'] for c in batch])
            contextual = self.embed([c['context'] for c in batch])
            progress()
            with self.lock:
                if not self.client.collection_exists(cfg.collection):
                    self.client.create_collection(cfg.collection, vectors_config={
                        name: models.VectorParams(size=len(raw[0]), distance=models.Distance.COSINE)
                        for name in ('raw', 'contextual')})
                self.ensure_payload_indexes()
                self.client.upsert(cfg.collection, points=[models.PointStruct(
                    id=str(uuid.UUID(c['chunk_id'][:32])), vector={'raw': r, 'contextual': x},
                    payload={**c, 'index_fingerprint':fingerprint, 'published':False})
                    for c, r, x in zip(batch, raw, contextual)], wait=True)
        with self.lock:
            self.client.set_payload(cfg.collection, payload={'published': True},
                points=models.Filter(must=[models.FieldCondition(key='document_id',
                    match=models.MatchValue(value=chunks[0]['document_id']))]), wait=True)
        self.bm_cache.clear()

    def ensure_payload_indexes(self) -> None:
        """Ensure cloud filters work for both new and existing collections."""
        cfg = settings()
        if not cfg.qdrant_url or self._indexed_collection == cfg.collection:
            return
        with self.lock:
            if not self.client.collection_exists(cfg.collection):
                return
            schema = self.client.get_collection(cfg.collection).payload_schema or {}
            for field, field_type in (
                ('document_id', models.PayloadSchemaType.KEYWORD),
                ('published', models.PayloadSchemaType.BOOL),
                ('page_number', models.PayloadSchemaType.INTEGER),
                ('section', models.PayloadSchemaType.KEYWORD),
                ('document_name', models.PayloadSchemaType.KEYWORD),
            ):
                if field not in schema:
                    self.client.create_payload_index(
                        cfg.collection, field, field_type, wait=True)
            self._indexed_collection = cfg.collection

    def restore_catalog(self) -> int:
        """Restore payloads in bounded batches; keep only document metadata in RAM."""
        if not settings().qdrant_url or self.store.documents():
            return 0
        cfg = settings()
        expected = digest(f'{cfg.collection}|{cfg.embedding_model}|{cfg.chunk_words}|v1')
        with self.lock:
            if not self.client.collection_exists(cfg.collection):
                return 0
            self.ensure_payload_indexes()
            offset, documents = None, {}
            while True:
                points, offset = self.client.scroll(cfg.collection, offset=offset, limit=32,
                    scroll_filter=models.Filter(must=[models.FieldCondition(key='published',
                        match=models.MatchValue(value=True))]), with_payload=True, with_vectors=False)
                for point in points:
                    chunk = point.payload
                    if chunk.get('index_fingerprint') != expected:
                        raise ValueError('Cloud collection uses a different index configuration; choose a new collection.')
                    documents[chunk['document_id']] = chunk['document_name']
                with self.store.db() as db:
                    db.executemany('INSERT OR REPLACE INTO chunks VALUES (?,?,?)',
                        ((p.payload['chunk_id'], p.payload['document_id'], json.dumps(p.payload)) for p in points))
                del points
                if offset is None:
                    break
        for doc_id, name in documents.items():
            with self.store.db() as db:
                count = db.execute('SELECT count(*) FROM chunks WHERE doc=?', (doc_id,)).fetchone()[0]
            self.store.save_doc({'id':doc_id, 'name':name, 'searchable':True,
                'stage':'Searchable — restored from Qdrant', 'chunks':count,
                'revision':'restored', 'graph_revision':'restored', 'original_pdf_available':False})
        return len(documents)

    def dense(self, query: str, document_ids: list[str], contextual: bool = True, k: int | None = None,
              metadata: dict | None = None) -> list[dict]:
        vector = self.embed([query])[0]
        conditions = [models.FieldCondition(key='document_id', match=models.MatchAny(any=document_ids)),
                      models.FieldCondition(key='published', match=models.MatchValue(value=True))]
        for field, value in (metadata or {}).items():
            if field not in ('page_number', 'section', 'document_name'):
                raise ValueError('Unsupported metadata filter')
            conditions.append(models.FieldCondition(key=field, match=models.MatchValue(value=value)))
        with self.lock:
            if not self.client.collection_exists(settings().collection):
                return []
            self.ensure_payload_indexes()
            result = self.client.query_points(settings().collection, query=vector,
                using='contextual' if contextual else 'raw', query_filter=models.Filter(must=conditions),
                limit=k or settings().retrieval_k, with_payload=True).points
        return [dict(p.payload, score=p.score) for p in result]

    def sparse(self, query: str, document_ids: list[str], contextual: bool = True, k: int | None = None,
               metadata: dict | None = None) -> list[dict]:
        key = (tuple(sorted(document_ids)), contextual, self.store.version())
        with self.lock:
            if key not in self.bm_cache:
                chunks = self.store.chunks(document_ids)
                self.bm_cache = {key: (chunks, BM25Okapi([tokens(c['context' if contextual else 'text']) or ['_'] for c in chunks]) if chunks else None)}
            chunks, index = self.bm_cache[key]
        if index is None:
            return []
        scores = index.get_scores(tokens(query))
        # Negative BM25 scores can be valid on very small corpora: use lexical overlap as eligibility.
        qtokens = set(tokens(query))
        indices = [i for i in np.argsort(scores)[::-1]
                   if qtokens.intersection(tokens(chunks[i]['text'])) and
                   all(chunks[i].get(f) == v for f, v in (metadata or {}).items())]
        return [dict(chunks[i], score=float(scores[i])) for i in indices[:k or settings().retrieval_k]]

    def hybrid(self, query: str, document_ids: list[str], contextual: bool = True, **kwargs) -> list[dict]:
        with ThreadPoolExecutor(2) as pool:
            dense = pool.submit(self.dense, query, document_ids, contextual, **kwargs)
            sparse = pool.submit(self.sparse, query, document_ids, contextual, **kwargs)
            rankings = []
            for future in (dense, sparse):
                try:
                    rankings.append(future.result())
                except Exception as exc:
                    self.store.failure('retrieval', exc)
        return rrf(*rankings)[:kwargs.get('k') or settings().retrieval_k]

    @cached_property
    def ranker(self):
        from flashrank import Ranker
        return Ranker(model_name=settings().reranker_model, cache_dir=str(self.store.root / 'models' / 'reranker'))

    def rerank(self, query: str, hits: list[dict], k: int | None = None) -> tuple[list[dict], bool]:
        try:
            from flashrank import RerankRequest
            with self.model_lock:
                result = self.ranker.rerank(RerankRequest(query=query, passages=[
                    {'id': c['chunk_id'], 'text': c['text']} for c in hits]))
            by_id = {c['chunk_id']: c for c in hits}
            return [dict(by_id[c['id']], rerank_score=float(c['score'])) for c in result[:k or settings().reranker_k]], True
        except Exception as exc:
            self.store.failure('reranking', exc)
            return hits[:k or settings().reranker_k], False

    def close(self):
        if 'client' in self.__dict__:
            self.client.close()
