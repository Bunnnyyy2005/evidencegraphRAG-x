# EvidenceGraph-X evaluation results

Results documented on 5 October 2026 from `EvidenceGraph-X_Obtained_Metrics.xlsx`. The tables reproduce the workbook’s Obtained column and supplied evaluation scopes. Scores and shares use a 0–1 scale. Timings use seconds, memory uses MiB and event counts are counts rather than distinct failed questions.

## Evaluation coverage

The workbook reports a 120-question run, retrieval measurements over 96 answerable questions, abstention measurements over 24 unanswerable questions, 50 RAGAS-judged questions, 96 citation-ID checks, 96 verifier checks and 100 human-audited labels. This does not imply that all 120 labels were audited.

## Retrieval

| Metric | Obtained value | Scope |
|---|---:|---|
| Recall@5 | 0.7934 | 96 answerable questions |
| Recall@10 | 0.8925 | 96 answerable questions |
| Hit@5 | 0.8774 | 96 answerable questions |
| Hit@10 | 0.9431 | 96 answerable questions |
| MRR | 0.727 | 96 answerable questions |
| nDCG@10 | 0.757 | 96 answerable questions |

## Answer quality

| Metric | Obtained value | Scope |
|---|---:|---|
| Abstention accuracy | 0.8473 | All 24 unanswerable questions |
| Citation-ID precision | 0.9942 | All answerable questions (ID validity) |
| Verifier claim-support rate | 0.9226 | All answerable questions |
| RAGAS faithfulness | 0.903 | 50+ judged questions |
| RAGAS answer relevancy | 0.884 | 50+ judged questions |
| RAGAS context precision | 0.765 | 50+ judged questions |
| RAGAS context recall | 0.893 | 50+ judged questions |

## Latency (end-to-end)

| Metric | Obtained value | Scope |
|---|---:|---|
| Latency mean (s) | 4.93 | 120-question run |
| Latency P50 (s) | 3.57 | Per-stage timing |
| Latency P95 (s) | 8.15 | Per-stage timing |
| Deployed multi-hop graph query, total (s) | 6.55 | Multi-hop query on the deployed app |
| Deployed multi-hop graph stage (s) | 1.39 | Graph stage of the same query |
| Cache hit time (s) | 0.055 | Exact-cache hit |

## Pipeline stage

| Metric | Obtained value | Scope |
|---|---:|---|
| Retrieval P50 (s) | 0.503 | Per-stage timing |
| Retrieval P95 (s) | 1.3 | Per-stage timing |
| Graph P50 (s) | 1.41 | Per-stage timing |
| Graph P95 (s) | 3.94 | Per-stage timing |
| Rerank P50 (s) | 0.129 | Per-stage timing |
| Rerank P95 (s) | 0.283 | Per-stage timing |
| Generation P50 (s) | 1.57 | Per-stage timing |
| Generation P95 (s) | 2.67 | Per-stage timing |
| Verification P50 (s) | 2.05 | Per-stage timing |
| Verification P95 (s) | 4.12 | Per-stage timing |

## Cache

| Metric | Obtained value | Scope |
|---|---:|---|
| Cache hit rate | 0.2928 | Realistic repeat-query workload |

## Cost / tokens

| Metric | Obtained value | Scope |
|---|---:|---|
| Input tokens per query | 2799.36 | Per fresh query |
| Output tokens per query | 599.43 | Per fresh query |
| LLM calls per query | 4.1 | Per fresh query |
| Retries recorded | 0 | 120-question run |

## Telemetry

| Metric | Obtained value | Scope |
|---|---:|---|
| Usage records fully complete (share) | 0.9969 | All usage records |
| Questions with telemetry (share) | 0.993 | All questions |

## Reliability

| Metric | Obtained value | Scope |
|---|---:|---|
| Rate-limit events: evidence grading | 5 | 120-question run (event count) |
| Rate-limit events: generation | 3 | 120-question run (event count) |
| Rate-limit events: graph traversal | 3 | 120-question run (event count) |
| Missing-SciPy errors | 0 | 120-question run (event count) |
| Rate-limit events: retrieval | 1 | 120-question run (event count) |
| Failure events: verification | 0 | 120-question run (event count) |
| Runtime errors in final summary | 0 | 120-question run (event count) |

## Resources

| Metric | Obtained value | Scope |
|---|---:|---|
| Memory after query (MiB) | 349.7 | After a query, 512 MB host |

## Eval coverage

| Metric | Obtained value | Scope |
|---|---:|---|
| Questions with RAGAS judging (n) | 50 | Sample size |
| Questions with citation-ID check (n) | 96 | Sample size |
| Questions with verifier check (n) | 96 | Sample size |
| Human-audited labels (n) | 100 | Sample size |

## Definitions and remaining measurements

Abstention is reported for the unanswerable subset; it is not overall answer correctness. Citation-ID precision measures valid evidence IDs, and verifier claim support reflects the application verifier. Human-audited label coverage is not a measured human answer-correctness score.

The workbook labels latency P50/P95 as per-stage timing. Their exact aggregation, run configuration, judge identity, confidence intervals and per-question records are not specified, so no additional claims about them are derived here. Record-level denominators and averaging methods for completeness shares are also unspecified.

Dollar cost, cost reduction, semantic citation correctness, answer completeness, graph evidence-path validity and paired graph/reranking accuracy gains are not included in this workbook and remain pending. Token averages do not by themselves establish dollar savings.

Machine-readable transcription: [eval/obtained_metrics.json](eval/obtained_metrics.json). Runtime logs, saved responses, dataset audit flags and evaluator calculations remain unchanged.
