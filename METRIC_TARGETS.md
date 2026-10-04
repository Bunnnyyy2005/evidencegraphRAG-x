# EvidenceGraph-X metric targets

The supplied workbook contains planning targets. The observations below retain the reported results; targets require new measurements before they can be claimed as achieved. Scores use a 0–1 scale unless the metric specifies seconds, tokens, counts or memory.

Source: `EvidenceGraph-X_Target_Metrics.xlsx`, supplied on 5 October 2026. Its observed values are rounded from the 4 October project report. Machine-readable targets: [eval/metric_targets.json](eval/metric_targets.json).

Sample sizes and scopes differ. RAGAS observations use only 1–3 generated answers; the workbook targets require at least 50 judged questions. A numeric threshold being met in a small sample does not establish validated performance. Target latency assumes architecture changes that have not been benchmarked. Failure targets refer to a full 120-question run.

Abstention accuracy must be checked across answerable and unanswerable questions. Reviewing only the 24 unanswerable questions measures a narrower abstention behavior. No dollar-cost or cost-reduction target was supplied; both remain unmeasured.

## Retrieval

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Recall@5 | 0.6354 | 0.8 | higher | 96 answerable Qs; provisional page labels |
| Recall@10 | 0.7604 | 0.9 | higher | 96 answerable Qs |
| Hit@5 | 0.7604 | 0.88 | higher | 96 answerable Qs |
| Hit@10 | 0.875 | 0.95 | higher | 96 answerable Qs |
| MRR | 0.5269 | 0.74 | higher | 96 answerable Qs |
| nDCG@10 | 0.5519 | 0.76 | higher | 96 answerable Qs |

## Answer quality

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Abstention accuracy | 0.4828 | 0.85 | higher | Current from earlier n=116 run; re-measure on all 24 unanswerable Qs |
| Citation-ID precision | 1 | 1 | higher | Keep at 100% (ID validity) |
| Verifier claim-support rate | 0.8667 | 0.92 | higher | Current n=40 |
| RAGAS faithfulness | 1 | 0.92 | higher | Current n=1 (not meaningful); target is on n>=50 |
| RAGAS answer relevancy | 0.9131 | 0.9 | higher | Current n=3; target is on n>=50 |
| RAGAS context precision | 0.6708 | 0.75 | higher | Current n=3; target is on n>=50 |
| RAGAS context recall | 1 | 0.9 | higher | Current n=3; target is on n>=50 |

## Latency (end-to-end)

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Latency mean (s) | 23.77 | 4.5 | lower | 120 records |
| Latency P50 (s) | 13.77 | 3.5 | lower | Fast path / cache-aware |
| Latency P95 (s) | 48.79 | 8 | lower | Needs fewer LLM calls + retry-free runs |
| Deployed multi-hop graph query, total (s) | 23.64 | 7 | lower | One smoke test; 10 LLM calls |
| Deployed multi-hop graph stage (s) | 3.03 | 1.5 | lower | Same smoke test |
| Cache hit time (s) | 0.066 | 0.05 | lower | Already good; keep under 0.1 s |

## Pipeline stage

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Retrieval P50 (s) | 2.09 | 0.5 | lower | 77 stage events |
| Retrieval P95 (s) | 6.51 | 1.2 | lower | 77 stage events |
| Graph P50 (s) | 6.17 | 1.5 | lower | 17 events |
| Graph P95 (s) | 17.75 | 4 | lower | 17 events |
| Rerank P50 (s) | 0.139 | 0.14 | lower | Already good; hold steady |
| Rerank P95 (s) | 0.316 | 0.3 | lower | Already good |
| Generation P50 (s) | 4.45 | 1.5 | lower | 5 events |
| Generation P95 (s) | 4.71 | 2.5 | lower | 5 events |
| Verification P50 (s) | 10.57 | 2 | lower | 5 events; run in background / on demand |
| Verification P95 (s) | 12.99 | 4 | lower | 5 events |

## Cache

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Cache hit rate | 0.3333 | 0.3 | higher | Current is 1 of 3 queries (not meaningful); target on a realistic repeat workload |

## Cost / tokens

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Input tokens per query | 3904 | 2800 | lower | Current from graph smoke test (one fresh query) |
| Output tokens per query | 2754 | 600 | lower | Current from graph smoke test |
| LLM calls per query | 10 | 4 | lower | Current from graph smoke test |
| Retries recorded | 0 | 0 | lower | Partial telemetry |

## Telemetry

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Usage records fully complete (share) | 0.666667 | 1 | higher | 80 of 120 records complete |
| Questions with telemetry (share) | 0.616667 | 1 | higher | First 46 of 120 lack telemetry |

## Reliability

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Rate-limit events: evidence grading | 138 | 5 | lower | Events, not distinct failed Qs |
| Rate-limit events: generation | 61 | 3 | lower | Events |
| Rate-limit events: graph traversal | 28 | 3 | lower | Events |
| Missing-SciPy errors | 1 | 0 | lower | Fixed after the run; keep at 0 |
| Rate-limit events: retrieval | 14 | 1 | lower | Events |
| Failure events: verification | 1 | 0 | lower | Events |
| Runtime errors in final summary | 0 | 0 | lower | Already 0 after retries |

## Resources

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Memory after query (MiB) | 437 | 350 | lower | Local Docker; 512 MB host had an OOM failure |

## Eval coverage

| Metric | Recorded observation | Target (unverified) | Better when | Scope |
|---|---:|---:|---|---|
| Questions with RAGAS judging (n) | 3 | 50 | higher | 1 to 3 today |
| Questions with citation-ID check (n) | 36 | 96 | higher | All answerable Qs |
| Questions with verifier check (n) | 40 | 96 | higher | All answerable Qs |
| Human-audited labels (n) | 0 | 100 | higher | Audit is pending |

## Measure before publishing

Keep saved responses, checkpoint files and telemetry as recorded. Use reviewed labels, matched workloads and complete token records for final comparisons. For controlled variants, use the procedure in [CONTROLLED-EVALUATION.md](CONTROLLED-EVALUATION.md). A target is a goal, not an evaluator output.

## Separate user-reported run

The user reports obtaining the spreadsheet values with separate codes. [USER_REPORTED_RESULTS.md](USER_REPORTED_RESULTS.md) records all 48 values with unverified status and unspecified run scope. Historical validation records, logs and test counts are preserved.
