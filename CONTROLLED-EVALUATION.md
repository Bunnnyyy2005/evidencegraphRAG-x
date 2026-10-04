# Controlled evaluation pilot

Extract this ZIP into the project root. It adds eval/controlled.py and tests/test_controlled.py; existing app behavior is unchanged.

## First step: prepare without API calls

```powershell
python -u -m eval.controlled --prepare
```

This selects six deterministic questions: two single-hop, two multi-hop, two unanswerable, spread across documents. It writes eval/results/controlled_pilot/selected.jsonl. Review question, reference answer and cited physical PDF pages. Correct labels before running. Set requires_manual_validation=false only after actual review. Do not tune on the final held-out evaluation set.

## Run after review

```powershell
python -u -m eval.controlled --request-interval 15
```

If labels are not reviewed yet, --allow-unreviewed explicitly permits exploratory results. It does not establish accuracy. Repeat the exact command after an interruption to resume. Do not run dashboard queries or graph extraction concurrently with this experiment. The interval reduces bursts but cannot guarantee staying below token or daily limits. There is no account/key rotation.

Variants use identical selected questions, documents and models, with cache off:
- hybrid: contextual hybrid retrieval, query transforms, corrective retrieval and verification; reranker off, graph off.
- reranked: identical, but reranker on.
- graph (opt-in): identical to reranked, but graph on. Every selected document must be Graph ready. Existing assignment.pdf is not in the built-in gold dataset; do not substitute unreviewed invented labels or claim that its graph proves corpus graph readiness.

To add graph after preparing a fully indexed, reviewed dataset, use a fresh output folder with --dataset PATH --prepare, then --variants hybrid reranked graph. Changing corpus revision, settings, labels or pacing requires a fresh output folder. No ingestion is triggered by this tool.

## Outputs

comparison.json contains retrieval/abstention metrics, mean/P50/P95 latency, token completeness, failures and estimated inference cost. Each variant has responses.jsonl, checkpoint.json, report.md and answer_review.csv. Fill the review CSV against the original PDFs: 1=fully correct/supported, 0=incorrect/unsupported; leave blank if not reviewed. This pilot does not turn verifier verdicts into human accuracy.

Latency includes quota pacing and retries, and sequential variant order can introduce warm-up/time-of-day effects. It is evaluation elapsed time, not an unbiased deployment speed benchmark. Use repeated, counterbalanced runs for final latency claims.

Cost uses configured per-model prices, or GPT-OSS Groq defaults checked on 2026-10-04 at https://console.groq.com/docs/models: 20B input/output $0.075/$0.30 per million; 120B $0.15/$0.60. This is a list-price inference estimate, not a bill; hosting, ingestion, graph construction and judges are excluded. Missing usage yields null cost, not zero. Recheck prices for later runs.

Failures stop progression to the next variant after the current variant finishes; they remain visible. A completed run with failures is not a clean comparison. Resuming preserves failed responses too: fix the cause and use a NEW output folder for a clean rerun. Never erase failures to inflate scores.

## Next experiments

After the pilot and human review, use the same reviewed questions to compare graph on/off when graphs are complete. Then measure exact-cache cold/repeat pairs separately, counting only actual hits. Compare total matched-workload cost using 100*(baseline-candidate)/baseline only when costs are complete and baseline > 0; report quality alongside any saving. Expand to a held-out sample after changes are selected. Six pilot questions cannot establish best accuracy.

Candidate architecture to assess: document-scoped hybrid retrieval -> reranking -> bounded graph expansion for relationship questions -> evidence grading -> cited generation -> claim checks / abstention. Keep each feature only if paired measurements justify its accuracy/latency/cost tradeoff. No architecture can promise maximum accuracy before testing.

## Current evaluation results

The latest obtained-metrics workbook is transcribed in [EVALUATION_STATUS.md](EVALUATION_STATUS.md) and [eval/obtained_metrics.json](eval/obtained_metrics.json). It records retrieval, RAGAS, timing, cache, usage, reliability, memory and coverage metrics. Historical implementation checks and test counts in this document refer to their original validation date; the new benchmark does not alter them. Dollar cost and paired feature gains remain pending.
