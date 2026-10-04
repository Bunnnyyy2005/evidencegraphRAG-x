"""Summarize measured events; missing observations stay NOT MEASURED."""
import json
import argparse
from pathlib import Path
import numpy as np
from app.utils import Store

NOT_MEASURED = 'NOT MEASURED'

def percentiles(values: list[float]) -> dict:
    return {'count':len(values),'p50':float(np.percentile(values,50)) if values else NOT_MEASURED,
            'p95':float(np.percentile(values,95)) if values else NOT_MEASURED}

def summarize(events: list[dict]) -> dict:
    queries = [e for e in events if e['category']=='query']
    result = {'query_count':len(queries),'cache_hit_rate':sum(e['cache_hit'] for e in queries)/len(queries) if queries else NOT_MEASURED}
    result['seconds'] = {name:percentiles([e['timings'][name] for e in queries if name in e['timings']])
        for name in ('retrieve','graph_retrieval','reranking','generate','verify','total')}
    for stage in ('stage1_seconds','stage2_seconds'):
        result['seconds'][stage] = percentiles([e[stage] for e in events if stage in e])
    result['seconds']['cache_hit'] = percentiles([e['timings']['total'] for e in queries if e['cache_hit']])
    result['seconds']['cache_miss'] = percentiles([e['timings']['total'] for e in queries if not e['cache_hit']])
    usage = [e['usage'] for e in queries]
    result['llm_calls'] = sum(u['llm_calls'] for u in usage)
    result['llm_retries'] = sum(u['llm_retries'] for u in usage)
    result['tokens_per_query'] = (sum(u['prompt_tokens']+u['completion_tokens'] for u in usage)/len(usage)
        if usage and all(u['tokens_available'] for u in usage) else NOT_MEASURED)
    result['estimated_paid_usd'] = (sum(u['estimated_paid_usd'] for u in usage)
        if usage and all(u['estimated_paid_usd'] is not None for u in usage) else NOT_MEASURED)
    categories = ['parsing','chunking','entity extraction','relation extraction','retrieval','graph traversal','reranking','generation','citation','verification']
    result['failures'] = {stage:sum(e.get('stage')==stage for e in events if e['category']=='failure') for stage in categories}
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='eval/results/latency.json');args=parser.parse_args()
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    output=summarize(Store().events());path.write_text(json.dumps(output,indent=2));print(json.dumps(output,indent=2))
