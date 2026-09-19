# v3.9.1.7 장시간 성능·요청 격리 검증 계획

## 자동·소스 게이트

- [x] `POLL-SINGLE-FLIGHT` — runtime/log/workspace/account/AlphaArena 폴링마다 미완료 요청이 1개를 넘지 않는다.
- [x] `ACCOUNT-LOCK-ISOLATION` — 15초 계좌 조회 중에도 설정 snapshot과 AI 커스텀 catalog가 대기하지 않는다.
- [x] `MEMBERSHIP-SINGLE-FLIGHT` — 2초 runtime 폴링 중 외부 멤버십 확인은 분당 1개만 실행한다.
- [x] `KPI-COUNT-OVER-200` — 종료 거래가 200건을 넘어도 운영 KPI의 총 거래·승률·PnL이 전체 DB 집계와 일치한다.
- [x] `KPI-SCOPE` — 메인 전체와 거래소별 집계가 서로 섞이지 않고 KRW/USDT를 합산 표시하지 않는다.
- [x] `DB-PERFORMANCE` — Teayu 지원 DB에서 메인 P95 63.0ms, Binance 상세 P95 129.9ms로 목표를 통과했다.
- [x] `LOG-TAIL` — 파일 크기와 무관한 64KB 역방향 tail 구현과 3,002행 회귀로 전체 파일 역직렬화를 차단했다.

## Windows·장시간 외부 게이트

- [ ] `WIN-BUILD` — `NoahAI-3.9.1.7-Setup.exe`, `NoahAIEngine.exe`, blockmap, `latest.yml(3.9.107)`을 동일 소스로 빌드하고 SHA-256을 확정한다.
- [ ] `UPGRADE-3916-3917` — 공개 v3.9.1.6에서 업데이트 후 설정·API 자격증명·전략·학습·DB·로그가 유지된다.
- [ ] `SIX-EXCHANGE-START` — PAPER에서 6개 거래소를 독립 시작하고 거래 실행·정지와 UI 응답이 서로 막히지 않는다.
- [ ] `SOAK-24H` — 24시간 동안 요청 수·스레드·RSS·DB 지연이 지속 증가하지 않는다.
- [ ] `SETTINGS-AI-CUSTOM` — soak 중 설정 열기/저장/닫기와 AI 커스텀 source 분석·검증 시작이 정상 응답한다.
- [ ] `ROLLBACK` — 3.9.1.7 제거/롤백 후 사용자 데이터가 보존되고 v3.9.1.6 재실행 조건을 기록한다.

미완료 항목이 있으면 `publish_ready=false`를 유지합니다. LIVE 주문 검증은 별도 승인 없이는 수행하지 않습니다.
