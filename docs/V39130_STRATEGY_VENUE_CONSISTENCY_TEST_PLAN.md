# v3.9.1.30 검증·배포 계약

범위: Binance/Upbit/Bithumb/Coinone/Bybit/Bitget/OKX, Kiwoom/Shinhan/Mirae/KIS. Teayu 폴더는 읽기 전용 참고 자료이며 테스트는 임시 합성 원장을 사용한다.

- [x] VERIFIED SOURCE-SCOPE: 기관·기간 필터를 제한보다 먼저 적용, 통화·PAPER/LIVE 분리, 카드와 표 공통 집계, 추가 기록 시 캐시 무효화.
- [x] VERIFIED SOURCE-TIMEFRAME: 선언 시간봉·독립 방향별 상위봉 수집, 미완성/미지원 자료 차단, 실제 기간 기록, 동일 봉 런타임 평가.
- [x] VERIFIED SOURCE-BROKER: Windows 키움 process proxy 선택, 유휴 이벤트 처리, timeout/EOF/응답 불일치 채널 폐기, 미확정 주문 재시도 차단, KIS 상태 로그. 실제 Windows COM은 별도 게이트.
- [x] VERIFIED UI-RENDER: 실제 StrategyStudio 컴포넌트에서 코인·주식 × 1280/1440/1920, 배율 1.25의 날짜/상태/변경점 확인. 코인·주식 1280에서 보완 이동→저장→승인→재생→PAPER 흐름 통과. SourceWorkspace의 코인·주식 승인 차단 화면에서 API 인증과 계정 거래 권한이 분리되고, HTTP 409가 승인 대기 행동 안내로 변환됨을 확인. 합성 응답을 사용한 화면 검증이며 실제 거래 실행 E2E가 아님.
- [x] VERIFIED FULL-REGRESSION: 2026-09-14 전체 Python `2,296 passed, 8 skipped` (36초), Node 22 production build 51 modules, 표면 계약 감사 PASS(5서비스·35기능·11기관·9설정·11매뉴얼). pytest의 Starlette/httpx deprecation 1건과 Vite 큰 청크 경고는 남아 있으며 실패는 아님. skip과 합성 회귀는 아래 실제 환경 게이트를 대신하지 않음.
- [x] WIN-BUILD: 2026-09-14 현재 소스 fingerprint로 새 설치본·engine·blockmap·latest.yml SHA-256 확인. installer `b4508fe4a26290b23b6ef823732eae63fc0aa4f5a6549b43477fb6e50b01c363`, engine `76f8b60212cff7cad7c41fc8c6b7c19d6921779d7d53adc085e4bf56cc975347`, blockmap `bce88b04a4f8d7549185047060053f013f42b919ee7eb3097e0a57c703830a76`, latest.yml `bbdede1bdec852e5a239558d2401da35577e31efddbc3d6035bfb12c39902569`.
- [ ] WIN-UPGRADE / ROLLBACK: v3.9.1.29 → v3.9.1.30 업데이트/재시작/롤백 및 API 키·전략·PAPER 이력 보존.
- [ ] KIWOOM-E2E: Windows OpenAPI+ 실제 로그인/조회/취소/부분체결/프로세스 복구. ActiveX 설치와 Python/COM 비트수 일치 확인.
- [ ] KIS-E2E: 실전/모의 서버, 인증 제한, 주식/ETF 조회·체결/수수료·세금 대조.
- [ ] VENUE-E2E: 7개 코인·4개 증권사 중 사용 가능한 환경의 실제 시세/PAPER·거래 통계 동일 기간 대조. 미지원 API는 정확한 미지원 표시. Coinone LIVE는 별도 온보딩 승인 전 차단.
- [ ] BITHUMB-E2E: 공식 15m/4h 직접 조회와 2h 완전 묶음, 요청 시간봉·비용·통계 대조.
- [ ] RECONCILE-E2E / REPORT-E2E: LIVE 청산 주문·부분체결·수수료·세금과 카드/통계/리포트 동일 범위 비교. 대조 미확정은 확정 손익에 포함하지 않음.
- [ ] SPOT-FUTURES-PAPER: 현물 LONG 로트와 선물 LONG/SHORT, 기관·통화·버전 분리 및 재시작 보존 확인.
- [ ] PAPER-SOAK: 고정 전략/시장봉/설정으로 24~72시간 PAPER 운용, 재시작과 수량·위험 한도·지연/재진입 기록 대조.

제한: 증권사 과거 시세 공급은 현재 일봉이다. 분봉 지원을 구현했다고 표시하지 않는다. 판단봉과 주문봉이 서로 다른 주문 시뮬레이션, 전체 Pine 문법 호환, 외부 플랫폼 성과와 동일 결과는 보장 범위에 없다.

공개 시세 연결 점검(2026-09-14, 인증키·주문 없이 현재 소스 호출): Binance/Upbit/Coinone/Bybit/OKX/Bitget 15m 응답 및 오름차순·닫힌 봉 확인. Bithumb 공식 15m와 4h는 각각 200봉 중 완료 199봉 확인. Coinone 100봉 요청에 실제 98봉 반환을 확인했으며 요청 수를 성과 표본 수로 꾸미지 않는다. 이는 시세 조회 증거이고 PAPER 운용·실체결 확인은 아니다.

화면 회귀 실행법: `webui/qa/README.md`. StrategyStudio 6개 조합, SourceWorkspace 16개 조합(코인/주식, 800/1280/1440/1920, 연결/미연결), 회원 권한 차단 2개 조합에서 겹침·가림·로그 높이·오류 없음. 반응형 세로 배치를 포함하며 실제 Windows DPI는 별도다.

이 계획의 미완료 환경 게이트가 있으면 stable 게시를 중단한다. 후보 빌드는 가능하지만 사용자가 실행 환경에서 확인한 결과를 기록하기 전 완료 체크를 하지 않는다.
