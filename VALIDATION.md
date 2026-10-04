# Delivered validation record

Checked on 2026-10-03 using Python 3.12.14 on Linux x86-64. This is implementation validation, not a benchmark-results claim.

| Check | Observed result | Scope |
|---|---|---|
| Core dependency installation | Successful | Pinned requirements installed into an isolated Python environment. |
| Optional RAGAS installation/imports | Successful | Current metric collections and LLM/embedding adapter APIs import with Community 0.4.1 pinned. No judge calls made. |
| Optional Docling CPU installation | Successful | Torch 2.14.1+cpu; `torch.version.cuda` is `None`. Dependency resolver selected no CUDA packages. |
| Docling real PDF smoke | Successful | A generated text PDF was parsed by **Docling**, not its fallback; one evidence block returned. |
| Unit/API tests | 24 passed | Metadata/hierarchy, table unit, real PDF parsing, local Qdrant API, sparse isolation, RRF, graph query parameters, routing/retry/abstention, verification failures, cache scope, dataset distribution, token access control and configuration checks. LLM-boundary doubles are used where marked in test code. |
| Real CPU retrieval smoke | Successful | Generated text PDF → PyMuPDF → BGE-small FastEmbed → local Qdrant and BM25 → RRF → FlashRank. No fabricated vectors or reranker scores in this smoke. |
| Python compilation | Successful | Backend and evaluator source compiled. |
| Dependency consistency | Successful | `pip check` reported no broken requirements with core and optional packages installed. |
| JavaScript syntax | Successful | `node --check static/app.js`. |
| Dataset structural validation | Successful | 120 records: 48 single-hop, 48 multi-hop, 24 unanswerable; **120 labels still require human review**. |
| Local service check | Successful | Local Qdrant connected; Neo4j, Redis and Groq were explicitly **NOT CONFIGURED**. |
| Browser visual/interaction checks | NOT COMPLETED | Browser binary was absent; Playwright download returned truncated archives. No visual success is claimed. |
| Live Groq generation/verification | NOT MEASURED | No user API credentials supplied. Deterministic boundary tests do not establish model quality. |
| Live Qdrant Cloud / Neo4j Aura / Upstash | NOT TESTED | APIs/configuration implemented; actual account connectivity requires credentials. |
| Docker build/run | NOT TESTED HERE | Docker executable is unavailable in the authoring environment. The supplied workflow includes an actual Docker build, and setup.md has local commands. |
| OCI ARM64 deployment | NOT DEPLOYED | Deployment files and current official free-resource instructions are supplied; no VM/account resources were created. Validate ARM wheels and the build on your VM. |
| Corpus benchmark / ablations / RAGAS scores | NOT MEASURED | Scripts are complete; full corpus/provider experiments have not run. No target or historical baseline is substituted for results. |
| Corpus latency/cache/cost/graph improvement | NOT MEASURED | A small retrieval smoke is not a full-system performance benchmark. |

## Reproduce checks

From the repository root in the activated environment:

```powershell
python -m pip install -r requirements.txt
python -m pip check
pytest
python -m compileall -q app eval
python -m eval.evaluate --validate
python -m eval.evaluate --check-services
```

Install optional tooling using its separate requirements file before testing its integrations. Full corpus evaluation, ablation, audit and deployment commands are in setup.md. Windows execution, live managed services and public deployment must be tested in the intended environment before making those portfolio claims.

## Target values for future measurements

See [METRIC_TARGETS.md](METRIC_TARGETS.md) for all 48 supplied goals and their recorded observations. These are planning inputs, not test outcomes. Existing validation records and evaluator outputs retain their measured values.

## Separate user-reported run

The user reports obtaining the spreadsheet values with separate codes. [USER_REPORTED_RESULTS.md](USER_REPORTED_RESULTS.md) records all 48 values with unverified status and unspecified run scope. Historical validation records, logs and test counts are preserved.
