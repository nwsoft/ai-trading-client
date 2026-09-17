# v3.9.1.38 전략 과거재생·기관별 거래내역 검증 및 배포 원장

기준일: 2026-09-17

소스 후보: **v3.9.1.38** · updater **3.9.138**

현재 공개 stable/latest: **v3.9.1.37**

이 문서는 공개 v37 이후 추가된 변경을 v38 새 산출물로만 배포하기 위한 단일 검증 원장이다. 기존 v37 태그·설치기·blockmap·`latest.yml`·manifest를 수정하거나 같은 버전으로 재게시하지 않는다.

## 릴리스 범위

1. Strategy Studio 과거재생 결과에 검증 당시 캔들, 진입·청산 타점, 청산 기준 누적 수익률과 거래표를 연결한다.
2. 수익률·가격 정밀도, 선택 거래 구간과 원본 값 표시를 보강한다. 과거 검증은 미래 수익, PAPER, LIVE 또는 여권 등급을 보증하지 않는다.
3. 기관별 거래내역을 실제 실행 모드에 맞춰 표시한다. PAPER에서는 현재 PAPER 거래내역, LIVE에서는 해당 계정·기관에 저장된 LIVE 종료 기록을 기본 탭으로 표시한다.
4. LIVE/PAPER 거래내역은 기본 접힘이며 기관 또는 실행 모드가 바뀌면 다시 접힌다. 이력 탭 조회는 실제 실행 모드를 바꾸지 않는다.
5. 확정 손익과 미확정·외부·가져오기·통화 불명·조회 실패를 분리한다. 다른 계정·기관·PAPER/LEARNING 기록을 LIVE 확정 성과로 섞지 않는다.

## 자동 검증

- [x] v3.9.1.38 버전 승격 후 Python 전체 회귀: **2,572 passed / 8 skipped / 3 subtests passed**, 기존 Starlette 폐기예정 경고 1건.
- [x] 거래내역 관련 집중 회귀: **70 passed**, 기존 Starlette 폐기예정 경고 1건.
- [x] Node **22.23.1** Web TypeScript/Vite production build: **61 modules PASS**, 기존 500kB 초과 번들 경고 유지.
- [x] Strategy Replay Python↔TypeScript 표시 계약, 코인·주식/ETF·저가 자산·0거래·구형 결과 회귀 PASS.
- [x] 7개 코인 거래소와 4개 증권사의 격리 원장 읽기, 기관 별칭, 계정 분리, 실제 Recorder 스키마, 주식/ETF 행 보존 PASS.
- [x] 격리 브라우저에서 11개 기관의 PAPER/LIVE 전환, 기본 접힘, 포지션·통계 문구, 빈 목록·실패·복구·1080px 표시와 브라우저 오류 0건 확인.
- [x] 매뉴얼 11개 섹션 재생성과 문서/버전 정합 검사 PASS.
- [x] v3.9.1.38 버전 승격 뒤 전체 Python, Node 22 Web build, 두 브라우저 fixture, 매뉴얼 재추출과 문서 정합을 재실행함.
- [x] `release_gate.py --profile prekey` PASS: 증권 집중 176 passed / 6 skipped, 4개 증권사 모드·무키 경로, 7개 거래소 준비도 보고, 사용자 노출 동기화, 다중 거래소 불변조건 확인. 자격정보 없는 오프라인 게이트이며 실계정 E2E를 뜻하지 않음.

## Windows 새 산출물 필수 게이트

- [ ] **WIN-BUILD** — 깨끗한 원격 v38 대상 커밋에서 x64 `NoahAIEngine.exe`와 x86 `NoahAIKiwoomHost.exe` 새 빌드.
- [ ] 두 PE의 ProductVersion/FileVersion `3.9.1.38`, 아키텍처, source fingerprint와 manifest SHA-256 대조.
- [ ] `NoahAI-3.9.1.38-Setup.exe`, blockmap, updater `3.9.138`의 `latest.yml` 생성 및 내부 엔진 smoke.
- [ ] Windows 100/125/150/175% DPI에서 과거재생 차트와 접힌/펼친 거래내역, 최소 지원 창 크기 확인.
- [ ] **WIN-UPGRADE** — 공개 v3.9.1.37 → v3.9.1.38 자동 확인·다운로드·안전 종료·설치·재시작.
- [ ] **ROLLBACK** — v38 설치 실패·안전 종료 실패 시 기존 v37 설치와 사용자 설정·원장이 손상되지 않고 복구 절차가 동작함.
- [ ] 업데이트 후 설정, 자격정보, 전략 원문·버전·검증 결과, PAPER 포지션·원장과 LIVE 원장 보존 대조.

## 기관·계정 E2E 필수 게이트

- [ ] **SPOT-FUTURES-PAPER** — Binance·Upbit·Bithumb·Bybit·Bitget·OKX의 PAPER/LIVE 모드별 제목·내역과 현물/선물·기관 분리 확인.
- [ ] **BITHUMB-E2E** — Bithumb 실제 인증 환경에서 시세·잔고·PAPER 및 허용된 LIVE 이력 조회가 다른 기관 원장과 분리됨.
- [ ] Coinone PAPER와 저장 이력 표시 확인. LIVE 준비 상태를 이번 화면 변경만으로 승격하지 않음.
- [ ] **KIS-E2E** — 한국투자 실제 인증 환경에서 주식/ETF 일봉 과거검증, PAPER 및 허용된 LIVE 이력 조회 확인.
- [ ] 신한·미래에셋에서 주식/ETF 일봉 과거검증과 PAPER 거래내역 확인.
- [ ] 실제 LIVE 권한이 있는 기관에서 NoahAI 종료 거래 1건 이상을 주문/체결/수수료 원장과 대조. 권한 없는 기관은 주문하지 않음.
- [ ] **KIWOOM-E2E** — 키움 로그인→종목/일봉 조회→PAPER→중지/재연결을 확인하고 중복 로그인·호스트 자동 재시작이 재발하지 않는지 확인.
- [ ] **RECONCILE-E2E** — 조회 실패를 거래 0건으로 표시하지 않고 복구 뒤 최신 해당 기관 원장을 주문·체결·수수료 기록과 대조함.
- [ ] **REPORT-E2E** — 모드별 거래내역·통계·내보내기 보고서가 같은 기관·계정·통화·전략 버전 원장을 사용함.
- [ ] **SOAK** — 24시간 이상 PAPER 연속 운용과 종료·재시작 뒤 전략/원장/화면 일치 확인.

## 게시 게이트

- [ ] Git 대상 커밋·원격 커밋·빌드 fingerprint 일치 및 비밀정보/사용자 DB/로그 미포함.
- [ ] 새 v3.9.1.38 태그가 정확한 빌드 커밋을 가리키며 기존 태그와 충돌하지 않음.
- [ ] 릴리스 자산의 파일명·크기·SHA와 새 manifest 일치.
- [ ] stable 게시 뒤 Releases 첫 항목, Atom 첫 항목, Latest, Windows `latest.yml`이 모두 v3.9.1.38.
- [ ] 공개 URL HTTP 200, 실제 설치기·blockmap·`latest.yml` 원격 해시 대조.

## 현재 판정

**소스 후보 / Windows 재빌드·실계정·업데이트 E2E 대기.** 자동 회귀와 격리 화면 검증은 실제 Windows 설치본, 키움 OCX, 기관별 실계정 데이터 수집 또는 장시간 운용을 대신하지 않는다. 위 미완료 필수 게이트를 수행하기 전에는 v3.9.1.38 배포 완료로 표시하지 않는다.

세부 기능 증거는 [과거재생 시각화](STRATEGY_REPLAY_VISUALIZATION_20260917.md), [기관별 거래내역](SOURCE_TRADE_HISTORY_20260917.md), 일반 절차는 [빌드 가이드](BUILD_GUIDE.md)와 [배포 체크리스트](DEPLOY_CHECKLIST.md)를 따른다.
