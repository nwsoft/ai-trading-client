# ChatGPT Project Knowledge Pack (2026-06-22)

## 1. 목적

ChatGPT Pro 프로젝트에 문서를 대량 업로드할 때,
중복/이력 문서로 컨텍스트를 낭비하지 않고 특허/비즈니스 문서 작성에 바로 쓰이는
핵심 문서를 우선 투입하기 위한 기준서다.

## 2. 업로드 전략 (크레딧/컨텍스트 절약)

1. Tier 1(필수 정본)만 먼저 업로드한다.
2. ChatGPT가 문맥을 안정적으로 잡은 뒤 Tier 2, Tier 3를 순차 추가한다.
3. 이력성/중복 문서는 기본적으로 제외한다.

## 3. Tier 1: 필수 정본 (먼저 업로드)

1. [MASTER_DOCUMENTATION.md](MASTER_DOCUMENTATION.md)
2. [CHANGELOG.md](CHANGELOG.md)
3. [ARCHITECTURE.md](ARCHITECTURE.md)
4. [TRADING_FLOW.md](TRADING_FLOW.md)
5. [TEST_STATUS.md](TEST_STATUS.md)
6. [SAAS_BUSINESS_PLAN_CODE_VERIFIED_20260609.md](SAAS_BUSINESS_PLAN_CODE_VERIFIED_20260609.md)
7. [SAAS_UPDATE_PLAN_CODE_VERIFIED_20260609.md](SAAS_UPDATE_PLAN_CODE_VERIFIED_20260609.md)
8. [PATENT_PRIORITY_TOP2_20260608.md](PATENT_PRIORITY_TOP2_20260608.md)
9. [PATENT_INVESTOR_IP_BRIEF_20260608.md](PATENT_INVESTOR_IP_BRIEF_20260608.md)
10. [FINAL_BUSINESS_PATENT_READINESS_20260622.md](FINAL_BUSINESS_PATENT_READINESS_20260622.md)
11. [NOAHAI_IR_TECHNICAL_BRIEF.md](NOAHAI_IR_TECHNICAL_BRIEF.md)
12. [NOAHAI_IR_MASTER.md](NOAHAI_IR_MASTER.md)

## 4. Tier 2: 특허 작성 강화팩 (필요 시 추가)

1. [PATENT_SPEC_DRAFT_20260608.md](PATENT_SPEC_DRAFT_20260608.md)
2. [ARCHITECTURE.md](ARCHITECTURE.md)
3. [AI_API_ARCHITECTURE.md](AI_API_ARCHITECTURE.md)
4. [operations/INCIDENT_RESPONSE_SCENARIOS.md](operations/INCIDENT_RESPONSE_SCENARIOS.md)
5. [LEGAL_RESPONSIBILITY_BOUNDARY_20260428.md](LEGAL_RESPONSIBILITY_BOUNDARY_20260428.md)

## 5. Tier 3: 사업 제안/IR 강화팩 (필요 시 추가)

1. [BUSINESS_PROPOSAL_2026.md](BUSINESS_PROPOSAL_2026.md)
2. [KPI_VC_TIPS_GUIDE_20260428.md](KPI_VC_TIPS_GUIDE_20260428.md)
3. [BROKER_EXPANSION_ROADMAP.md](BROKER_EXPANSION_ROADMAP.md)
4. [UPDATE_PLAN.md](UPDATE_PLAN.md)
5. [LEGAL_PACKAGE_20260428_INDEX.md](LEGAL_PACKAGE_20260428_INDEX.md)

## 6. 기본 제외 권장 (컨텍스트 낭비 방지)

- 동일 주제의 과거 이력 문서 다수
- 날짜 고정 스냅샷 문서(현재 정본이 있는 경우)
- 테스트 중간 산출물/초기 분석 드래프트

예시:
- `*_20260118.md`, `*_20260424.md` 계열 과거 상태 문서 다수
- 동일 기능에 대한 root-cause/history 전용 문서 다수

## 7. ChatGPT 작업 순서 (권장)

1. Tier 1 업로드
2. 아래 고정 프롬프트로 "팩트 추출표" 생성
3. 특허 문서 작업이면 Tier 2 추가
4. 사업/제안서 작업이면 Tier 3 추가
5. 초안 완료 후 [FINAL_BUSINESS_PATENT_READINESS_20260622.md](FINAL_BUSINESS_PATENT_READINESS_20260622.md)로 문구 교정

## 8. ChatGPT 시작 프롬프트 (복붙용)

```text
업로드한 NoahAI 문서를 기준으로, 다음 형식으로만 정리해줘.
1) 확인된 사실(코드/문서 정합)
2) 부분확인 사실(추가 증빙 필요)
3) 미구현/로드맵 항목
4) 특허 문구에서 과장 위험 문장 교정안
5) 투자/사업 제안서에서 즉시 사용 가능한 주장 10개

중요 규칙:
- 미구현 항목을 구현 완료처럼 쓰지 말 것
- "가능"과 "완료"를 구분할 것
- 결과는 표 형태 + 최종 1페이지 요약으로 출력할 것
```

## 9. 출력물 품질 규칙

- 사실 문장은 근거 문서명을 함께 표기
- 수치/버전은 최신 기준선으로 통일(`v3.9.0.2`)
- "자동 과금/강제 게이팅"은 구현 전까지 로드맵으로만 표기

---

작성일: 2026-06-22
적용 범위: ChatGPT Pro 프로젝트 문서 업로드/작성 작업
