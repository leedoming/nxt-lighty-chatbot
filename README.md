# nxt-lighty-chatbot

광주대학교 학사정보를 Slack에서 질의할 수 있도록 구축한 RAG 챗봇의 Lambda 애플리케이션 코드입니다.

## Service flow

```text
Slack question
  -> AWS Lambda / Slack Bolt
  -> thread or DM history collection
  -> prompt construction
  -> Amazon Bedrock Agent
  -> academic-information knowledge source
  -> tagged response parsing
  -> department routing / Slack Block Kit
  -> DynamoDB context and interaction state
```

주요 구현은 Bedrock 호출, Slack 이벤트 처리, 대화 이력, 응답 파싱, 담당 부서 버튼 및 DynamoDB 상태 관리를 모듈로 분리해 구성했습니다.

## Retrospective RAG evaluation

초기 개발 당시에는 서비스 구현과 정성 테스트에 집중했기 때문에, 이후 원본 학사정보 corpus와 실제 운영 응답을 복원해 **offline RAG evaluation**을 추가했습니다.

평가 범위:

- corpus 품질 및 ingestion 누락 점검
- document / section Retrieval Recall@K, MRR
- retrieved evidence Fact Coverage
- fact-aware chunking A/B
- 사용자 용어 ↔ 행정 용어 alias 및 metadata-aware reranking
- historical Slack final-answer correctness / completeness / groundedness
- thread vs DM multi-turn context retention / reference resolution
- abstention, department routing, format 및 delivery failure 분석

자세한 재현 방법과 해석상 주의점은 [`evaluation/README.md`](evaluation/README.md)를 참고하세요.

> Note: 오프라인 retrieval 수치는 과거 Bedrock Knowledge Base 자체를 재측정한 결과가 아니라, 2025-03-25에 수집된 동일 원천 corpus를 복원해 수행한 benchmark입니다. 개발용 seed benchmark에서 튜닝된 수치는 최종 production accuracy로 해석하지 않습니다.
