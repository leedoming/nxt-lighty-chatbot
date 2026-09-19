# Offline RAG Evaluation

This directory retrospectively evaluates the Gwangju University academic-information RAG chatbot using the recovered 2025-03-25 corpus and preserved historical Slack responses.

The evaluation is intentionally split into two layers:

1. **Reconstructed retrieval benchmark** — corpus coverage, chunking and ranking without requiring the retired AWS Bedrock Knowledge Base.
2. **Historical final-answer review** — actual historical answer behavior, including factuality, groundedness, routing, format/delivery, and multi-turn context behavior.

## Important interpretation

- `data/golden_seed_v0.jsonl` is a **developmental seed benchmark** created while inspecting the corpus. Tuned scores are useful for failure analysis and A/B development, not as an unbiased production accuracy estimate.
- `data/golden_review_candidate_v1.jsonl` contains 50 questions selected without retrieval-score-based cherry-picking for later human review and benchmark freezing.
- Retrieval metrics describe an **offline reconstruction over the recovered source corpus**, not the historical Amazon Bedrock Knowledge Base itself.
- Historical final-answer examples are preserved convenience samples, not a random sample of all production traffic.

## Recovered corpus

- 41 academic-information JSON documents
- common metadata: `title`, `sections`, `url`, `mn`, `dep`, `dep_tel`
- crawl date: 2025-03-25

`data/corpus_20250325/` contains the 41 recovered source JSON files used by the executable benchmark. `data/corpus_20250325.jsonl` is also provided as a compact consolidated snapshot.

## Setup and run

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate

pip install -r evaluation/requirements.txt
python evaluation/retrieval_eval.py
python evaluation/chunking_ab_eval.py
python evaluation/guarded_rerank_eval.py
python evaluation/coverage_probe_eval.py
pytest -q
```

## Developmental retrieval result

On the 70-question seed benchmark, the guarded reranker improved the previous fact-aware hierarchical baseline while preserving hard-question and Top-5 fact coverage:

| Metric | Previous best | Guarded reranker |
|---|---:|---:|
| Document Recall@1 | 91.4% | 95.7% |
| Document Recall@5 | 97.1% | 100% |
| Section Recall@1 | 67.1% | 72.9% |
| Section Recall@5 | 97.1% | 100% |
| Fact Coverage@1 | 67.6% | 70.5% |
| Fact Coverage@5 | 98.6% | 100% |
| Hard-question Fact Coverage@1 | 90.0% | 90.0% |

These remain **developmental figures** because the same seed benchmark was used during iteration.

## Failure-driven findings

- long sections diluted specific facts inside the correct document;
- user terminology and administrative terminology diverged (`전과` vs `모집단위이동`);
- some HTML tables contained facts missing from the extracted `sections` field;
- indiscriminately adding all HTML increased noise, so structured ingestion should be selective;
- final-answer quality and department routing can fail independently;
- OOD questions can produce unsupported answers if abstention is not enforced;
- delivery/rendering failures should be measured separately from answer correctness;
- **DM follow-ups can lose the active referent even when the preceding single-turn answer is grounded.**

## Historical final-answer review v1

`results/final_answer_eval_v1.*` contains anonymized labels for **29 preserved historical cases**:

- 20 thread cases
- 9 DM cases

The v1 schema separates:

- correctness / completeness / groundedness
- abstention / department routing
- format / delivery
- `context_retention`
- `reference_resolution`
- `role_adherence`

The raw Slack screenshots and user-identifying evidence are intentionally **not committed** to the public repository.

The DM cases are especially useful for failure taxonomy. Two separate classroom-rental follow-ups lost the antecedent `강의실` and drifted to either dormitory-room transfer or personal-item lending. Treat these as conversation-context/reference-resolution failures, not automatically as retrieval failures.

Do not turn the selected-case counts into a production accuracy percentage.

## Reports

- `reports/CORPUS_AUDIT.md`
- `reports/CHUNKING_AB_REPORT.md`
- `reports/RETRIEVAL_V3_REPORT.md`
- `reports/FINAL_ANSWER_EVAL_V1_REPORT.md`
- `reports/CONVERSATION_MODE_ANALYSIS.md`
