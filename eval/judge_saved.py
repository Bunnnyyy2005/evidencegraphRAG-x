"""Judge saved answers with per-metric checkpoints; never run generation."""
import argparse
import hashlib
import json
from pathlib import Path
from app.config import settings
from .evaluate import dataset, ragas_scores, bootstrap, judge_parameters

METRICS=('faithfulness','answer_relevancy','llm_context_precision_with_reference','context_recall')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',default='eval/results/exploratory_full')
    parser.add_argument('--output',default='eval/results/ragas_saved')
    parser.add_argument('--limit',type=int,default=1)
    parser.add_argument('--request-interval',type=float)
    parser.add_argument('--max-tokens',type=int)
    parser.add_argument('--metrics',nargs='+',choices=METRICS,
                        help='Judge only selected metrics, without calling the others.')
    args=parser.parse_args()
    if args.limit < 1: raise ValueError('--limit must be positive.')
    source=Path(args.input)/'responses.jsonl'
    records=dataset()
    answers={r['id']:r for r in map(json.loads,source.read_text(encoding='utf-8').splitlines())}
    selected=[r for r in records if r['id'] in answers and r['type']!='unanswerable'
              and not answers[r['id']].get('abstained',True)][:args.limit]
    if not selected: raise ValueError('No successfully generated answerable responses to judge.')
    cfg=settings()
    interval,model_args=judge_parameters(cfg.judge_model,args.request_interval,args.max_tokens)
    identity={'answers_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'records':records,'judge_model':cfg.judge_model,'judge_base_url':cfg.judge_base_url,
              'embedding_model':cfg.embedding_model,'judge_max_tokens':model_args['max_tokens'],
              'judge_reasoning':model_args.get('reasoning_effort','default')}
    if cfg.judge_model.startswith('qwen/'):
        identity['faithfulness_verdict_batch_size']=1
    signature=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    path=output/'checkpoint.json'
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {
        'signature':signature,'scores':{},'judge_model':cfg.judge_model}
    if state['signature']!=signature:
        raise ValueError('Saved answers, dataset or judge configuration changed. Use a new --output folder.')
    def persist(index,row):
        state['scores'][selected[index]['id']]=row
        temp=output/'checkpoint.json.tmp'
        temp.write_text(json.dumps(state,indent=2,allow_nan=False),encoding='utf-8')
        temp.replace(path)
    print(f'Judging {len(selected)} saved answer(s); completed metrics are reused.',flush=True)
    print(f'Judge: {cfg.judge_model}; interval: {interval}s; output budget: '
          f'{model_args["max_tokens"]} tokens',flush=True)
    scores=ragas_scores(selected,[answers[r['id']] for r in selected],
        existing=[state['scores'].get(r['id'],{}) for r in selected],on_progress=persist,
        request_interval=interval,max_tokens=model_args['max_tokens'],metrics=args.metrics)
    names=args.metrics or METRICS
    summary={name:bootstrap([s[name] for s in scores if isinstance(s.get(name),(float,int))])
             for name in names}
    summary.update(judge_model=cfg.judge_model,questions_selected=len(selected),
        metrics_requested=list(names),
        judge_request_interval=interval,judge_max_tokens=model_args['max_tokens'],
        faithfulness_verdict_batch_size=1 if cfg.judge_model.startswith('qwen/') else None,
        judge_cost_usd='NOT MEASURED',
        eligible_saved_answers=sum(r['id'] in answers and r['type']!='unanswerable'
            and not answers[r['id']].get('abstained',True) for r in records),
        coverage='Successfully generated answerable responses only',
        status='EXPLORATORY — HUMAN LABEL AUDIT PENDING' if any(
            r.get('requires_manual_validation',True) for r in selected) else 'AUDITED DATASET')
    (output/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)
    print(f'Results: {output}. Run the same command to retry only missing metrics.',flush=True)

if __name__=='__main__':main()
