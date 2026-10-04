"""Same dataset, genuine feature switches, separate outputs; no target numbers."""
import argparse
import csv
import json
from pathlib import Path
from app.workflow import Options
from .evaluate import dataset, run

VARIANTS={
 '01_dense':dict(mode='dense',contextual=False,reranker=False,graph=False,crag=False,verifier=False,cache=False,transforms=False),
 '02_sparse':dict(mode='sparse',contextual=False,reranker=False,graph=False,crag=False,verifier=False,cache=False,transforms=False),
 '03_hybrid':dict(contextual=False,reranker=False,graph=False,crag=False,verifier=False,cache=False,transforms=False),
 '04_contextual':dict(reranker=False,graph=False,crag=False,verifier=False,cache=False,transforms=False),
 '05_reranker':dict(graph=False,crag=False,verifier=False,cache=False,transforms=False),
 '06_graph':dict(crag=False,verifier=False,cache=False,transforms=False),
 '07_crag':dict(verifier=False,cache=False,transforms=False),
 '08_full':dict()}

def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int);p.add_argument('--allow-unreviewed',action='store_true')
 p.add_argument('--ragas',action='store_true');p.add_argument('--graph-only',action='store_true');args=p.parse_args()
 records=dataset();records=[r for r in records if r['type']=='multi-hop'] if args.graph_only else records
 if args.limit:records=records[:args.limit]
 root=Path('eval/results/graph-benchmark' if args.graph_only else 'eval/results/ablation');root.mkdir(parents=True,exist_ok=True)
 variants={name:opts for name,opts in VARIANTS.items() if not args.graph_only or name in ('01_dense','03_hybrid','06_graph')}
 if args.graph_only:
  # Isolate the graph contribution: use identical raw chunks, no reranking or query transforms.
  variants['06_graph']={**variants['03_hybrid'],'graph':True}
 rows=[]
 for name,opts in variants.items():
  summary=run(records,Options(**opts),root/name,args.ragas,warm_cache=name=='08_full',allow_unreviewed=args.allow_unreviewed)
  row={'variant':name,'status':summary['status'],'runtime_errors':summary['runtime_errors']}
  for metric in ('recall@5','recall@10','mrr','ndcg@10','faithfulness','evidence_path_validity','latency_seconds','cache_hit'):
   row[metric]=summary.get(metric,{}).get('mean','NOT MEASURED')
  rows.append(row)
 (root/'comparison.json').write_text(json.dumps(rows,indent=2))
 with (root/'comparison.csv').open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 keys=list(rows[0]);lines=['# Ablation comparison','','Full variant enables transforms as well as verification/cache; use graph-only for a controlled graph comparison.',
  'Unavailable services are reported in run summaries; a graph variant without Neo4j is not evidence of graph quality.','',
  '| '+' | '.join(keys)+' |','| '+' | '.join('---' for _ in keys)+' |']
 lines+=['| '+' | '.join(str(r[k]) for k in keys)+' |' for r in rows]
 (root/'report.md').write_text('\n'.join(lines)+'\n');print(root/'report.md')

if __name__=='__main__':main()
