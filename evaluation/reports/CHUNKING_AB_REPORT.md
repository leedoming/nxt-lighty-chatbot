# Chunking A/B Evaluation Report

> 상태: **developmental benchmark**. 현재 70개 질문은 원문을 보고 만든 seed v0이므로 아래 수치는 설계/회귀 확인용이며, 포트폴리오 최종 수치로 확정하지 않습니다.

## 1. 실험 목적

기존 광주대 학사정보 JSON의 `sections` 단위를 그대로 검색하는 방식과, 긴 section을 사실 단위에 가깝게 분할하는 **fact-aware atomic chunking**을 비교했습니다. AWS Knowledge Base는 사용하지 않고 corpus snapshot과 로컬 TF-IDF 기반으로 재현했습니다.

- Baseline: section 172개, character n-gram TF-IDF
- Candidate: atomic chunk 331개, target 120자 / max 190자 / 1-unit overlap
- Candidate retrieval: document score + atomic chunk score의 hierarchical ranking
- 지표: Document Recall@K/MRR, Parent Section Recall@K/MRR, Required Fact Coverage@K

## 2. 핵심 결과

| Metric | Baseline | Atomic + hierarchical | 변화 |
|---|---:|---:|---:|
| Document Recall@1 | 91.4% | 91.4% | +0.0%p |
| Parent Section Recall@1 | 61.4% | **67.1%** | **+5.7%p** |
| Parent Section MRR | 0.746 | **0.783** | +0.037 |
| Required Fact Coverage@1 | 63.8% | **67.6%** | **+3.9%p** |
| Required Fact Coverage@5 | 98.6% | 98.6% | +0.0%p |
| Hard-query Fact Coverage@1 | 60.0% | **90.0%** | **+30.0%p** |

해석: 문서 자체를 찾는 능력은 이미 높은 수준이라 변화가 없었고, atomic chunking은 **같은 문서 안에서 질문에 필요한 근거 section/fact를 상위에 올리는 데 효과**가 있었습니다. 특히 seed에서 hard로 표시한 질문의 Top-1 fact coverage가 크게 개선됐습니다. 반면 Document Recall@5는 100% → 97.1%로 소폭 하락하여, chunk 수 증가에 따른 경쟁/노이즈도 확인됐습니다.

## 3. 대표 개선 사례

- `q034` 계절학기에는 한 학기에 최대 몇 학점까지 들을 수 있어? — section rank 4 → **1**, Fact@1 0.0 → **1.0**
- `q064` 사회봉사 교과목 성적은 어떤 방식으로 표시돼? — section rank 3 → **1**, Fact@1 0.0 → **1.0**
- `q009` 간호학과로 전과해서 들어갈 수 있어? — section rank 2 → **1**, Fact@1 0.0 → **1.0**
- `q022` 2008년 이후 3학년 편입생은 졸업을 위해 몇 학점을 이수해야 해? — section rank 2 → **1**, Fact@1 0.0 → **1.0**
- `q039` 사회봉사 교과목은 봉사활동을 몇 시간 이상 해야 학점 인정이 가능해? — section rank 2 → **1**, Fact@1 0.0 → **1.0**
- `q070` 질병 때문에 결석한 경우 진단서를 내면 한 학기에 최대 얼마까지 출석 인정이 돼? — section rank 2 → **1**, Fact@1 0.0 → **1.0**

## 4. 대표 회귀 사례

- `q024` 광주대 수강신청을 휴대폰으로 해도 돼? — section rank 2 → **8**, Top1 `수강교과목 철회 / 관련규정: 학칙시행세칙 제42조`
- `q001` 일반휴학은 개강하고 언제까지 신청할 수 있어? — section rank 1 → **2**, Top1 `일반휴학 / 신청방법`
- `q008` 전과 신청은 보통 몇 월에 받아? — section rank 5 → **8**, Top1 `조기졸업 / 신청기간(시기)`
- `q040` 현장실습 1, 2, 3과 현장실습 4는 각각 언제 개설돼? — section rank 1 → **1**, Top1 `현장실습 / 관련규정: 현장실습 수업에 관한 운영지침`
- `q065` KT장학금의 최소 성적 기준은 어떻게 돼? — section rank 1 → **1**, Top1 `교외장학금 / 일반장학금`

회귀 패턴은 주로 `신청기간`, `신청방법`처럼 비슷한 section title이 여러 문서에 반복되거나, 질문 표현과 공식 문서명이 다른 경우(예: **전과 ↔ 모집단위이동**)에 발생했습니다. 다음 단계에서는 chunk를 더 쪼개기보다 **문서/section metadata와 용어 alias를 별도 필드로 두고 field-aware ranking**하는 편이 타당합니다.

## 5. HTML 누락 정보 probe

Corpus audit에서 `교내장학금(498)`은 section 본문이 약 196자뿐인데 HTML에는 상세 장학금 표가 남아 있었습니다. 상세 표의 정보만 묻는 8개 개발용 probe를 별도로 구성했습니다.

| Ingestion | Document R@1 | Fact Coverage@1 | Fact Coverage@5 |
|---|---:|---:|---:|
| sections only | 0.0% | 10.4% | 16.7% |
| sparse HTML table rows 추가 | **100.0%** | **100.0%** | **100.0%** |

이 결과는 retrieval 모델 개선보다 먼저 **수집/전처리 단계의 coverage loss**를 확인한 사례입니다. 단, probe 문항도 HTML에서 직접 만든 개발용 세트이므로 100%라는 수치를 최종 품질 수치로 사용하지 않습니다. 의미 있는 결론은 “sections-only ingestion에서는 상세 장학정보가 검색 corpus에 존재하지 않았다”는 점입니다.

또한 모든 HTML을 무차별적으로 추가한 variant는 기존 70문항 성능을 떨어뜨렸습니다. 따라서 HTML은 **sections가 비어 있거나 원문 대비 지나치게 축약된 문서에만 선택적으로 구조화 ingest**하는 방향이 적절합니다.

## 6. 현재 결론

1. 기존 section 단위는 긴 규칙/목록에서 관련 fact가 희석되는 문제가 있습니다.
2. 120~190자 수준의 fact-aware atomic chunk + 1-unit overlap이 seed benchmark에서 가장 균형이 좋았습니다.
3. 하지만 chunking만으로 `전과↔모집단위이동`, 반복되는 `신청기간` heading 문제는 해결되지 않습니다. 다음 개선축은 alias/metadata-aware ranking입니다.
4. 교내장학금처럼 HTML에만 남은 상세 정보는 전처리 coverage 문제이므로 selective HTML/table extraction이 필요합니다.
5. **70문항 seed는 반드시 사람 검수 후 freeze하여 최종 benchmark로 사용**해야 합니다.

## 7. 포트폴리오에 지금 써도 되는 것 / 아직 쓰면 안 되는 것

### 지금 써도 되는 사실
- 과거 학사정보 corpus를 복원해 AWS KB 없이 오프라인 retrieval evaluation 파이프라인을 구축함.
- source/section/fact 수준의 지표를 분리해 평가하도록 구성함.
- 전처리 audit에서 section에 누락되고 HTML 표에만 존재하는 상세정보를 발견함.
- chunking/ingestion variant를 동일 benchmark에서 비교하고 회귀 사례를 분석함.

### 아직 최종 수치로 쓰면 안 되는 것
- `Section Recall@1 67.1%`, `Hard Fact Coverage@1 90%`, HTML probe `100%` 등의 값.
- 이유: 평가질문이 corpus를 본 뒤 작성된 seed이고 아직 독립적인 human review/freeze를 거치지 않았음.

## 8. 다음 실험

`seed_v0 human review → benchmark_v1 freeze → alias/metadata-aware retrieval → baseline vs final 재평가` 순서로 진행합니다. 최종 보고에서는 frozen benchmark에 대한 수치만 성능 개선 근거로 사용합니다.
