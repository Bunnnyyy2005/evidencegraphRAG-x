"""LangGraph routing, conditional transformation, CRAG retry and claim verification."""
import time
import contextvars
from concurrent.futures import ThreadPoolExecutor
from typing import TypedDict, Literal
from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
from .config import settings
from .retrieval import rrf
from .utils import usage_context, RateLimitError
from .verification import Answer, verify, render_claims

class Options(BaseModel):
    mode: Literal['dense','sparse','hybrid'] = 'hybrid'
    contextual: bool = True
    reranker: bool = True
    graph: bool = True
    crag: bool = True
    verifier: bool = True
    cache: bool = True
    transforms: bool = True

class Route(BaseModel):
    category: Literal['factoid','multi-hop','global','off-scope']
    reason: str

class Transform(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=3)

class Grade(BaseModel):
    sufficient: bool
    score: float = Field(ge=0,le=1)
    reason: str

class MapResult(BaseModel):
    relevant_chunk_ids: list[str]
    note: str

class State(TypedDict, total=False):
    question: str
    document_ids: list[str]
    options: dict
    category: str
    route_reason: str
    queries: list[str]
    retry: int
    hits: list[dict]
    evidence: list[dict]
    sufficient: bool
    grade: dict
    answer: dict
    claims: list[dict]
    audit: list[dict]
    abstained: bool
    reason: str
    timings: dict
    warnings: list[str]
    map_notes: list[str]
    reranker_ran: bool


def route_hint(question: str) -> str:
    q = question.casefold()
    if any(t in q for t in ('summarize','summarise','major limitations','main risks','overall','across the document')):
        return 'global'
    if any(t in q for t in ('compare','relationship',' and ','whereas','how does')):
        return 'multi-hop'
    return 'factoid'

class Workflow:
    def __init__(self, store, retrieval, graph, llm, cache):
        self.store, self.retrieval, self.graph, self.llm, self.cache = store, retrieval, graph, llm, cache
        builder = StateGraph(State)
        for name in ('route','transform','retrieve','grade','rewrite','generate','verify','abstain'):
            builder.add_node(name, self.timed(name, getattr(self, name)))
        builder.add_edge(START,'route')
        builder.add_conditional_edges('route',lambda s: 'abstain' if s['category']=='off-scope' else 'transform')
        builder.add_edge('transform','retrieve')
        builder.add_edge('retrieve','grade')
        builder.add_conditional_edges('grade',lambda s: 'generate' if s['sufficient'] else 'rewrite' if s['retry']==0 and s['options']['crag'] else 'abstain')
        builder.add_edge('rewrite','retrieve')
        builder.add_edge('generate','verify')
        builder.add_edge('verify',END)
        builder.add_edge('abstain',END)
        self.compiled = builder.compile()

    def timed(self, name, function):
        def call(state):
            start = time.perf_counter()
            update = function(state)
            times = {**state.get('timings',{}), **update.get('timings',{})}
            times[name] = times.get(name,0)+time.perf_counter()-start
            update['timings'] = times
            return update
        return call

    def route(self, state):
        try:
            route = self.llm.json('Classify the question. Off-scope only for requests unrelated to document QA, '
                'not merely because you do not know the answer.', {'question':state['question']}, Route)
        except Exception:
            route = Route(category=route_hint(state['question']),reason='Deterministic fallback router')
        self.store.event('route',route.model_dump())
        return {'category':route.category,'route_reason':route.reason}

    def transform(self, state):
        queries = [state['question']]
        if state['options']['transforms'] and state['category']=='multi-hop':
            try:
                queries += self.llm.json('Decompose the question into at most two targeted retrieval questions. '
                    'Retain identifiers and numbers.', {'question':state['question']}, Transform).queries[:2]
            except Exception as exc:
                self.store.failure('retrieval',exc)
        elif state['options']['transforms'] and settings().use_hyde and len(state['question'].split()) < 7:
            try:
                queries += self.llm.json('Write one short hypothetical retrieval passage, not a factual answer. '
                    'It will only be used for searching and never cited.', {'question':state['question']},Transform).queries[:1]
            except Exception as exc:
                self.store.failure('retrieval',exc)
        return {'queries':queries}

    def global_evidence(self, state):
        """Map across every selected paragraph (or community), then reduce to original evidence."""
        chunks = self.store.chunks(state['document_ids'])
        by_id = {c['chunk_id']:c for c in chunks}
        communities = self.graph.communities(state['document_ids']) if state['options']['graph'] else []
        groups, covered = [], set()
        for community in communities:
            ids = [cid for cid in community['chunk_ids'] if cid in by_id]
            if ids:
                groups.append(([by_id[cid] for cid in ids],community['summary']))
                covered.update(ids)
        remaining = [c for c in chunks if c['chunk_id'] not in covered]
        # Page/section ordered scan, not top-k vector search.
        remaining.sort(key=lambda c:(c['document_id'],c['page_number'],c['parent_id']))
        groups += [(remaining[i:i+12], '') for i in range(0,len(remaining),12)]
        selected, notes, failures = [], [], 0
        for group, summary in groups:
            try:
                result = self.llm.json('Select original chunks needed to answer this global question. '
                    'Write a short evidence-grounded note. Community summary is a guide, not authoritative evidence.',
                    {'question':state['question'],'community_summary':summary,
                     'evidence':[{'chunk_id':c['chunk_id'],'text':c['text']} for c in group]},MapResult)
                allowed = {c['chunk_id'] for c in group}
                selected.extend(by_id[cid] for cid in result.relevant_chunk_ids if cid in allowed)
                notes.append(result.note)
            except Exception as exc:
                failures += 1
                self.store.failure('generation',exc)
        return rrf(selected), notes, failures

    def retrieve(self, state):
        cfg, options = settings(), state['options']
        rankings, warnings = [], list(state.get('warnings',[]))
        notes = []
        times = dict(state.get('timings',{}))
        if state['category']=='global' and options['transforms']:
            hits, notes, failures = self.global_evidence(state)
            rankings.append(hits)
            if failures:
                warnings.append(f'{failures} global map groups failed; global coverage incomplete.')
        search = getattr(self.retrieval, options['mode'])
        def graph_branch():
            started = time.perf_counter()
            result = self.graph.retrieve(state['question'], state['document_ids'])
            return result, time.perf_counter() - started
        with ThreadPoolExecutor(max_workers=4) as pool:
            searches = [pool.submit(search, query, state['document_ids'], options['contextual'])
                        for query in state['queries']]
            graph_future = (pool.submit(contextvars.copy_context().run, graph_branch)
                            if options['graph'] and state['category'] in ('multi-hop', 'global') else None)
            for future in searches:
                try:
                    rankings.append(future.result())
                except Exception as exc:
                    self.store.failure('retrieval', exc)
                    warnings.append('One retrieval branch failed.')
            if graph_future:
                try:
                    graph_hits, graph_seconds = graph_future.result()
                    rankings.append(graph_hits)
                    times['graph_retrieval'] = times.get('graph_retrieval', 0) + graph_seconds
                except Exception as exc:
                    self.store.failure('graph traversal', exc)
        hits = rrf(*rankings)[:cfg.retrieval_k]
        start = time.perf_counter()
        ran = False
        if options['reranker'] and hits:
            # Keep at least ten ranked candidates for valid Recall@10 before generation truncation.
            hits, ran = self.retrieval.rerank(state['question'],hits,k=max(10,cfg.reranker_k))
        times['reranking'] = times.get('reranking',0)+time.perf_counter()-start
        evidence, used = [], 0
        for hit in hits[:cfg.reranker_k]:
            # Only the original chunk is a citation target. Parent context is separately marked.
            size = len(hit['text'])+len(hit.get('parent_text',''))
            if used+size > cfg.max_context_chars:
                continue
            evidence.append(hit); used += size
        return {'hits':hits,'evidence':evidence,'map_notes':notes,'warnings':warnings,
                'timings':times,'reranker_ran':ran}

    def grade(self, state):
        if not state['evidence']:
            return {'sufficient':False,'reason':'No usable evidence was retrieved.'}
        if not state['options']['crag']:
            return {'sufficient':True,'grade':{'status':'DISABLED'}}
        try:
            grade = self.llm.json('Does the original evidence jointly answer ALL parts of the question? '
                'Do not use prior knowledge. A topical match is insufficient.',
                {'question':state['question'],'evidence':[c['text'] for c in state['evidence']]},Grade)
            good = grade.sufficient and grade.score >= settings().grade_threshold
            return {'sufficient':good,'grade':grade.model_dump(),'reason':grade.reason}
        except RateLimitError as exc:
            self.store.failure('evidence grading',exc)
            return {'sufficient':False,'reason':str(exc)}
        except Exception as exc:
            self.store.failure('retrieval',exc)
            return {'sufficient':False,'reason':'Evidence grading unavailable.'}

    def rewrite(self, state):
        try:
            queries = self.llm.json('Rewrite or step back to the underlying technical concept to improve retrieval. '
                'Preserve named entities, negation and numbers. Return at most three complementary searches.',
                {'question':state['question'],'grader':state.get('grade',{})},Transform).queries
        except Exception:
            queries = [state['question']]
        return {'queries':queries,'retry':1}

    def generate(self, state):
        try:
            answer = self.llm.json('Answer only from evidence. Return atomic claims each with one or more '
                'chunk_id citations. Original text must support every claim; parent context only clarifies meaning. '
                'If evidence is inadequate return an empty claims list. Never emit invented IDs or inline citation labels.',
                {'question':state['question'],'evidence':[
                    {'chunk_id':c['chunk_id'],'original':c['text'],'parent_context':c.get('parent_text','')}
                    for c in state['evidence']]},Answer,large=True)
            return {'answer':answer.model_dump()}
        except RateLimitError as exc:
            self.store.failure('generation',exc)
            return {'answer':{'claims':[]},'reason':str(exc)}
        except Exception as exc:
            self.store.failure('generation',exc)
            return {'answer':{'claims':[]},'reason':'Generation unavailable.'}

    def verify(self, state):
        claims,audit = verify(Answer.model_validate(state['answer']),state['evidence'],self.llm,state['options']['verifier'])
        failure_reason = next((r['reason'] for r in audit if r['reason'].startswith('LLM quota/rate limit')), None)
        if failure_reason is None and state.get('reason','').startswith(('LLM quota/rate limit','Generation unavailable')):
            failure_reason = state['reason']
        return {'claims':claims,'audit':audit,'abstained':not bool(claims),
                'reason':state.get('reason','') if claims else (
                    failure_reason or 'No supported answer survived generation and verification.')}

    def abstain(self, state):
        return {'claims':[],'audit':[],'abstained':True,
                'reason':state.get('reason','Question is outside document QA.')}

    def query(self, question: str, document_ids: list[str], options: Options | None = None,
              cache_namespace: str = '') -> dict:
        started = time.perf_counter()
        opt = (options or Options(reranker=settings().use_reranker,graph=settings().graph_enabled)).model_dump()
        known = {d['id'] for d in self.store.documents() if d.get('searchable')}
        ids = sorted(set(document_ids) & known) if document_ids else sorted(known)
        usage = dict(llm_calls=0,llm_retries=0,prompt_tokens=0,completion_tokens=0,
                     tokens_available=True,cost_available=True,estimated_paid_usd=0.)
        token = usage_context.set(usage)
        vector, scope = [], self.cache.scope(self.store.version(),ids,{**opt, '_namespace':cache_namespace})
        try:
            if opt['cache'] and self.cache.client is not None:
                if settings().semantic_cache:
                    vector = self.retrieval.embed([question])[0]
                cached = self.cache.get(scope,question,vector)
                if cached:
                    response = {**cached,'cache_hit':True,'timings':{'total':time.perf_counter()-started},'usage':usage}
                    self.store.event('query',{'cache_hit':True,'timings':response['timings'],'usage':usage})
                    return response
            if ids:
                state = self.compiled.invoke({'question':question,'document_ids':ids,'options':opt,
                    'retry':0,'timings':{},'warnings':[]},config={'recursion_limit':20})
            else:
                state = {'abstained':True,'reason':'No selected document is searchable yet.','claims':[],
                         'audit':[],'evidence':[],'hits':[],'timings':{},'warnings':[],'retry':0}
            response = {k:state.get(k) for k in ('abstained','reason','claims','audit','evidence','hits','warnings','grade','category','route_reason','retry','reranker_ran')}
            response['answer'] = render_claims(state['claims'],state.get('evidence',[])) if state['claims'] else 'I cannot answer from the available verified evidence.'
            response['timings'] = {**state['timings'],'total':time.perf_counter()-started}
            response['cache_hit'] = False
            response['usage'] = usage
            response['document_version'] = self.store.version()
            if not usage['cost_available']:
                usage['estimated_paid_usd'] = None
            if opt['cache']:
                self.cache.put(scope,question,vector,response)
            self.store.event('query',{'cache_hit':False,'timings':response['timings'],'usage':usage,'retry':state['retry']})
            return response
        finally:
            usage_context.reset(token)
