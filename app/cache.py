"""Bounded Redis cache with corpus/config versions and explicit opt-in semantic matching."""
import json
import math
import redis
from .config import settings
from .utils import digest


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0
    denom = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x, y in zip(a,b))/denom if denom else 0

class Cache:
    def __init__(self, store):
        self.store = store
        self.client = redis.Redis.from_url(settings().redis_url, socket_timeout=3,
            socket_connect_timeout=3, decode_responses=True) if settings().redis_url else None

    def scope(self, version: str, ids: list[str], options: dict) -> str:
        cfg = settings()
        return 'eg:' + digest(json.dumps([version, sorted(ids), options, cfg.llm_model,
            cfg.small_model, cfg.embedding_model, cfg.reranker_model, cfg.grade_threshold,
            cfg.retrieval_k, cfg.reranker_k, cfg.max_context_chars, cfg.semantic_cache, 'workflow-v1'], sort_keys=True))

    def get(self, scope: str, query: str, vector: list[float]) -> dict | None:
        if self.client is None:
            return None
        try:
            # One bounded list avoids global key scans and unbounded per-query command counts.
            for raw in self.client.lrange(scope, 0, settings().cache_entries-1):
                item = json.loads(raw)
                exact = item['query'].strip().casefold() == query.strip().casefold()
                if exact or (settings().semantic_cache and cosine(vector, item['vector']) >= settings().cache_threshold):
                    return {**item['response'], 'cache_match': 'exact' if exact else 'semantic'}
        except Exception as exc:
            self.store.failure('cache', exc)
        return None

    def put(self, scope: str, query: str, vector: list[float], response: dict) -> None:
        if self.client is None or response.get('abstained'):
            return
        try:
            item = json.dumps({'query': query, 'vector': vector, 'response': response})
            with self.client.pipeline(transaction=True) as pipe:
                pipe.lpush(scope, item).ltrim(scope, 0, settings().cache_entries-1).expire(scope, settings().cache_ttl).execute()
        except Exception as exc:
            self.store.failure('cache', exc)
