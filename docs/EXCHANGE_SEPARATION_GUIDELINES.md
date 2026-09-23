# NoahAI 거래소·자산군 실행 계약

## Coinone 공통 실행 조건 적용 — 2026-09-24

2026-09-24 최종 정책 정정 (v3.9.1.46 소스 후보): Coinone 전용 E2E 승인 차단을 제거했습니다. 등록부의 LIVE 허용과 주문 어댑터를 공통 실행 조건에 맞추며, 옛 coinone_live_e2e_verified 값은 사용하지 않습니다. API 인증·명시적 LIVE 시작·회원/주문 범위·위험/최소주문/소유권 조건은 유지합니다. 실제 계좌 검증은 테스터가 진행하며 자동시험 통과를 실계좌 검증 완료로 표시하지 않습니다. 업데이트가 자동 거래를 시작하지 않습니다.

아래 이전 점검의 Coinone LIVE 미지원·승인 전 차단은 변경 전 이력입니다. 위 정책을 현재 기준으로 사용합니다.

기준 버전: v3.9.1.27 공개판  
상태: Windows 공개 자산 게시·`publish_ready=true`; 기관별 자격정보·실계정·장시간 E2E는 별도  
정본 책임: 거래소 유형, 주문 방향, 주문 단위, PAPER/LIVE 동등성, 회귀 방지

이 문서는 과거의 단순한 `trader.py` 대 `unified_trader.py` 파일 분리 문서를 대체한다. 실행 파일 이름이 아니라 실제 거래소 상품과 주문 API 계약을 기준으로 판단한다.

## 1. 절대 기준

1. 국내 원화 거래소 Upbit·Bithumb은 KRW 현물이다.
2. Binance·Bybit·OKX·Bitget의 현재 NoahAI 암호화폐 실행 상품은 USDT 선물이다.
3. 현물 `SHORT` 분석 토큰은 신규 공매도가 아니다. NoahAI가 매수해 관리하는 LONG의 `EXIT`로만 해석한다.
4. PAPER는 실주문을 막는 실행 모드이지 거래소 상품을 바꾸는 모드가 아니다.
5. LEARNING의 분석·신호·학습 행은 주문·체결·PAPER 성과가 아니다.
6. 수동 매수, 에어드롭, 외부 봇 보유분은 NoahAI 소유권 원장이 없으면 자동 청산하지 않는다.
7. 거래소 API 오류를 빈 잔고·무포지션·체결 성공으로 변환하지 않는다.
8. 전략의 `거래당 계좌 손실 N%`는 기관 공통 위험 의미이며, 암호화폐 선물의 `증거금 최대 N%`와 주식·ETF의 `종목당 투자 비중 최대 N%`는 자산별 주문 단위로만 변환한다. 어느 기관도 단위 없는 값을 퍼센트로 추정하지 않는다.

기계 판독 정본은 `trading/exchanges/venue_capabilities.py`이며, 주문 경로는 이 계약과 다른 결론을 만들 수 없다.

## 2. 거래소별 상품 계약

| 거래소 | 상품 | 기준통화 | 신규 LONG | 신규 SHORT | 레버리지 | 청산 |
|---|---|---:|---:|---:|---:|---|
| Binance | USDT 선물 | USDT | 허용 | 허용 | 허용 | 반대방향 reduce-only 및 보호주문 |
| Bybit | USDT 무기한 선물 | USDT | 허용 | 허용 | 허용 | 반대방향 reduce-only |
| OKX | USDT SWAP | USDT | 허용 | 허용 | 허용 | `tdMode`·`posSide`와 reduce-only |
| Bitget | USDT Futures | USDT | 허용 | 허용 | 허용 | 계정 포지션 모드에 맞는 close/reduce-only |
| Upbit | KRW 현물 | KRW | 매수 | 금지 | 금지 | NoahAI 관리 LONG만 매도 |
| Bithumb | KRW 현물 | KRW | 매수 | 금지 | 금지 | NoahAI 관리 LONG만 매도 |
| 키움·신한·미래·KIS | 현금 주식/ETF | KRW | 매수 | 기본 금지 | 기본 금지 | NoahAI 관리 보유분만 매도 |

증권사의 신용·대주·공매도 상품은 별도 공식 계약과 구현·승인·테스트 없이 위 표에 추가하지 않는다.

## 3. 신호를 실행으로 바꾸는 규칙

| 분석 신호 | KRW 현물 | USDT 선물 |
|---|---|---|
| `LONG` | 신규 매수 후보 | LONG 신규 진입 후보 |
| `SHORT` | 관리 LONG이 있으면 청산, 없으면 `skip_unowned_exit` | SHORT 신규 진입 후보 |
| `HOLD` | 주문 없음 | 주문 없음 |

신호는 주문을 강제하지 않는다. 데이터 신선도, 전략 조건, 신뢰도, 잔고, 최소 주문, 포지션 한도, 손실 가드레일, 중복 주문 방지와 포지션 대조를 모두 통과해야 주문 후보가 된다.

## 4. 주문 수량과 통화 단위

### Upbit

- 시장가 매수: KRW 총 주문금액. API의 `ord_type=price` 의미다.
- 시장가 매도: 보유 코인 수량. API의 `ord_type=market` 의미다.
- NoahAI 내부 포지션 수량은 코인 수량으로 보존하되, LIVE 시장가 매수 제출 직전에 최종 정밀 수량 × 참조가격을 KRW 총액으로 변환한다.
- 5,000 KRW 최소금액과 시장 정밀도를 통과하지 못하면 실패 폐쇄한다.

### Bithumb

- 현재 CCXT 계약은 현물 주문의 base 수량을 제출한다.
- Upbit의 `params.cost`를 Bithumb에 복사하지 않는다.
- 미체결/체결 API가 종목을 요구하면 NoahAI가 알고 있는 주문 종목별로 조회한다.

### 해외 선물

- 수량은 각 거래소 contract/amount 정밀도와 최소 노셔널을 따른다.
- 신규 LONG/SHORT와 청산 주문을 구별하며 청산은 포지션 확대가 불가능해야 한다.
- Bybit의 `positionIdx`, OKX의 `posSide`·`tdMode`, Bitget의 `tradeSide`·포지션 모드는 계정의 단방향/헤지 모드와 일치해야 한다.
- 앱은 사용자 승인 없이 거래소 계정 포지션 모드를 자동 변경하지 않는다. 모드 불일치는 주문 실패로 닫고 명확한 안내를 남긴다.

## 5. LEARNING / PAPER / LIVE

| 모드 | 시장 분석 | 주문 계획 | 가상 체결 | 외부 주문 | 성과 원장 |
|---|---:|---:|---:|---:|---|
| LEARNING | 예 | 예 | 아니오 | 아니오 | 학습/판단 기록만 |
| PAPER | 예 | 예 | 예 | 아니오 | PAPER 전용 |
| LIVE | 예 | 예 | 아니오 | 승인 범위만 | 거래소 체결 + NoahAI 관리 원장 |

PAPER는 LIVE와 같은 방향 허용, 기준통화, 포지션 한도, TP/SL 단위, 전략·가드레일을 사용한다. 차이는 네트워크 주문·실제 체결이 없고 추정 수수료·슬리피지를 포함한 시뮬레이션 체결 모델을 쓴다는 점이다. 따라서 PAPER 성과를 LIVE 실체결 성과라고 표시하지 않는다. 열린 PAPER 포지션은 계정별 snapshot으로 재시작 복구하며 같은 position ID 청산은 한 번만 집계한다.

## 6. 시장국면과 코인 선정

- 빠른 시장국면은 15분봉 20개를 사용하며 기본 5분 TTL로 거래소별 한 번만 갱신한다.
- 거래 주기가 10초여도 같은 15분봉을 매번 다시 요청하지 않는다.
- 동시 요청은 거래소별 single-flight로 합치고 네트워크 호출 중 전역 설정 잠금을 잡지 않는다.
- Upbit·Bithumb 대표 심볼은 `BTC/KRW`, 해외 선물은 해당 거래소의 BTC/USDT 선물 심볼을 사용한다.
- Upbit 종목별 현재가는 분석 스레드가 공유하는 짧은 캐시·최소 요청 간격·429 backoff를 사용하고, 제한된 시간 안의 마지막 성공값만 stale fallback으로 허용한다.
- 국면 판단, 후보 점수, 종목 상세 신호, 주문 가드레일을 별도 단계로 기록한다.
- `normal`, 후보 10개, 높은 후보 점수 중 어느 하나도 실제 주문을 보장하지 않는다.

## 7. 오류 시 실패 폐쇄

- 주문 단위·가격·최소금액을 확정하지 못하면 주문하지 않는다.
- 현물 SHORT가 진입 포지션 기록 단계에 도달하면 코드 오류로 차단한다.
- 포지션 조회 실패를 0개로 바꾸지 않는다.
- 거래소 응답을 확인하지 못한 주문은 재제출하기 전에 client order ID로 대조한다.
- PAPER 행에 계산값이 없으면 0원 수익·패배로 위장하지 않고 미확정 상태로 분리한다.
- 계정 포지션 모드 불일치는 API 키 오류로 안내하지 않는다.

## 8. 필수 회귀 행렬

| 경로 | 필수 자동검증 | Windows/실환경 게이트 |
|---|---|---|
| Upbit PAPER | LONG 생성, SHORT 신규진입 0, 관리 LONG 청산 | 장시간 가상 진입·청산·PnL |
| Upbit LIVE | 시장가 BUY=KRW cost, SELL=base qty | 승인된 최소 매수→조회→청산 |
| Bithumb PAPER/LIVE | LONG/청산, base qty, 종목별 체결 조회 | 승인된 최소 매수→조회→청산 |
| Binance PAPER/LIVE | LONG/SHORT, 최소규격, 보호주문 | 지정 소액·재시작·TP/SL |
| Bybit PAPER/LIVE | LONG/SHORT, reduce-only, 시간 오차 분류 | 계정 포지션 모드별 주문·청산 |
| OKX PAPER/LIVE | LONG/SHORT, `tdMode`, `posSide`, reduce-only | net/hedge 모드별 주문·청산 |
| Bitget PAPER/LIVE | LONG/SHORT, 포지션 모드, reduce-only | one-way/hedge 모드별 주문·청산 |
| 전체 | LEARNING 주문 0, PAPER 외부주문 0, 기준통화 분리 | 6개 동시 24~72시간 soak |

## 9. 변경 체크리스트

거래·전략·PAPER·통계 코드를 바꿀 때 다음을 함께 확인한다.

1. `venue_capabilities.py`의 상품·통화·SHORT·레버리지 계약
2. 어댑터의 시장가 매수/매도 수량 단위와 client order ID
3. 신규 진입과 청산의 방향·소유권·reduce-only
4. LEARNING/PAPER/LIVE의 주문 여부와 원장 분리
5. PAPER와 LIVE의 방향·기준통화·TP/SL 단위 동등성
6. 시장국면·후보·상세분석·주문 가드레일의 단계 분리
7. 위 회귀 행렬과 `tests/test_v39116_market_execution_contract.py`
8. 인앱 매뉴얼, 사용자 가이드, 변경 이력, 배포 체크리스트
9. Windows 엔진·설치기·blockmap·`latest.yml` 식별
10. 승인된 PAPER/소액 LIVE와 거래소 원장 대조
11. PAPER 중지 권한·열린 포지션 재시작·멱등 청산·추정 비용의 원장/화면 대조
12. Binance 일반/Algo 보호 주문 감사와 UPBIT 429 복구

자동테스트 통과만으로 Windows 설치본이나 실계정 거래가 검증됐다고 기록하지 않는다.

## 10. 신규 거래소·증권사 온보딩 Definition of Done

새 기관은 다음 순서로 추가하며 어느 단계도 기존 기관의 기본값을 복사해 추정하지 않는다.

1. `venue_capabilities.py`에 고유 ID와 서비스, 상품, 기준통화, SHORT/레버리지, 주문 단위를 등록한다.
2. `validate_venue_onboarding_profile()`에 포지션 모드·보호주문·대조·멱등성·비용·시간·호출 제한·native escape hatch 계약을 제출한다.
3. API 어댑터와 자격증명 저장·마스킹·연결 진단을 구현한다. CCXT 사용 여부와 실제 거래 적합성은 별개다.
4. LIVE/PAPER/LEARNING의 주문 권한, 열린 포지션, 청산, 부분체결, 재시작, 안전 종료를 구현한다.
5. `trade_log`, 외부 확인 체결, PAPER 원장, 통계 표시 기준, KPI·리포트·로그·알림의 기관 소유권을 연결한다.
6. Strategy Studio 전략 버전과 기관별 PAPER/LIVE 결과를 `event_id`로 중복 없이 귀속한다.
7. Web UI inventory·기관 탭·설정·어시스턴트·사용자 매뉴얼과 개발/릴리스 문서를 동기화한다.
8. 등록부 드리프트 테스트, 어댑터 mock, 실패·재시도·시간오차·호출제한, 대상 OS 패키지, PAPER soak, 승인된 소액 LIVE 대조를 통과한다.

현재 등록부에 없는 기관은 모든 공통 조회·명령에서 실패 폐쇄한다. 미래 기관이 KRW 현물, USDT 선물 또는 국내 현금주식과 다른 상품이면 기존 세 분류에 억지로 넣지 않고 새로운 market type과 별도 회귀 행렬을 먼저 정의한다.

기관 등록부는 클라이언트만의 목록으로 끝나지 않는다. `scripts/export_strategy_venue_registry.py`로 Web UI와 daltrading 전략 허브 산출물을 생성하고 `--check`로 세 표면의 ID·별칭·상품·통화·PAPER/LIVE 상태가 같은지 확인한다. 허브는 이 등록부에서 기관 필터를 만들며, 기관명이 카테고리 정의에 하드코딩되어서는 안 된다. `paper_supported`는 PAPER 대상 노출 권한이고 `live_supported + onboarding_status=live_ready`는 LIVE/E5 표시의 최소 전제다.
