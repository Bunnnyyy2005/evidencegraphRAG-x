"""Validated entity relations, Neo4j provenance, bounded traversal and community retrieval."""
import json
import time
from typing import Literal
import networkx as nx
from neo4j import GraphDatabase
from pydantic import BaseModel, Field
from .config import settings
from .utils import digest, RateLimitError

class Entity(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    type: str = Field(min_length=1, max_length=80)

class Relation(BaseModel):
    source: str
    target: str
    relation: str = Field(min_length=1, max_length=100)
    evidence: str = Field(min_length=3)

class Extraction(BaseModel):
    entities: list[Entity] = Field(max_length=20)
    relations: list[Relation] = Field(max_length=30)

class Summary(BaseModel):
    summary: str
    chunk_ids: list[str]

class Seeds(BaseModel):
    entities: list[str] = Field(max_length=10)

# Values are always parameters. Hop bounds are configuration-validated integers.
def traversal_query(hops: int) -> str:
    if hops not in (1, 2):
        raise ValueError('Only 1 or 2 hops are supported')
    return f'''
    MATCH (seed:Entity) WHERE seed.document_id IN $documents AND seed.name IN $names
    MATCH p=(seed)-[:RELATES_TO*1..{hops}]-(target:Entity)
    WHERE ALL(r IN relationships(p) WHERE r.document_id IN $documents)
    RETURN [n IN nodes(p) | n.name] AS names,
           [r IN relationships(p) | {{source:r.source, target:r.target, relation:r.relation,
             chunk_id:r.chunk_id, evidence:r.evidence}}] AS edges
    LIMIT $limit
    '''

class Graph:
    def __init__(self, store, llm):
        self.store, self.llm = store, llm
        self.driver = None
        self._last_graph_request = None
        cfg = settings()
        if cfg.graph_enabled and cfg.neo4j_uri:
            self.driver = GraphDatabase.driver(cfg.neo4j_uri, auth=(cfg.neo4j_user, cfg.neo4j_password),
                                               connection_timeout=10)

    def run(self, cypher: str, **params) -> list[dict]:
        if self.driver is None:
            raise RuntimeError('Neo4j not configured')
        with self.driver.session(database=settings().neo4j_database) as session:
            return session.execute_write(lambda tx: tx.run(cypher, **params).data())

    def _extract_json(self, *args, **kwargs):
        """Pace background graph calls; pause instead of waiting through long quotas."""
        cfg = settings()
        for attempt in range(cfg.graph_rate_limit_retries + 1):
            if self._last_graph_request is not None:
                delay = cfg.graph_request_interval - (time.monotonic() - self._last_graph_request)
                if delay > 0:
                    time.sleep(delay)
            self._last_graph_request = time.monotonic()
            try:
                return self.llm.json(*args, **kwargs)
            except RateLimitError as exc:
                if attempt >= cfg.graph_rate_limit_retries or exc.retry_after > cfg.graph_max_retry_wait:
                    raise
                self.store.event('graph_retry', {'attempt': attempt + 1, 'retry_after_seconds': exc.retry_after})
                time.sleep(exc.retry_after)

    def enrich(self, chunks: list[dict]) -> dict:
        if self.driver is None:
            return {'status': 'Searchable — graph not configured', 'processed': 0}
        if not chunks:
            raise ValueError("No saved chunks available for graph extraction")
        self.driver.verify_connectivity()
        doc_id = chunks[0]['document_id']
        self.run('CREATE CONSTRAINT eg_node_id IF NOT EXISTS FOR (n:EGNode) REQUIRE n.id IS UNIQUE')
        self.run('''UNWIND $rows AS row
            MERGE (d:EGNode:Document {id:row.document_id}) SET d.name=row.document_name
            MERGE (s:EGNode:Section {id:row.section_id}) SET s.title=row.section
            MERGE (s)-[:PART_OF]->(d)
            MERGE (c:EGNode:Chunk {id:row.chunk_id}) SET c.document_id=row.document_id,
                c.page=row.page_number, c.text=row.text
            MERGE (c)-[:PART_OF]->(s)''', rows=chunks)
        network = nx.Graph()
        processed, failed = 0, 0
        paused = None
        chosen = chunks[:settings().graph_chunk_limit] if settings().graph_chunk_limit else chunks
        checkpoint = digest('graph-extraction-v1:' + settings().small_model)
        completed = {r['id'] for r in self.run(
            'MATCH (c:Chunk) WHERE c.document_id=$doc AND c.graph_checkpoint=$checkpoint RETURN c.id AS id',
            doc=doc_id, checkpoint=checkpoint)}
        for chunk in chosen:
            if chunk['chunk_id'] in completed:
                processed += 1
                continue
            try:
                extracted = self._extract_json('Extract explicitly supported entities and relations. '
                    'Each relation evidence must be an exact substring of text. Do not infer causal links.',
                    {'text': chunk['text']}, Extraction)
                entities = {e.name.casefold().strip(): e for e in extracted.entities}
                valid = []
                for r in extracted.relations:
                    a, b = r.source.casefold().strip(), r.target.casefold().strip()
                    if a not in entities or b not in entities or r.evidence not in chunk['text']:
                        self.store.event('failure', {'stage': 'relation extraction', 'error_type': 'InvalidProvenance'})
                        continue
                    valid.append({**r.model_dump(), 'source': a, 'target': b,
                                  'source_id': digest(doc_id+':'+a), 'target_id': digest(doc_id+':'+b),
                                  'edge_id': digest(chunk['chunk_id']+a+b+r.relation)})
                    network.add_edge(a, b)
                self.run('''MATCH (c:Chunk {id:$chunk}) UNWIND $entities AS e
                    MERGE (n:EGNode:Entity {id:e.id}) SET n.name=e.name,n.type=e.type,n.document_id=$doc
                    MERGE (c)-[:MENTIONS]->(n)''', chunk=chunk['chunk_id'], doc=doc_id,
                    entities=[{'id': digest(doc_id+':'+name), 'name': name, 'type': e.type} for name, e in entities.items()])
                self.run('''UNWIND $relations AS r
                    MATCH (a:Entity {id:r.source_id})
                    MATCH (b:Entity {id:r.target_id})
                    MERGE (a)-[e:RELATES_TO {id:r.edge_id}]->(b)
                    SET e.source=r.source,e.target=r.target,e.relation=r.relation,
                        e.evidence=r.evidence,e.chunk_id=$chunk,e.document_id=$doc''',
                    relations=valid, chunk=chunk['chunk_id'], doc=doc_id)
                # Mark only after both entity and relation writes have succeeded.
                self.run('MATCH (c:Chunk {id:$chunk}) SET c.graph_checkpoint=$checkpoint',
                         chunk=chunk['chunk_id'], checkpoint=checkpoint)
                processed += 1
            except RateLimitError as exc:
                paused = exc
                self.store.failure('entity extraction', exc)
                break
            except Exception as exc:
                failed += 1
                self.store.failure('entity extraction', exc)
        # Include edges from earlier completed chunks when rebuilding communities.
        network = nx.Graph()
        for row in self.run('MATCH ()-[r:RELATES_TO]->() WHERE r.document_id=$doc AND r.chunk_id IN $chunks RETURN r.source AS source,r.target AS target',
                            doc=doc_id, chunks=[c['chunk_id'] for c in chosen]):
            network.add_edge(row['source'], row['target'])
        communities = list(nx.community.greedy_modularity_communities(network)) if network.number_of_edges() and paused is None else []
        summaries = 0
        summary_failed = 0
        for index, members in enumerate(communities):
            try:
                rows = self.run('''MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
                    WHERE e.document_id=$doc AND e.name IN $names
                    RETURN DISTINCT c.id AS chunk_id,c.text AS text,c.page AS page ORDER BY c.page LIMIT 16''',
                    doc=doc_id, names=list(members))
                community_id = digest(doc_id + ':community-v2:' + '|'.join(sorted(members)))
                summary_key = digest(checkpoint + json.dumps(rows, sort_keys=True))
                saved = self.run('MATCH (g:Community {id:$id}) WHERE g.summary_checkpoint=$key RETURN g.id AS id',
                                 id=community_id, key=summary_key)
                if saved:
                    summaries += 1
                    continue
                summary = self._extract_json('Summarize this community using only the supplied evidence. '
                    'Return supporting chunk_ids from the input.', {'evidence': rows}, Summary)
                valid_ids = sorted(set(summary.chunk_ids) & {r['chunk_id'] for r in rows})
                if not valid_ids:
                    summary_failed += 1
                    continue
                self.run('''MATCH (d:Document {id:$doc})
                    MERGE (g:EGNode:Community {id:$id}) SET g.document_id=$doc,g.summary=$summary,g.chunk_ids=$chunks,g.summary_checkpoint=$key
                    MERGE (g)-[:PART_OF]->(d)
                    WITH g UNWIND $members AS name MATCH (e:Entity {name:name,document_id:$doc})
                    MERGE (e)-[:PART_OF]->(g)''', doc=doc_id, id=community_id, key=summary_key,
                    summary=summary.summary, chunks=valid_ids, members=list(members))
                summaries += 1
            except RateLimitError as exc:
                paused = exc
                self.store.failure('community summary', exc)
                break
            except Exception as exc:
                summary_failed += 1
                self.store.failure('graph traversal', exc)
        if paused is not None:
            return {'status': 'Searchable — graph paused (LLM rate limit)',
                    'processed': processed, 'failed': failed, 'total': len(chunks),
                    'communities': summaries, 'deferred': len(chosen)-processed-failed,
                    'retry_after_seconds': paused.retry_after}
        return {'status': 'Graph ready' if processed == len(chunks) and failed == 0 and summary_failed == 0 else 'Graph partial',
                'processed': processed, 'failed': failed, 'total': len(chunks), 'communities': summaries}

    def retrieve(self, question: str, document_ids: list[str]) -> list[dict]:
        if self.driver is None:
            return []
        try:
            seeds = self.llm.json('Extract entity names likely mentioned in the question. Do not answer it.',
                                  {'question': question}, Seeds).entities
            candidates = self.run('''MATCH (e:Entity) WHERE e.document_id IN $documents
                AND ANY(name IN $names WHERE e.name=toLower(name) OR e.name CONTAINS toLower(name))
                RETURN DISTINCT e.name AS name LIMIT 20''', documents=document_ids, names=seeds)
            names = [r['name'] for r in candidates]
            if not names:
                return []
            paths = self.run(traversal_query(settings().graph_hops), documents=document_ids,
                             names=names, limit=settings().graph_limit)
            direct = self.run('''MATCH (c:Chunk)-[:MENTIONS]->(e:Entity)
                WHERE e.document_id IN $documents AND e.name IN $names
                RETURN DISTINCT c.id AS chunk_id,e.name AS name LIMIT 100''', documents=document_ids, names=names)
            chunks = {c['chunk_id']: c for c in self.store.chunks(document_ids)}
            graph = nx.Graph()
            for path in paths:
                nx.add_path(graph, path['names'])
            graph.add_nodes_from(names)
            ppr = nx.pagerank(graph, personalization={n: float(n in names) for n in graph})
            hits = {}
            for row in direct:
                cid = row['chunk_id']
                if cid in chunks:
                    hits[cid] = dict(chunks[cid], score=ppr.get(row['name'], 0),
                        graph_path={'entities': [row['name']], 'edges': [], 'chunk_id': cid, 'kind': 'MENTIONS'})
            for path in paths:
                # Every edge must still exist in the current searchable corpus, with exact provenance.
                if not all(e['chunk_id'] in chunks and e['evidence'] in chunks[e['chunk_id']]['text'] for e in path['edges']):
                    continue
                for edge in path['edges']:
                    cid = edge['chunk_id']
                    score = sum(ppr.get(n, 0) for n in path['names'])
                    if cid not in hits or score > hits[cid]['score']:
                        hits[cid] = dict(chunks[cid], score=score,
                            graph_path={'entities': path['names'], 'edges': path['edges'], 'chunk_id': cid, 'kind': 'RELATES_TO'})
            return sorted(hits.values(), key=lambda h: -h['score'])[:settings().retrieval_k]
        except Exception as exc:
            self.store.failure('graph traversal', exc)
            return []

    def communities(self, document_ids: list[str]) -> list[dict]:
        if self.driver is None:
            return []
        try:
            return self.run('''MATCH (c:Community) WHERE c.document_id IN $documents
                RETURN c.id AS id,c.summary AS summary,c.chunk_ids AS chunk_ids
                ORDER BY c.id LIMIT $limit''', documents=document_ids, limit=settings().graph_limit)
        except Exception as exc:
            self.store.failure('graph traversal', exc)
            return []

    def close(self):
        if self.driver:
            self.driver.close()
