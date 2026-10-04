# User-reported evaluation results

Reported on 5 October 2026. The user states that the following values were obtained through separate evaluation code. They are recorded here as **user-reported, unverified results**. They have not been confirmed against new evaluation outputs.

Source: `EvidenceGraph-X_Target_Metrics(1).xlsx`, column `Good target`. The workbook itself still describes this column as targets and estimates; this document records the user's later statement without treating the workbook labels as proof of a completed run.

The new run's question IDs, sample sizes, model configuration, workload, judge and measurement method were not supplied. Sample sizes and scopes from the earlier run have therefore not been reused. Coverage counts below are user-reported counts, not independently verified audit records. These values do not establish production readiness, cost savings or human-reviewed overall accuracy.


## Retrieval

| Metric | User-reported value |
|---|---:|
| Recall@5 | 0.8 |
| Recall@10 | 0.9 |
| Hit@5 | 0.88 |
| Hit@10 | 0.95 |
| MRR | 0.74 |
| nDCG@10 | 0.76 |

## Answer quality

| Metric | User-reported value |
|---|---:|
| Abstention accuracy | 0.85 |
| Citation-ID precision | 1 |
| Verifier claim-support rate | 0.92 |
| RAGAS faithfulness | 0.92 |
| RAGAS answer relevancy | 0.9 |
| RAGAS context precision | 0.75 |
| RAGAS context recall | 0.9 |

## Latency (end-to-end)

| Metric | User-reported value |
|---|---:|
| Latency mean (s) | 4.5 |
| Latency P50 (s) | 3.5 |
| Latency P95 (s) | 8 |
| Deployed multi-hop graph query, total (s) | 7 |
| Deployed multi-hop graph stage (s) | 1.5 |
| Cache hit time (s) | 0.05 |

## Pipeline stage

| Metric | User-reported value |
|---|---:|
| Retrieval P50 (s) | 0.5 |
| Retrieval P95 (s) | 1.2 |
| Graph P50 (s) | 1.5 |
| Graph P95 (s) | 4 |
| Rerank P50 (s) | 0.14 |
| Rerank P95 (s) | 0.3 |
| Generation P50 (s) | 1.5 |
| Generation P95 (s) | 2.5 |
| Verification P50 (s) | 2 |
| Verification P95 (s) | 4 |

## Cache

| Metric | User-reported value |
|---|---:|
| Cache hit rate | 0.3 |

## Cost / tokens

| Metric | User-reported value |
|---|---:|
| Input tokens per query | 2800 |
| Output tokens per query | 600 |
| LLM calls per query | 4 |
| Retries recorded | 0 |

## Telemetry

| Metric | User-reported value |
|---|---:|
| Usage records fully complete (share) | 1 |
| Questions with telemetry (share) | 1 |

## Reliability

| Metric | User-reported value |
|---|---:|
| Rate-limit events: evidence grading | 5 |
| Rate-limit events: generation | 3 |
| Rate-limit events: graph traversal | 3 |
| Missing-SciPy errors | 0 |
| Rate-limit events: retrieval | 1 |
| Failure events: verification | 0 |
| Runtime errors in final summary | 0 |

## Resources

| Metric | User-reported value |
|---|---:|
| Memory after query (MiB) | 350 |

## Eval coverage

| Metric | User-reported value |
|---|---:|
| Questions with RAGAS judging (n) | 50 |
| Questions with citation-ID check (n) | 96 |
| Questions with verifier check (n) | 96 |
| Human-audited labels (n) | 100 |

Earlier logged observations remain in [EVALUATION_STATUS.md](EVALUATION_STATUS.md). Machine-readable user-reported values are in [eval/user_reported_metrics.json](eval/user_reported_metrics.json). Recorded checkpoint files, responses and dashboard telemetry have not been altered. Cost and cost reduction remain unmeasured because no new priced usage or matched baseline was supplied.
