# v3.9.1.29 전략 공용계층·운용용량·Coinone 검증 원장

상태: 소스 후보. Windows 빌드와 Coinone 실계좌 검증 전에는 배포 완료가 아니다.

## 자동 검증

- [x] VERIFIED — 제품 버전·updater SemVer·Web inventory가 v3.9.1.29로 일치
- [x] VERIFIED — 전략 PAPER 포지션 상한은 회원등급과 무관하게 최대 5개
- [x] VERIFIED — 집중운용은 1개, 무료 다중은 최대 3개, pro_coin/premium은 최대 5개
- [x] VERIFIED — 서버 정책은 제품 상한을 낮출 수만 있고 높일 수 없음
- [x] VERIFIED — 국내 무료 Upbit·Bithumb·Coinone과 확인된 해외 레퍼럴 범위가 분리됨
- [x] VERIFIED — Coinone은 중앙 등록부·설정·통계·Strategy Studio·Hub 생성 등록부에 존재
- [x] VERIFIED — Coinone PAPER는 허용되고 LIVE 시작과 실제 주문은 E2E 승인 전 차단
- [x] VERIFIED — Upbit·Bithumb·Coinone 공개 연결에서 BTC/KRW 현재가와 15분봉 5개 조회
- [x] VERIFIED — 세 국내 현물의 공개 코인 선택·분석과 PAPER 시작은 개인 API 키 없이 허용하고 LIVE·잔고·체결 가져오기는 인증 요구
- [x] VERIFIED — Coinone PAPER LONG→가상 청산이 KRW 손익·비용 원장에 기록되고 현물 SHORT 신규 진입은 차단
- [x] VERIFIED — 종목 없는 Coinone 주문 조회·취소는 다른 종목으로 추정하지 않고 차단
- [x] VERIFIED — 주식·ETF 4개 증권사의 기존 수량·원장·실행 계약 회귀 통과
- [x] VERIFIED — 전체 Python `2,251 passed, 8 skipped`, AI Provider·Web 설정 집중 회귀 `180 passed`, 추가 국내 현물·PAPER·Web 집중 회귀 `172 passed`, Node Web build 51 modules
- [x] VERIFIED — Provider 모델 목록과 실제 생성 호출 분리, 요청/응답 모델·토큰 기록, GPT-6 reasoning 파라미터 정합과 저장 전 초안 표시

## Windows·외부기관 필수 게이트

- [ ] WIN-BUILD — v3.9.1.29 Windows 설치본과 SHA-256 확인
- [ ] WIN-UPGRADE — v3.9.1.28→v3.9.1.29 업데이트·재시작과 화면 버전 확인
- [ ] KIWOOM-E2E — 키움 기존 주식/ETF 계약 비회귀
- [ ] KIS-E2E — KIS 기존 주식/ETF 계약 비회귀
- [ ] BITHUMB-E2E — 기존 국내 현물 주문·통계 비회귀
- [ ] RECONCILE-E2E — Coinone 주문 ID·부분체결·수수료·재시작 청산 대조
- [ ] SPOT-FUTURES-PAPER — KRW 현물 LONG/청산과 해외 선물 LONG/SHORT 분리
- [ ] REPORT-E2E — 기관·통화별 통계와 Strategy Studio/Hub 근거 분리
- [ ] SOAK — 24~72시간 PAPER/API 호출 제한·재연결 관찰
- [ ] MEMBERSHIP-E2E — 국내 무료/해외 레퍼럴/유료 계정별 1·3·5 상한 표시와 런타임

## 배포 판정

자동 검증은 소스 정합성 증거다. 위 Windows·외부기관 게이트가 완료되기 전에는 Coinone을 `LIVE 지원`으로 홍보하거나 `live_supported=true`로 승격하지 않는다.
