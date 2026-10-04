# FINAL PROJECT TREE

40 purpose-bearing files; model caches, PDFs, secrets and generated results are excluded.

```text
evidencegraph-x/
    .dockerignore
    .env.example
    .github/workflows/eval.yml
    .gitignore
    Dockerfile
    MANIFEST.md
    README.md
    VALIDATION.md
    app/__init__.py
    app/cache.py
    app/config.py
    app/graph.py
    app/ingest.py
    app/main.py
    app/retrieval.py
    app/utils.py
    app/verification.py
    app/workflow.py
    data/README.md
    deploy/Caddyfile
    deploy/compose.yml
    docker-compose.yml
    eval/DATASET.md
    eval/__init__.py
    eval/ablation.py
    eval/corpus.json
    eval/evaluate.py
    eval/gold_set.jsonl
    eval/latency.py
    eval/manual_audit.csv
    pytest.ini
    requirements-docling.txt
    requirements-eval.txt
    requirements-optional.txt
    requirements.txt
    setup.md
    static/app.js
    static/index.html
    static/styles.css
    tests/test_core.py
```

| File | Purpose | Dependencies | How it is used |
|---|---|---|---|
| `.dockerignore` | Exclude secrets/data from Docker build context | Docker | Applied during image build |
| `.env.example` | Complete non-secret configuration template | Settings | Copy to .env and configure |
| `.github/workflows/eval.yml` | Tests/build, optional benchmark and measured baseline gate | GitHub Actions, optional secrets/variable | Runs on pushes/PRs or manual dispatch |
| `.gitignore` | Exclude credentials and runtime artifacts | Git | Applied automatically by Git |
| `Dockerfile` | Non-root Python app image and health check | Docker, requirements.txt | docker build -t evidencegraph-x . |
| `MANIFEST.md` | Exact project tree and per-file guide | None | Locate every delivered file |
| `README.md` | Overview, architecture and honest benchmark status | Markdown | Read first for project scope |
| `VALIDATION.md` | Actual checks and integration limits | None | Review before making portfolio claims |
| `app/__init__.py` | Backend package identity | Python | Supports python -m app.main |
| `app/cache.py` | Versioned exact/semantic Redis caching | Redis | Optional query cache; fails open to normal workflow |
| `app/config.py` | Central typed environment configuration | pydantic-settings | Loaded by all backend components |
| `app/graph.py` | Neo4j extraction, communities, traversal and PPR | Neo4j, NetworkX, LLM | Enriches Stage 2 and retrieves provenance support |
| `app/ingest.py` | PDF parsing, metadata/chunks and two-stage indexing | PyMuPDF, optional Docling, retrieval/graph | Called by queued uploads or ingestion CLI |
| `app/main.py` | FastAPI endpoints, background queue and lifecycle | FastAPI, Uvicorn, backend services | python -m app.main |
| `app/retrieval.py` | Raw/contextual dense, BM25, RRF and reranking | FastEmbed, Qdrant, BM25, FlashRank | Called independently or through workflow |
| `app/utils.py` | SQLite persistence, JSON inference, usage/failure telemetry | SQLite, HTTPX, Pydantic | Used by ingestion/workflow/evaluation |
| `app/verification.py` | Claim schemas, citation checks and entailment filtering | Pydantic, configured LLM | Called after generation |
| `app/workflow.py` | LangGraph router, transforms, CRAG and verification flow | LangGraph, other backend components | Invoked by query endpoint and evaluator |
| `data/README.md` | Runtime directory and backup explanation | None | Explains generated data paths |
| `deploy/Caddyfile` | Automatic HTTPS reverse proxy configuration | Caddy, public hostname/ports | Mounted by deployment Compose |
| `deploy/compose.yml` | Public app/proxy services and persistent volumes | Docker Compose, PUBLIC_HOST, .env | Use deployment Compose command in setup.md |
| `docker-compose.yml` | Local app with persistent named data volume | Docker Compose, .env | docker compose up -d --build |
| `eval/DATASET.md` | Review procedure, metric definitions and dataset limits | None | Read before interpreting benchmark results |
| `eval/__init__.py` | Evaluation package identity | Python | Supports python -m eval.evaluate |
| `eval/ablation.py` | Eight ablations and controlled graph comparison | evaluate.py, feature options | python -m eval.ablation |
| `eval/corpus.json` | Official URLs, edition hashes and page counts | Official PDF sources | Read by downloader/ingestion and audits |
| `eval/evaluate.py` | Corpus management, metrics, judge adapter, reports and gate | Backend, NumPy, optional RAGAS | python -m eval.evaluate |
| `eval/gold_set.jsonl` | 120 provisional source-anchored question records | Exact corpus editions, human audit | Shared dataset for all experiments |
| `eval/latency.py` | Measured p50/p95, usage/cache/failure summaries | SQLite Store, NumPy | python -m eval.latency; GET /metrics |
| `eval/manual_audit.csv` | 12-record initial human-audit form | Reviewer/source pages | Fill judgments; no fabricated audit provided |
| `pytest.ini` | Test discovery and project import path | pytest | Used by pytest |
| `requirements-docling.txt` | Optional CPU layout parser dependencies | Core, official CPU Torch wheels | pip install -r requirements-docling.txt |
| `requirements-eval.txt` | Optional current RAGAS dependencies | Core requirements | pip install -r requirements-eval.txt |
| `requirements-optional.txt` | Convenience install for both optional toolsets | Two optional requirements files | pip install -r requirements-optional.txt |
| `requirements.txt` | Pinned lean CPU runtime/test dependencies | pip, Python 3.12 | pip install -r requirements.txt |
| `setup.md` | Windows operations and free deployment manual | Python/Docker/accounts as described | Follow from the first command |
| `static/app.js` | API interactions, progress polling and safe rendering | Browser fetch/DOM API | Loaded by index.html |
| `static/index.html` | Upload/query/evidence UI layout | Browser, app.js/styles.css | Served at GET / |
| `static/styles.css` | Responsive dark UI styling | Browser CSS | Loaded by index.html |
| `tests/test_core.py` | 24 offline unit/API/contract tests | pytest, core runtime | pytest |

## Current evaluation results

The latest obtained-metrics workbook is transcribed in [EVALUATION_STATUS.md](EVALUATION_STATUS.md) and [eval/obtained_metrics.json](eval/obtained_metrics.json). It records retrieval, RAGAS, timing, cache, usage, reliability, memory and coverage metrics. Historical implementation checks and test counts in this document refer to their original validation date; the new benchmark does not alter them. Dollar cost and paired feature gains remain pending.
