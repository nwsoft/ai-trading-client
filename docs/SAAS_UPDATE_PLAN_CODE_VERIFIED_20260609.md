# NoahAI Client SaaS 업데이트 플랜 (코드 검증 기반, 2026-06-09)

## 1. 목적

이 문서는 실제 코드 상태를 기준으로 NoahAI Client를 SaaS 운영 구조로 전환하기 위한 개발 플랜을 정의한다.

## 2. 코드 검증 결과 (현 상태)

- 인증/세션 서버 연동은 이미 동작 중
  - 클라이언트 상태체크 서버 URL: user_status_manager.py -> https://daltrading.net
  - 로그인/상태 체크 엔드포인트 사용: /auth/api_login, /auth/check_status
- 사용자 등급 데이터는 수신/저장됨
  - login_modern.py: user_grade를 token.json에 저장
  - main.py + api/backend_api.py: user_grade 로드/설정
- 그러나 등급별 기능 제한(실행 게이팅)은 코드에 실구현 미완
  - user_grade는 주로 표시/로그 용도
  - 문서 스펙은 존재: docs/MEMBERSHIP_FEATURE_GATING_SPEC_20260608.md

판정:

- SaaS 전환 기반(인증, 세션, 관리자 등급 변경)은 있음
- 실제 과금/제한형 SaaS(쿼터, 동시성 제한, 초과 과금)는 구현 필요

## 3. 핵심 갭

1. 등급별 실행 게이트 미구현
- max_exchanges, max_brokers, max_concurrent_orchestration
- ai_call_quota_month, max_auto_trading_hours_per_day, max_trades_per_day

2. 서버-클라이언트 정책 동기화 미구현
- 로그인 시 user_grade만 받고 상세 플랜 정책은 받지 않음
- 정책 캐시/버전 관리 부재

3. 과금 이벤트/초과 과금 집계 미구현
- 초과 사용량 집계 이벤트와 청구 연동 필요

## 3-1. 증권사 SaaS 온보딩 게이트 (2026-06-17 추가)

증권사 연동은 "API 존재 여부"가 아니라 아래 4개 기준 충족으로 온보딩 승인한다.

1. 개인 사용 가능 (개인 계정 신청/승인 가능)
2. 서버 동작 가능 (클라이언트 PC 종속 없이 서버 경로 운영 가능)
3. 다수 고객 계좌 연결 가능 (멀티 테넌트 운영 시나리오 허용)
4. 약관/제휴 정책 허용 (서비스 약관/제휴 조건 위배 없음)

운영 규칙:
- 4개 중 1개라도 불충족이면 "연구/PoC" 상태로 분류하고 상용 기본 온보딩에서 제외
- 각 항목은 증권사 공식 문서 URL + 내부 검증 로그를 증빙으로 남긴다
- 키움의 경우 REST 포털 존재 사실과 별개로, 현재 클라이언트 구현(OpenAPI+ ActiveX)과 SaaS 서버 경로를 분리해 판단한다

## 4. 개발 단계 (실행 순서)

### Phase 1 (1주): 정책 조회/캐시 계층

- 서버 API 추가
  - GET /auth/plan_policy
  - 응답: 플랜별 한도/기능 플래그/버전
- 클라이언트 구현
  - api/backend_api.py에 plan_policy 조회 메서드 추가
  - 로그인 직후 정책 캐시 저장(token.json 분리 권장)

산출물:

- 정책 스키마 문서
- 정책 버전 필드(policy_version)

### Phase 2 (2주): 실행 게이팅 적용

- 게이팅 적용 지점
  - 거래소/증권사 연결 시점: max_exchanges, max_brokers
  - 모두 시작/배치 시작: max_concurrent_orchestration
  - 자동매매 루프: max_auto_trading_hours_per_day, max_trades_per_day
  - AI 호출 경로: ai_call_quota_month, ai_call_overage_enabled
- UI 반영
  - 제한 기능 비활성화/배지/업그레이드 안내

산출물:

- gate_decision 모듈
- feature_gate_denied, plan_limit_reached 로그 이벤트

### Phase 3 (1주): BYOK/Platform 분기

- billing_mode에 따라 호출비 처리 분기
  - platform_or_byok
- BYOK 키 검증 실패 시 안전 폴백

산출물:

- byok_key_validation_failed 이벤트
- BYOK/Platform 상태 UI

### Phase 4 (1주): 과금 이벤트/운영 리포트

- 초과 이벤트 집계
  - ai_call_quota_exceeded
  - auto_trading_time_exceeded
- 관리자 대시보드 노출
  - 플랜별 제한 도달률
  - 업그레이드 전환율

## 5. 수용 기준 (Definition of Done)

- FREE/BASIC/STARTER/PLUS/PRO/ENTERPRISE 테스트 케이스 통과
- 플랜 변경 후 60초 이내 정책 반영
- 다운그레이드 시 초과 리소스 안전 종료
- 30일 운영에서 제한 판단 오류율 0.5% 미만

## 6. 위험 및 대응

- 위험: 클라이언트 단독 검증 우회
- 대응: 서버 최종 검증 이중화 필수

- 위험: 정책 변경 시 캐시 불일치
- 대응: policy_version 비교 + 강제 무효화

---

문서 상태: Update Plan v1.0 (code-verified)
