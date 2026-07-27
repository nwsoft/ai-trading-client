# Membership Feature Gating Runtime Spec (2026-06-26)

## 1. 목적

본 문서는 기존 정책 문서(MEMBERSHIP_FEATURE_GATING_SPEC_20260608.md)를
실행 가능한 런타임 스펙으로 구체화한다.
핵심은 "등급 표시"가 아니라 "등급 강제"다.

## 2. 가능 여부 판정

판정: 레퍼럴 등급의 서버 정책·공식 클라이언트 실행 게이트·운영 KPI 1차 구현 완료

근거:
- 사용자 인증/세션/등급 수신 경로는 이미 존재
  - user_status_manager.py, api/backend_api.py
- code-verified 문서에서 등급 강제 게이팅 미구현이 이미 확인됨
  - docs/SAAS_UPDATE_PLAN_CODE_VERIFIED_20260609.md

2026-07-27 구현 범위:

- `referral / pro_coin / pro_stock / premium` 서버 등급 계약
- 서버 관리자 레퍼럴 거래소·코드·URL 관리
- 로그인 및 1분 상태 확인 정책 갱신
- 레퍼럴 국내 거래소·국내 증권 설정 제거
- 거래소 시작 직전 실행 게이트
- 사용자별 동시 실행 거래소 수 KPI

남은 범위는 변조 바이너리까지 서버에서 차단하는 주문 프록시/원격 증명과 일반 SaaS 요금제의 호출량·시간·거래횟수 과금 게이트다.

## 3. 용어

- role: 권한 역할 (admin, operator, user)
- tier: 과금 등급 (free, basic, starter, plus, pro, enterprise)
- entitlements: 기능/한도 정책 집합
- policy_version: 정책 버전

## 4. 서버 응답 스키마 (로그인/리프레시 공통)

```json
{
  "user": {
    "id": "u_123",
    "email": "user@example.com",
    "role": "user",
    "tier": "starter"
  },
  "policy": {
    "policy_version": "2026-06-26.1",
    "expires_at": "2026-07-26T00:00:00Z",
    "entitlements": {
      "max_exchanges": 2,
      "max_brokers": 1,
      "max_concurrent_orchestration": 1,
      "ai_call_quota_month": 5000,
      "ai_call_overage_enabled": true,
      "max_auto_trading_hours_per_day": 2,
      "max_trades_per_day": 20,
      "can_multi_exchange": false,
      "can_policy_automation": false,
      "can_advanced_risk_policy": false,
      "can_team_rbac": false
    }
  },
  "server_time": "2026-06-26T10:00:00Z"
}
```

## 5. 클라이언트 캐시 정책

### 5-1. 저장 구조

- token.json
  - 최소 인증 정보 + user.id + role + tier
- plan_policy_cache.json (신규 권장)
  - policy_version
  - entitlements
  - fetched_at
  - expires_at

### 5-2. 갱신 규칙

- 로그인 성공 시 즉시 갱신
- 앱 시작 시 만료 여부 확인
- 실행 중 1분 주기 정책 재검증
- policy_version 변경 시 즉시 캐시 무효화

## 6. 런타임 게이팅 적용 지점

### 6-1. UI 게이트 (표시 계층)

- 탭/버튼 비활성화 + 락 배지 + 업그레이드 CTA
- 예: 고급 리스크 정책, 배치 시작, 다중 거래소

주의:
- UI 게이트는 안내 목적이며 보안 경계가 아니다.

### 6-2. 실행 게이트 (강제 계층)

필수 강제 지점:
- 거래소/브로커 연결 시
  - max_exchanges, max_brokers
- 오케스트레이션 시작 시
  - max_concurrent_orchestration
- 자동매매 루프
  - max_auto_trading_hours_per_day
  - max_trades_per_day
- AI 호출 경로
  - ai_call_quota_month
  - ai_call_overage_enabled

실행 거부 시 표준 이벤트:
- feature_gate_denied
- plan_limit_reached
- ai_call_quota_exceeded

## 7. 권한 판단 함수 표준

```python
def evaluate_gate(action: str, context: dict, policy: dict) -> tuple[bool, str]:
    ent = policy.get("entitlements", {})

    if action == "connect_exchange":
        if context.get("connected_exchanges", 0) >= ent.get("max_exchanges", 0):
            return False, "max_exchanges"

    if action == "start_auto_trading":
        if context.get("today_trading_hours", 0) >= ent.get("max_auto_trading_hours_per_day", 0):
            return False, "max_auto_trading_hours_per_day"
        if context.get("today_trade_count", 0) >= ent.get("max_trades_per_day", 0):
            return False, "max_trades_per_day"

    if action == "ai_call":
        if context.get("month_ai_calls", 0) >= ent.get("ai_call_quota_month", 0):
            if not ent.get("ai_call_overage_enabled", False):
                return False, "ai_call_quota_month"

    return True, "ok"
```

## 8. 오프라인/만료 정책

기본 원칙: 서버 권한 우선

- soft grace: 24시간
  - 마지막 유효 정책으로 조회/모니터링 기능만 허용
- hard expiry: 24시간 초과
  - 실주문/자동매매/유료 기능 차단
- 재연결 시 서버 정책 즉시 재적용

## 9. 서버 우선 원칙 (우회 방지)

- 클라이언트 정책은 편의 캐시로만 사용
- 서버 API는 최종 권한 재검증 필수
  - 주문 실행
  - AI 유료 호출
  - 리포트 내보내기 등 과금 민감 기능
- 레퍼럴 정책 캐시 누락·문자열 변조·국내 거래소 주입은 공식 클라이언트 실행 게이트에서 fail-closed 한다.
- 거래소 주문이 사용자 PC에서 직접 나가는 동안에는 재작성된 비공식 바이너리를 서버가 완전히 통제할 수 없다. 절대적인 서버 차단을 요구하면 주문 프록시 또는 원격 증명 계층을 도입한다.

## 10. 감사 로그/정책 전파

필수 로그 이벤트:
- feature_gate_denied
- plan_limit_reached
- ai_call_quota_exceeded
- policy_cache_refreshed
- policy_cache_expired
- policy_version_mismatch
- downgrade_applied

운영 대시보드 지표:
- tier별 차단률
- 차단 후 업그레이드 전환율
- policy_version 불일치율

## 11. 기존 코드와의 호환 레이어

- 기존 user_grade 필드는 tier로 매핑하여 유지
- 미수신 사용자 기본값:
  - role=user
  - tier=free
- settings.json의 subscription_tier는 서버 미연결 시 임시 fallback으로만 사용

## 12. 단계별 도입 순서

### Phase A (1주)

- policy API 연동
- 캐시 파일 분리(plan_policy_cache.json)
- UI 읽기 전용 게이트 적용

### Phase B (2주)

- 실행 게이트 적용 (거래소/자동매매/AI 호출)
- 표준 거부 사유 코드 정착

### Phase C (1주)

- 서버 최종 재검증 연동
- 오프라인 만료 정책/강제 차단 적용

### Phase D (1주)

- 운영 리포트/대시보드
- 업그레이드 퍼널 최적화

## 13. 테스트 수용 기준

- FREE/BASIC/STARTER/PLUS/PRO/ENTERPRISE 정책 테스트 통과
- 정책 변경 후 60초 이내 반영
- 오프라인 24시간 초과 시 유료 실행 차단 100%
- 공식 클라이언트 정책 캐시 조작·국내 거래소 주입 차단 100%
- 변조 바이너리 서버 최종 차단은 주문 프록시/원격 증명 도입 후 별도 수용 기준

## 14. 결론

회원 등급 기반 기능 제한은 현재 코드 기반에서 충분히 구현 가능하다.
이미 존재하는 인증/세션/등급 수신 경로 위에,
정책 캐시 + 실행 게이트 + 서버 최종 검증을 추가하면
문서 스펙을 운영 가능한 SaaS 게이트로 전환할 수 있다.

---
문서 상태: runtime draft v1.0
