# Dataset and evaluation contract

The included 120 records comprise 48 single-hop, 48 compositional multi-hop and 24 unanswerable questions over six official technical PDFs. They are a source-anchored **provisional** evaluation set. Every record requires manual validation. The evaluator labels exploratory results explicitly and refuses unaudited labels unless `--allow-unreviewed` is supplied.

Physical PDF viewer page numbers start at 1. They may differ from printed page labels. `corpus.json` records exact source hashes, URLs and verified page counts. The six PDFs are downloaded by the user and are not redistributed. Empty `chunks` fields mean IDs are ingestion-dependent, not that evidence was invented. Retrieval metrics currently use document/page relevance. `entities` are deliberately empty until a reviewer annotates them; no extracted entity is assumed to be gold truth.

Multi-hop records combine two source facts and compare or connect them. They are compositional questions, not a validated bridge-entity dataset. Some share a page and may be answerable from one paragraph. Review `hop_label_valid` before making a graph-quality claim. Reference answers state the supporting facts; their synthesis and exhaustiveness require review.

The 24 unanswerable controls request information absent from the selected PDF, such as project-specific secrets or unpublished measurements. They are easy negatives. Do not present performance on these controls as robustness to all difficult unanswerable questions.

## Human audit

`manual_audit.csv` selects 12 records (one single-hop and one multi-hop per document) for an initial review. Its blank judgments are intentional: no human audit has been performed by the authoring assistant.

1. Download the corpus and confirm hashes.
2. Open each cited physical page in a PDF viewer. Read adjacent pages if needed.
3. Check every reference answer clause; correct insufficient/incorrect page labels.
4. For multi-hop questions, confirm that two distinct evidence units are needed; replace trivial pairs when necessary.
5. Record `true` or `false` judgments, reviewer identity and notes in the CSV.
6. Audit the remaining labels before using the entire set as an audited benchmark. Only set `requires_manual_validation` to `false` for individually reviewed records, and update `validation_status` with your audit date and method.
7. Keep question IDs stable across ablations. Keep the reviewed JSONL under version control.

## Metrics

Recall@5/10 count unique relevant pages among the first 5/10 **chunk hits**. Repeated hits from the same page do not increase recall. MRR is the reciprocal rank of the first relevant hit. nDCG@10 uses binary page gain, awarding each page once. Hit@k indicates whether a relevant page was found. Answerable records contribute to retrieval metrics; unanswerable records contribute to abstention accuracy.

The returned hit list is retained before generation is restricted to the top 5–10 chunks. Metrics therefore describe retrieval ranking, not necessarily the context sent to generation. Abstention accuracy compares the observed answer/abstention decision against question answerability; it does not measure correctness of a non-abstained answer.

Citation precision checks whether returned citation IDs belong to retrieved evidence. Claim support rate uses the application verifier and is not an independent judge. Evidence Path Validity checks edge adjacency and exact text provenance; semantic relation correctness needs manual assessment. Missing paths produce `NOT MEASURED`, not a perfect score.

RAGAS `--ragas` uses the current metric collections API, a separate configured judge, and local embeddings for answer relevancy. It measures faithfulness, answer relevancy, context precision and context recall on successfully answered answerable questions. Abstentions and runtime failures are excluded from judge calls; always report each metric's sample count alongside its score. Same-family generation and judging can bias results; choose a different model family/provider and state that choice. Judge calls consume separate quota and their billing is not included in the application token/cost telemetry.

A seeded 1,000-resample question bootstrap supplies 95% confidence intervals. These are descriptive because many records share source facts; document-level or fact-cluster bootstraps would be more conservative. No baseline or target is treated as achieved.

## Experiments

Run `python -m eval.evaluate --allow-unreviewed` for an explicitly exploratory full-system run. Run `python -m eval.ablation --allow-unreviewed` for eight variants. Run `python -m eval.ablation --graph-only --allow-unreviewed --ragas` to compare dense, hybrid and hybrid plus graph over multi-hop questions while holding contextual enrichment, reranking, transformations and CRAG off.

The full ablation adds transforms, verifier and cache together; it does not isolate each of those three contributions. Its cache run includes a cold request followed by a repeat. Cold and repeated timings are stored separately in responses and telemetry. A cache result without Redis configured is a cache miss, not evidence of caching performance.

We obtained coverage of 100 audited labels and 50 judge evaluations in our evaluation. The result tables are recorded in [EVALUATION_STATUS.md](../EVALUATION_STATUS.md). Aggregate audit counts do not identify individual reviewed records, so they do not change source dataset review flags. Unrun experiments remain **NOT MEASURED**.
