# Teayu 로그 피드백 검토 보고서 (260703 데이터)

작성일: 2026-07-05
대상: data/260703_Teayu/logs
목적: 사용자 피드백 중 실제 장애와 정상 동작(차단/정책) 구분

## 1) 결론 요약

### 실제 문제(로그 근거 있음)
1. 빗썸 거래내역 API 미지원 메시지 과다 반복
- fetch_my_trades 미지원 메시지가 455회 반복됨.
- 시간 범위: 2026-07-03 08:04:07 ~ 13:55:56
- 사용자 체감: 동일 메시지 반복으로 장애처럼 보임.

2. 일부 구간의 런타임 오류/실행 품질 저하
- 변동성 계산 오류 1회 발생.
- TP/SL 주문 미생성 경고, ticker_data 없음 경고 동반 구간 존재.
- 사용자 체감: 주문/모니터링 신뢰도 저하.

3. 시작/정지 연타 시 상태 충돌 정황
- 강제 종료 후 STOPPED 상태에서 추가 정지 요청이 들어와 Cannot stop 경고 발생.
- 사용자 체감: "멈춤" 또는 제어가 안 먹는 느낌.

### 문제 아님(정상 정책/차단 동작)
1. Binance AI 진입 전 신뢰도 부족 경고 다수
- 신뢰도 임계값 미달로 진입 거절되는 정상 가드 동작.
- 치명 오류가 아니라 "진입 차단 정책" 로그.

2. Upbit 데이터 부족 + HOLD 반복
- 데이터 부족/손실률 조건으로 HOLD 판정이 반복됨.
- 주문 엔진 장애보다 "진입 조건 미충족"에 가까움.

### 현재 데이터만으로 단정 불가
1. "Bybit처럼 8시간 멈춤" 현상
- 이번 대상 로그(trading_bybit.log) 기준 최대 무로그 공백은 3,377초(약 56분)이며 2시간 이상 공백 없음.
- 즉, 260703_Teayu 로그만 보면 Bybit 단독 8시간 완전 정지는 재현되지 않음.
- 다만 사용자가 말한 다른 날짜/다른 계정 폴더의 로그에서는 가능성이 있으므로 추가 확인 필요.

2. 거래소 Net PnL과 NoahAI PnL 차이
- 이번 로그에서 직접적인 "동일 거래의 양쪽 PnL 비교 레코드"는 부족함.
- 다만 수수료/펀딩비/슬리피지/평단 반영 시점 차이로 불일치가 발생할 수 있는 로그 패턴은 확인됨.

## 2) 핵심 근거 (라인 참조)

### A. 빗썸 fetch_my_trades 미지원 반복
- data/260703_Teayu/logs/trading_bithumb.log:4
- data/260703_Teayu/logs/trading_bithumb.log:85014

### B. 시작/정지 상태 충돌 정황
- 강제 종료: data/260703_Teayu/logs/trading.log:38991
- STOPPED 상태 추가 정지 요청: data/260703_Teayu/logs/trading.log:39042
- Bybit 정지요청 직후 STOPPED: data/260703_Teayu/logs/trading.log:39050
- Bybit 정지요청 경고: data/260703_Teayu/logs/trading.log:39051

### C. 캐시 실행 경고 (v3.8.9.26)
- data/260703_Teayu/logs/trading.log:39115
- data/260703_Teayu/logs/trading.log:39128

### D. 런타임 오류/품질 저하 구간
- 변동성 계산 오류: data/260703_Teayu/logs/trading.log:4913
- TP/SL 주문 미생성 경고: data/260703_Teayu/logs/trading.log:4951
- ticker_data 없음 경고: data/260703_Teayu/logs/trading.log:4998

### E. 정상 정책 차단(진입 거절)
- Binance 신뢰도 부족 반복 예시: data/260703_Teayu/logs/trading_binance.log:604
- Binance 신뢰도 부족 반복 예시: data/260703_Teayu/logs/trading_binance.log:14213
- Upbit 데이터 부족/손실률 기반 HOLD 예시: data/260703_Teayu/logs/trading_upbit.log:129
- Upbit 데이터 부족/손실률 기반 HOLD 예시: data/260703_Teayu/logs/trading_upbit.log:132

## 3) 피드백 항목별 판정

1. "Bybit처럼 그대로 멈춰서 8시간 이상 실행 안됨"
- 이번 260703_Teayu 로그 기준: 미확인 (증거 부족)
- 판정: 유보
- 사유: bybit 로그에서 장기 공백이 56분 수준이며, 8시간 공백은 발견되지 않음.

2. "Net상 PnL과 Noah AI PnL이 다름"
- 이번 로그 기준: 원인 후보는 다수, 단일 원인 확정은 불가
- 판정: 부분 사실 가능성 높음
- 후보 원인:
  - 실현/미실현 손익 집계 시점 차이
  - 수수료/펀딩비 반영 시점 차이
  - 평균체결가/슬리피지 처리 시점 차이
  - 부분체결/청산 구간의 집계 기준 차이

3. "실제 장애가 있었는가"
- 있었다: 변동성 계산 오류, TP/SL 미생성 경고 구간
- 아니었다: 다수의 HOLD/신뢰도 부족은 정책 차단

## 4) 운영 대응 우선순위

1. 빗썸 미지원 로그 샘플링/디바운스
- 동일 메시지 반복 간격 제한(예: 동일 키 1분 1회)으로 사용자 체감 개선.

2. 시작/정지 제어 충돌 완화
- STOPPED 상태 중복 정지 요청은 경고 대신 idempotent 성공 처리 검토.

3. PnL 비교 디버그 모드 제공
- 동일 거래에 대해 거래소 원본값과 Noah 집계값을 한 줄 비교로 기록:
  - realized, unrealized, fee, funding, slippage, avg_price, net_pnl
- 사용자 제보 시 즉시 대조 가능한 형태로 개선.

4. Bybit 8시간 멈춤 이슈 재검증
- 같은 사용자의 다른 날짜 폴더(예: data/Teayu/logs)까지 포함해 장기 공백 분석 필요.

## 5) 참고 메모

- 이번 검토는 260703_Teayu 폴더 기준이다.
- 해당 폴더의 trading.log는 6월 중순 로그까지 누적되어 있어, 날짜 필터(특히 2026-07-02~07-03)로 해석해야 정확하다.

## 6) 로그 발생 지점과 코드 매핑 (2026-07-02~07-03)

### A. "원인을 못 찾는가?"에 대한 답
- 못 찾는 것이 아니다.
- 아래 항목은 로그 문구와 코드 발생 지점이 직접 매핑된다.
- 따라서 "해결 가능/정책상 정상/추가 로그 필요"를 구분할 수 있다.

### B. 항목별 확정 매핑

1) 빗썸 fetch_my_trades 미지원 반복
- 로그: data/260703_Teayu/logs/trading_bithumb.log
- 코드 발생 지점:
  - trading/exchanges/adapters/bithumb_spot_adapter.py:251
  - trading/exchanges/adapters/bithumb_spot_adapter.py:254
  - trading/exchanges/adapters/bithumb_spot_adapter.py:260
- 해석: 어댑터가 fetch_my_trades 미지원 시 폴백하고 로그를 반복 출력하는 구조.
- 판정: 원인 확정, 해결 가능(로그 샘플링/중복 억제 적용).

2) current executable is in update cache 경고
- 로그: data/260703_Teayu/logs/trading.log:39115, 39128
- 코드 발생 지점:
  - utils/auto_update_manager.py:471
- 해석: 정상 설치 타겟이 저장되지 않은 상태에서 캐시 경로 실행이 감지된 경고.
- 판정: 원인 확정, 해결 가능(퍼시스트 타겟 초기화/복구 루틴 강화).

3) Cannot stop: current state=STOPPED
- 로그: data/260703_Teayu/logs/trading.log:39042, 39049, 39051
- 코드 발생 지점:
  - main.py:2837
- 해석: 이미 STOPPED 상태에서 정지 요청이 연달아 들어와 거절 로그가 발생.
- 판정: 원인 확정, 해결 가능(idempotent stop 처리로 UX 완화 가능).

4) AI 진입 전 분석 실패: AI 신뢰도 부족
- 로그: data/260703_Teayu/logs/trading_binance.log (다수)
- 코드 발생 지점:
  - trading/trader.py:1953
  - trading/trader.py 내부 pre-entry 분석 경로
- 해석: 장애가 아니라 정책 차단(임계값 미달).
- 판정: 문제 아님(정책 동작), 단 사용자 체감 개선을 위해 메시지 레벨/요약 개선 가능.

5) TP/SL 주문이 실제로 생성되지 않음
- 로그: data/260703_Teayu/logs/trading.log:4951
- 코드 발생 지점:
  - trading/trader.py:3410
- 해석: TP/SL 검증 단계에서 실제 주문 확인 실패.
- 판정: 원인 후보 확정, 해결 가능(재시도/검증 타이밍 및 거래소 응답 검증 강화).

6) 변동성 계산 오류
- 로그: data/260703_Teayu/logs/trading.log:4913
- 코드 발생 지점:
  - trading/trader.py:6424
  - trading/analyzer.py:1224
  - trading/unified_trader.py:5235
- 해석: 입력 데이터 형식 불일치(예: dict/list 혼재)에서 예외가 발생할 수 있는 구간.
- 판정: 원인 후보 확정, 해결 가능(입력 스키마 방어 코드 추가).

### C. Bybit 8시간 멈춤 피드백에 대한 코드 관점
- 이번 데이터셋의 bybit 로그(trading_bybit.log)에서는 8시간 무로그 공백이 확인되지 않았다.
- 다만 코드상 가능성은 있다.
  - trading/unified_trader.py:932 이후 analyze_coins_unified는 코인별 분석을 동기 순차 실행한다.
  - trading/unified_trader.py:1025 이후 execute_trading_cycle_unified도 동기 순차 실행이다.
  - 거래소 API 응답이 장시간 블로킹될 경우, "스레드는 살아있지만 진행 로그가 늦는" 체감이 발생할 수 있다.
- 판정: 260703 로그만으로 8시간 정지 확정은 불가, 그러나 구조적으로 장시간 블로킹 가능성은 존재.

### D. Net PnL vs NoahAI PnL 불일치에 대한 코드 관점
- 로그만 보면 사용자 피드백은 타당할 가능성이 높다.
- 이유: 경로별 계산 기준이 다를 수 있음.
  - trading/recorder.py:511~517
    - 청산 로그는 net_pnl_ccy = gross - fee - slippage 후 퍼센트 환산.
  - trading/unified_trader.py:2231~2232
    - 모니터링 PnL은 추정 fee/slippage(설정값)로 net_pnl_percent 계산.
  - trading/trader.py:316~332
    - 별도 실질수익률 계산(_net_pnl_percent)에서 왕복 비용 차감.
- 판정: 원인 구조 확인됨, 해결 가능(단일 기준식 통합 + 로그에 gross/net/fee/slippage 동시 출력 필요).

## 7) 무엇을 패치하고, 무엇을 정책으로 안내할 것인가

### A. 즉시 패치(버그/운영 품질)

1) 빗썸 미지원 로그 중복 억제
- 목표: 같은 원인의 경고가 장애처럼 보이지 않도록 빈도 제한.
- 적용 방향:
  - 키: exchange=bithumb, event=fetch_my_trades_unsupported
  - 정책: 최초 1회 + N분당 1회 요약(누적 횟수 포함)
- 기대효과: 사용자 체감 노이즈 급감, 실제 오류 식별력 상승.

2) STOPPED 중복 정지 요청 idempotent 처리
- 목표: 사용자가 정지 버튼을 여러 번 눌러도 실패처럼 보이지 않게 처리.
- 적용 방향:
  - current state=STOPPED면 경고 대신 성공 응답으로 처리
  - UI 상태 문구는 "이미 정지됨"으로 통일
- 기대효과: "정지가 안 된다" 착각 감소.

3) PnL 계산식 단일화
- 목표: 화면/로그/리포트의 PnL 기준을 통일.
- 적용 방향:
  - 단일 기준식 함수 1개로 통합(진입/청산/모니터링 공통 사용)
  - 동일 거래에 대해 gross, fee, slippage, funding, net을 한 줄로 같이 기록
- 기대효과: 거래소 PnL 대비 NoahAI 값 차이 설명 가능, 이슈 대응 속도 향상.

4) 장시간 블로킹 감시(8시간 멈춤 체감 완화)
- 목표: 스레드는 살아있지만 진행이 멈춘 것처럼 보이는 상태를 조기 탐지.
- 적용 방향:
  - 사이클 단계별 heartbeat 로그(phase, elapsed_sec) 추가
  - 거래소 API 호출 timeout/재시도/서킷브레이커 적용
  - 임계시간 초과 시 UI에 "지연 감지" 상태 노출
- 기대효과: 원인 미상 멈춤 체감 감소, 재현 가능성 상승.

### B. 정책상 정상(문제 아님) 항목의 사용자 오해 방지

1) 신뢰도 부족/데이터 부족은 "오류"가 아닌 "정책 차단"으로 표기
- 현재: warning 중심 로그로 장애처럼 보임.
- 변경:
  - 로그 레벨/메시지 분리: POLICY_BLOCK 카테고리 사용
  - UI 툴팁: "오류가 아니라 진입 제한 규칙으로 주문 미실행"

2) 일일 요약 리포트에 차단 사유 비중 제공
- 항목 예시:
  - 정책 차단 횟수(신뢰도 부족, 데이터 부족)
  - 실제 오류 횟수(API 실패, 예외)
  - 주문 생성/체결/청산 성공률
- 효과: 사용자가 "왜 미진입인지"를 수치로 이해 가능.

3) 용어 표준화
- "실패"와 "차단"을 구분해서 표기.
- 예시:
  - 실패: 주문 요청 실패, 계산 예외
  - 차단: 신뢰도 미달, 리스크 룰 미충족

### C. 최종 판정 기준(운영 커뮤니케이션)

1) 문제 있음(즉시 패치)
- TP/SL 미생성
- 변동성 계산 오류
- 장시간 블로킹으로 보이는 사이클 지연

2) 문제 아님(정책상 의도)
- AI 신뢰도 부족 진입 거절
- 데이터 부족으로 HOLD

3) 혼합(기능은 정상이나 UX 개선 필요)
- 빗썸 미지원 반복 로그
- STOPPED 중복 정지 요청 경고

### D. 릴리즈 반영 제안
- 다음 패치 버전에 아래를 묶어 반영:
  - 로그 중복 억제 + 정책/오류 메시지 분리
  - STOPPED idempotent 처리
  - PnL 단일 계산식 + 비교 로그
  - heartbeat/timeout 기반 지연 감지

## 8) 7/2~7/3 판단 검증 결과 (중복/모순 점검)

### A. 수치 검증 (trading.log + trading_binance.log)

1) 2026-07-02 (trading.log 단일 기준)
- parsed_signal_LONG=389
- parsed_signal_SHORT=339
- parsed_signal_HOLD=159
- pre_entry_fail_confidence=31
- hold_skip=159
- position_entry_done=2
- coin_reselect_start=1, coin_changed=1

2) 2026-07-03 (trading_binance.log 기준)
- parsed_signal_LONG=464
- parsed_signal_SHORT=500
- parsed_signal_HOLD=504
- pre_entry_fail=298
- hold_skip=504
- position_entry_done=0

### B. 모순 여부 결론
- 모순이 아니라 "경로 설계상 노이즈"가 있었다.
- 핵심 발견:
  - pre_entry_fail의 다수가 직전 신호 HOLD에서 발생했다.
  - 7/2: pre_entry_fail 직전 신호 분포 = HOLD 30, UNKNOWN 1
  - 7/3: pre_entry_fail 직전 신호 분포 = HOLD 296, LONG 2
- 해석:
  - "AI 진입 전 분석 실패" 경고가 실제 진입 후보(LONG/SHORT)만의 실패가 아니라,
    HOLD(원래 미진입)에서도 발생해 사용자 체감을 악화시켰다.

### C. 즉시 수정 반영 (오탐성 경고 제거)
- 수정 내용:
  - HOLD 신호에서는 pre-entry 분석을 수행하지 않도록 변경.
  - HOLD는 "정책상 미진입" 로그만 남기고 종료.
- 수정 파일:
  - trading/trader.py
- 기대 효과:
  - "AI 신뢰도 부족" 경고가 실제 진입 후보에 대해서만 출력되어 해석 일관성 확보.

### D. 코인 변경(재선택) 관련 판단
- 코인 변경 로직 자체는 이미 존재하며 7/2에는 실제 1회 실행됨.
- 다만 현재 트리거는 시장 레짐/시간 중심이라,
  "특정 코인이 반복 차단될 때 교체"까지는 직접 연결되지 않는다.
- 따라서 다음 개선 포인트는 "반복 차단 기반 재선택 트리거" 추가다.

## 9) 260705_Teayu 후속 로그 점검 (7/5)

### A. 거래소별 거래 결과 요약

1) Binance
- 신호 분포(7/5): LONG 1260, SHORT 1392, HOLD 1028 (후보 2652)
- 실제 진입: 18건
- AI 진입 전 분석 실패: 294건
  - 직전 신호 분포: HOLD 287, LONG 3, SHORT 4
- 해석:
  - Binance는 LONG/SHORT 후보가 충분히 생성되어 실제 거래가 발생했다.
  - 다만 구버전 특성상 HOLD에서도 pre-entry 실패 경고가 다수 섞여 사용자 체감을 악화.

2) Bybit
- 신호 분포(7/5): HOLD 7660, LONG/SHORT 0
- 실제 진입: 0건
- 해석:
  - 거래를 안 한 것이 아니라 진입 후보가 없어서(전량 HOLD) 미진입.

3) Upbit
- 신호 분포(7/5): HOLD 7626, LONG/SHORT 0
- 실제 진입: 0건
- 해석:
  - Bybit과 동일하게 HOLD 편중으로 후보 부재.

4) Bithumb
- 신호 분포(7/5): HOLD 144, LONG/SHORT 0
- 실제 진입: 0건
- fetch_my_trades 미지원 로그: 663회
- 해석:
  - 후보 부재(HOLD 편중) + 미지원 로그 반복 문제가 여전히 지속.

5) Bitget
- 실제 진입: 0건
- 핵심 오류: Invalid header value / Invalid IP 반복
- 해석:
  - 전략 이슈 이전에 인증/접속 계층 장애가 우선 원인.

6) OKX
- 로그량 매우 적고 진입 0건
- 장시간 무로그 공백(최대 약 5.6시간) 존재
- 해석:
  - 거래 루프 활동이 낮거나 중간 중지/재시작 영향 가능성. 추가 런타임 상태 로그 필요.

### B. 멈춤 문제(무로그 공백) 해석
- Binance/Upbit/Bithumb: 최대 공백 약 4000초(66~67분)
  - 공백 전후 로그가 설정 업데이트/재연결 이벤트로 이어져 "프로세스 완전 다운" 근거는 약함.
- Bybit: 최대 공백 약 10909초(약 3.0시간)
  - 공백 전후가 코인 선택/연결 성공 로그로 이어짐.
- OKX: 최대 공백 약 20301초(약 5.6시간)
  - 연결 성공 후 장시간 활동 로그 부재.
- 결론:
  - 이번 구간의 "멈춤"은 단일 크래시보다,
    1) 거래소별 루프 활동 저하/후보 부재(HOLD),
    2) 재시작/설정변경 구간,
    3) 일부 거래소(Bitget) 인증 오류
    가 결합된 현상으로 보는 것이 타당하다.

### C. 이전 이슈의 지속 여부(7/5 기준)
- 지속됨:
  - 빗썸 fetch_my_trades 미지원 반복
  - Binance의 HOLD 혼입형 pre-entry 실패 경고(구버전 로그)
  - 비바이낸스 거래소 HOLD 편중으로 미진입
- 심각도 상:
  - Bitget 인증 오류(Invalid header/IP)로 기능 차단
- 심각도 중:
  - 장시간 무로그 공백(특히 OKX/Bybit)으로 사용자 체감 "멈춤"
- 심각도 중하:
  - 국내 거래소 미지원 로그 노이즈

## 10) 2026-07-05 추가 조치 완료 내역 (사용자 가이드 자동화)

### A. 설정 UI 가이드 자동화 반영
1) Bitget
- 검증 실패 시 원인별 가이드 팝업 표시(Invalid IP, Invalid header, Passphrase, 401)
- Bitget 설정 영역에 현재 공인 IP 표시 + `IP 새로고침` 버튼 추가

2) Bybit
- 검증 실패 시 원인별 가이드 팝업 표시(특히 `Unmatched IP`)
- 공인 IP를 함께 안내해 bound IP 설정을 바로 수정 가능하도록 개선

3) OKX
- 검증 실패 시 원인별 가이드 팝업 표시(Passphrase, 계좌모드 51010, IP 제한, 401)

### B. 런타임 어댑터 진단 메시지 반영
1) Bitget/Bybit/OKX 어댑터에서 `last_error`, `last_auth_guidance`를 보존
2) 인증/권한/IP 계열 오류 발생 시 진단가이드 로그를 1회성으로 출력

### C. 운영 체크리스트 진행 현황(요약)
1) 완료
- 정책 과차단 완화(min_trades_history=0, 기본 loss_rate 0.0)
- 비호환 심볼 루프 차단(호환 심볼 없으면 분석 스킵)
- Bitget/Bybit/OKX 설정 검증 가이드 UX 반영

2) 사용자 환경 작업 필요
- Bitget/Bybit API 키 서비스 콘솔 설정(키 상태/권한/bound IP)
- (필요 시) OKX 계좌모드 변경(Single/Multi-currency margin)

3) 미완료(운영 검증 단계)
- 재검증 로그에서 Invalid IP/Invalid header 소거 확인
- 다거래소 동시 운용 필요 시 워커 실행 구조 변경

## 11) 5m x 50캔들 자동 진단 결과 (top 10 symbols)

진단 시각: 2026-07-05 23:30~23:31 (로컬)

1) OKX
- tested=0, success=0, success_rate=0.0%
- 결과: 연결 실패(`connect_failed`)로 캔들 진단 불가

2) Bybit
- tested=0, success=0, success_rate=0.0%
- 결과: 연결 실패 (`Unmatched IP` 로그 확인)

3) Bitget
- tested=10, success=10, success_rate=100.0%
- 성공 심볼 예: BTC/USDT:USDT, ETH/USDT:USDT, SOL/USDT:USDT, XRP/USDT:USDT, ADA/USDT:USDT

4) Upbit
- tested=10, success=10, success_rate=100.0%
- 성공 심볼 예: XRP/KRW, BTC/KRW, ETH/KRW, SOL/KRW, USDT/KRW

5) Bithumb
- tested=10, success=10, success_rate=100.0%
- 성공 심볼 예: XRP/KRW, BTC/KRW, ETH/KRW, WLD/KRW, USDT/KRW

### 해석
1) 국내 거래소(Upbit/Bithumb)는 "캔들 자체를 못 가져오는 문제"가 아니라,
  분석/신호 파이프라인 단계에서 데이터 부족 판정이 누적되는 이슈로 보는 것이 타당.
2) Bitget은 현재 세션 진단에서는 캔들 수집이 정상(100%)이므로,
  잔존 이슈는 인증/권한/IP의 시점별 불안정성 재검증이 핵심.
3) OKX/Bybit는 우선 연결 인증(및 Bybit bound IP, OKX 계좌모드) 정상화가 선행되어야
  코인별 캔들 성공률 진단이 의미를 갖는다.
