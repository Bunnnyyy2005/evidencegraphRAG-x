# EvidenceGraph-X evaluation status

## Latest user-reported run

The user reports a separate run on 5 October 2026. Its 48 supplied values are in [USER_REPORTED_RESULTS.md](USER_REPORTED_RESULTS.md), labeled user-reported and unverified. New run logs and scope were not supplied. The following observations are from the earlier logged run and have not been overwritten.

Recorded: 2026-10-04. Source: outputs provided by the user in this conversation. The new controlled pilot's final results have not been provided. All results remain exploratory; human label audit is pending.

## Observed results

| Metric | Observed value | Coverage / limitation |
|---|---:|---|
| Retrieval Recall@5 | 0.6354 | 96 questions in earlier exploratory report; rate-limit-affected run, unaudited labels |
| Retrieval Recall@10 | 0.7604 | Same 96 questions |
| Retrieval Hit@5 | 0.7604 | Same 96 questions |
| Retrieval Hit@10 | 0.8750 | Same 96 questions |
| MRR | 0.5269 | Same 96 questions |
| nDCG@10 | 0.5519 | Same 96 questions |
| Abstention accuracy | 0.4828 | Earlier report, n=116, before four runtime-error repairs; not a clean final result |
| Citation-ID precision | 1.0000 | n=36; valid retrieved citation IDs, not semantic support |
| Application verifier claim-support rate | 0.8667 | n=40; verifier judgment, not human ground truth |
| RAGAS answer relevancy | 0.9131 | Qwen judge, 3 successfully generated HTTP answers |
| RAGAS context precision with reference | 0.6708 | Same 3 answers |
| RAGAS context recall | 1.0000 | Same 3 answers |
| RAGAS faithfulness | 1.0000 | Qwen judge, only 1 answer, batched statement verification |

RAGAS sampling covers successfully generated answerable responses only; it excludes failed/abstained answers and does not establish overall system accuracy. The full run had many provider quota failures. No single overall RAG accuracy percentage is supported.

## Metrics still pending

| Metric | Status |
|---|---|
| Human-reviewed answer correctness / accuracy | NOT MEASURED |
| Answer completeness | NOT MEASURED |
| Semantic citation correctness | NOT MEASURED |
| Faithfulness on a representative sample | PENDING |
| Answer relevancy on a representative sample | PENDING |
| Context precision and recall on a representative sample | PENDING |
| Clean-run abstention accuracy | PENDING |
| Retrieval metrics on human-reviewed labels | PENDING |
| Graph evidence-path validity | NOT MEASURED |
| Paired accuracy improvement from reranking | PENDING controlled pilot |
| Paired accuracy improvement from graph retrieval | NOT MEASURED |

## Performance and cost

| Metric | Observed value | Limitation |
|---|---:|---|
| Full-run mean latency | 23.77 s | 120 records; includes rate-limit-affected responses |
| Full-run P50 / P95 latency | 13.77 / 48.79 s | Same 120 records |
| One deployed multi-hop query latency | 23.64 s | One smoke test; graph retrieval executed in 3.03 s |
| One cached-query latency | 0.066 s | One smoke test, not a workload benchmark |
| Observed input / output tokens | 189,636 / 107,378 | 120 usage records; only 80 marked complete |
| Estimated cost | NOT MEASURED | Earlier output has no configured per-model pricing estimate |
| Cost reduction | NOT MEASURED | Requires matched baseline, complete usage and quality comparison |

Deployment and graph execution smoke tests succeeded. This establishes that tested features execute; it does not establish production readiness or maximum accuracy. Missing values have not been replaced with invented scores.

## Planned thresholds

The 48 spreadsheet targets are documented alongside their observations in [METRIC_TARGETS.md](METRIC_TARGETS.md). These values are unverified goals. They do not replace the measurements above or establish completion of the pending evaluations.
