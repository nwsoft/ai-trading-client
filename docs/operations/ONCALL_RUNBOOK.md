# 증권 자동매매 온콜 런북

## 목적
- 장애 또는 이상 거래 상황에서 운영자가 즉시 점검/차단/복구를 수행한다.

## 필수 점검 순서
1. 프로세스 상태 확인
- 클라이언트 실행 여부, 브로커 연결 상태, 최근 주문 로그 확인

2. 즉시 위험 차단
- 설정에서 stock_auto_trading.global_kill_switch = true
- 자동매매 모드(AUTO) 비활성화

3. 현재 노출 확인
- 미체결 주문 수
- 보유 포지션 수량/평가금
- 최근 1시간 주문 성공/실패 비율

4. 루트 원인 분류
- 브로커 인증 오류
- 브로커 API 지연/장애
- 정책 차단(손실 한도/가드레일/거버넌스)
- 코드 예외

5. 복구 검증
- stock_live_readiness_run.py --all-supported-brokers 실행
- test_stock_live_readiness_scripts.py 최소 회귀
- 자동매매 1사이클 dry 확인

## 긴급 중지 체크리스트
- global_kill_switch ON
- enable_stock_live_order OFF
- broker.allow_live_order OFF
- AUTO 모드 OFF

## 재가동 체크리스트
- PRECHECK 경고/차단 해소
- 브로커별 주문 drill skip 사유 해소
- 최근 주문 실패 원인 해결
- 소액 모드로 1~2 사이클 관찰 후 정상화
