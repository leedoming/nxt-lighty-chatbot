# Lighty Offline Retrieval Evaluation — v3

> **Status: developmental only.** The 70-question seed set was authored from the recovered corpus, so the metrics below are for engineering comparison, not final portfolio claims. A 50-question review candidate is included for human approval before freezing a final benchmark.

## What changed in v3

The previous best retrieval candidate used:

- fact-aware atomic chunks (`target=120`, `max_chars=190`, one-unit overlap)
- character n-gram TF-IDF
- hierarchical document + chunk ranking

v3 adds a **guarded metadata reranker** rather than replacing the base ranker.

1. The original user query still drives the main content/document score.
2. Domain aliases are applied only to **document-title metadata** (e.g. `전과 → 모집단위이동`).
3. Generic intents are applied only to **section-heading metadata** (e.g. `몇 월/언제 → 신청기간`, `서류/증빙 → 제출서류`).
4. The reranker adds only **positive score deltas** when the expanded query improves metadata similarity. It never subtracts from the original lexical score.
5. Hyperparameter selection was constrained so **hard-question Top-1 fact coverage and overall Top-5 fact coverage could not regress** from the previous best run.

Selected development configuration: `alias bonus α=0.20`, `intent bonus β=0.08`.

## Developmental results (70 seed questions)

| Metric | Previous best | v3 guarded reranker | Change |
|---|---:|---:|---:|
| Document Recall@1 | 91.43% | **95.71%** | **+4.29%p** |
| Document Recall@5 | 97.14% | **100.00%** | **+2.86%p** |
| Document MRR | 0.944 | **0.973** | +0.029 |
| Section Recall@1 | 67.14% | **72.86%** | **+5.71%p** |
| Section Recall@3 | 88.57% | **91.43%** | +2.86%p |
| Section Recall@5 | 97.14% | **100.00%** | **+2.86%p** |
| Section MRR | 0.783 | **0.822** | +0.038 |
| Fact Coverage@1 | 67.63% | **70.53%** | **+2.90%p** |
| Fact Coverage@3 | 89.86% | **91.30%** | +1.45%p |
| Fact Coverage@5 | 98.55% | **100.00%** | **+1.45%p** |
| Hard-question Fact Coverage@1 | **90.00%** | **90.00%** | no regression |
| Hard-question Fact Coverage@5 | **100.00%** | **100.00%** | no regression |

For context, the original full-section char-TF-IDF baseline had Section Recall@1 **61.43%** and Fact Coverage@1 **63.77%**. The combined path from section baseline → fact-aware chunking → guarded metadata reranking therefore improved evidence ranking while preserving Top-5 coverage.

## Representative fixes

- `전과 신청은 보통 몇 월에 받아?`
  - previous document / section rank: **8 / 8**
  - v3: **1 / 1**
  - reason: title-only alias `전과 → 모집단위이동` + heading intent `몇 월 → 신청기간`

- `오버라이드 신청은 언제 해야 해?`
  - previous section rank: **2**
  - v3: **1**
  - Top-1 fact coverage: **0 → 1.0**
  - reason: heading-intent bonus promoted `신청시기` without changing content scoring.

- `관공서에서 FAX 민원으로 증명서를 신청하면 보통 얼마나 걸려?`
  - previous document / section rank: **2 / 2**
  - v3: **1 / 1**
  - Top-1 fact coverage: **0 → 1.0**

- `개명해서 이름이 바뀌었는데 학적정보를 어떻게 수정해?`
  - previous document rank: **2**
  - v3: **1**
  - remaining issue: the exact evidence section still ranks below the best section; title routing improved before evidence localization did.

## Remaining failure patterns

1. **Repeated generic headings** — `신청방법`, `신청기간`, `유의사항` appear across many academic topics. Title-level routing helps, but section selection can still be ambiguous inside one document.
2. **Source terminology mismatch** — aliases solve some cases (`전과 ↔ 모집단위이동`) but should stay curated and scoped; broad aliases can create false routing (an early `국가장학 → 교외장학금` rule was removed after it hurt a FAQ query).
3. **Information missing from normalized sections** — some HTML tables, especially detailed internal scholarship data, contain facts absent from `sections`. This is an ingestion-completeness problem, not a ranking problem.
4. **Mobile course-registration query** — `광주대 수강신청을 휴대폰으로 해도 돼?` improved from document rank 8 → 4 but remains unresolved. This needs source-structure inspection or a more specific metadata field, not more generic alias expansion.

## Benchmark freeze candidate

`evaluation/golden_review_candidate_v1.*` contains **50 questions** selected without using model performance:

- all 10 hard questions retained
- all 36 categories represented
- remaining slots filled by deterministic category/difficulty round-robin
- difficulty mix: **10 hard / 27 medium / 13 easy**

It is **not frozen yet**. The next valid step is human review of wording, gold section, and required facts. After approval, rename/freeze it and run baseline/final exactly once for portfolio-facing numbers.

## Files

- `evaluation/guarded_rerank_eval.py` — guarded alias/intent reranking experiment
- `evaluation/alias_metadata_eval_v2.py` — scoped domain aliases + heading-intent rules
- `outputs/guarded_rerank_results.json` — full developmental result
- `outputs/guarded_rerank_summary.csv` — hyperparameter sweep
- `outputs/guarded_rerank_changes.csv` — only queries whose ranking changed
- `evaluation/golden_review_candidate_v1.csv` — human-review sheet for benchmark freeze
- `tests/test_retrieval_v3.py` — regression tests (`3 passed`)

## Safe portfolio wording before benchmark freeze

> 기존 광주대학교 학사정보 RAG corpus를 복원해 source·section·fact 단위의 오프라인 평가 파이프라인을 구축했습니다. 긴 section 내 근거 희석과 HTML 표 정보 누락을 확인한 뒤 fact-aware chunking과 title/section metadata 기반 guarded reranking을 비교 검증했습니다.

Do not use the developmental percentages in a resume until the 50-question benchmark has been reviewed and frozen.
