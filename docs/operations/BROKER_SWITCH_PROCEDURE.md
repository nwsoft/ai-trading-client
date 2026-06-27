# 브로커 전환 절차

## 목적
- 장애/정책 이슈 시 실주문 브로커를 안전하게 전환한다.

## 사전 조건
- 대상 브로커 api_type/api_version 조합 유효
- 인증정보(account_no, app_key/app_secret 또는 id/password) 준비
- allow_live_order, enable_stock_live_order 정책 확인

## 전환 순서
1. 기존 브로커 주문 중지
- global_kill_switch ON
- 기존 브로커 allow_live_order OFF

2. 대상 브로커 설정 적용
- stock_broker_configs.<broker>.enabled = true
- api_type/api_version 지정
- 인증정보 입력

3. 점검 실행
- stock_d1_preflight.py
- stock_supported_mode_matrix_check.py
- stock_live_readiness_run.py --all-supported-brokers

4. 제한 모드 재가동
- 소량 주문수/작은 수량으로 AUTO 1~2사이클
- execution_metrics(지연, 실패율, 슬리피지) 확인

5. 정상 복귀
- global_kill_switch OFF
- 운영 한도(일/주/월 손실, 집중도) 재확인

## 롤백
- 전환 후 실패 시 즉시 대상 브로커 allow_live_order OFF
- 기존 브로커 설정으로 복귀 후 readiness 재검증
