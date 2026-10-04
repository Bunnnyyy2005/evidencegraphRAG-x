# EvidenceGraph-X: complete setup and operating manual

## A–B. Download, open and locate the project

Extract `evidencegraph-x.zip` into your Documents folder. Open the extracted **evidencegraph-x** folder in VS Code with File → Open Folder. Select Terminal → New Terminal → PowerShell.

All Windows commands below run from **PROJECT ROOT**, unless explicitly marked otherwise:

```powershell
cd "$env:USERPROFILE\Documents\evidencegraph-x"
Get-Location
Get-ChildItem
```

Expected: the location ends with `evidencegraph-x`, and `app`, `eval`, `static`, `requirements.txt` and this manual are listed. This is the directory containing `app/`, not `app/` itself. If your extraction created two nested folders, open the inner folder containing `requirements.txt`. A “path does not exist” error means you must substitute your actual extracted location. Never run the application from `app/` or the evaluator from `eval/`.

## C–F. Python 3.12 and the virtual environment

From PROJECT ROOT:

```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip check
```

Expected: Python 3.12.x, then an activated prompt prefixed with `(.venv)`, successful installs, and `No broken requirements found`. The environment keeps project packages separate from your other projects. Installation may take several minutes and requires internet access; the first retrieval also downloads the embedding/reranking models.

| Error | Solution |
|---|---|
| `py -3.12` unavailable | Install Python 3.12 from python.org, then reopen VS Code. If `python --version` is already 3.12, use `python -m venv .venv`. |
| Script execution disabled | Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again. This affects only this terminal. |
| pip installs into the wrong Python | Use `python -m pip` in the activated environment; inspect `Get-Command python`. |
| Wheel installation fails | Confirm 64-bit Python 3.12, upgrade pip, and read the first actual error above the final pip message. |
| Network/proxy/certificate error | Configure your approved proxy/certificate. Do not disable TLS verification. |

No CUDA or local large language model is required. CPU defaults work on the specified RTX 3050 laptop even when CUDA is unavailable.

## G–I. Create and configure `.env`

From PROJECT ROOT:

```powershell
Copy-Item .env.example .env
code .env
```

Expected: a local `.env` containing documented defaults. It is ignored by Git. If `code` is unavailable, open `.env` in the VS Code Explorer. All fields are defined in `app/config.py`; environment variables override `.env`. Blank optional prices are allowed.

For the first run, **only GROQ_API_KEY is required to generate and verify answers**. Leave `QDRANT_URL`, Neo4j and Redis fields blank to use local dense/sparse retrieval without optional services. Configure all managed services for the full graph/cache experiment.

| Variable(s) | What to configure |
|---|---|
| `GROQ_API_KEY` | Your Groq API key, obtained below. |
| `LLM_BASE_URL` | Default Groq OpenAI-compatible API base URL. |
| `LLM_MODEL`, `SMALL_MODEL` | Current configured GPT-OSS answer and smaller orchestration models. Verify their availability using the service check. |
| `QDRANT_URL`, `QDRANT_API_KEY` | HTTPS cloud cluster URL and database key; blank URL selects local Qdrant. |
| `COLLECTION` | Dedicated collection name. A new collection is created automatically. |
| `EMBEDDING_MODEL`, `EMBEDDING_THREADS` | FastEmbed-supported model and CPU thread count. Defaults use BGE small and 2 threads. |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` | Aura credentials; typically `neo4j+s://…`, `neo4j`, downloaded password and `neo4j`. |
| `GRAPH_ENABLED`, `GRAPH_CHUNK_LIMIT`, `GRAPH_HOPS`, `GRAPH_LIMIT` | Enable graph, optional enrichment cap (`0` = all chunks), one/two hops, bounded traversal records. A cap produces **Graph partial**, not a claim of complete enrichment. |
| `REDIS_URL` | Upstash TLS Redis URL: `rediss://default:PASSWORD@HOST:PORT`. URL-encode special password characters. This is the Redis TCP credential, not the REST token. |
| `SEMANTIC_CACHE`, `CACHE_THRESHOLD`, `CACHE_TTL`, `CACHE_ENTRIES` | Exact cache is default; opt in to approximate semantic reuse and its false-match risk. |
| `PARSER` | `pymupdf` for lean first run; `docling` after installing its optional CPU requirements. |
| `CHUNK_WORDS`, `PARENT_WORDS` | Search-window and expanded paragraph limits. |
| `RETRIEVAL_K`, `RERANKER_K`, `USE_RERANKER`, `RERANKER_MODEL` | Candidate count, generation count and lightweight FlashRank model. |
| `GRADE_THRESHOLD`, `MAX_CONTEXT_CHARS`, `USE_HYDE` | Evidence sufficiency threshold, context budget and opt-in hypothetical search passage. |
| `MAX_UPLOAD_MB`, `MAX_PAGES` | Upload and page limits. |
| `DATA_DIR`, `HOST`, `PORT` | Local storage, bind address and port. Defaults: `data`, `0.0.0.0`, `7860`. |
| `API_TOKEN` | Optional shared access token. Set a strong random value before public deployment; enter it in the UI. This project is a shared-corpus demo, not a multi-tenant app. |
| `LLM_TIMEOUT`, `LLM_MAX_TOKENS` | Provider request limits. |
| `SMALL_INPUT_USD_MILLION`, `SMALL_OUTPUT_USD_MILLION`, `LARGE_INPUT_USD_MILLION`, `LARGE_OUTPUT_USD_MILLION` | Optional current paid-price assumptions; blank means estimated paid cost is unmeasured. |
| `JUDGE_BASE_URL`, `JUDGE_API_KEY`, `JUDGE_MODEL` | Separate OpenAI-compatible judge for optional RAGAS; use another model family. |

Changing the embedding model or chunk/index representation requires a new `DATA_DIR` and `COLLECTION`, then re-ingestion. Do not reuse embeddings produced by another model just because the dimensions match.

## J. Qdrant Cloud Free

Visit https://cloud.qdrant.io/ and create an account. Create a **Free** cluster, wait for it to become ready, then copy its HTTPS cluster endpoint and create a database API key. Paste these into `.env`; do not include an extra `/collections` path. The app creates named `raw` and `contextual` dense vectors automatically on the first upload. BM25 runs from the persisted chunk catalog; RRF combines it with Qdrant dense hits in Python.

Expected: service check reports `qdrant: CONNECTED`. `401`/`403` means the database key is wrong or lacks access; timeout often means the endpoint/port or firewall is wrong. A schema/dimension error requires a new collection. Current Free capacity is 1 GB RAM and 4 GB disk; this is a small demo corpus, not an unlimited service.

## K. Neo4j AuraDB Free

Visit https://console.neo4j.io/ and create an **AuraDB Free** instance. Download the credential file while the console offers it. Keep the provided password and `neo4j+s://` connection URI in `.env`. Wait until the instance reports ready. The app creates its ID constraint and graph nodes/relationships automatically; no APOC or Graph Data Science installation is needed. Community detection and Personalized PageRank run in NetworkX.

Expected: `neo4j: CONNECTED` in the check below. Authentication failure means the downloaded password or username differs. Connectivity failure can mean a paused instance, network restrictions on Bolt/TLS, or an incorrect URI. Resume paused databases in the console. If unavailable, the PDF remains searchable via hybrid retrieval. Current Free limits include 200,000 nodes and 400,000 relationships. One LLM extraction per chunk can hit Groq quotas long before this graph limit.

## L. Upstash Redis Free

Visit https://console.upstash.com/ and create a Redis database on its Free plan. Copy its Redis endpoint, port and password. Construct `REDIS_URL` using `rediss://default:…@…:…`, retaining TLS. Expected: `redis: CONNECTED`. A REST endpoint or REST token will not work with the Python Redis client. If authentication fails, verify the TCP password; if no Redis is configured, the app answers without caching. The documented Free allowance is 256 MB storage and 500,000 commands/month; cache reads and writes consume commands.

## M. Groq and optional independent judge

Visit https://console.groq.com/keys, create an API key and set `GROQ_API_KEY`. Leave the API base URL at its default. The report's Llama 3.1/3.3 IDs were retired from free/developer usage; this repository uses configurable `openai/gpt-oss-20b` and `openai/gpt-oss-120b` replacements. Model availability and limits can vary by account; the check below asks the actual models endpoint.

Expected: both configured model IDs report `AVAILABLE`. If not, choose an available JSON-capable model from https://console.groq.com/docs/models and update `.env`. Free quotas vary by model/account and can throttle a full benchmark. `429` is quota/rate limiting, not successful evaluation. Wait for quota reset or use a smaller experiment. Inference/extraction retries once; unsupported evidence still leads to abstention.

For optional judge metrics, obtain a separate provider key and configure its OpenAI-compatible base URL and model. Its free availability, if any, is provider/account-specific. Judge credentials are not required for custom retrieval/trust metrics.

## N–O. Verify services and health

From PROJECT ROOT, with the environment activated:

```powershell
python -m eval.evaluate --check-services
python -m eval.evaluate --validate
pytest
```

Expected: configured services say `CONNECTED`, configured models say `AVAILABLE`, and the dataset check prints `120` questions with `48/48/24` distribution. Optional services say `NOT CONFIGURED` when blank. Tests make no paid LLM calls. The included validation report records the actual delivered test run; future test counts may change as you edit the project.

A failed service is reported separately. Fix its configuration, then rerun the check. The `/health` endpoint below checks app liveness and configuration presence, not remote-service connectivity.

## P–Q. Start the application and open it

Recommended command, from PROJECT ROOT:

```powershell
python -m app.main
```

Expected: Uvicorn reports that it is listening on `http://0.0.0.0:7860`. Open **http://localhost:7860** in your browser. From a second PowerShell terminal:

```powershell
Invoke-RestMethod http://localhost:7860/health
```

Expected: `status` is `ok`. A port-in-use error means another process owns 7860; stop it or change `PORT`. A blank page means the server stopped, the port differs, or you opened an HTTPS URL for a local HTTP server. Use Ctrl+C to stop the app.

Development-only alternative: `uvicorn app.main:app --reload --port 7860`. Keep **one worker**: local Qdrant, background ingestion and model memory are intentionally shared in a single process. Do not run the ingestion CLI simultaneously with a server using the same local Qdrant directory.

## R–T. Download and upload the evaluation PDFs

From PROJECT ROOT, in an activated second terminal:

```powershell
python -m eval.evaluate --download-corpus
```

Expected: six official files appear under `data/evaluation/`, each with a verified SHA-256. If a source returns `403`, retry later or download from the official URL in `eval/corpus.json` with your browser and save under the exact listed filename. If the hash differs, do not silently accept it: confirm the document edition and re-audit page references. The repository does not include or redistribute these PDFs.

In the UI, upload each file using its exact downloaded filename. The document list updates every three seconds. Progress states are Queued → Parsing → Chunking → Embedding → Indexing → Searchable → Graph extraction → Graph ready/Graph partial. **Searchable** means Stage 1 has completed; queries can run while Stage 2 continues. A malformed PDF is recorded as Failed; other documents remain usable. First-time model downloads and hundreds of pages can take minutes. The specification's ingestion and latency numbers are targets, not guarantees.

For unattended corpus ingestion, first stop the server and run from PROJECT ROOT:

```powershell
python -m eval.evaluate --ingest-corpus
```

Expected: one final stage per document. This processes Stage 1 and Stage 2 sequentially for reproducibility. It can consume many extraction calls if graph enrichment is enabled; `GRAPH_CHUNK_LIMIT` can limit a demo but then graph completeness is explicitly partial. Restart the server afterward. Re-upload deduplicates identical bytes; changing the bytes produces a new document version.

| Problem | Resolution |
|---|---|
| PDF has no text | OCR it externally first; lean mode does not perform OCR. |
| Upload larger than configured limit | Use a smaller file or deliberately raise `MAX_UPLOAD_MB`/`MAX_PAGES`. |
| Graph unavailable/partial | Check Neo4j/Groq connectivity and failure counts. Hybrid remains usable. |
| Initial search is slow | Allow initial model downloads; CPU embedding and reranking are real inference. |

## U. Ask sample questions and inspect evidence

Select a PDF to narrow scope, or leave all unchecked to use all searchable documents. Try “How do verification and validation differ?” with the NASA handbook, or “What does this document say about flow control?” with RFC 9000. The three sample buttons fill the question box; submit it to query.

Expected: an answer or an explicit abstention, evidence snippets, physical page citations, claim statuses, real graph paths when retrieved, node timing and token usage. `ENTAILMENT` means the configured LLM verifier ran and judged the claim supported; it is not proof of correctness. The UI removes claims classified as partial, contradicted or insufficient. If the verifier fails, the claim is removed. An empty answer after this process is an abstention.

Global questions scan selected chunks/community evidence in a map-reduce step and can take much longer than factoid queries. Use them deliberately. The UI shows incomplete global map coverage if a group fails. An unchanged repeated query is cached only when Redis is available; semantic matching requires explicit opt-in.

## V. Run evaluation

Stop the server first if using local Qdrant. From PROJECT ROOT:

```powershell
python -m eval.evaluate --allow-unreviewed
```

This runs all 120 questions, stores actual responses and calculates retrieval, trust and system metrics. Outputs are saved to `eval/results/full/`: `summary.json`, `metrics.csv`, `per_question.jsonl`, `responses.jsonl`, and `report.md`. It requires Groq calls for routing, grading, generation and verification. Runtime can range from minutes to much longer depending on quotas and retry delays; no measured runtime is promised. A smaller initial check is:

```powershell
python -m eval.evaluate --limit 5 --allow-unreviewed
```

The included labels require human review, so results are marked **EXPLORATORY — HUMAN LABEL AUDIT PENDING**. Read `eval/DATASET.md`, fill the small audit CSV and review the remaining labels before publishing audited scores. After individually reviewing all records and updating their review fields, run the same command without `--allow-unreviewed`. A missing-corpus error means a filename/hash does not match the annotated edition or ingestion did not finish.

For independent RAGAS scores, from PROJECT ROOT:

```powershell
python -m pip install -r requirements-eval.txt
python -m eval.evaluate --ragas --allow-unreviewed
```

Expected: faithfulness, answer relevancy, context precision and context recall observations with their sample counts. Set judge credentials first. Unrun metrics stay `NOT MEASURED`; judge failures are not converted into invented zeros. Judge calls are billed/limited separately and are not included in app token telemetry.

## W. Run ablation and the graph benchmark

From PROJECT ROOT, with the server stopped for local Qdrant:

```powershell
python -m eval.ablation --allow-unreviewed
python -m eval.ablation --graph-only --allow-unreviewed
```

The first command runs eight feature configurations over the same records. The second compares dense, hybrid and hybrid plus graph on multi-hop records, with matching non-graph settings. Each writes per-run outputs and a comparison CSV, JSON and Markdown report under `eval/results/ablation/` or `eval/results/graph-benchmark/`. Add `--ragas` when judge tooling/credentials are configured. Eight full runs can require thousands of API calls; use `--limit 5` to test the harness first. Do not interpret a graph variant without successful graph enrichment as evidence about graph quality.

## X–Y. Inspect results, latency/cost, failures and tests

From PROJECT ROOT:

```powershell
code eval/results/full/report.md
python -m eval.latency
code eval/results/latency.json
pytest
```

Expected: measured summary tables, p50/p95 timings, cache observations and failure counts. The UI's “Inspect system metrics” button reads the same recorded events. If no experiment ran, values are `NOT MEASURED`. Optional paid-cost estimates depend on prices you explicitly configure and provider-reported token counts. Free-tier use is not a claim of zero economic cost. Node durations are inclusive (retrieval includes graph and reranking), so do not add inclusive and substage timing fields together.

## Z–AA. Docker locally

Install Docker Desktop for Windows, enable its supported Linux-container backend, and start Docker Desktop. From PROJECT ROOT:

```powershell
docker version
docker build -t evidencegraph-x .
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

Expected: successful image build, a running/healthy `app` service, and http://localhost:7860. Compose keeps data in a named volume and leaves Qdrant/Neo4j/Redis managed services external. Local Qdrant also works in the volume. A daemon connection error means Docker Desktop is stopped; an env-file error means `.env` is missing. A dependency download error requires internet access. Build validation must be run on your machine or in the supplied CI workflow if Docker is unavailable in the authoring environment.

Stop from PROJECT ROOT:

```powershell
docker compose down
```

Data survives normal `down`. Avoid `down -v` unless you intend to delete local corpus/index storage.

## AB. Push the repository to GitHub

Create an empty GitHub repository in the browser, then run from PROJECT ROOT:

```powershell
git init
git add .
git status
git commit -m "Build EvidenceGraph-X"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/evidencegraph-x.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub account. Expected: source/config/docs/tests are committed, and `.env`, uploads, models, results and the venv are absent from `git status`. GitHub authenticates using its supported credential flow. If the remote already exists, use `git remote set-url origin …`. If Git requires identity, configure `git config user.name "Your Name"` and `git config user.email "Your Email"`, then commit again. If the remote contains initial commits, clone it and copy project files into that checkout instead of force pushing.

The Actions workflow runs tests, dataset structural validation and a Docker build. Its optional manual benchmark consumes provider quota and uses repository secrets. It is not automatically an audited benchmark or a quality-regression gate; use reviewed saved results to compare changes. Once you have an audited measured baseline, run `python -m eval.evaluate --baseline PATH_TO_SAVED_SUMMARY.json --tolerance 0.02`. This gate requires identical dataset hashes/options and no runtime errors; it fails on a measured retrieval drop beyond the supplied absolute tolerance. It rejects unaudited or unmeasured baselines. No baseline is pre-filled. To enable the same gate in the manually triggered CI benchmark, set repository variable `EVAL_BASELINE_JSON` to the complete previously measured audited summary JSON. Unaudited current labels will make that gate fail rather than manufacture a pass.

## AC–AE. Free deployment: Oracle Always Free + Docker + HTTPS

The official Hugging Face docs now require a paid plan to create a Docker compute Space, even though CPU Basic has no hourly charge. That option is therefore **not claimed as free**. Render's 512 MB Free instance is a poor fit for local embeddings/parsing/reranking. The free route here is an OCI Always Free **Ampere A1** VM with up to **2 OCPUs / 12 GB RAM** within the current allowance.

Oracle account verification may require a payment card. Stay on Always Free-eligible resources and within total tenancy quotas; trial credits are not permanent free hosting. A1 capacity is not guaranteed, and Oracle can reclaim idle VMs. See the current official sources in `README.md` before provisioning. No account or infrastructure has been created by this repository.

1. In https://cloud.oracle.com/, select your home region and create a VM using `VM.Standard.A1.Flex`, 2 OCPUs, 12 GB memory and an Always Free-eligible Ubuntu image. Use a 50 GB boot volume; total eligible boot/block volumes must stay within 200 GB. Save your SSH private key and record the public IPv4 address. Confirm the console's eligibility/cost estimate before creation. If capacity is unavailable, try another availability domain in the home region or retry later; do not silently choose a paid shape.
2. Attach the VM to a public subnet with its normal internet route. In the attached network security group/security list, allow TCP 22 **from your own IP**, and TCP 80/443 for the public app. Do not expose 7860; the deployment proxy publishes only 80 and 443.
3. From your Windows terminal (any directory), connect:

```powershell
ssh -i "C:\path\to\your-private-key" ubuntu@YOUR_VM_PUBLIC_IP
```

Expected: a Linux shell. Permission denied means the key or username is wrong; timeout means the IP, route or SSH ingress is wrong. Protect the key file and use the image's documented default user.

4. The following commands run on the **Ubuntu VM**, first from your home directory, then PROJECT ROOT (`~/evidencegraph-x`). Install Docker Engine using the official Ubuntu instructions at https://docs.docker.com/engine/install/ubuntu/; those instructions configure Docker's apt repository and install `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin` and `docker-compose-plugin`. For the basic VM utilities:

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF_DOCKER
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF_DOCKER
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker version
sudo docker compose version
git clone https://github.com/YOUR_USERNAME/evidencegraph-x.git
cd evidencegraph-x
cp .env.example .env
nano .env
chmod 600 .env
```

Expected: Docker/Compose versions and a cloned repository. Follow the official installation page if `docker` is absent; do not substitute Docker Desktop on a headless VM. Use `sudo` for subsequent Docker commands if your user is not in the Docker group.

5. In VM PROJECT ROOT, configure `.env` with Groq and managed service secrets as above. Set a strong `API_TOKEN`. Add:

```dotenv
PUBLIC_HOST=YOUR_VM_PUBLIC_IP.sslip.io
```

Substitute the actual IPv4 digits, e.g. `203.0.113.25.sslip.io` is only an illustrative address. The free sslip.io/nip.io DNS service resolves IP-containing names; you may use an existing domain instead. It has shared service/certificate limits. Verify DNS points to your VM before requesting a certificate. Allow 80/443 through the VM's OS firewall as well as OCI's network rules; preserve existing SSH access. Caddy automatically obtains and renews TLS certificates when DNS and inbound ports work. On the VM, inspect `sudo ufw status`. If UFW is active, preserve your SSH rule, then run `sudo ufw allow 80/tcp` and `sudo ufw allow 443/tcp`. OCI Ubuntu images can also have iptables reject rules independent of UFW: inspect `sudo iptables -L INPUT -n --line-numbers`; if they block these ports, allow them with `sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT` and the equivalent for 443. Use the VM image's firewall persistence procedure so a reboot retains the rules.

6. From VM PROJECT ROOT:

```bash
sudo docker compose --env-file .env -f deploy/compose.yml up -d --build
sudo docker compose --env-file .env -f deploy/compose.yml ps
sudo docker compose --env-file .env -f deploy/compose.yml logs -f app proxy
```

Expected: app and proxy running, followed by successful HTTPS certificate logs. First build/model downloads can take minutes. The official Python image and Caddy image support ARM64; build on the VM so wheels match its architecture. The parser defaults to PyMuPDF; optional Docling is not included in the compact image.

7. Open `https://YOUR_VM_PUBLIC_IP.sslip.io/health`, then the root URL. Expected: health JSON and the UI. Enter the API token, upload a small PDF, wait for Stage 1, ask a grounded question, inspect citations, then verify graph readiness and a repeated exact-cache query when those services are configured. A certificate error/502 requires inspecting proxy/app logs and DNS/firewall settings. A `401` means the UI token is missing or wrong.
8. Data is held in the `evidence-data` Docker volume on persistent VM disk. Export/back up that volume and your corpus outside the VM before relying on it. On ephemeral hosts, committed Qdrant payloads can restore the catalog/BM25, but original PDF files and local telemetry are not recoverable from Qdrant; re-upload originals for page viewing. Sleeping/paused/reclaimed free resources require operational attention; no keepalive circumvention is included.
9. To update from VM PROJECT ROOT: `git pull --ff-only`, then repeat the deployment Compose command. Expected: rebuilt service with data retained. If a pull conflicts, resolve the local source changes rather than forcing over them.

## AF. Troubleshooting reference

| Symptom | Meaning | Fix |
|---|---|---|
| Answers always abstain | Missing key, failed evidence grading, insufficient context or rejected claims | Run service check; inspect recorded stages/claim reasons; ask a question clearly covered by a selected source. |
| Wrong citation page compared to printed label | Citations use physical PDF viewer pages | Use the viewer's page index, not the footer page label. |
| Tables/normative words parse oddly | PDF layout/text order may obscure semantics | Compare source page; use optional Docling and re-ingest into a new data directory/collection; never trust a score without source audit. |
| Reranker unavailable | Model download or runtime failure | Retrieval ranking is retained and failure is recorded; fix model/network settings and retry. |
| RAGAS import error | Incompatible optional dependency update | Reinstall pinned `requirements-eval.txt`, especially Community 0.4.1, and run `pip check`. |
| Qdrant storage lock | Two processes opened the same local path | Stop server before CLI evaluation/ingestion; run one worker. |
| Cache returns a near-match answer | Semantic caching was explicitly enabled | Set `SEMANTIC_CACHE=false`; exact repeats are safer. Corpus/settings scope changes invalidate old keys. |
| Disk grows | Original PDFs, local index, model cache and event logs persist | Back up useful data; use a new directory or deliberately remove unwanted local artifacts while the app is stopped. |
| Source hash mismatch | Official bytes changed or a different edition was downloaded | Re-audit source pages and dataset hashes before evaluation. |
| Public demo displays all users' PDFs | The repository is a shared-corpus portfolio app | Use the API token and only public demo documents; it does not provide per-user tenancy. |

## Optional Docling parsing on the laptop

From PROJECT ROOT in your activated Windows environment:

```powershell
python -m pip install -r requirements-docling.txt
python -m pip check
```

Then set `PARSER=docling` in `.env` and restart. Explicit CPU Torch/TorchVision wheels avoid CUDA dependencies on Windows/Linux x86. Docling still adds substantial dependencies and layout model downloads. OCR is disabled in this adapter. Docling failure falls back to PyMuPDF and is recorded. It is optional because the core application must remain usable on limited hardware. This adapter's runtime status is stated honestly in `VALIDATION.md`.

## Target values for future measurements

See [METRIC_TARGETS.md](METRIC_TARGETS.md) for all 48 supplied goals and their recorded observations. These are planning inputs, not test outcomes. Existing validation records and evaluator outputs retain their measured values.

## Separate user-reported run

The user reports obtaining the spreadsheet values with separate codes. [USER_REPORTED_RESULTS.md](USER_REPORTED_RESULTS.md) records all 48 values with unverified status and unspecified run scope. Historical validation records, logs and test counts are preserved.
