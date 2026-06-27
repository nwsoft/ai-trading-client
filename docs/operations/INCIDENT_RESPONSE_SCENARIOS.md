# 장애 시나리오 대응 절차

## 시나리오 1: 주문 실패율 급증
증상
- trade_order_failed 이벤트 급증
- execution_metrics.reject_rate 상승

대응
1. global_kill_switch ON
2. 브로커별 API 응답 지연 확인
3. stock_live_smoke_check.py 재실행
4. 실패 코드/메시지 상위 3개 원인 분류
5. 수정 후 소액 재가동

## 시나리오 2: 중복 주문 발생 의심
증상
- 동일 종목/방향/수량 주문이 짧은 시간 내 반복

대응
1. 자동매매 즉시 중지
2. stock_order_idempotency 키 로그 확인
3. 브로커 측 미체결/체결 상태 비교
4. 중복 원인(재시작/네트워크 재전송) 확인
5. 재시작 후 runtime sync 상태 확인

## 시나리오 3: 손실 급증
증상
- 일/주/월 손실 한도 접근 또는 초과

대응
1. risk_governance_enabled 확인
2. daily/weekly/monthly 한도 점검
3. max_symbol_weight_percent 초과 여부 점검
4. 필요 시 손실 한도 보수화
5. 전략 임계값 재검토 후 재개

## 시나리오 4: 브로커 장애
증상
- 특정 브로커 connect/balance/orders 실패

대응
1. 해당 브로커 allow_live_order OFF
2. 대체 브로커 전환 절차 수행
3. preflight + readiness 재검증
4. 장애 브로커 복구 후 단계적 복귀
