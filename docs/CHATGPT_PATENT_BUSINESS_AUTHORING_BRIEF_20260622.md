# ChatGPT 특허/사업 작성 브리프 (팩트 고정본, 2026-06-22)

## 1. 이 문서의 용도

ChatGPT에서 특허 문서, 사업 제안서, 투자 설명 자료를 작성할 때
사실/미구현 항목을 혼동하지 않도록 기준 팩트를 고정한다.

## 2. 고정 팩트 (확인됨)

1. 인증/세션 기반 사용자 운영 경로가 실제 코드에 존재한다.
2. `user_grade` 수신/저장/표시 경로가 존재한다.
3. 멀티 거래소 상태 관리 및 격리 구조가 존재한다.
4. 판단 점수/리스크/reasoning 기록 구조가 존재한다.
5. 분석/거래 로그의 DB 저장 구조가 존재한다.

근거 정본:
- [FINAL_BUSINESS_PATENT_READINESS_20260622.md](FINAL_BUSINESS_PATENT_READINESS_20260622.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [TRADING_FLOW.md](TRADING_FLOW.md)

## 3. 고정 팩트 (부분확인)

1. 특허 1순위의 "완전 감사 재현"은 현재 일부 충족 수준이다.
2. 특허 2순위의 운영 안정화 주장은 구조 근거는 충분하나,
   대외 제출용 시나리오 증빙 패키지는 추가 보강이 필요하다.

## 4. 고정 팩트 (미구현/로드맵)

1. 등급별 실행 강제 게이팅(플랜 한도 차단)은 미구현이다.
2. 자동 초과 과금/청구 파이프라인은 미구현이다.
3. 따라서 "완전 과금형 SaaS 상용 완료"로 표현하면 안 된다.

근거 정본:
- [SAAS_BUSINESS_PLAN_CODE_VERIFIED_20260609.md](SAAS_BUSINESS_PLAN_CODE_VERIFIED_20260609.md)
- [SAAS_UPDATE_PLAN_CODE_VERIFIED_20260609.md](SAAS_UPDATE_PLAN_CODE_VERIFIED_20260609.md)
- [MEMBERSHIP_FEATURE_GATING_SPEC_20260608.md](MEMBERSHIP_FEATURE_GATING_SPEC_20260608.md)

## 5. 문장 규칙 (ChatGPT에 반드시 지시)

1. "구현 완료"와 "구현 예정"을 혼용하지 말 것
2. "가능"과 "운영 중"을 구분할 것
3. "특허 출원 가능"과 "특허 등록 완료"를 구분할 것
4. 미구현 항목을 영업 문구로 확정 표현하지 말 것

## 6. 특허 문서 작성 입력 템플릿

```text
아래 NoahAI 팩트를 기준으로 특허 명세서 초안을 작성해줘.
- 구현 확인 항목: 인증/세션, user_grade 수신저장표시, 멀티거래소 상태격리, 판단/리스크/이유 로그, DB 저장
- 부분확인 항목: 완전 감사 재현, 운영 안정화 증빙 패키지
- 미구현 항목: 등급 강제 게이팅, 자동 초과 과금

요구사항:
1) 청구항 초안은 구현 근거 범위를 넘지 말 것
2) 실시예는 금융 중심으로 쓰되 범용 확장 가능성을 분리 기술할 것
3) 마지막에 "추가 증빙 필요 목록" 10개를 표로 제시할 것
```

## 7. 사업 제안서 작성 입력 템플릿

```text
아래 NoahAI 팩트 고정본을 기준으로 B2B/B2C 혼합 사업 제안서를 작성해줘.
중요: 미구현 항목(강제 게이팅/자동 과금)은 로드맵으로만 표기.

출력 형식:
1) 현재 판매 가능한 패키지
2) 90일 내 출시 가능한 업셀 패키지
3) 기술 리스크/법무 리스크/운영 리스크 표
4) 투자자용 핵심 메시지 10개
5) 과장 위험 문장과 교정 문장 대응표
```

## 8. 최종 교정 기준

ChatGPT 초안 완료 후 반드시 아래 문서로 교정한다.

1. [FINAL_BUSINESS_PATENT_READINESS_20260622.md](FINAL_BUSINESS_PATENT_READINESS_20260622.md)
2. [SAAS_BUSINESS_PLAN_CODE_VERIFIED_20260609.md](SAAS_BUSINESS_PLAN_CODE_VERIFIED_20260609.md)
3. [PATENT_PRIORITY_TOP2_20260608.md](PATENT_PRIORITY_TOP2_20260608.md)

---

작성일: 2026-06-22
기준 버전: v3.9.0.2
