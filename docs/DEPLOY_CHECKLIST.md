## 2026-09-19 - v3.9.1.40 Strategy Studio Readability and AlphaArena Safety Patch

현재 소스 후보 **v3.9.1.40** · updater **3.9.140**. 현재 공개 stable/latest는 **v3.9.1.39**이며 기존 공개 자산은 보존합니다.

- 전략 스튜디오 코인/주식·ETF 공통 설명 가독성, 입력 공간, 단계 이동을 개선합니다. 검증·승인·여권 정책은 바꾸지 않습니다.
- AlphaArena 실행 중 PAPER 변경을 통한 LIVE 주문 경로를 차단합니다. 설정 변경 시 정지하고 새 설정으로 명시적 재시작하며, 이전 요청 종료 전 중복 시작은 거부합니다.
- 전용 DeepSeek 키와 저장된 엔진으로 실행/연결 점검을 통일하고, AI 설명·판단·PAPER 결과 누락을 수정합니다.
- AlphaArena는 가상 손익 검증이 아닌 PAPER 판단 실험임을 표시합니다. 다른 거래소 화면에서도 실행 상태와 정지를 제공합니다.
- 설정의 실제 호출 점검 버튼과 매뉴얼 이름을 맞추고, 키/기관 변경 및 알림 실패 시 오래된 성공 표시를 제거합니다. 공개/보호 Project 모델 목록을 분리합니다.
- Windows 새 설치본·업데이트·원격 게시 검증은 미완료입니다. 코드/화면 검사만으로 배포 완료를 표시하지 않습니다.
- [v40 검증·배포 계획](V39140_STUDIO_ALPHA_SETTINGS_TEST_PLAN.md)

이하 과거 버전의 후보·배포 보류·공개 기준은 당시 기록이며 현재 배포 상태를 뜻하지 않습니다。

## 2026-09-18 · v3.9.1.39 PnL 재감사 — 배포 보류

현재 소스 후보 **v3.9.1.39** · updater **3.9.139** · 공개 stable/latest **v3.9.1.38**. **PnL 재감사로 배포 보류**입니다.

현재 공개 버전: **v3.9.1.38** stable/latest.

- 시간/수량 유일 후보의 자동 주문 연결은 소유권 오인 위험으로 철회했습니다. 주문 ID 없는 과거 외부 청산 자동 복구는 아직 미완료입니다.
- PAPER/LIVE 격리, 청산 방향·중복 귀속, 미확인 비용 통화, 수수료 환급, UTC 입력 및 증권 KRW 집계를 보강했습니다.
- NoahAI 연결 청산 순손익과 거래소 수집 체결 총손익을 구분하고 미확정 거래가 있으면 부분 합계로 표시합니다.
- 미대조 성과가 수익성 검증의 정상/콜드스타트 판정과 Smart Exit 통계 조정에 사용되지 않도록 보강했습니다. 직접 학습·저널 경로까지 완료된 것은 아닙니다.
- 추가 집중 회귀 **58 passed**, 전체 **2,606 passed / 8 skipped / 3 subtests**, Node 22.23.1 Web **61 modules** build PASS. 격리 코인/주식 UI fixture에서 API 쓰기·브라우저 오류 0건과 카드 겹침 해소를 확인했습니다. 이전 2,577건 및 prekey 결과는 재감사 전 코드의 기록입니다.
- 실제 외부 청산 주문 소유권 연결, 사용자 원본 대조, 전체 AI 소비자 감사, Windows/업데이트/실계정 게이트가 남았습니다.

상세 원인·검증·미완료 게이트: [PnL 신뢰성 재감사](V39139_PNL_TRUST_AUDIT.md).

## v3.9.1.38 전략 과거재생·기관별 거래내역 (공개 기록)

- [x] v3.9.1.38 버전 승격 후 전체 Python 2,572 passed / 8 skipped / 3 subtests, 거래내역 집중 70 passed, Node 22.23.1 Web 61 modules, 문서·매뉴얼 정합.
- [x] 격리 브라우저에서 7개 거래소·4개 증권사의 LIVE/PAPER 전환·기본 접힘·주식/ETF·실패/복구 검사, 브라우저 오류 0건.
- [x] v3.9.1.38 버전 승격 뒤 전체 자동 검증·두 격리 브라우저 fixture 재실행 및 최종 수치 기록.
- [x] 변경 파일 38개를 명시한 prekey 릴리스 게이트와 사용자 노출 문서 동기화 PASS. 실제 게시 때는 Git 작업트리에서 변경 수집·source revision을 다시 증명.
- [ ] Windows x64/x86 새 설치본·과거재생/거래내역 DPI·실계정·v37→v38 업데이트·장시간 PAPER 검증.
- [ ] v3.9.1.38 새 자산 게시·원격 해시·stable/latest 확인. 현재 공개 v3.9.1.37 자산은 유지.

현재 소스 후보 버전: **v3.9.1.38** · updater **3.9.138**.

현재 공개 버전: **v3.9.1.37** stable/latest.

공개 v37 이후 변경은 v38 새 산출물로만 배포하며 기존 v37 태그·설치기·blockmap·`latest.yml`·manifest를 덮어쓰지 않습니다.

- Strategy Studio 과거재생 캔들·타점·수익률 곡선·거래표와 코인/주식/ETF 표시 계약 확인.
- 실행 모드별 PAPER/LIVE 거래내역, 기본 접힘, 확정/미확정·기관·계정 분리 확인.
- 제품 `3.9.1.38`, updater `3.9.138`, Windows 두 PE와 설치기 파일명·해시·manifest를 한 빌드에서 생성·대조.
- 공개 v37→v38 자동업데이트에서 안전 종료와 설정·전략·검증·PAPER/LIVE 원장 보존 확인.
- [v3.9.1.38 검증·배포 원장](V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md).

## v3.9.1.37 키움 조회 대기·실패 상태 수정 (2026-09-17 공개 기록)

v3.9.1.37은 stable/latest로 공개됐습니다. 아래 후보·공개 v36 표기는 당시 기록이며 현행 배포 판단에는 사용하지 않습니다.

- [x] 전체 Python 2,494 passed / 8 skipped / 3 subtests, Web 빌드·문서·매뉴얼·업데이트 Provider 회귀.
- [x] v3.9.1.37 자산 게시와 stable/latest 확인.
- 실제 키움 계정·장시간 운용은 공개 사실과 별도 운영 검증으로 유지합니다.
- [검증 계획](V39137_KIWOOM_BOUNDED_QUERIES_TEST_PLAN.md) · [사용자 로그 분석](V39137_KIWOOM_USER_LOG_ANALYSIS.md).

## 이전 버전 기록 (이하 후보·공개·검증 상태는 당시 기록)

## v3.9.1.36 키움 세션·증권 PAPER·전략검증 정합 (2026-09-16 소스 후보)

현재 소스 후보 버전: **v3.9.1.36** · updater **3.9.136**. 현재 공개 기반: v3.9.1.35 stable/latest. 공개 자산을 교체하지 않고 새 버전으로만 배포합니다.

- [x] 키움 timeout 뒤 자동 호스트 재시작 차단·수동 재연결 latch 소스 회귀.
- [x] 네 증권사 PAPER 주식/ETF 원장·비용·재시작 보존 소스 회귀.
- [x] 네 증권사 주식/ETF 전략 일봉·기관 범위·비용 계약 소스 회귀.
- [x] 전체 Python 2,466 passed / 8 skipped / 3 subtests, Web 52 modules, 매뉴얼/문서 정합, 개발 릴리스 게이트, 격리 브라우저 fixture, npm production audit.
- [ ] Windows x64/x86 새 빌드·PE/버전/SHA·v3.9.1.35 업데이트.
- [ ] 키움 실로그인 단절/중복 로그인, 네 증권사 PAPER·전략검증, 24시간 운용.
- 검증 정본: [v3.9.1.36 검증 계획](V39136_KIWOOM_SESSION_STOCK_PAPER_VALIDATION_TEST_PLAN.md).


## 이전 버전 기록 (아래 현재·공개 표기는 당시 기록이며 현행 판단에 사용하지 않음)

# 배포 체크리스트 (2026-09-16 · v3.9.1.34 키움 x86·릴리즈 무결성 후보 기준)


## 현재 버전 기준 · v3.9.1.34 검증 후보

현재 소스 후보 버전: **v3.9.1.34** · 현재 공개 안정판: **v3.9.1.33**. 제품 3.9.1.34 / updater 3.9.134, 설치 파일 `NoahAI-3.9.1.34-Setup.exe`입니다. x64 엔진과 x86 키움 호스트가 모두 포함되어야 합니다.

[v3.9.1.34 필수 게이트](V39134_KIWOOM_X86_RELEASE_INTEGRITY_TEST_PLAN.md). 미완료 행이 있으면 prerelease만 허용하며 공개 안정판 v3.9.1.33은 유지합니다.

## v3.9.1.32 소스 후보 · 공개 v3.9.1.31

v3.9.1.32는 국면 재선정 대기를 실제 변경 알림과 분리하고, 저장한 업데이트 확인 주기를 앱 공통 타이머로 실행합니다. Coinone의 미제공 활성 상태를 중단으로 오해하던 후보 수집을 수정하고, KIS·미래에셋의 주식/ETF 목록을 공식 공개 마스터로 분리합니다. 네 증권사 워커의 후보 없음·분석 완료·오류를 해당 기관 로그로 전달합니다. 주문 권한·TP/SL·점수 없는 진입 차단은 유지합니다.

제품 버전 3.9.1.32 / updater 3.9.132. 새 Windows 설치본의 설정창 미방문 주기 확인, 상태 5분 요약, Coinone 후보 점수·PAPER, KIS 장중 주기 로그를 확인해야 합니다. 사용자 공유 데이터는 읽기 전용입니다.

[근본 원인과 필수 검증](V39132_RUNTIME_RECOVERY_TEST_PLAN.md)

## 이전 문서 기록 (아래 현재·후보 표기는 당시 기준)

운영 환경 배포 전/후 점검해야 할 항목을 정리했습니다. 내부 통합 후보는 기존 `build_safe.py`와 Web UI/Electron bundle을 분리해 검증합니다.

## v3.9.1.31 패치 필수 게이트

> 현재 공개 Windows 기준은 v3.9.1.30입니다. v3.9.1.31은 같은 번호의 기존 자산을 덮어쓰지 않고 새 설치기·blockmap·`latest.yml`·manifest로만 공개합니다.

- 제품 버전 `3.9.1.31`, updater SemVer `3.9.131`, 설치 파일 `NoahAI-3.9.1.31-Setup.exe`, blockmap과 `latest.yml`의 크기·SHA-512가 manifest와 일치해야 한다.
- 메뉴얼 정본을 다시 생성했을 때 `docs/USER_MANUAL_SECTIONS.json`과 완전히 같고, 11개 고유 탭·UTF-8 무손실·현행 7개 코인 거래소·4개 증권사·Coinone LIVE 차단·v3.9.1.31 최신 항목 검사를 통과해야 한다.
- 소개부터 업데이트까지 모든 탭에서 요약 카드와 전체 본문이 기본 노출되고, 전역 검색이 탭 제목뿐 아니라 본문 전체 일치 항목을 순서대로 이동하는지 확인한다.
- Windows 100/125/150/175% DPI와 최소 지원 창 너비에서 제목·표·목록·주의 카드·긴 영문 모델명·기관명이 잘리거나 겹치지 않는지 확인한다.
- AlphaArena는 v3.9.1.31에서 PAPER 전용이며 LIVE 모드 시작이 `alpha_arena_live_blocked_pending_external_gate`로 실패 폐쇄되는지 확인한다.
- v3.9.1.30의 거래 수량·신호·가드레일·PAPER/LIVE 원장·기관별 통계·Strategy Studio 시간봉 계약이 메뉴얼 UI 변경으로 달라지지 않았는지 집중 회귀한다.
- v3.9.1.30→v3.9.1.31 자동 업데이트와 재시작에서 설정·자격증명·거래/PAPER 원장·전략 버전·검증 시도·사용자 초안이 보존되는지 확인한다.
- 각 결과는 [v3.9.1.31 검증·배포 계약](V39131_READABLE_MANUAL_RELEASE_TEST_PLAN.md)에 기록하고, 필수 미완료 항목이 있으면 stable 게시를 중단한다.

## v3.9.1.30 공개 기준

> v3.9.1.30 Windows 자산은 공개 기준입니다. PAPER 범위·전략 시간봉·증권 연결 진단 계약은 후속 버전에서도 유지합니다.

- 세부 소스·운영 경계는 [v3.9.1.30 테스트 계획](V39130_STRATEGY_VENUE_CONSISTENCY_TEST_PLAN.md)을 따른다.
- Windows 설치·업데이트/롤백·실계정 KIS/키움·장시간 PAPER는 소스 테스트와 별개의 환경 게이트로 계속 기록한다.

## v3.9.1.27 패치 필수 게이트

> 직전 공개 v3.9.1.26 자산은 변경하거나 같은 번호로 다시 게시하지 않습니다. 후속 수정은 v3.9.1.27 새 산출물로만 배포합니다.

- 제품 버전 `3.9.1.27`, updater SemVer `3.9.127`, 설치 파일 `NoahAI-3.9.1.27-Setup.exe`, blockmap과 `latest.yml`이 일치해야 한다.
- [v3.9.1.27 검증 원장](V39127_STRATEGY_ASSISTANT_CONTINUITY_TEST_PLAN.md)의 소스·Windows 항목을 완료해야 한다.
- 공개 v3.9.1.26→v3.9.1.27 자동 업데이트에서 다운로드·안전 종료·재시작·설정/원장/전략 초안 보존을 확인한다.
- 실제 Provider에서 30/30 429를 만들고 텍스트·Pine 로컬 분석은 계속되며 이미지·영상은 정확한 안내를 내는지 확인한다.
- 실제 사용자 DeepSeek 계정의 모델 조회에서 `deepseek-v4-flash`·`deepseek-v4-pro`를 확인하고, 계정에 노출된 경우에만 `deepseek-v4-flash-vision-exp` 이미지 분석을 시험한다. 확인되지 않은 `deepseek-v4.1-flash` 문자열을 수동 저장하지 않는다.
- 일반 `deepseek-v4-flash`를 선택한 차트 분석은 Provider 호출 전에 모델 capability 오류로 차단되고, 텍스트·JSON 요청은 정상 동작하는지 확인한다.
- AI 비용 카드는 실제 토큰·등록 단가가 있는 사용자 요청형 호출만 증가하고, 캐시 재사용·실패·토큰 미제공·단가 미등록은 0원 성공으로 오인되지 않는지 확인한다. Provider 콘솔 청구와 자동매매 백그라운드 비용은 별도 대조한다.
- YouTube 입력은 자막이 있으면 전사 모델을 호출하지 않고, 자막이 없을 때만 사용자가 선택한 OpenAI 전사 경로와 비용 안내를 사용하는지 확인한다.
- 암호화폐와 주식·ETF에서 확인창·생성 시각·AI 답변 검토 전달·재분석을 각각 확인한다.
- 레버리지 선택지는 암호화폐 최대 5배, 주식·ETF 1배로 유지되는지 확인한다.

## v3.9.1.26 공개 기준

> v3.9.1.26은 공개됐습니다. 위험예산 입력·질문형 확인 계약은 후속 버전에서도 유지합니다.

- 제품 버전 `3.9.1.26`, updater SemVer `3.9.126`, 설치 파일 `NoahAI-3.9.1.26-Setup.exe`, blockmap과 `latest.yml`이 일치해야 한다.
- [v3.9.1.26 검증 원장](archive/release/V39126_STRATEGY_RISK_INPUT_RECOVERY_TEST_PLAN.md)의 소스·Windows 항목을 완료해야 한다.
- 공개 v3.9.1.25→v3.9.1.26 자동 업데이트에서 다운로드·안전 종료·재시작·설정/원장 보존을 확인한다.
- 암호화폐 원문에서 `거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%`가 위험예산으로 인식되고 최종 저장값과 같은지 확인한다.
- 주식·ETF 원문에서 `거래당 계좌 손실 0.5%, 종목당 투자 비중은 최대 10%`가 1배 LONG 현물 계약으로 유지되는지 확인한다.
- `%` 없는 위험값은 추측되지 않고 차단되는지, 현재 선택값 추가 뒤 재분석이 필요한지 확인한다.
- 원클릭 보완이 진입·청산·방향·지표·임계값을 생성하지 않는지 확인한다.
- 아래 v3.9.1.25 및 누적 게이트를 계속 적용한다.

## v3.9.1.25 공개 기준

> v3.9.1.25는 공개됐습니다. Strategy Studio 입력 보존·AI 문맥·따라 만들기 복구 계약은 후속 버전에서도 유지합니다.

## v3.9.1.24 공개 기준

> v3.9.1.24는 공개됐습니다. Strategy Studio 가독성·허브 접근 계약은 후속 버전에서도 유지합니다.

## v3.9.1.23 공개 기준

> v3.9.1.23은 공개됐습니다. 통계·PAPER 생명주기 계약은 후속 버전에서도 유지합니다.

- 제품 버전 `3.9.1.23`, updater SemVer `3.9.123`, 설치 파일 `NoahAI-3.9.1.23-Setup.exe`, blockmap과 `latest.yml`이 일치해야 한다.
- [v3.9.1.23 검증 원장](archive/release/V39123_CANONICAL_LIVE_STATISTICS_TEST_PLAN.md)의 소스·Windows·실사용 항목을 완료해야 한다.
- 기관 등록부, 런타임·통계 집합, Web UI inventory 드리프트 테스트를 통과해야 한다. 향후 기관 추가 시 자격증명·주문·수명주기·원장·통계·PAPER·Strategy Studio·문서 중 하나라도 누락되면 지원 완료로 표시하지 않는다.
- 거래 통계에서 오늘·7일·30일·전체·사용자 지정의 `exit_time` 경계를 한국시간/UTC 혼합 계정으로 대조한다.
- 표시 기준을 설정해도 거래·체결·학습·Strategy Studio PAPER·위험 원장·열린 포지션이 변하지 않고, 기준 뒤 청산부터 포함되는지 확인한다.
- 6개 거래소와 4개 증권사에서 거래 통계·운영 KPI·AI 리포트의 같은 기간 체크섬과 KRW/USDT 분리를 대조한다.
- 현재 포지션은 모든 활성 기관 계좌 조회 성공 시에만 최신 합계를 사용하고 일부 실패에서는 저장 원장 참고 상태를 표시하는지 확인한다.
- `data/Teayu` 등 실제 사용자·테스터 폴더를 테스트 fixture나 자동 실계정 대상으로 사용하지 않는다. 개발·prekey 게이트는 offline으로 실행하고, release 실증권 점검은 승인된 QA 계정을 `--readiness-account`로 명시한다.
- 기관별 `통계 표시 기준 새로 시작`은 선택한 거래소/증권사 LIVE 화면만 바꾸고 다른 기관·다른 자산군·PAPER·학습·위험 원장에는 영향을 주지 않는지 확인한다. `전체` 선택은 현재 자산군 전체 표시 범위임을 확인한다.
- 전체 PAPER에서는 메인 운영 KPI가 현재 가상 포지션과 오늘 PAPER 청산으로 자동 전환되고, 거래 통계의 LIVE/PAPER 선택이 서로 다른 원장을 표시하는지 확인한다.
- Strategy Studio에서 최소 조건 전 일시정지가 `미통과`가 아닌 `PAPER 일시정지`이며, 재개 후 거래소별 근거와 활성 검증일수가 이어지는지 확인한다.
- `새 검증 시작`의 2회 확인 뒤 현재 진행률만 0으로 바뀌고 이전 attempt·패키지 여권·가상 청산 원장은 보존되는지 확인한다.
- 아래 v3.9.1.22 및 누적 게이트도 계속 적용한다.

## v3.9.1.22 패치 필수 게이트

> 공개 v3.9.1.21 자산은 변경하지 않습니다. 아래 수정은 v3.9.1.22 새 산출물로만 배포합니다.

- 제품 버전 `3.9.1.22`, updater SemVer `3.9.122`, 설치 파일 `NoahAI-3.9.1.22-Setup.exe`, blockmap과 `latest.yml`이 일치해야 한다.
- [v3.9.1.22 검증 원장](archive/release/V39122_UNIFIED_SIZING_PARALLEL_PAPER_TEST_PLAN.md)의 소스·Windows·실사용 항목을 완료해야 한다.
- 기존 v3.9.1.21 설정은 고정 Notional로 유지되고 계좌 위험 모드를 명시적으로 켠 경우만 수량이 변하는지 확인한다.
- 6개 거래소와 4개 증권사에서 평가금·SL·위험률·위험배수·Notional·증거금·수량·레버리지 XAI를 실제 주문값과 대조한다.
- LIVE 전략과 PAPER 관찰 전략이 서로의 신호·포지션·자금·주문 권한을 공유하지 않는지 확인한다.
- 아래 v3.9.1.21 및 누적 게이트도 계속 적용한다.

## v3.9.1.21 누적 게이트

> v3.9.1.21은 공개됐습니다. PAPER PnL·비용·로그·성과회복 귀속 계약은 후속 버전에서도 유지합니다.

- 제품 버전 `3.9.1.21`, updater SemVer `3.9.121`, 설치 파일 `NoahAI-3.9.1.21-Setup.exe`, blockmap과 `latest.yml`이 일치해야 한다.
- [v3.9.1.21 검증 원장](archive/release/V39121_PAPER_PNL_COST_VENUE_ATTRIBUTION_TEST_PLAN.md)의 소스·Windows·실사용 항목을 완료해야 한다.
- 6개 거래소 PAPER 활성 포지션의 청산 전 미실현 PnL과 예상 비용을 런타임·화면에서 대조한다.
- v3.9.1.19 Binance 비용 0 행의 추정 복구·미확정 분리 건수와 전략 스튜디오 비용 합계를 대조한다.
- 6개 거래소 동시 실행에서 로그 탭 교차 혼입이 없고 성과회복 제한이 거래소별 최신 표본으로 적용되는지 확인한다.
- 키움·신한·미래에셋·한국투자의 주식/ETF PAPER 포지션에서 현재가 기준 미실현 순손익, KRW gross/net PnL, 수수료·예상 세금·슬리피지를 대조한다.
- 주식과 ETF의 세금 계약, 부분청산 비용 배분, 보유량 초과 매도 차단 및 열린 포지션의 비용 계약 보존을 확인한다.
- 증권 PAPER 성과회복이 해당 증권사 PAPER 원장만 읽고 LIVE 체결 또는 다른 증권사 표본과 섞이지 않는지 확인한다.
- 4개 증권사 동시 조회·PAPER 운용에서 XAI·거래 로그의 소유 증권사와 화면 탭이 일치하는지 확인한다.
- v3.9.1.20→v3.9.1.21 업데이트 후 설정·자격증명·전략·PAPER 원장과 열린 PAPER 상태가 보존되는지 확인한다.
- Windows 산출물과 6개 거래소·4개 증권사 실제 환경 게이트 전에는 `pending_windows_rebuild`, `publish_ready=false`를 유지한다.
- 아래 v3.9.1.20 및 누적 게이트도 계속 적용한다.

## v3.9.1.20 누적 게이트

> v3.9.1.20은 공개됐습니다. PAPER 중지 권한·재시작 복구·멱등 청산·다중 전략 순환 계약은 후속 버전에서도 유지합니다.

- [v3.9.1.20 검증 원장](archive/release/V39120_PAPER_LIFECYCLE_EXECUTION_INTEGRITY_TEST_PLAN.md)의 누적 항목을 유지한다.
- PAPER 일시정지→늦은 청산→동기화만으로 실행 권한이 되살아나지 않는지 확인한다. 사용자가 명시적으로 `PAPER 검증 재개`한 경우에만 같은 attempt의 실행 권한이 다시 생기고 기존 근거가 이어져야 한다.
- 열린 Binance·Upbit·Bithumb·Bybit·Bitget·OKX PAPER 포지션을 만든 뒤 정상/강제 종료와 재시작에서 전략 버전·TP/SL·수량·진입가가 복구되는지 확인한다.
- 같은 position ID의 청산 재처리가 PAPER 이력·승률·전략 검증에 한 번만 집계되는지 확인한다.
- Binance PAPER에서 gross PnL, 왕복 추정 fee, 추정 slippage, net PnL의 산식과 화면 합계가 일치하는지 확인한다.
- 같은 거래소·종목에서 관찰 전략 2개 이상이 공유 슬롯을 공정 순환하고 LIVE 적용 전략의 충돌 HOLD 계약은 유지되는지 확인한다.
- UPBIT 다중 분석에서 public ticker 429가 폭증하지 않고 cache/backoff 뒤 복구되는지 확인한다.
- 100MB 이상 학습 데이터에서 이벤트 기록이 매번 전체 JSON 재작성으로 변하지 않고 journal 복구·checkpoint·archive가 중복/누락 없이 동작하는지 확인한다.
- Binance 일반 오픈 주문과 Algo Order 양쪽의 TP/SL을 감사해 실제 보호 주문을 누락 경고하지 않는지 확인한다.
- v3.9.1.19→v3.9.1.20 업데이트 후 설정·자격증명·전략·PAPER 원장과 열린 PAPER 상태가 보존되는지 확인한다.
- v3.9.1.19 및 누적 게이트도 계속 적용한다.

## v3.9.1.19 누적 게이트

> v3.9.1.19는 공개됐습니다. UNIFIED Binance 귀속·패키지 무결성·검증 대상 분리 계약은 후속 버전에서도 유지합니다.

- 제품 버전 `3.9.1.19`, updater SemVer `3.9.119`, 설치 파일 `NoahAI-3.9.1.19-Setup.exe`, blockmap과 `latest.yml`이 일치해야 한다.
- `archive/release/V39119_STRATEGY_PASSPORT_INTEGRITY_TEST_PLAN.md`의 소스·Windows·실사용 항목을 완료해야 한다.
- Binance 전용 전략과 UNIFIED 전략의 Binance PAPER 진입·청산이 각각 정확한 저장 버전에 귀속되는지 확인한다.
- `.noahstrategy` 내보내기→파일 저장→가져오기 후 IR/content hash가 같고, v3.9.1.18 구형 파일 복구가 해시 일치 파일에만 허용되는지 확인한다.
- 화면의 검증 대상이 원문 구조화 규칙과 NoahAI 기본 진입 오버레이를 구분하며 여권·랭킹에서 혼합되지 않는지 확인한다.
- 기존 미구조화 PAPER 후보를 보존하되 기본 NoahAI 분석·진입이 6개 거래소에서 계속되는지 확인한다.
- 최종 적용 전략의 조건 미충족은 기본 신호로 우회하지 않고 HOLD를 유지하는지 확인한다.
- 전략 문서 저장 → 실행 준비 → 사용자 승인 → PAPER 전진검증의 네 게이트가 UI와 API에서 분리되고, 실행 준비 실패 전략의 승인·자동검증·PAPER·적용이 모두 거부되는지 확인한다.
- 독립 전략의 LONG/SHORT별 방향·선언형 진입조건·전략 소유 TP/SL 단위와 안전 범위가 부족하면 실행 준비가 거부되고 UI에 정확한 이유가 표시되는지 확인한다.
- `confirm` 전략의 `inherit_noah_base`는 NoahAI 스마트 청산을 사용하고, `strategy_owned`는 승인된 고정 TP/SL을 유지하며, 독립 전략은 상속을 선택할 수 없는지 확인한다.
- 오늘·주간·월간·최근 1시간 AI 리포트 요약과 상세가 같은 청산 원장·거래소 필터·기간 하한·현재시각 상한을 사용하고 KRW/USDT를 합산하지 않는지 확인한다.
- 100건이 넘는 상세 원장을 페이지 이동해도 누락·중복이 없고, 전체 기간 체크섬과 통화별 손익·수수료가 요약과 일치하며 미래 시각 행이 제외되는지 확인한다.
- Upbit·Bithumb PAPER의 LONG/관리 LONG 청산과 Binance·Bybit·Bitget·OKX PAPER의 LONG/SHORT가 v3.9.1.16 거래소 계약을 유지하는지 확인한다.
- 6개 거래소 LEARNING·PAPER에서 LIVE 손실 판정·잔고 조회·외부 손실 알림이 0건인지 확인한다.
- LIVE에서만 거래소별 실현·미실현 손익으로 일일 손실을 판정하고, 빈/무효 잔고·포지션 응답을 100% 손실로 표시하지 않는지 확인한다.
- Telegram·Discord 실제 수신에서 `[LIVE]`·거래소·KRW/USDT를 대조하고, 6개 거래소별 ON/OFF·저장·재시작 보존을 확인한다.
- OKX 실제 파생 ticker가 `quoteVolume`을 생략해도 원문 `volCcy24h×last` USDT 거래대금으로 후보가 숫자 점수를 만들고, `vol24h`/CCXT `baseVolume` 계약 수를 기초자산 수량으로 오인하지 않는지 확인한다.
- OKX 정상 국면에서 `코인 선택 데이터 저장 완료`가 약 1분마다 반복되지 않고, 확정 국면 변경 또는 기본 3시간 주기에서만 정상 선정 세션이 추가되는지 확인한다.
- 강제 `fallback_unscored`에서 복구 간격이 60초부터 최대 15분으로 증가하고 동일 실패 원장은 기본 15분보다 자주 저장되지 않으며, 복구 성공 뒤 단계가 초기화되는지 확인한다.
- Strategy Studio의 Validation Lab과 거래소·기준통화별 PAPER 근거가 API 값과 일치하고 KRW/USDT가 합산되지 않는지 확인한다.
- 자연어/Pine 정답 코퍼스의 지원 입력은 의미가 보존되고 미지원 기능·단위 없는 TP/SL은 저장·승인 전에 차단되는지 확인한다.
- v3.9.1.18→v3.9.1.19 업데이트 후 설정·자격증명·전략·PAPER 원장이 보존되고 종료·재시작·롤백이 동작하는지 확인한다.
- Windows 산출물과 실제 계정 게이트 전에는 `pending_windows_rebuild`, `publish_ready=false`를 유지한다.
- 아래 v3.9.1.17 및 v3.9.1.16 누적 게이트도 계속 적용한다.

## v3.9.1.16 누적 게이트

> v3.9.1.15 자산은 변경하지 않습니다. 국내 KRW 현물 주문단위, 현물/선물/PAPER 실행 계약과 국면 요청 안정화는 v3.9.1.16 새 자산에서만 배포합니다.

- 제품 버전 `3.9.1.16`, updater SemVer `3.9.116`, 설치 파일 `NoahAI-3.9.1.16-Setup.exe`, blockmap과 새 `latest.yml`이 일치해야 한다.
- `archive/release/V39116_VENUE_EXECUTION_CONTRACT_TEST_PLAN.md`의 소스·PAPER·LIVE·업데이트 항목을 완료해야 한다.
- Upbit 시장가 매수 요청이 base 수량이 아니라 승인된 KRW 총액이고, 시장가 매도는 NoahAI 관리 base 수량인지 거래소 원장과 대조한다.
- Bithumb에 Upbit의 KRW cost 파라미터가 전달되지 않고 종목별 주문·체결 조회가 동작하는지 확인한다.
- Upbit·Bithumb에서 신규 SHORT·레버리지·수동/에어드롭 보유분 자동 매도가 0건인지 PAPER와 승인된 최소 LIVE에서 확인한다.
- Binance·Bybit·OKX·Bitget에서 LONG/SHORT와 reduce-only 청산이 유지되는지 확인한다. Bybit·OKX·Bitget은 단방향/헤지 계정 모드를 각각 검증한다.
- LEARNING 주문·가상체결 0건, PAPER 외부주문 0건, KRW/USDT 성과 원장 분리를 확인한다.
- 6개 거래소 동시 운용에서 15분봉 국면 요청이 기본 5분 동안 거래소별 1회이고 동일 분석 로그가 10초마다 반복되지 않는지 확인한다.
- v3.9.1.15→v3.9.1.16 업데이트 후 설정·자격증명·전략·PAPER 원장을 보존하고 설치·재시작·롤백을 확인한다.
- Windows 산출물과 실제 계정 게이트 전에는 `pending_windows_rebuild`, `publish_ready=false`를 유지한다.
- 아래 v3.9.1.15 누적 게이트도 계속 적용한다.

## v3.9.1.15 누적 게이트

> v3.9.1.14 자산은 이미 게시되었습니다. 주문규격 정합, Strategy Studio Level 4, Binance 후보 선정 복구, 단일 사이클과 상태 보존형 포지션 정합화는 v3.9.1.15 새 자산으로만 배포합니다.

- 제품 버전 `3.9.1.15`, updater SemVer `3.9.115`, 설치 파일 `NoahAI-3.9.1.15-Setup.exe`, blockmap과 새 `latest.yml`이 일치해야 한다.
- `archive/release/V39115_BINANCE_CYCLE_RECONCILIATION_TEST_PLAN.md`의 Windows 항목이 모두 완료돼야 한다.
- `archive/release/V39115_ORDER_CONTRACT_LEVEL4_STRATEGY_HUB.md`의 Windows 주문·Level 4 항목이 모두 완료돼야 한다.
- 기존 `min_trade_amount=20` 계정에서 초기 위험배수 0.10의 Binance PAPER 주문이 거래소 최소 규격 안에서 5.10 USDT로 검증되고, 설정 목표 20 USDT와의 잘못된 재비교가 없는지 확인한다.
- Opportunity 승인 상한이 최소 주문보다 작을 때 수량을 올리지 않고 주문 0건과 명시 가드레일 사유를 확인한다. SPLIT/PARALLEL/BEST의 승인 수량과 실제 제출 수량도 대조한다.
- Level 4 안정형·표준형·적극형 저장·재시작·IR/XAI·PAPER를 확인하고 승인·LIVE·손실중단·주문규격·TP/SL·중복방지·포지션 대조·긴급정지 해제 시도가 저장 단계에서 거부되는지 확인한다.
- Windows 신규·기존 사용자 각각에서 Binance 후보가 20초 안에 숫자 점수로 선정되고, 현재 사용자 캐시에만 상품·티커·백업 파일이 생성되는지 확인한다.
- 미산출 폴백을 재현한 뒤 실패 캐시 무효화·60초 쿨다운 재선정·복구 후 자동 `scored` 전환과 경고 비폭증을 확인한다.
- 설정/API 갱신 뒤 Evaluator와 Trader가 같은 최신 Binance 연결을 사용하는지 확인한다.
- 시작 버튼 1회 뒤 즉시 Binance 사이클이 1회만 실행되고 다음 사이클이 설정 간격 전에 시작되지 않는지 확인한다.
- 정상 포지션·정상 무포지션·네트워크 실패·시간 오차에서 포지션과 거래 플래그가 올바르게 유지 또는 정리되는지 확인한다.
- 계정 상태를 확인하지 못한 사이클에서 신규 주문이 0건이고 기존 TP/SL 보호 상태가 유지되는지 확인한다.
- 공개 v3.9.1.14 자산은 변경하지 않으며 Windows 산출물과 외부 게이트 전에는 `pending_windows_rebuild`, `publish_ready=false`를 유지한다.
- 아래 v3.9.1.14 누적 게이트도 계속 적용한다.

## v3.9.1.14 누적 게이트

- `archive/release/V39114_SELECTION_RECOVERY_BROKER_LIFECYCLE_TEST_PLAN.md`의 6개 거래소 후보 복구와 4개 증권사 조회 후 종료 계약을 유지한다.
- `archive/release/V39113_OKX_UI_ACCESSIBILITY_TEST_PLAN.md`의 OKX 지연 종료, 화면 3개 프리셋, 업데이트 알림과 PAPER 안내를 유지한다.
- Binance·Bybit 시간 복구, KIS 토큰 single-flight, LEARNING 명시 시작과 사용자 데이터 보존을 다시 확인한다.
- 아래 v3.9.1.12 누적 게이트도 계속 적용한다.

## v3.9.1.12 누적 게이트

- 제품 버전 `3.9.1.12`, updater SemVer `3.9.112`, 설치 파일 `NoahAI-3.9.1.12-Setup.exe`, blockmap과 새 `latest.yml`이 일치해야 한다.
- 공개 v3.9.1.11에서 업데이트한 뒤 사용자 설정·자격증명·전략 버전·PAPER 원장과 전략 패키지 저장소가 보존되는지 확인한다.
- AI 커스텀 상단 `무료 전략 허브 열기`·`제출·다운로드 안내`, 전략 목록 상단 `내 전략 제출`, 버전별 `허브에 제출` 링크가 공식 HTTPS 주소를 여는지 확인한다.
- `.noahstrategy` 내보내기 → daltrading 로그인 → 수동 제출 → 검토 상태 → 승인 전략 다운로드 → 비활성 가져오기 → 사용자 승인·자동검증·PAPER 재검증을 확인한다.
- API 키·계좌·잔고·개인 거래내역·승인/활성 상태와 로컬 절대경로가 제출 패키지와 공개 검증 여권에 포함되지 않는지 확인한다.
- 인앱 메뉴얼, `USER_MANUAL_SECTIONS.json`, 사용자 가이드와 AI 어시스턴트가 저장 위치·자동 업로드 금지·백테스트 한계·무료 베타 경계를 같은 의미로 안내하는지 확인한다.
- `docs/archive/release/V39112_STRATEGY_HUB_MANUAL_TRUST_TEST_PLAN.md`에 미완료 항목이 있으면 `publish_ready=false`를 유지하고 GitHub Release를 만들지 않는다.
- 아래 v3.9.1.11 누적 게이트도 계속 적용한다.

## v3.9.1.11 누적 게이트

- 제품 버전 `3.9.1.11`, updater SemVer `3.9.111`, 설치 파일 `NoahAI-3.9.1.11-Setup.exe`와 새 `latest.yml`이 일치해야 한다.
- 공개 v3.9.1.10에서 업데이트 후 6개 거래소에 먼저 중지 신호가 전달되고 60초 안에 잔류 프로세스 없이 종료되는지 확인한다.
- PAPER TP/SL 구형 단위, 활성 포지션 재시작 복구, 전략별 관찰 일수·청산 수, Upbit 현물 LONG 진입/청산을 `archive/release/V39111_SAFE_SHUTDOWN_PAPER_VALIDATION_TEST_PLAN.md`로 확인한다.
- 공통 SmartExitPolicy의 종목/거래소 표본 범위, 비용·변동성·ATR·RR 결정 추적과 AI 커스텀 불변 계약을 PAPER/LIVE dry-run에서 대조한다.
- 통합 5개 거래소의 새 PAPER 청산이 0원으로 저장되지 않고 KRW/USDT별 승률·손익·수수료와 개별 원장 합계가 일치하는지 확인한다.
- 아래 v3.9.1.10 누적 게이트도 계속 적용한다.

## v3.9.1.10 누적 게이트

- 제품 버전 `3.9.1.10`, updater SemVer `3.9.110`, 설치 파일 `NoahAI-3.9.1.10-Setup.exe`, 새로 생성한 `latest.yml` 참조가 모두 일치해야 한다.
- 공개 v3.9.1.9에서 업데이트 감지 → 안전 종료 → 설치 → 재시작과 잔류 `NoahAIEngine.exe` 0개를 확인한다.
- 집중 운용 1개·다중 운용 기본 3개·고급 상한 2개가 저장·재시작 뒤 Binance와 통합 거래소의 LIVE/PAPER에 동일하게 적용되는지 확인한다.
- PAPER 카드가 실계정 포지션이 아니라 런타임 가상 포지션을 표시하고 4개 이상 내부 스크롤, 가상 통계와 종료 이력 분리를 확인한다.
- 100MB 이상 PAPER 원장에서 반복 workspace 갱신 시간이 파일 전체 크기에 비례하지 않는지 확인한다.
- 적용 중 AI 커스텀 V1이 전역 PAPER에서 별도 재적용 없이 가상 실행되고 후보의 PAPER 전진검증 상태와 혼동되지 않는지 확인한다.
- 과거 자동검증 통과 전략이 명시적 PAPER 시작 전에는 실행 풀에 들어가지 않고, 시작 뒤에는 LIVE 활성 전략과 분리된 PAPER 풀에서만 실행되는지 확인한다.
- PAPER 최소 3건·7일 진행률, 일시정지/재개/새 검증 시도, 기본 전략과 AI 커스텀 전략의 최근 모의 청산 이력 및 실거래 통계 분리를 확인한다.
- 일반 안내의 포지션 답변이 관리 포지션·TP/SL·전략 버전·최근 신호에 근거하고, 심층분석에도 동일한 구조화 근거가 전달되는지 실제 Provider로 확인한다.
- Discord Webhook과 Telegram Bot Token/Chat ID를 저장·테스트하고 앱 재시작 뒤 등록 상태가 유지되며, 자격증명 원문은 설정 API·로그·지원 번들에 노출되지 않는지 확인한다.
- Telegram 개인/그룹 대화방 자동 찾기, 가드레일 중단·손실 경고·시장국면·런타임 이벤트, AI 리포트 수동 발송을 실제 수신 메시지와 대조한다.
- Discord/Telegram timeout·429·5xx·네트워크 단절을 강제로 만들어도 거래 루프·설정·AI 커스텀 응답이 대기하지 않고 제한 큐·재시도·cooldown이 상한대로 동작하는지 확인한다.
- WebUI 키움이 AnyIO worker에서 COM을 직접 만들지 않고 QAx 별도 프로세스로 연결·종료·재시작되는지 Windows에서 확인한다.
- Upbit·Bithumb 현물 SELL이 신규 SHORT 주문을 만들지 않고 보유자산만 줄이는지 PAPER/소액 승인 환경에서 확인한다.
- Binance·Bybit·OKX·Bitget LONG/SHORT와 거래소별 심볼 정규화·기준통화를 확인한다.
- 거래소 확인 체결, NoahAI 청산, 연결/미연결/레거시 상태와 오늘·주간·월간 SQL 전체 집계가 실제 API/DB와 일치하는지 확인한다.
- Bithumb 다종목 미체결, KIS ETF/ETN 현재가, 키움 별도 프로세스 QAx/COM 연결·종료·재시작을 Windows 실계정 읽기로 확인한다.
- 100MB 이상 학습 파일에서 최근 50개 초기 표시·50개 더보기·현재 운영 파일의 정확한 전체 학습 수와 UI 응답성을 확인한다.
- 메인 최근 100줄·거래소별 최근 200줄과 파일/세션 병합, 거래소·레벨·카테고리·숨김 필터를 확인한다.
- 6개 거래소 각각의 로그 분리와 독립 시작·정지, PAPER 일괄 시작/정지, 대시보드 KPI·실행 상태 갱신을 확인한다.
- 상세 로그·로그 레벨 저장 뒤 Trader·통합 Trader·Analyzer·connector의 즉시 반영과 재시작 유지를 확인한다.
- Windows cp949 로캘에서 기존 `🔧` 예외를 재현하고 새 sidecar가 UTF-8로 시작되어 API 요청 전에 중단되지 않는지 확인한다.
- Binance·Upbit·Bithumb·Bybit·OKX·Bitget 각각에서 기존 키 인식과 새 키 저장 → 재조회 → 앱 재시작 → 실제 읽기 계정 점검을 확인한다.
- HTTP 200이라도 거래소별 응답 `status`가 `success`가 아니면 연결 성공으로 표시하지 않는지 확인한다.
- 일반/고급 설정과 거래소/AI 자격증명을 저장한 뒤 검증 영수증, 닫기·재열기·앱 재시작 값 유지까지 확인한다.
- 기존 공통 AI 키 설정과 Provider별 신형 설정을 각각 복사해 OpenAI·DeepSeek 모델 조회를 확인하고, `NoahAIEngine.exe` TOC에 `openai`·`httpx`·`jiter`가 모두 포함돼야 한다.
- 키/SDK가 없어 네트워크를 호출하지 않은 경우와 실제 외부 API 요청 후 인증·권한·모델 오류가 난 경우를 화면 문구와 지원 로그에서 구분한다.
- 코인 선정·분석·최적화 중에도 내부 `.backup` 자동 복구와 사용자 미요청 복구가 발생하지 않아야 한다.
- `docs/archive/release/V39110_PAPER_POSITION_POLICY_STATISTICS_TEST_PLAN.md`에 미완료 항목이 있으면 `publish_ready=false`를 유지하고 GitHub Release를 만들지 않는다.

## v3.9.1.0 Web UI 내부 통합 후보 게이트

- 현재 검증 수치는 `docs/TEST_STATUS.md`의 최신 실행만 사용한다. 과거 `1,507 passed` 표시는 현재 Windows bundle 검증이 아니다.
- Web UI는 새 디자인이 아니라 기존 v3.9.0.10 `AITrading.exe`/`python3 main.py` UI의 기술 이전이다. 로그인창, 상단 사용자·거래소 표시, 서비스 버튼, 기능 탭 순서, 설정창, 하단 상태바가 기존 화면과 동등하지 않으면 빌드 성공과 무관하게 배포 금지다.
- 기존 CTk 기준 화면은 `ui/login_modern.py`, `ui/dashboard_modern.py`, `ui/settings_modern.py`이며, React/Electron 구현은 이 구조를 따라야 한다. “React 화면이 열린다”는 UI parity가 아니다.
- 화면별 최종 판정은 `docs/WEB_UI_1_TO_1_PARITY_EXECUTION_PLAN_v3.9.1.0.md`에 `SOURCE / MAC RENDER / LEGACY COMPARE / WINDOWS E2E`를 분리해 기록한다. `docs/WEB_UI_LEGACY_PARITY_MATRIX_v3.9.1.0.md`는 과거 부분 비교 참고자료일 뿐 완료 원장이 아니다. SOURCE PASS를 사용자 UI 완료로 승격하지 않는다.
- 위 실행 원장의 필수 행에 `OPEN`, `SOURCE`, `MAC`이 하나라도 남으면 Setup.exe 생성 여부와 무관하게 테스터·공개 배포를 금지한다.
- 게시 스크립트도 같은 원장을 읽어 미완료 상태에서는 `ConfirmExternalGates`가 전달돼도 실패해야 한다. 사람의 체크 실수로 이 차단을 우회하지 않는다.
- `config/web_ui_feature_inventory.json`에 `source_connected_parity_open`, `source_connected_external_e2e_open`, `legacy_parity_in_progress`, `read_first`가 하나라도 남으면 전체 기능 동등성 완료로 승인하지 않는다.
- Windows에서 `scripts/build_web_ui_windows.ps1`로 engine sidecar + Web assets + Electron NSIS를 한 번에 생성하고 산출물 SHA-256을 기록한다.
- `scripts/verify_web_engine_bundle.py`가 완성 `Analysis-00.toc`에서 `main`, `ui.*`, `tkinter`, `customtkinter` 0개를 확인해야 한다.
- Gateway는 loopback에만 bind하고 실행 token·Origin 제한·CSP·명시 intent를 유지하며 엔진 미연결 명령이 fail-closed인지 확인한다.
- Electron/engine sidecar의 단일 설치 bundle, 코드서명 정책, health, 원자 교체, 실패 롤백, 사용자 데이터 보존을 Windows에서 검증한다.
- 2026-08-20 Windows 후보는 `built_windows_unverified`, `publish_ready=false`다. 설치기 SHA-256은 `0f6888f0ef61ea1d815284048795196d1a481ec36d3e4778b6e3eb486197ac14`, source fingerprint는 `2e09b62a567af466ba54bd40efcce6a8b323c88cc72acfd8e4d39a46902ee950`이며 게시 시점에도 일치해야 한다. 로컬 설치·실행·engine health·메뉴 제거·안전 종료·제거는 PASS지만 원장의 OPEN/부분 항목 때문에 게시 스크립트가 차단됐다.

## 운영 정책 (2026-06-26 반영)

- SaaS 구축 완료 전까지 배포 지원 범위는 Windows 전용으로 고정한다.
- 개발 작업은 macOS/Linux에서도 가능하나, v3.9.1.0 최종 고객 배포 산출물은 Windows에서 생성한 `NoahAI-3.9.1.0-Setup.exe` 설치 bundle이다. 사용자는 설치 뒤 시작 메뉴/바탕화면의 NoahAI 앱을 실행하며 Node·Python을 별도로 설치하지 않는다.
- GitHub Release에는 `NoahAI-3.9.1.0-Setup.exe`, `latest.yml`, 동일 설치기의 `.blockmap`을 항상 함께 게시한다. `AITrading.exe + release-manifest.json` 단일 파일 교체는 v3.9.0.10에서 종료된 레거시 업데이트 계약이다.

## 0) v3.9.1.0 패키징 스펙 요약
- 소스 게이트: `.venv/bin/python scripts/active_source_audit.py`, `.venv/bin/python verify_build_includes.py`, `.venv/bin/python scripts/doc_consistency_check.py`, `.venv/bin/python scripts/verify_web_engine_bundle.py --spec-only`, 전체 pytest를 먼저 통과
- 격리 경계: `docs/SOURCE_QUARANTINE_MANIFEST_20260801.md`의 16개 아티팩트와 레거시 `theme_system`은 빌드 입력에 포함 금지
- 배포 상태: v3.9.1.0은 `built_windows_unverified`, `publish_ready=false`. 외부 게이트 확인 전 배포 완료로 변경하지 않음
- 직전 자산: v3.9.0.10 EXE SHA-256 `6aaa66787666...`는 `deploy/previous/AITrading-v3.9.0.10-AI-Custom-Management-Runtime-Integrity-Update.exe`에 보존
- UI 반복 게이트: 기존 CTk 기준 화면과 Web UI 화면을 먼저 대조한 뒤 Web UI 설정 100회, 5개 서비스·6개 거래소·4개 증권사 왕복 200회 후 잔류 dialog·빈 본문·가로 overflow·예기치 않은 종료 0건. Legacy CustomTkinter USER/GDI/TK_MENU 카운트는 fallback 비교 자료로만 기록한다.
- AI 커스텀 관리 게이트: 수정본이 다음 버전으로 저장되고 기존 승인본 불변, 활성 삭제 차단, 해제 후 삭제와 런타임 풀 제거 확인
- 레퍼럴 배포 게이트: daltrading 마이그레이션·관리자 설정의 암호화 Affiliate 조회 키·자동/예외 판정·주기 재검증·공식 HTTPS 링크·클라이언트 승인 전 API 검증/실행 차단을 테스트한 뒤 거래소별로 활성화
- **Web 스펙 정책**: v3.9.1.0은 독립 `noahai_web_engine.spec`만 사용한다. 레거시 `aiautotrade*.spec`을 읽거나 상속하면 빌드를 실패시킨다.
- UI 정책: v3.9.1.0 이상 설치 bundle은 React/Electron만 사용자 UI로 포함하고 CustomTkinter/Tkinter를 x64 sidecar에서 제외한다. Windows 키움 OpenAPI+의 PyQt5는 별도 x86 호스트에만 유지한다.
- VC 정책: x64 엔진과 x86 키움 호스트는 각 아키텍처의 공식 VC143 CRT를 사용하며 서로의 Qt/VC DLL을 섞지 않는다.
- datas 포함
  - config: `config/settings_template.json`, `config/token_template.json`, `config/theme_config.json`
  - Python 코드: PyInstaller Analysis/hiddenimports로 수집하며 소스 폴더를 `datas`로 이중 번들하지 않음
  - 루트 리소스: `README.md`, `requirements*.txt`, `icon.ico`, `icon.png`
  - 포함 안 함: data 폴더(런타임에 `path_utils`가 사용자 Documents 하위에 생성)
- hiddenimports(발췌)
  - 사용자 GUI: Electron bundle에 포함. `tkinter`, `customtkinter`, `main`, `ui`는 sidecar 포함 금지
  - 거래/네트워크: `websockets`, `websocket`, `websocket_client`, `binance`, `ccxt`, `ccxt.binance`, `ccxt.upbit`, `ccxt.bithumb`
  - 증권 어댑터(hidden import): `trading.exchanges.exchange_factory`, `trading.exchanges.adapters.kiwoom_stock_adapter`, `trading.exchanges.adapters.stock_mock_adapter`, `trading.exchanges.adapters.shinhan_stock_adapter`, `trading.exchanges.adapters.mirae_asset_stock_adapter`, `trading.exchanges.adapters.korea_investment_stock_adapter` (실브로커 4개 + mock 1개)
  - 키움 x86 호스트 전용: `pykiwoom`, `pykiwoom.kiwoom`, `PyQt5`, `PyQt5.QtWidgets`, `PyQt5.QtCore`, `PyQt5.QtGui`, `PyQt5.QAxContainer`
  - 유틸: `openai`, `numpy`, `pandas`, `loguru`, `aiohttp`, `ujson`, `dateparser`, `colorama`, `dotenv`, `psutil` 등
  - AI 자격증명: v3.9.0.5는 필수 `keyring`·Windows 보안 저장소 hidden import 없음
  - 플랫폼 주의: `win32_setctime`는 Windows 전용. macOS/Linux 빌드 시 제거/무시 필요
- excludes
  - macOS/Linux: `PyQt5`, `PySide6`, `qt4`, `qt6`, `wx`, `gtk` 등
  - Windows x64 엔진: `PyQt5`, `pykiwoom`, `PySide6`, `qt4`, `qt6`, `wx`, `gtk`; PyQt5·pykiwoom은 x86 키움 호스트에서만 수집
  - 과학/노트북 대형 패키지: `matplotlib`, `scipy`, `scikit-learn`, `tensorflow`, `torch`, `jupyter`, `ipython`, `pytest`, `unittest` 등

권장 Python 버전: 3.11+ (개발/테스트는 3.11-3.13에서 확인)
키움 OpenAPI+ 실연동 권장: Windows Python 3.11.x 32bit (COM/ActiveX bitness 일치)

## 1) 필수 설정
- OpenAI API Key 설정 및 테스트
- 거래소 API Key/Secret(및 OKX Passphrase) 입력 및 연결 테스트
- enabled_exchanges/selected_exchange 확인
- default_margin_type (ISOLATED/CROSS) 설정 확인
- 증권사 설정 저장 검증
  - `stock_broker_configs.shinhan.app_key/app_secret` 값 반영 확인
  - `stock_broker_configs.miraeAsset.app_key/app_secret` 값 반영 확인
- 저장 후 자동 1차 진단 옵션 확인
  - `ui_settings.auto_show_stock_broker_diagnosis_after_save` 기본값 `true`
  - 위험 경고 시 `연결 실패 5분 점검 가이드 열기`로 상세 체크리스트 실행

## 1-A) 사용자 동선/매뉴얼 동기화 (배포 게이트)
- 새 EXE를 캐시의 `AITrading.new.exe`가 아니라 정상 설치 경로에서 실행하고 자동 업데이트 진단의 설치 대상도 같은 정상 EXE인지 확인
- `release-manifest.json`의 installer·`latest.yml`·blockmap·engine sidecar SHA-256이 실제 빌드와 일치하지 않으면 업로드하지 않는다. 빌드 직후 상태는 `built_windows_unverified`, `publish_ready=false`이며 외부 게이트 통과 전 이를 배포 완료로 바꾸지 않는다.
- 릴리스 자산 재생성 뒤에도 `release_label=v3.9.1.0 Web UI Internal Integration Candidate`가 유지되고, bundle이 있으면 `build_status=built_windows_unverified`, `publish_ready=false`, 모든 자산의 `size>0`, SHA-256 비어 있지 않음을 확인
- x64 엔진에 PyQt5·pykiwoom이 없고, x86 키움 호스트가 PE `0x14c`이며 패키지 manifest SHA-256과 일치하는지 확인
- 키움 OCX 등록 환경에서 호스트 로그인/진단을 실행하고 x64 엔진의 실제 차트 OCR도 별도로 확인
- 승인된 레퍼럴 계정으로 Binance PAPER를 60분 이상 실행하고 제보 PC에서도 APPCRASH 재발 여부와 새 덤프를 확인
- Windows에서 로그인 성공 로그에 이메일·세션 ID·토큰·UID·레퍼럴 코드/URL이 남지 않고, 열린 로그가 25MB 회전 중 파일 잠금 오류를 만들지 않는지 확인
- Windows 이전 실행 PID 진단이 `<built-in function kill>` 오류 없이 초기화되는지 확인
- 설정창을 같은 프로세스에서 연속 100회 열고 닫아도 새 설정 Toplevel이 늘지 않고 상단 빈 영역·본문 밀림·하단 버튼 소실·`pyimage` 오류·대시보드 모달 고착·빈 흰색 확인창이 없는지 확인
- 블록체인↔주식/증권을 100회 왕복해 거래소와 증권사가 섞이지 않고, `코인 정보`/`종목 정보`가 source 탭보다 앞에 유지되며, 포지션 카드 2건 이상의 모든 글자가 보이는지 확인
- 위 두 시험의 각 10회마다 USER/GDI 수를 기록하고 `No more menus can be allocated`가 없으며 자원 수가 전환 횟수에 비례해 계속 증가하지 않는지 확인
- Bitget-only 레퍼럴 PAPER 프로필에서 Binance REST·WebSocket·K라인·펀딩비·OI 호출이 0건이고 토큰화 주식 심볼이 코인 후보에 포함되지 않는지 확인
- Upbit·Bithumb LIVE 소액 검증에서 기존 dust가 포지션 슬롯을 점유하지 않고 동일종목 중복 진입이 차단되며 앱 진입 전 수량은 청산하지 않는지 확인
- EXE와 manifest 다운로드 주소가 GitHub HTTPS인지 확인. 무서명 정책과 Windows SmartScreen/Defender 평판 경고 가능성을 배포 안내에 표시
- 열린 포지션/주문/주문 제출 중 기본 연기, 유지 모드 TP·SL 전수 확인, 청산 모드 실제 0건 확인을 각각 검증
- 종료·DB/log flush 실패 시 적용 금지와 `auto_update_transaction.json`의 단계·이전/새 버전·SHA·대상/백업 경로 기록 확인
- 재시작 후 버전·DB quick_check·API 읽기·포지션 복구 health check, 실패 자동 복원, 성공 알림, 사용자 재개 전 주문 잠금 확인
- 24~72시간 실행에서 숨은 AI 학습 탭이 `initial_defer_until_visible`을 반복 기록하지 않고 `ui_perf_metrics.jsonl`이 20MB×3 회전을 넘지 않는지 확인
- 숨은 금융 인텔리전스 탭에서 작업 없는 50ms 큐 폴링이 없고, 탭 파괴 후 callback이 재등록되지 않는지 확인
- 숨은 거래소·증권사 상세 탭에서 잔고·포지션·통계 API 호출이 중지되고, 다시 열면 최신값을 즉시 조회하는지 확인
- 비정상 종료 시 `runtime_stability.jsonl`·`runtime_faulthandler.log`를 회수하고 정상 종료와 구분
- 깨끗한 Windows PC에서 Python·pip·keyring 설치 없이 AI API 키 저장→앱 종료→재시작 복원이 되는지 확인
- v3.9.0.3 `credential_ref`만 있는 Provider는 일반 설정 저장을 막지 않고 `키 재입력 필요`로 표시되며, 키를 다시 입력하면 로컬 키가 정본이 되는지 확인
- 설정·백업을 지원 로그 압축에 포함하지 않으며 사용자별 설정 경로 권한과 마스킹 UI를 확인
- Binance 탭 진입 후 12초 안에 잔고 값·연결 대기·조회 실패가 표시되고 카드가 영구 `로딩 중`에 머물지 않는지 확인
- 실제 AI 기능 검증 중 설정 창을 닫아도 `invalid command name` TclError가 기록되지 않는지 확인
- Binance 진입 직후 실제 포지션 확인 뒤 TP/SL 1:1이 생성되고, 이미 청산된 포지션에는 `-4509` 보호주문을 반복하지 않는지 확인
- `trade_enabled_exchanges=[]` 저장 시 모든 실제 주문이 차단되고, 활성 거래소 일괄 선택 후 저장할 때만 선택 거래소 주문이 허용되는지 확인
- Binance/Bybit/OKX/Bitget/Upbit/Bithumb을 최소 위험으로 각각 주문 제출·체결·취소/청산 E2E 확인
- 코인 선정 정상 상태는 숫자 점수(`scored`), 목표 미달은 유효 후보만 `scored_partial`, 평가 전면 실패는 `fallback_unscored`·미산출로 표시되는지 확인
- `fallback_unscored`에서 Binance와 통합 거래소의 PAPER/LIVE 신규 진입은 0건이고 기존 포지션 TP/SL·감시·청산은 유지되는지 확인
- Binance의 거래 가능한 USDT 무기한 선물 전체 티커 중 거래대금 상위 후보가 실제 평가되며 거래소 정보 배열의 앞 100개 순서에 좌우되지 않는지 확인
- 정상 점수 후보가 있어도 후속 HOLD·AI 커스텀·가드레일 차단 시 주문하지 않는다는 설명이 Web UI와 내장 메뉴얼에 동일하게 표시되는지 확인
- AI 커스텀 고급모드에서 EMA 17·63, 15분·1시간 조건과 미지원 기간 501 차단, 런타임 실제 계산값 메타데이터를 확인
- AI 커스텀의 `AI 멘토 인터뷰`가 8개 프로필 질문 뒤 2~3개 후보를 설명하고, 후보 불러오기가 저장·승인·적용을 자동 실행하지 않는지 확인
- 같은 전략의 새 버전에서 `변경점 N개`를 열어 이전/변경 값을 확인하고 승인 전 활성 버전이 바뀌지 않는지 확인
- 고급 규칙의 부분청산·다단계 TP·추적손절·손익분기·재진입 범위 오류가 저장 전에 차단되는지 확인
- Binance·Bybit·OKX·Bitget PAPER와 최소 실계정에서 부분청산이 reduce-only 체결 확인 뒤 한 번만 기록되고 마지막 잔여 수량은 완전청산 통계로 이어지는지 확인
- 인증 개인 체결 스트림을 연결한 거래소는 공개 시세 WS와 별개로 건강 상태가 표시되고, 끊김 뒤 마지막 커서 이후 REST 증분 복구가 중복 없이 이어지는지 확인
- 전략 검증 연구소의 미사용 구간·워크포워드·비용/파라미터 민감도·몬테카를로·과최적화·PAPER 결과를 확인하고 `auto_promoted=false`인지 확인
- `.noahstrategy` 6단계 구현 시 API 키·계좌·잔고·개인 거래·로컬 절대경로·승인/활성 상태가 포함되면 내보내기/가져오기가 모두 실패 폐쇄되는지 확인
- 대시보드 하단에 `v3.9.1.0 Web UI Internal Integration Candidate` 식별과 `업데이트·사용법` 버튼이 노출되는지 확인
- 1500×980과 배포 최소 지원 해상도에서 하단 3영역이 한 줄로 유지되고 거래소·분석 탭의 마지막 카드·버튼이 잘리지 않는지 확인
- macOS와 Windows에서 상단 서비스·매뉴얼·설정·종료 아이콘의 모양·크기·정렬이 동일한지 확인
- 현재 서비스의 고유 선택 색상·테두리와 비선택 탭의 배경 구분이 명확한지 확인
- `업데이트·사용법` 클릭 시 사용자 매뉴얼 `업데이트` 탭이 열리고, 여기서 `AI 커스텀`·`금융 인텔리전스` 상세 사용법으로 이동 가능한지 확인
- 사용자 매뉴얼 `업데이트` 최상단에 Fix 1 설정창·서비스 탭·포지션 렌더 수정과 `pending_windows_rebuild` 경계가 노출되는지 확인
- 대시보드 업데이트 카드에 `AI 커스텀 P1~P3 · Windows UI 생명주기·서비스 탭 안정화`가 표시되는지 확인
- 거래 통계 기존 4개 KPI 아래 실제 운용 한 줄에 USDT·KRW 체결금액과 평균 보유시간·유효 건수가 표시되는지 확인
- AI 자동 리포트 오늘·주간·월간·실시간에 같은 통화 분리·청산일·보유시간 기준이 표시되는지 확인
- AI 커스텀의 거래당 허용손실·최대 증거금·레버리지 상한·국면 이탈 선택과 `개선안 · …` 버튼을 확인
- AI 커스텀의 `처음 사용법 AI에게 묻기`, `이 결과 AI에게 묻기`, 명시 국면 추천·제외 근거를 확인
- EMA/SMA 20·50·200, ADX, ATR, MACD 세부값, 볼린저 폭, 거래량·시간 조건이 XAI와 자동검증에서 같은 의미로 표시되는지 확인
- 미지원 필드·연산자가 조용히 무시되지 않고 승인 전에 `unsupported_executable_conditions`로 차단되는지 확인
- 자동검증 결과에 비용 전/후 PnL, 진입·청산 양쪽 수수료, 슬리피지·스프레드, Profit Factor, 기대값, MDD, 거래목록·국면별 결과가 표시되는지 확인
- 코인 전략의 명시 청산 조건이 진입 당시 전략 버전과 함께 포지션에 보존되고 Binance/Unified 모니터에서 평가되는지 확인
- 주식/ETF는 현재 선언형 진입·신호 임계값까지만 공통 지원하며 명시 청산까지 지원한다고 오표시하지 않는지 확인
- AI 어시스턴트가 모호한 설정 요청을 재질문하고, 현재값·변경안·위험을 설명한 뒤 허용 설정만 확인형으로 저장하는지 확인
- 설정 저장 후 파일 재조회 값이 변경안과 일치하는지 확인하고, 불일치 시 원래 설정으로 자동 롤백되는지 확인
- 현재 로그인 사용자의 앱 데이터 `assistant/settings_change_history.json`에 비밀값 없이 감사 이력이 저장되고 앱 재시작 뒤에도 마지막 변경 되돌리기가 가능한지 확인
- 주문·거래 시작/정지·API 키 변경을 채팅이 직접 실행하지 않는지 확인
- 자동검증 미통과 안전 시험만 1배·최대 1%이며 일반 운용 레버리지는 위험모델에서 계산되는지 확인
- 선택 거래소만 실제 주문하고 다른 활성 거래소는 학습 전용으로 표시·동작하는지 확인
- 전략 차단 결과에 국면 판단 시각·신뢰도·현재/후보 국면이 남고, 오래된 입력과 한 번만 튄 일반 국면 전환이 즉시 주문 근거가 되지 않는지 확인
- 동일 시장상태 캐시, 시장 이벤트 재호출, 호출 한도 시 로컬 신호 지속 로그를 확인
- 신규 거래의 `trade_log`에 진입/청산 주문번호·모델·전략·실체결 수수료 출처가 저장되는지 확인
- 7일 챔피언/챌린저에 수수료 차감 순PnL·거래당 순기대값·모델/전략별 비교가 표시되는지 확인
- 설정 `거래소 API` 탭에 아래 2개가 노출되는지 확인
  - `연결 실패 5분 점검 가이드 열기` 버튼
  - `설정 저장 후 연결 위험이 보이면 자동으로 1차 진단 안내` 체크박스
- 자동 동기화 게이트 통과 확인
  - `python3 scripts/user_visible_sync_guard.py --strict`
  - 사용자 노출 코드 변경 시 문서/인앱 4종(`CHANGELOG`, `USER_GUIDE`, `USER_GUIDE_AI_EXECUTION`, `user_manual_widget`) 누락이 없어야 함
- `.git`이 없는 복사본에서는 변경 파일 목록을 직접 전달해야 함
  - PowerShell: `$env:SYNC_GUARD_CHANGED_FILES='ui/dashboard_modern.py,ui/widgets/custom_strategy_widget.py,docs/CHANGELOG.md,docs/USER_GUIDE.md,RELEASE_NOTES.md,USER_GUIDE_AI_EXECUTION.md,ui/widgets/user_manual_widget.py'`
  - 이후 `python build_safe.py --platform windows` 실행
- 문서 진입점 확인
  - `RELEASE_NOTES.md`
  - `docs/CHANGELOG.md`
  - `docs/USER_GUIDE.md`
  - `USER_GUIDE_AI_EXECUTION.md`
  - `docs/STOCK_BROKER_WINDOWS_CONNECTION_CHECKLIST_20260611.md`

## 2) 경로/권한
- 저장 경로 확인: `docs/STORAGE_PATHS.md`
- 사용자 Documents/NoahAI* 하위 디렉토리 생성 권한 확인
- logs/analytics 디렉토리 쓰기 권한 확인

OS별 권한/경로 팁
- Windows
  - 경로: `C:\Users\<USER>\Documents\NoahAI\<username>`
  - Windows Defender의 Controlled Folder Access가 쓰기를 차단할 수 있음 → 예외 추가 또는 기능 비활성화 필요
  - 바이러스 백신/EDR의 랜섬웨어 보호 정책에 의해 `Documents` 쓰기 제한 여부 확인
- macOS
  - 경로: `~/Documents/NoahAI/<username>`
  - 처음 접근 시 “Documents” 접근 권한을 요청할 수 있음 → 시스템 설정 > 개인정보 보호 및 보안 > 파일 및 폴더에서 허용
  - iCloud Drive가 “데스크탑 및 문서” 동기화 중일 때 동기화 지연/충돌 가능성 확인
- Linux
  - 경로: `~/Documents/NoahAI/<username>` (배포 정책에 따라 XDG 문서 경로 상이 가능)
  - 디렉토리 소유권/퍼미션 확인(`chown -R <user>:<group> ~/Documents/NoahAI`)
  - SELinux/AppArmor 정책으로 쓰기 제한 시 예외 정책 추가 필요

## 3) 로그/모니터링
- trading.log 생성/회전 확인
- position_sizing_debug 필요 시 true로 활성화(문서화된 키워드 확인)
- position_sizing_persist 필요 시 true로 CSV 생성 확인

## 4) 의존성/환경
- Python 3.11+ 확인
- requirements 설치 (플랫폼별 파일 구분)
  - 개발/macOS: `pip install -r requirements.txt`
  - Windows 배포: `pip install -r requirements_windows.txt`
- **키움증권 Windows 빌드 PC 1회 필수**: `py -3.11-32 -m pip install -r requirements_kiwoom_x86.txt`
  - pykiwoom은 PyQt5.QAxWidget 기반이므로 전용 32비트 Python 환경에서 고정 의존성을 설치한다.
  - pyaudio 설치 실패 시: `pip install pipwin && pipwin install pyaudio`
- 음성 사용 시 STT 의존성 설치 확인
  - `SpeechRecognition>=3.10.0`
  - `pyaudio>=0.2.14`
  - macOS: PortAudio 선설치 필요 가능 (`brew install portaudio` 후 `pip install pyaudio` 권장)
- 네트워크 접근 가능(거래소/백엔드/OpenAI)
- 방화벽/프록시: HTTPS(443) 허용, 기업망 프록시 설정 확인
- OS 권한: 사용자 Documents/NoahAI* 폴더 쓰기 권한 확인(Windows/macOS/Linux)
 - 시간 동기화: NTP 동기화 또는 OS 시간 정확도 보장(서명/만료/서버 검증 이슈 예방)

## 5) 기능 확인
- 설정 저장 → 런타임 재초기화 동작 확인(대시보드 즉시 반영)
- Analyzer가 거래소별 데이터(CCXT OHLCV) 수신하는지 로그 확인
- UnifiedTrader 선물 주문 시 레버리지/마진 타입 자동 설정 로그 확인
- 대시보드 애널리틱스 요약 표시/자동 새로고침 동작 확인
- 네 서비스의 금융 인텔리전스 화면과 기본 버튼 확인
  - 블록체인·주식/증권 `금융 인텔리전스`
  - 자산 통합 `성과·위험 분석`
  - AI애널리스트 `금융 인텔리전스 허브`
- 결과의 출처·기준시각·오류·가정 표시와 분석/주문 분리 문구 확인

## 6) 백업/복구
- Documents/NoahAI*/logs, analytics, config, trading.db 주기적 백업
- 장애 발생 시 로그/CSV 기반 원인 분석 절차

## 7) 문서 링크
- 아키텍처: ARCHITECTURE.md
- 업데이트 계획: UPDATE_PLAN.md
- 저장 경로: STORAGE_PATHS.md
- 사용자 가이드: USER_GUIDE.md
- 마스터 문서: MASTER_DOCUMENTATION.md

## 8) FAQ (요약)
- CSV(analytics) 미생성: settings의 `position_sizing_persist: true` 확인, Documents/NoahAI*/analytics 쓰기 권한 확인
- 로그 미생성: Documents/NoahAI*/logs 권한/경로 확인, settings의 log_level 확인
- OpenAI 오류: API Key/네트워크/프록시 확인, 일시적 429/5xx 시 재시도
- 거래소 API 오류: 키/권한/네트워크/시간 동기화 확인, CCXT 버전 호환성 점검
- 프록시/방화벽: HTTPS 443 허용, 기업망 프록시 설정 반영
 - Windows 권한 문제: Controlled Folder Access 예외 추가, 관리자 권한으로 1회 실행 후 사용자 권한으로 재시도
 - macOS 권한 문제: “파일 및 폴더” 접근 권한 허용 후 앱 재실행

---

## 9) 빌드 절차(요약)

사전 준비
- 가상환경 구성 및 의존성 설치(프로젝트 루트에서 실행)

빌드 실행(v3.9.1.0 Web UI bundle 기준)
1) Windows 후보 빌드
   - `powershell -ExecutionPolicy Bypass -File scripts/build_web_ui_windows.ps1`
2) 산출물 확인
   - `deploy/web-release/NoahAI-3.9.1.0-Setup.exe`
   - `deploy/web-release/latest.yml`
   - `deploy/web-release/NoahAI-3.9.1.0-Setup.exe.blockmap`
   - installer에 내장되는 `deploy/web-engine/NoahAIEngine.exe`
3) 빌드 직후 manifest 확인
   - 네 자산의 크기·SHA-256이 채워지고 `build_status=built_windows_unverified`, `publish_ready=false`여야 한다.
4) `WEB_UI_TESTER_RUNBOOK_v3.9.1.0.md`를 완료한 뒤 게시
   - `powershell -ExecutionPolicy Bypass -File scripts/publish_web_ui_windows_release.ps1 -ConfirmExternalGates`
   - 로컬/원격 digest가 모두 일치해야 성공한다.

`build_safe.py`, `build_release_windows.ps1`, `release_tag_push.ps1`, `AITrading.exe` 단일 교체는 v3.9.0.x 레거시 복구용이다. v3.9.1.0 이상에서는 레거시 release 스크립트가 의도적으로 중단된다. macOS/Linux 빌드는 개발/내부 검증 용도로만 사용하고 고객 Windows 배포 자산으로 사용하지 않는다.

## 9-B) GitHub 자동 릴리즈 운영 (중요)

기준 저장소
- 자동업데이트 조회/릴리즈 업로드 기준 저장소는 `nwsoft/ai-trading-client` 단일 저장소로 운영한다.
- 웹사이트 저장소(`nwsoft/noahailabs-website`)는 공지/문서 반영 용도로만 사용한다.

자동 릴리즈가 동작하는 조건
- 클라이언트 코드가 Git 저장소 루트(`.git` 존재)여야 한다.
- GitHub Actions는 수동 실행으로 Windows 내부 후보를 빌드하고 artifact로 보관한다. 단순 태그 push만으로는 공개 릴리스를 만들지 않는다.
- 워크플로 파일: `.github/workflows/windows-release.yml`

`.git`이 없는 복사본에서 해야 할 일
1) Git 저장소 상태 확인
  - `git rev-parse --is-inside-work-tree`
2) `fatal: not a git repository`가 나오면 아래 중 하나 선택
  - A안(권장): 실제 클라이언트 Git 작업본(원격 연결된 폴더)에서 빌드/태그/푸시 진행
  - B안: 현재 폴더를 Git 저장소로 초기화 후 원격 연결
    - `git init`
    - `git remote add origin https://github.com/nwsoft/ai-trading-client.git`
    - 기본 브랜치 맞춤(`main` 또는 기존 운영 브랜치)

사용자가 GitHub에서 해야 할 작업
1) 저장소 존재 확인: `nwsoft/ai-trading-client`
2) Actions 권한 확인
  - Repository Settings > Actions > Workflow permissions: `Read and write permissions`
3) 릴리즈 권한 확인
  - 워크플로의 `permissions: contents: write`가 유지되어야 릴리즈 업로드 가능
4) v3.9.1.0 배포 실행
  - Actions의 `Windows Web UI Build And Release`를 먼저 `publish_release=false`로 실행해 내부 후보 artifact를 만든다.
  - Windows 테스터 실행표가 통과한 경우에만 `publish_release=true`, `confirm_external_gates=true`로 다시 실행하거나 로컬 게시 스크립트를 사용한다.

전환 운영 기준(질문 반영)
- `v3.9.0.5`:
  - 클라이언트 저장소 릴리즈 업로드(필수)
  - 웹사이트 저장소 공지/다운로드 안내 반영(권장)
- `v3.9.0.1`부터:
  - 자동업데이트 기준은 클라이언트 저장소 하나만 사용
  - 웹사이트는 문서/공지만 반영

## 9-A) macOS 서명 및 노타라이즈 절차 (선택·권장)

사전 준비
- Apple Developer 계정(Developer ID Application 인증서 보유)
- Xcode 및 Command Line Tools 설치
- notarytool 자격 증명 저장(1회):
  - xcrun notarytool store-credentials "noahai-notary" --apple-id <APPLE_ID> --team-id <TEAM_ID> --password <APP_SPECIFIC_PASSWORD>

1) 앱 번들 확인
- build_safe.py --platform macos 실행 후 dist/AITrading.app 생성 확인
- 필요 시 격리 속성 제거: xattr -dr com.apple.quarantine dist/AITrading.app

2) 엔타이틀먼트 파일(선택)
- CustomTkinter 기반 앱은 별도 entitlements 없이도 동작 가능
- 필요한 경우 최소 예시(entitlements.plist):
  - com.apple.security.files.user-selected.read-write (선택)
  - com.apple.security.cs.allow-unsigned-executable-memory (특수 케이스)
  - 샌드박스는 일반적으로 사용하지 않음

3) 코드서명(하든드 런타임 포함)
- codesign --force --deep --options runtime \
  --sign "Developer ID Application: YOUR NAME (TEAMID)" \
  --entitlements entitlements.plist \
  dist/AITrading.app
- entitlements가 불필요하면 --entitlements 옵션 생략 가능

4) 노타라이즈 제출 및 대기
- xcrun notarytool submit dist/AITrading.app --keychain-profile "noahai-notary" --wait
- 성공 시 id/status 출력

5) 스테이플(티켓 부착)
- xcrun stapler staple dist/AITrading.app

6) 검증
- spctl --assess --type execute -v dist/AITrading.app
- codesign -dv --verbose=4 dist/AITrading.app

문제 해결
- OSStatus -67062: 인증서/팀 ID/애플 ID 매칭, 신뢰 설정 확인
- Notarization Rejected: notarytool 로그로 거절 사유 확인 → entitlements/서명 옵션 보정 후 재시도

## 10) 사후 점검(필수)

패키징 구성 점검
- dist/ 또는 deploy/ 산출물 내에서 다음 확인
  - 포함: config 템플릿 3종, icon.ico/png, 코드 모듈(trading, api 등)
  - 포함 제외: data 폴더 전부(런타임 생성)
  - 배제: PyQt5/PySide6/Qt 관련 DLL/so, Jupyter/과학 패키지 바이너리

런타임 경로/권한 점검
- 빌드 산출물 실행 → 최초 실행 시 다음 확인
  - `~/Documents/NoahAI*` 폴더 자동 생성
  - 하위 `logs/` 내 `trading.log` 생성 및 로그 기록
  - `analytics/` 폴더(옵션)와 설정 템플릿 복사 위치 정상
  - 오류 시 `noahai_client/path_utils.py`의 경로 해석 로직 및 OS 권한 확인

기능 스모크 테스트(페이퍼 모드)
- 기본 설정으로 대시보드 실행 → 차트/요약/AI 탭 로딩 확인
- Analyzer에서 CCXT OHLCV 수신 로그 확인
- 모의 포지션 진입/청산 시도 → 레버리지/마진 타입 설정 로그 및 PnL 계산 정상 확인

## 11) 트러블슈팅

실행 중 "Module not found" 오류
- hiddenimports에 누락된 모듈 추가 후 재빌드(예: 특정 거래소 어댑터)
- macOS에서 `win32_setctime` 관련 오류 시 hiddenimports에서 제거

UI 초기화 오류/Qt 로딩 시도
- dist/deploy 내에 `PyQt5`, `PySide*`, `Qt*` 파일이 포함되었는지 확인 → 스펙 excludes 재점검
- 레거시 PyQt 파일은 ImportError 스텁으로 유지되어야 함

문서/권한 관련 오류
- macOS: 시스템 설정 > 개인정보 보호 및 보안 > 파일 및 폴더에서 앱 접근 허용 후 재실행
- Windows: Defender Controlled Folder Access 예외 추가 또는 임시 비활성화 후 재시도

네트워크/프록시
- 기업망 프록시 설정 반영 필요. HTTPS 443 오픈 여부 확인
- OpenAI/거래소 API 429/5xx는 지수 백오프 재시도 후 로그 확인
