# 증권 실연동 준비 체크리스트 (2026-04-28)

## 목적

증권 실주문 전, D1 사전점검 스크립트와 동일 기준으로
브로커별 필수 입력값과 차단 조건을 점검한다.

- 실행 스크립트: scripts/stock_d1_preflight.py
- 통과 기준: BLOCKED 없이 READY_FOR_NEXT_STEP

## 공통 차단 조건

- api_type/api_version 조합이 지원 목록과 불일치
- live_api 경로인데 브로커별 필수 인증값 누락
- 핵심 파일 누락

## 브로커별 필수값

### 키움 (kiwoom, openapi/pykiwoom)

#### 사전 환경 요건 (Windows 전용)
- `pip install pykiwoom>=0.1.9 PyQt5>=5.15.0` (Windows 빌드 PC에서 1회 실행)
- 키움증권 HTS 설치 (OpenAPI+ 활성화 포함)
- macOS/Linux에서는 `api_version: mock` 설정 후 데모 모드만 사용 가능

필수 설정값:
- id
- password
- cert_password
- account_no

추가 제약:

- macOS/Linux 에서는 실주문 검증 제한 (Windows + pykiwoom 필요)

### 신한 (shinhan, rest/openapi)

- app_key
- app_secret
- account_no

### 미래에셋 (miraeAsset, rest/openapi)

- app_key
- app_secret
- account_no

## 실주문 활성 조건

아래 2개가 모두 true여야 실제 live 주문 경로가 열린다.

- 전역 플래그: enable_stock_live_order=true
- 브로커 플래그: stock_broker_configs.[broker].allow_live_order=true

## 권장 절차

한 번에 실행하려면 아래 전체 실행기를 사용한다.

- `python scripts/stock_live_readiness_run.py --broker kiwoom`
- 엄격 모드: `python scripts/stock_live_readiness_run.py --broker kiwoom --strict`

1. settings에서 브로커별 필수값 입력
2. scripts/stock_d1_preflight.py 실행
3. BLOCKED 원인 제거
4. scripts/stock_live_smoke_check.py 실행
5. scripts/stock_live_order_drill.py --broker BROKER_NAME 실행 (기본 dry-run)
6. tests/test_stock_integration.py 재실행
7. 필요 시 명시 옵션으로 소량 주문/취소 drill 실행

## smoke 점검 스크립트

- 기본 실행: `python scripts/stock_live_smoke_check.py`
- 엄격 모드: `python scripts/stock_live_smoke_check.py --strict`

동작 원칙:

- preflight 기준으로 live 준비가 안 된 브로커는 자동 skip
- 기본 모드는 "실행 대상 없음"이어도 종료코드 0
- `--strict`에서는 실행 대상 없음/실패 시 종료코드 1

## order drill 스크립트

- 기본 dry-run: `python scripts/stock_live_order_drill.py --broker kiwoom`
- 엄격 모드: `python scripts/stock_live_order_drill.py --broker kiwoom --strict`
- 실제 주문 실행: `python scripts/stock_live_order_drill.py --broker kiwoom --execute --symbol 005930 --quantity 1 --order-type LIMIT --price 70000`
- 주문 후 즉시 취소 시도: `python scripts/stock_live_order_drill.py --broker kiwoom --execute --cancel-after ...`

동작 원칙:

- 기본은 dry-run이며 절대 주문하지 않음
- `--execute`가 있어야 실제 주문 호출
- `--execute`에서도 live order flag가 꺼져 있으면 skip 또는 strict fail

## 전체 실행기

- 파일: `scripts/stock_live_readiness_run.py`
- 순서: preflight -> smoke -> order drill(dry-run)
- 기본 모드: 단계 결과를 모두 보고
- `--strict`: preflight/smoke/drill 중 skip 또는 실패를 종료코드 1로 처리
