# Membership Feature Gating Spec (2026-06-08)

## 목적

이 문서는 NoahAI Client에서 회원 등급별 기능 차등을 구현하기 위한 기술 스펙이다.
사업 기준은 Noahailabs/docs/proposals/BM_MEMBERSHIP_MASTER_PLAN_20260608.md를 따른다.

## 1. 등급 정의

- FREE
- BASIC
- STARTER
- PLUS
- PRO
- ENTERPRISE

## 2. 게이팅 단위

- 계정/연결 한도
  - max_connected_accounts
  - max_exchanges
  - max_brokers
  - max_concurrent_orchestration

- 사용량 한도
  - ai_call_quota_month
  - ai_call_overage_enabled
  - max_auto_trading_hours_per_day
  - max_trades_per_day

- 기능 플래그
  - can_batch_start
  - can_policy_automation
  - can_advanced_risk_policy
  - can_audit_report_export
  - can_api_sdk_access
  - can_team_rbac
  - can_multi_exchange
  - can_byok_mode

- 운영 정책
  - billing_mode
  - log_retention_days
  - support_tier
  - sla_tier

## 3. 기본 정책값 (초안)

| key | FREE | BASIC | STARTER | PLUS | PRO | ENTERPRISE |
| --- | --- | --- | --- | --- | --- | --- |
| max_connected_accounts | 1 | 1 | 2 | 5 | 20 | 40 |
| max_exchanges | 0 | 1 | 2 | 5 | 10 | 20 |
| max_brokers | 0 | 1 | 1 | 3 | 5 | 10 |
| max_concurrent_orchestration | 0 | 1 | 1 | 3 | 10 | 20 |
| ai_call_quota_month | 50 | 1000 | 5000 | 20000 | 100000 | custom |
| ai_call_overage_enabled | false | true | true | true | true | custom |
| max_auto_trading_hours_per_day | 0 | 1 | 2 | 6 | 24 | 24 |
| max_trades_per_day | 0 | 5 | 20 | 80 | 300 | custom |
| can_batch_start | false | false | false | true_limited | true | true |
| can_policy_automation | false | false | false | true_limited | true | true |
| can_advanced_risk_policy | false | false | false | true | true | true |
| can_audit_report_export | false | basic | basic | enhanced | advanced | custom |
| can_api_sdk_access | false | false | false | limited | true | true |
| can_team_rbac | false | false | false | limited | true | true |
| can_multi_exchange | false | false | limited | true | true | true |
| can_byok_mode | false | true | true | true | true | true |
| billing_mode | none | platform_or_byok | platform_or_byok | platform_or_byok | platform_or_byok | custom |
| log_retention_days | 7 | 30 | 30 | 90 | 365 | custom |
| support_tier | community | standard | standard | priority | priority_plus | sla |
| sla_tier | none | none | none | basic | standard | custom |

## 4. BYOK 분리 정책

- Platform mode
  - NoahAI가 AI API 호출을 대행
  - 고객은 구독 + 호출 초과 과금을 지불

- BYOK mode
  - 고객이 자신의 AI API 키를 직접 등록
  - 고객이 AI 호출비를 직접 부담
  - NoahAI는 플랫폼 이용료/자동화/운영 기능에 대해 과금

## 5. 구현 지점 (권장)

- 인증/세션 계층: 사용자 등급 로드
- 권한 계층: 기능 플래그 판정 함수
- 실행 계층: 동시 실행 한도, 자동매매 시간, 거래횟수 체크
- 호출 계층: 월 호출량 및 초과과금 카운터 반영
- 리포트 계층: 내보내기/보관 기간 제한
- UI 계층: 비활성 기능 숨김 또는 락 배지 노출

## 6. 핵심 가드

- 서버/클라이언트 이중 검증
- 플랜 변경 시 즉시 반영 + 캐시 무효화
- 다운그레이드 시 초과 리소스 안전 종료
- BYOK 키 유효성 검증 및 실패 시 안전 폴백
- 오류 메시지는 기능명 + 업그레이드 안내를 명확히 표기

## 7. 이벤트 로깅

- feature_gate_denied
- plan_limit_reached
- ai_call_quota_exceeded
- byok_key_validation_failed
- upgrade_prompt_shown
- upgrade_completed
- downgrade_applied

## 8. 테스트 시나리오

1. FREE에서 자동매매 시간/거래횟수 제한 차단 확인
2. BASIC에서 일일 1시간 초과 시 자동 중지 확인
3. STARTER에서 일일 거래횟수 20회 초과 차단 확인
4. PLUS에서 다중 거래소 제한 규칙 동작 확인
5. PRO에서 24시간 운용 및 호출 초과 과금 동작 확인
6. BYOK 사용자 호출비 대행 미청구 확인
7. 플랜 업그레이드/다운그레이드 직후 권한 반영 확인

## 9. 릴리즈 순서

1. 읽기 전용 기능 게이팅 적용
2. 실행 한도 게이팅(시간/횟수/동시성) 적용
3. 호출량 카운터 및 초과과금 연동
4. BYOK 모드 연동
5. 관리자 콘솔 플랜 오버라이드 추가

---

작성일: 2026-06-08
문서 상태: 구현 스펙 초안 v1.1
