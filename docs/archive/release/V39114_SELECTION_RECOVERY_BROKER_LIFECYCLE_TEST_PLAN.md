# v3.9.1.14 후보 선정 복구·증권 조회 연결 안전 종료 검증 계획

상태: **소스 후보 완료 / Windows 빌드·실환경 검증 대기**  
제품 버전: `3.9.1.14` · updater SemVer: `3.9.114`  
예정 설치 파일: `NoahAI-3.9.1.14-Setup.exe`

## 소스·결정적 회귀

- [x] Binance·Upbit·Bithumb·Bybit·Bitget·OKX 30개 후보를 일괄 시세 스냅샷만으로 숫자 점수화한다.
- [x] `fallback_unscored` 전체 목록은 신규 진입과 상세 신호 분석을 생략하고 기존 포지션 관리는 유지한다.
- [x] 점수 실패 재시도는 기본 60초 쿨다운과 거래소별 single-flight를 사용한다.
- [x] 재선정 실패가 이전 정상 점수 후보를 덮지 않는다.
- [x] 키움·신한·미래에셋·KIS의 조회 전용 어댑터도 worker 유무와 관계없이 종료 대상에 포함한다.
- [x] 신한·미래에셋·KIS REST 세션과 토큰 상태를 명시적으로 정리한다.
- [x] Binance·Bybit 시간 오류를 인증 실패·빈 응답과 구분하고 서버 시간 차이 재측정 뒤 한 번 재시도한다.
- [x] KIS 토큰 발급을 single-flight로 합치고 유효 토큰 재사용·`EGW00133` 60초 쿨다운을 적용한다.
- [x] 관찰·학습 거래소 선택과 LEARNING worker 시작을 UI·매뉴얼에서 분리한다.
- [x] 관련 집중 회귀와 연결·시간·LEARNING 회귀.

## Windows·실환경 게이트

- [ ] `WIN-BUILD`: 같은 소스 fingerprint로 `NoahAIEngine.exe`, Setup, blockmap, `latest.yml`을 Windows x64에서 빌드한다.
- [ ] `WIN-UPGRADE`: 공개 v3.9.1.13에서 v3.9.1.14 확인·다운로드·안전 종료·설치·재시작을 검증한다.
- [ ] `CRYPTO-COLD-WARM`: 6개 거래소별 콜드/웜 선정 p95, 점수 상태, 재시도와 거래소 간 격리를 확인한다.
- [ ] `CRYPTO-LONG-RUN`: 6개 거래소 PAPER 12시간 이상 실행에서 후보 재선정이 포지션 감시·TP/SL·설정·AI 커스텀을 막지 않는지 확인한다.
- [ ] `BROKER-READ-CLOSE`: 거래 시작 없이 각 증권사 탭을 열고 잔고·보유종목 조회 후 종료해 프로세스·세션 잔존이 없는지 확인한다.
- [ ] `KIWOOM-COM`: 키움 로그인 대기, 정상 연결, 조회 진행 중 각각에서 NoahAI 소유 COM 자식만 정리되는지 확인한다.
- [ ] `REST-BROKERS`: 신한·미래에셋·KIS의 진행 중 요청 제한시간과 종료 후 재실행·재연결을 확인한다.
- [ ] `KIWOOM-E2E`: 키움 조회 전용 연결과 주문 worker를 각각 시작·종료하고 COM 자식·주문·미체결 상태를 대조한다.
- [ ] `KIS-E2E`: KIS 조회·모의/PAPER·LIVE 권한 경계를 확인하고 종료 후 HTTP 세션·토큰·worker가 남지 않는지 확인한다.
- [ ] `CLOCK-E2E`: Windows 시간 동기화를 끈 상태의 Binance·Bybit 오류 분류와 안내를 확인한 뒤 시간을 정상 복원하고 자동 재연결을 확인한다.
- [ ] `KIS-TOKEN-E2E`: 설정 연결 확인·증권 탭 계좌 조회·worker 시작이 겹쳐도 1분 안에 토큰 발급이 한 번뿐이며 기존 토큰으로 조회가 계속되는지 확인한다.
- [ ] `LEARNING-E2E`: 거래소만 선택한 정지 상태에는 분석 주기가 없고 `분석·학습 시작` 뒤 로그가 진행되며 실주문·PAPER 체결이 0건인지 확인한다.
- [ ] `BITHUMB-E2E`: Bithumb 콜드/웜 선정, 미점수 재시도, 현물 LONG PAPER와 기존 포지션 보존을 확인한다.
- [ ] `RECONCILE-E2E`: 선정 실패·재시도·앱 재시작 중 기존 PAPER/LIVE 포지션과 TP/SL 관리가 끊기거나 신규 진입으로 중복되지 않는지 확인한다.
- [ ] `SPOT-FUTURES-PAPER`: Upbit·Bithumb 현물 LONG과 Binance·Bybit·Bitget·OKX 선물 LONG/SHORT PAPER를 동일 검증표로 확인한다.
- [ ] `REPORT-E2E`: 코인 정보·실시간 로그·운영 KPI에 `scored`/`scored_partial`/`fallback_unscored`와 재시도 상태가 실제 엔진 상태와 일치하는지 확인한다.
- [ ] `SOAK`: 6개 거래소와 4개 증권사 조회를 포함한 Windows 12시간 운용에서 지연·중복 요청·종료 잔존 프로세스를 측정한다.
- [ ] `ROLLBACK`: v3.9.1.14 설치 실패 시 v3.9.1.13 사용자 데이터·설정·전략·원장을 보존하고 복구한다.

## 배포 판정

위 Windows 항목이 모두 완료되고 산출물 SHA-256·source fingerprint가 manifest와 일치할 때만 `publish_ready=true`로 전환합니다. macOS 소스 테스트나 Web build만으로 이 원장을 완료 처리하지 않습니다.
