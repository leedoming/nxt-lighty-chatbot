# Corpus audit — 광주대 Lighty 학사정보 snapshot

## Snapshot

- JSON 학사정보: **41개**
- PDF: **6개**
- DOCX: **5개**
- XLSX: **2개**
- TXT: **1개**
- 41개 JSON의 `crawled_date`: **2025-03-25**
- JSON metadata: `title`, `sections`, `url`, `mn`, `dep`, `dep_tel` 중심

## 평가에 우선 사용하기 좋은 데이터

41개 JSON은 질문-정답 근거를 만들기 좋다. 특히 휴학/복학/재입학/자퇴/졸업/수강/성적/장학/증명발급은 규정·기간·학점·절차가 명시돼 있어 retrieval benchmark의 gold source를 명확히 지정할 수 있다.

`광주대_부서연락처 및 업무 상세.txt`는 부서 routing 정답표 보조자료로 유용하다. 다만 문서 첫 문장과 서술 형태상 원천 웹페이지를 그대로 저장한 1차 자료라기보다 재정리된 2차 자료로 보이므로, 학사 사실값의 gold source로는 JSON을 우선한다.

## ingest 전에 제거/격리할 파일

- `숙명여대_교내 전화번호부2021.pdf`
- `숙명여대_교내 전화번호부2021.xlsx`
- `~$대_대학기관안내.docx` — Office 임시/잠금 파일

이 파일들이 운영 KB에 실제 ingest됐는지는 현재 자료만으로 확인할 수 없다. 다만 원본 폴더 단위 ingest를 다시 한다면 allow-list가 필요하다.

## 중복 가능성이 높은 자료

동일 정보를 서로 다른 포맷으로 보관한 쌍이 있다.

- 광주대 대학기관안내: DOCX + PDF
- 광주대 시설및생활안내: DOCX + PDF
- 광주대 증명서발급: DOCX + PDF
- 광주대 통학버스: DOCX + PDF
- 광주대 교내전화번호부: PDF + XLSX

모두 ingest하면 같은 근거가 검색 결과 상위에 중복 노출돼 다양성이 떨어질 수 있다. 오프라인 benchmark에서는 우선 JSON corpus만 사용했다.

## JSON parsing 품질 이슈

### 1. HTML에 정보가 더 많이 남아 있는 문서

일부 파일은 `sections`보다 `html_content`가 훨씬 크다.

- `교내장학금_498`: sections 약 201자 / HTML 약 9,400자
- `기준학점_475`: sections 약 403자 / HTML 약 2,550자
- `조기졸업_468`: sections 약 422자 / HTML 약 1,260자
- `오버라이드_476`: sections 약 154자 / HTML 약 771자

따라서 `sections`만 임베딩하면 표·세부조건 일부가 누락될 가능성이 있다. 최종 ingestion에서는 HTML table/list를 구조적으로 파싱하거나, sections와 HTML의 정보차를 검사해야 한다.

### 2. HTML-only 문서

- `강의실표기안내_490`
- `3월중 일정표_495`
- `3월중 일정표_496`

표가 평문으로 길게 붙어 있어 semantic chunking 없이는 검색 품질이 떨어질 수 있다.

### 3. department metadata 품질

- `dep`가 비어 있는 JSON 4개
- `헤이영캠퍼스_937`의 `dep`는 `수업학적팀팀`으로 오타가 있음
- `교무처` 하나로 묶여 있지만 실제 문의번호는 수업/학적/현장실습 등 업무별로 여러 개라, 부서 routing을 평가할 때는 최종적으로 **부서+업무 subtype**을 구분하는 편이 정확하다.

## 1차 오프라인 retrieval sanity check

70개 seed 질문(`seed_v0_needs_human_review`)으로 파이프라인 자체를 점검했다. 질문은 원문을 보고 작성했기 때문에 아래 수치는 **최종 포트폴리오 성능값이 아니다.**

- Whole-document BM25: document Recall@1 **67.1%**, Recall@5 **85.7%**
- Section character n-gram TF-IDF: document Recall@1 **85.7%**, Recall@5 **100%**; section Recall@1 **54.3%**, Recall@5 **98.6%**
- Section char TF-IDF + title boost: document Recall@1 **90.0%**; section Recall@1 **58.6%**, MRR **0.736**
- Hierarchical char retrieval + title boost: document Recall@1 **91.4%**; section Recall@1 **61.4%**, MRR **0.740**

이 결과는 한국어 학사질의에서 단순 whitespace/token BM25보다 character n-gram 기반 lexical retrieval이 강한 baseline이 될 수 있음을 보여준다. 다만 최종 수치는 사용자 표현으로 독립 작성한 held-out 질문셋에서 다시 측정해야 한다.

## 현재 failure pattern

seed benchmark에서 section retrieval이 자주 헷갈리는 유형:

- 동일 문서 안에 `신청기간`, `신청방법`, `유의사항`처럼 비슷한 section이 반복되는 경우
- `계절학기`처럼 한 질문의 답이 두 section에 걸쳐 있는 경우
- `복학`처럼 동일 키워드가 개별 안내 문서와 월별 학사일정 양쪽에 존재하는 경우
- 졸업요건처럼 한 section이 매우 길고 여러 입학연도/학과 조건을 한꺼번에 포함하는 경우

다음 실험은 긴 section을 더 작은 의미 단위로 나누고, `document title → section`의 2단계 검색을 적용하는 것이 타당하다.
