"""Page-level retrieval metrics, independent RAGAS judges, bootstraps and failure reports."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import time
import urllib.request
import numpy as np
from app.config import settings
from app.utils import Store, LLM, RateLimitError
from app.retrieval import Retrieval
from app.graph import Graph
from app.cache import Cache
from app.workflow import Workflow, Options
from .latency import summarize, NOT_MEASURED

ROOT = Path(__file__).resolve().parent

class EvaluationLLM(LLM):
    """Bounded quota waits for offline evaluation; dashboard behavior stays unchanged."""
    def __init__(self, store, request_interval=0, rate_limit_retries=0, max_rate_wait=60):
        super().__init__(store)
        self.request_interval = max(0, request_interval)
        self.rate_limit_retries = max(0, rate_limit_retries)
        self.max_rate_wait = max(0, max_rate_wait)
        self._next_request = 0

    def json(self, *args, **kwargs):
        for attempt in range(self.rate_limit_retries + 1):
            pause = self._next_request - time.monotonic()
            if pause > 0:
                time.sleep(pause)
            self._next_request = time.monotonic() + self.request_interval
            try:
                return super().json(*args, **kwargs)
            except RateLimitError as exc:
                if attempt == self.rate_limit_retries or exc.retry_after > self.max_rate_wait:
                    raise
                print(f'Groq rate limit: waiting {exc.retry_after}s '
                      f'(retry {attempt+1}/{self.rate_limit_retries})', flush=True)
                self.store.event('retry', {'model': exc.model, 'error_type': 'RateLimitError',
                                           'retry_after_seconds': exc.retry_after})
                time.sleep(exc.retry_after + 0.2)

def checkpoint(output, records, rows, responses):
    """Keep completed questions even if later inference or report writing fails."""
    (output/'responses.jsonl').write_text(
        '\n'.join(json.dumps({'id':r['id'], **x}) for r,x in zip(records,responses))+'\n',
        encoding='utf-8')
    (output/'per_question.jsonl').write_text(
        '\n'.join(json.dumps(row) for row in rows)+'\n', encoding='utf-8')

def evaluation_signature(records, options):
    cfg = settings()
    identity = {'records': records, 'options': options.model_dump(),
                'models': [cfg.small_model, cfg.llm_model], 'graph_enabled': cfg.graph_enabled,
                'collection': cfg.collection, 'data_dir': str(cfg.data_dir),
                'embedding_model': cfg.embedding_model}
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

def load_progress(output, records, signature):
    state_path = output/'checkpoint.json'
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding='utf-8'))
        if state['signature'] != signature:
            raise ValueError('Resume dataset/configuration changed. Use the original settings and dataset.')
    else:
        # Import the two checkpoints produced by the previous evaluator version.
        paths = [output/'per_question.jsonl', output/'responses.jsonl']
        if not all(p.exists() for p in paths):
            raise ValueError('Resume requires both saved per_question.jsonl and responses.jsonl.')
        saved = [[json.loads(line) for line in p.read_text(encoding='utf-8').splitlines()
                  if line.strip()] for p in paths]
        if abs(len(saved[0])-len(saved[1])) > 1:
            raise ValueError('Saved checkpoint lengths disagree; inspect files before resuming.')
        state = {'signature': signature, 'rows': saved[0], 'responses': saved[1],
                 'events': [], 'legacy_questions': min(map(len, saved))}
    for values in (state['rows'], state['responses']):
        if len(values) > len(records):
            raise ValueError('Saved results exceed the requested dataset.')
        for record, value in zip(records, values):
            if value.get('id') != record['id']:
                raise ValueError('Saved question IDs/order differ from the requested dataset.')
    count = min(len(state['rows']), len(state['responses']))
    state['rows'] = state['rows'][:count]
    state['responses'] = state['responses'][:count]
    # Keep the imported files intact before any subsequent writes.
    if not state_path.exists():
        for name in ('per_question.jsonl', 'responses.jsonl'):
            source = output/name
            backup = output/(name+'.before-resume')
            if not backup.exists():
                backup.write_bytes(source.read_bytes())
    return state

def save_progress(output, state):
    temporary = output/'checkpoint.json.tmp'
    temporary.write_text(json.dumps(state, allow_nan=False), encoding='utf-8')
    temporary.replace(output/'checkpoint.json')

def dataset(path: str | Path = ROOT/'gold_set.jsonl') -> list[dict]:
    rows=[json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate question IDs')
    return rows


def retrieval_metrics(hits: list[dict], record: dict) -> dict:
    """Relevant units are unique physical PDF pages, not arbitrary parser-dependent chunks."""
    gold={(record['document'],p) for p in record['pages']}
    if not gold:
        return {k:None for k in ('recall@5','recall@10','mrr','ndcg@10','hit@5','hit@10')}
    relevant_seen=set();gains=[]
    for hit in hits:
        unit=(hit['document_name'],hit['page_number'])
        gain=int(unit in gold and unit not in relevant_seen)
        gains.append(gain)
        if gain:relevant_seen.add(unit)
    ideal=sum(1/math.log2(i+2) for i in range(min(10,len(gold))))
    ranks=[i+1 for i,g in enumerate(gains) if g]
    return {'recall@5':sum(gains[:5])/len(gold),'recall@10':sum(gains[:10])/len(gold),
            'mrr':1/ranks[0] if ranks else 0.,'ndcg@10':sum(g/math.log2(i+2) for i,g in enumerate(gains[:10]))/ideal,
            'hit@5':int(bool(sum(gains[:5]))),'hit@10':int(bool(sum(gains[:10])))}


def path_validity(response: dict, chunks: dict) -> float | None:
    """Structural/provenance validity, not a claim of semantic relation correctness."""
    paths=[c['graph_path'] for c in (response.get('hits') or [])
           if (c.get('graph_path') or {}).get('edges')]
    if not paths:return None
    valid=[]
    for p in paths:
        edges=p['edges'];names=p['entities']
        ok=len(names)==len(edges)+1 and p['chunk_id'] in chunks
        for i,e in enumerate(edges):
            ok &= e['chunk_id'] in chunks and e['evidence'] in chunks[e['chunk_id']]['text']
            ok &= set([e['source'],e['target']])==set(names[i:i+2])
        valid.append(int(ok))
    return float(np.mean(valid))


def bootstrap(values: list[float]) -> dict:
    if not values:return {'mean':NOT_MEASURED,'ci95':NOT_MEASURED,'n':0}
    rng=np.random.default_rng(42)
    draws=rng.choice(values,size=(1000,len(values)),replace=True).mean(axis=1)
    return {'mean':float(np.mean(values)),'ci95':[float(x) for x in np.quantile(draws,[.025,.975])],'n':len(values)}


class JudgePacer:
    """Space every HTTP attempt, including SDK and structured-output retries."""
    def __init__(self, interval=15, clock=None, sleep=None):
        import asyncio
        self.interval=max(0, interval)
        self.clock=clock or time.monotonic
        self.sleep=sleep or asyncio.sleep
        self.lock=asyncio.Lock()
        self.next_request=0

    async def __call__(self, request):
        async with self.lock:
            delay=self.next_request-self.clock()
            if delay > 0:
                print(f'Judge pacing: waiting {delay:.1f}s',flush=True)
                await self.sleep(delay)
            self.next_request=self.clock()+self.interval

def judge_parameters(model, request_interval=None, max_tokens=None):
    """Conservative Qwen defaults for Groq's free token quota."""
    qwen=model.startswith('qwen/')
    interval=(60 if qwen else 15) if request_interval is None else request_interval
    budget=(2048 if qwen else 8192) if max_tokens is None else max_tokens
    if interval < 0 or budget < 1:
        raise ValueError('Judge interval must be nonnegative and output budget positive.')
    model_args={'max_tokens':budget,'temperature':0}
    if qwen or model.startswith('gemini-2.5-flash'):
        model_args['reasoning_effort']='none'
    return interval,model_args

def make_faithfulness(judge, batch_size=None):
    """Keep the RAGAS score formula, but bound each NLI output for small quotas."""
    from ragas.metrics.collections import Faithfulness
    from ragas.metrics.collections.faithfulness.util import NLIStatementOutput
    if batch_size is None:
        return Faithfulness(llm=judge)
    class BatchedFaithfulness(Faithfulness):
        async def _create_verdicts(self, statements, context):
            verdicts=[]
            for offset in range(0,len(statements),batch_size):
                batch=statements[offset:offset+batch_size]
                print(f'Faithfulness: checking statements {offset+1}-'
                      f'{offset+len(batch)} of {len(statements)}',flush=True)
                result=await super()._create_verdicts(batch,context)
                if len(result.statements)!=len(batch):
                    raise ValueError('Judge omitted a faithfulness verdict; score is unmeasured.')
                verdicts.extend(result.statements)
            return NLIStatementOutput(statements=verdicts)
    return BatchedFaithfulness(llm=judge)

def ragas_scores(records: list[dict], responses: list[dict], existing=None,
                 on_progress=None, request_interval=None, max_tokens=None,
                 metrics=None) -> list[dict]:
    """Optional judge, separate credentials/model family; no accidental OpenAI fallback."""
    cfg=settings()
    if not cfg.judge_api_key or not cfg.judge_model:
        raise ValueError('Set JUDGE_API_KEY and JUDGE_MODEL for --ragas')
    request_interval,model_args=judge_parameters(cfg.judge_model,request_interval,max_tokens)
    import asyncio
    import httpx
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.embeddings.base import BaseRagasEmbedding
    from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall
    retrieval=Retrieval(Store())
    class LocalEmbeddings(BaseRagasEmbedding):
        def embed_text(self,text,**kwargs):return retrieval.embed([text])[0]
        async def aembed_text(self,text,**kwargs):return await asyncio.to_thread(self.embed_text,text)
    async def score_all():
        http_client=httpx.AsyncClient(event_hooks={'request':[JudgePacer(request_interval)]})
        async with AsyncOpenAI(api_key=cfg.judge_api_key,base_url=cfg.judge_base_url,
                               timeout=cfg.llm_timeout,max_retries=2,http_client=http_client) as client:
            judge=llm_factory(cfg.judge_model,client=client,**model_args)
            faith=make_faithfulness(judge,1 if cfg.judge_model.startswith('qwen/') else None)
            relevance=AnswerRelevancy(llm=judge,embeddings=LocalEmbeddings())
            precision=ContextPrecision(llm=judge)
            recall=ContextRecall(llm=judge)
            output=[]
            for index,(record,response) in enumerate(zip(records,responses)):
                context=[c['text'] for c in (response.get('evidence') or [])]
                question=record['question'];answer=response['answer'];reference=record['gold_answer']
                jobs=[('faithfulness',lambda:faith.ascore(user_input=question,response=answer,retrieved_contexts=context)),
                      ('answer_relevancy',lambda:relevance.ascore(user_input=question,response=answer)),
                      ('llm_context_precision_with_reference',lambda:precision.ascore(user_input=question,reference=reference,retrieved_contexts=context)),
                      ('context_recall',lambda:recall.ascore(user_input=question,retrieved_contexts=context,reference=reference))]
                row=dict(existing[index]) if existing else {}
                for name,call in jobs:
                    if metrics is not None and name not in metrics:
                        continue
                    if isinstance(row.get(name),(float,int)) and math.isfinite(row[name]):
                        continue
                    print(f'Judging {record["id"]}: {name}',flush=True)
                    try:
                        result=await call()
                        value=float(result.value)
                        row[name]=value if math.isfinite(value) else None
                    except Exception as exc:
                        retrieval.store.failure('evaluation_judge',exc);row[name]=None
                    if on_progress:
                        on_progress(index, dict(row))
                    print(f'{name}: {row[name]}',flush=True)
                output.append(row)
            return output
    try:return asyncio.run(score_all())
    finally:retrieval.close()



def run(records: list[dict], options: Options, output: Path, use_ragas=False, warm_cache=False,
        allow_unreviewed=False, request_interval=0, rate_limit_retries=0, max_rate_wait=60,
        resume=False, retry_runtime_errors=False) -> dict:
    output.mkdir(parents=True,exist_ok=True)
    if retry_runtime_errors and not resume:
        raise ValueError('--retry-runtime-errors requires --resume.')
    if not settings().groq_api_key:
        raise ValueError('Configure GROQ_API_KEY before running generation/evaluation experiments.')
    if not allow_unreviewed and any(r.get('requires_manual_validation',True) for r in records):
        raise ValueError('Dataset contains unaudited labels. Complete manual audit or use --allow-unreviewed for explicitly exploratory results.')
    signature = evaluation_signature(records, options)
    state = load_progress(output, records, signature) if resume else {
        'signature': signature, 'rows': [], 'responses': [], 'events': [], 'legacy_questions': 0}
    if retry_runtime_errors:
        backup = output/f'checkpoint.before-runtime-retry-{time.time_ns()}.json'
        backup.write_text(json.dumps(state, allow_nan=False), encoding='utf-8')
    if resume:
        print(f'Resuming: {len(state["rows"])}/{len(records)} questions already saved.', flush=True)
    store=Store();retrieval=Retrieval(store)
    llm=EvaluationLLM(store, request_interval, rate_limit_retries, max_rate_wait)
    graph=Graph(store,llm)
    workflow=Workflow(store,retrieval,graph,llm,Cache(store))
    docs={d['name']:d for d in store.documents() if d.get('searchable')}
    missing=sorted({r['document'] for r in records}-set(docs))
    if missing:raise ValueError('Upload these named corpus PDFs first: '+', '.join(missing))
    for r in records:
        if docs[r['document']]['id']!=r['source_sha256']:
            raise ValueError('Corpus bytes differ from annotated edition: '+r['document'])
    all_chunks={c['chunk_id']:c for c in store.chunks()}
    rows,responses=state['rows'],state['responses']
    completed = len(rows)
    prior_events = state.get('events', [])
    start_events=time.time()
    cache_namespace = f'evaluation-{time.time_ns()}' if warm_cache else ''
    try:
        for n,record in enumerate(records,1):
            if n <= completed and not (retry_runtime_errors and
                    rows[n-1].get('failure') == 'runtime_error'):
                continue
            ids=[docs[record['document']]['id']]
            try:
                # In cache ablation both cold and repeated requests are logged; repeated response scored.
                response=workflow.query(record['question'],ids,options,cache_namespace=cache_namespace)
                cold_seconds=response['timings']['total']
                if warm_cache:response=workflow.query(record['question'],ids,options,cache_namespace=cache_namespace)
                response['cold_seconds']=cold_seconds
                metric=retrieval_metrics(response.get('hits') or [],record)
                audit=response.get('audit') or []
                entailments=sum(a['status']=='ENTAILMENT' for a in audit)
                verified=[a for a in audit if a['status']!='NOT_VERIFIED']
                citations=[cid for c in response.get('claims') or [] for cid in c['citations']]
                evidence_ids={c['chunk_id'] for c in response.get('evidence') or []}
                metric.update({'abstention_accuracy':int(response['abstained']==(record['type']=='unanswerable')),
                    'claim_support_rate':entailments/len(verified) if verified else None,
                    'citation_precision':sum(cid in evidence_ids for cid in citations)/len(citations) if citations else None,
                    'evidence_path_validity':path_validity(response,all_chunks),
                    'latency_seconds':response['timings']['total'],'cache_hit':int(response['cache_hit'])})
                failure=''
                if record['type']!='unanswerable' and not metric['hit@10']:failure='retrieval'
                elif record['type']!='unanswerable' and response['abstained']:failure='generation_or_verification'
                elif record['type']=='unanswerable' and not response['abstained']:failure='abstention'
                rows.append({'id':record['id'],'type':record['type'],'failure':failure,**metric})
                responses.append(response)
            except Exception as exc:
                store.failure('generation',exc)
                rows.append({'id':record['id'],'type':record['type'],'failure':'runtime_error','error_type':type(exc).__name__})
                responses.append({'answer':'','evidence':[],'abstained':True,'error_type':type(exc).__name__})
            if n <= completed:
                # Replace only the selected failed result, preserving dataset order.
                rows[n-1] = rows.pop()
                responses[n-1] = responses.pop()
            state['responses'] = [{'id':r['id'], **x} for r,x in zip(records,responses)]
            state['rows'] = rows
            state['events'] = prior_events + [e for e in store.events() if e['ts']>=start_events]
            save_progress(output, state)
            checkpoint(output, records, rows, responses)
            print(f'{n}/{len(records)} {record["id"]}',flush=True)
        if use_ragas:
            # Judge only answerable, successfully generated responses. Coverage is reported explicitly.
            selected=[i for i,(r,x) in enumerate(zip(records,responses)) if r['type']!='unanswerable' and not x['abstained']]
            if selected:
                scores=ragas_scores([records[i] for i in selected],[responses[i] for i in selected])
                for i,score in zip(selected,scores):
                    for key in ('faithfulness','answer_relevancy','llm_context_precision_with_reference','context_recall'):
                        value=score.get(key)
                        rows[i][key]=float(value) if isinstance(value,(int,float)) and math.isfinite(value) else None
        metric_names=sorted({key for row in rows for key,value in row.items() if isinstance(value,(float,int))})
        for name in ('faithfulness','answer_relevancy','llm_context_precision_with_reference','context_recall'):
            if name not in metric_names:metric_names.append(name)
        summary={name:bootstrap([r[name] for r in rows if isinstance(r.get(name),(float,int))]) for name in metric_names}
        summary['multi_hop']={name:bootstrap([r[name] for r in rows if r['type']=='multi-hop' and isinstance(r.get(name),(float,int))])
            for name in ('recall@10','mrr','faithfulness','evidence_path_validity')}
        summary['status']='EXPLORATORY — HUMAN LABEL AUDIT PENDING' if any(r.get('requires_manual_validation',True) for r in records) else 'AUDITED DATASET'
        summary['dataset_sha256']=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest()
        summary['options']=options.model_dump()
        summary['questions']=len(records)
        summary['runtime_errors']=sum(r['failure']=='runtime_error' for r in rows)
        summary['graph_ready_documents']=sum(d.get('stage')=='Graph ready' for d in docs.values())
        summary['resumed_questions']=completed
        summary['telemetry_missing_questions']=state.get('legacy_questions', 0)
        summary['telemetry_scope']=('Partial: earlier legacy checkpoint has no telemetry' if
            state.get('legacy_questions', 0) else 'All checkpointed evaluation sessions')
        summary['telemetry']=summarize(prior_events + [e for e in store.events() if e['ts']>=start_events])
        (output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
        (output/'responses.jsonl').write_text('\n'.join(json.dumps({'id':r['id'],**x}) for r,x in zip(records,responses))+'\n',encoding='utf-8')
        (output/'per_question.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n',encoding='utf-8')
        columns=sorted({k for r in rows for k in r})
        with (output/'metrics.csv').open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(rows)
        lines=['# Evaluation report',summary['status'],'','Page-level relevance; duplicate hits on one page count once.',
               'Citation precision measures valid retrieved citation IDs, not independent semantic correctness.',
               'Claim support rate is the application verifier’s judgment, not human ground truth.',
               'CIs use 1,000 seeded question bootstraps; correlated question pairs can make these optimistic.',
               f'Telemetry scope: {summary["telemetry_scope"]}; '
               f'{summary["telemetry_missing_questions"]} earlier questions lack event telemetry.','',
               '| Metric | Mean | 95% CI | n |','|---|---|---|---|']
        for name in metric_names:lines.append(f'| {name} | {summary[name]["mean"]} | {summary[name]["ci95"]} | {summary[name]["n"]} |')
        lines+=['','## Failure analysis','',json.dumps({x:sum(r['failure']==x for r in rows) for x in sorted({r['failure'] for r in rows if r['failure']})},indent=2),
                '', 'Pipeline failure events:', '```json',json.dumps(summary['telemetry']['failures'],indent=2),'```']
        (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        return summary
    finally:
        retrieval.close();graph.close();llm.client.close()


def download_corpus():
    target=Path('data/evaluation');target.mkdir(parents=True,exist_ok=True)
    for doc in json.loads((ROOT/'corpus.json').read_text()):
        path=target/doc['filename']
        if not path.exists():
            req=urllib.request.Request(doc['url'],headers={'User-Agent':'Mozilla/5.0 EvidenceGraph-X evaluation'})
            with urllib.request.urlopen(req,timeout=90) as response:path.write_bytes(response.read())
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=doc['sha256']:raise ValueError(f'{path}: source changed. Re-audit pages before evaluation.')
        print(f'{path}: verified SHA-256')


def ingest_corpus():
    from app.ingest import ingest
    store=Store();retrieval=Retrieval(store);llm=LLM(store);graph=Graph(store,llm)
    try:
        for doc in json.loads((ROOT/'corpus.json').read_text()):
            path=Path('data/evaluation')/doc['filename'];data=path.read_bytes();doc_id=hashlib.sha256(data).hexdigest()
            if doc_id!=doc['sha256']:raise ValueError('Source hash changed: '+str(path))
            (store.root/'uploads'/f'{doc_id}.pdf').write_bytes(data)
            store.save_doc({'id':doc_id,'name':doc['filename'],'stage':'Queued','searchable':False,'bytes':len(data)})
            ingest(doc_id,store,retrieval,graph)
            print(doc['filename'],store.document(doc_id)['stage'],flush=True)
    finally:
        retrieval.close();graph.close();llm.client.close()


def check_services():
    import httpx
    cfg=settings();store=Store();retrieval=Retrieval(store);llm=LLM(store);graph=Graph(store,llm);cache=Cache(store)
    results={}
    try:
        for name,fn in [('qdrant',lambda:retrieval.client.get_collections()),
                        ('neo4j',lambda:graph.driver.verify_connectivity() if graph.driver else 'NOT CONFIGURED'),
                        ('redis',lambda:cache.client.ping() if cache.client else 'NOT CONFIGURED')]:
            try:
                value=fn();results[name]='NOT CONFIGURED' if value=='NOT CONFIGURED' else 'CONNECTED'
            except Exception as exc:results[name]='FAILED: '+type(exc).__name__
        if cfg.groq_api_key:
            try:
                r=httpx.get(cfg.llm_base_url.rstrip('/')+'/models',headers={'Authorization':f'Bearer {cfg.groq_api_key}'},timeout=20);r.raise_for_status()
                ids={m['id'] for m in r.json()['data']}
                results['llm_models']={m:('AVAILABLE' if m in ids else 'NOT AVAILABLE') for m in [cfg.small_model,cfg.llm_model]}
            except Exception as exc:results['llm']='FAILED: '+type(exc).__name__
        else:results['llm']='NOT CONFIGURED'
        print(json.dumps(results,indent=2))
    finally:retrieval.close();graph.close();llm.client.close()


def compare_baseline(current: dict, baseline_path: str, tolerance: float) -> None:
    """Gate only measured results from the identical audited dataset and options."""
    baseline = json.loads(Path(baseline_path).read_text())
    for result in (current, baseline):
        if result.get('status') != 'AUDITED DATASET' or result.get('runtime_errors', 0):
            raise ValueError('Regression gating requires audited results without runtime errors')
    if current['dataset_sha256'] != baseline['dataset_sha256'] or current['options'] != baseline['options']:
        raise ValueError('Baseline dataset/options differ; this is not a controlled regression comparison')
    regressions = []
    for metric in ('recall@5', 'recall@10', 'mrr', 'ndcg@10'):
        actual, previous = current[metric]['mean'], baseline[metric]['mean']
        if not isinstance(actual, (int, float)) or not isinstance(previous, (int, float)):
            raise ValueError('Regression metric was not measured: ' + metric)
        if actual < previous - tolerance:
            regressions.append(metric)
    if regressions:
        raise ValueError('Measured regression exceeds tolerance: ' + ', '.join(regressions))
    print('Measured retrieval regression gate passed.')


def main():
    p=argparse.ArgumentParser();p.add_argument('--gold',default=str(ROOT/'gold_set.jsonl'));p.add_argument('--limit',type=int)
    p.add_argument('--output',default='eval/results/full');p.add_argument('--allow-unreviewed',action='store_true')
    p.add_argument('--resume',action='store_true',help='Keep checkpointed questions and run only the remainder.')
    p.add_argument('--retry-runtime-errors',action='store_true',
                   help='With --resume, rerun only saved runtime errors and unfinished questions.')
    p.add_argument('--ragas',action='store_true');p.add_argument('--download-corpus',action='store_true')
    p.add_argument('--ingest-corpus',action='store_true');p.add_argument('--check-services',action='store_true')
    p.add_argument('--request-interval',type=float,default=3,
                   help='Minimum seconds between evaluation LLM calls (default: 3).')
    p.add_argument('--rate-limit-retries',type=int,default=5,
                   help='Retries per LLM call for short rate limits (default: 5).')
    p.add_argument('--max-rate-wait',type=float,default=60,
                   help='Maximum individual quota wait in seconds (default: 60).')
    p.add_argument('--validate',action='store_true');p.add_argument('--baseline');p.add_argument('--tolerance',type=float,default=0.02);args=p.parse_args()
    if args.download_corpus:download_corpus();return
    if args.ingest_corpus:ingest_corpus();return
    if args.check_services:check_services();return
    records=dataset(args.gold)
    if args.validate:
        print(json.dumps({'count':len(records),'types':{t:sum(r['type']==t for r in records) for t in ('single-hop','multi-hop','unanswerable')},
                          'human_review_pending':sum(r.get('requires_manual_validation',True) for r in records)},indent=2));return
    if args.limit:records=records[:args.limit]
    result=run(records,Options(cache=False),Path(args.output),args.ragas,
               allow_unreviewed=args.allow_unreviewed, request_interval=args.request_interval,
               rate_limit_retries=args.rate_limit_retries, max_rate_wait=args.max_rate_wait,
               resume=args.resume, retry_runtime_errors=args.retry_runtime_errors)
    if args.baseline:compare_baseline(result,args.baseline,args.tolerance)
    print('Results:',args.output,'Status:',result['status'])

if __name__=='__main__':main()
