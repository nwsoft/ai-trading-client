## 2026-10-07 — v3.9.2.7 Windows 공개 게시 최신 승인

사용자는 이 세션에서 Codex의 즉시 Windows 전체 빌드와 nwsoft/ai-trading-client v3.9.2.7 stable/latest 공개 게시를 명시적으로 승인했습니다. 이 승인은 아래의 소스 준비만 허용했던 이전 담당·게시 제한을 대체합니다. 제품 3.9.2.7 / updater 3.9.207, 공개 빌드 기준 v3.9.2.6을 사용합니다. 검사 생략 없이 x64 엔진, x86 Kiwoom 호스트, bootstrap/IPC, 실제 PE 정본 아이콘, 공개 자산 해시와 정확한 소스 태그를 검증합니다.

수동 OCX 로그인·LIVE 계정·실제 설치 업데이트/롤백·장시간 운용·외부 서비스 인수는 증거가 없는 한 미완료입니다. 허브 파서 패치는 별도 서버 변경이며 이번 클라이언트 공개로 배포되지 않습니다. 아래 문장은 당시의 인계 이력으로 보존합니다. 최종 게시 증거는 reports에 기록합니다.

## 2026-10-07 — v3.9.2.7 전략 업로드·PAPER 계산 수정 (소스 후보·미배포)

현재 소스 후보: v3.9.2.7 · updater 3.9.207. 현재 공개 기반: v3.9.2.6.
현재 소스 후보 버전: **v3.9.2.7**
현재 공개 버전: **v3.9.2.6**

Windows 빌드·릴리즈·게시 담당은 사용자입니다. Codex는 수정·로컬 검증·배포 준비만 수행합니다. 허브 파서 패치는 별도 서버 반영이 필요합니다. [수정 원인·기존 사용자 재개·검증 경계](V3927_FEEDBACK_PATCH.md). 아래 버전별 후보·미배포 표기는 당시 이력입니다.

현재 승인 범위에서는 Codex가 GitHub 빌드 workflow를 실행하거나 설치 파일/릴리스를 게시하지 않습니다. 아래 .6의 과거 게시 승인 문장은 당시 이력이며 이번 .7에는 적용하지 않습니다. 사용자는 현행 소스에서 `scripts/build_windows.ps1`로 빌드하고 설치본 인수 후 `scripts/release_windows.ps1`로 게시합니다. 검사를 생략하는 옵션은 사용하지 않습니다.

### .7 Windows 소스 인계

`reports/v3927-handoff/`의 Git bundle과 `WINDOWS_HANDOFF.txt`를 Windows로 가져옵니다. bundle은 공개 `v3.9.2.6` 태그를 기반으로 하며 원격 저장소에 push하지 않은 로컬 수정입니다. 인계 안내의 SHA-256·커밋·소스 지문과 대조한 별도 작업트리에서 기존 Windows 환경을 준비합니다. Node는 package.json의 `>=22.12.0`을 사용합니다. 이 안내는 빌드·배포를 자동 실행하지 않습니다.

새 작업트리에 없는 생성 manifest는 빌드 스크립트가 버전·해시를 고정한 공개 .6 manifest로 준비합니다. 이전 공개 .6 설치기도 해시·크기를 검증한 뒤 확보합니다. 새 .7 manifest와 인수 결과는 사용자의 Windows 빌드에서 생성합니다. Git 외부에 보관한 과거 Mac 충돌 파일은 새 PC의 빌드 입력이 아니므로 없다고 빌드를 막지 않습니다. 활성 소스의 충돌 파일 검사는 계속 적용하고, 과거 보관 폴더가 있으면 전체 파일과 해시를 검사합니다.

## 2026-10-06 — v3.9.2.6 전략 스튜디오·자율주행 후속 (개발 진행·미배포)

현재 소스 후보: v3.9.2.6 · updater 3.9.206. 현재 공개 기반: v3.9.2.5.
현재 소스 후보 버전: **v3.9.2.6** · 현재 공개 버전: **v3.9.2.5**

3.9.2.5는 빌드·릴리스·배포 완료한 공개 버전으로 보존합니다. 이후 로그·배분 정정, 코인/주식 종목 선택, 시작 버튼 기반 자율주행과 전략 스튜디오의 남은 고도화를 3.9.2.6으로 진행합니다. [실행 원장·완료 조건](UPDATE_PLAN.md#v3926-autonomous-studio-release). 새 Windows 설치본·공개 게시·실환경 인수는 아직 완료하지 않았습니다. 아래 날짜별 소스/후보/배포 표기는 당시 이력입니다.

### 2026-10-06 현재 Windows 게시 승인

사용자는 이 세션에서 v3.9.2.6을 즉시 Windows 빌드하고 stable/latest GitHub 릴리스로 공개하도록 Codex에 명시적으로 승인했다. 아래 사용자만 게시한다는 지침은 이 승인 이전의 인계 이력이며 이번 실행에는 적용하지 않는다. 전체 자동 검증과 x64 엔진·x86 Kiwoom 호스트·bootstrap/IPC·실제 PE 아이콘 검증을 통과한 정확한 소스 커밋으로 게시한다. 새로운 로컬 승인 변경을 보존하고 동기화 안정성을 최소 60초 확인한다. 실계좌·OCX 로그인·실제 설치 업그레이드/롤백·장시간 운용 인수는 수행 증거가 없으면 계속 미완료로 남긴다. 게시 결과는 reports에 별도로 기록한다.

Windows 검증 중 source-map-js 1.2.1의 high 취약점(GHSA-68fv-2mgg-jv7q)이 확인되어 lockfile을 수정 버전 1.2.2로 갱신했다. 정수 밀리초와 고정 시계로 통합 노출 테스트를 재현 가능하게 정정했으며 같은 시각의 접수 후 예약은 계속 차단한다. 런타임 안전 조건은 변경하지 않았다. 수정 후 전체 자동 빌드를 다시 수행한다.

### .6 Windows 빌드·릴리스 담당 (현재 승인 이전 이력)

사용자 결정에 따라 Windows PC의 빌드·릴리스·배포는 사용자가 담당한다. Codex는 소스·로컬 검사·문서와 릴리스 브랜치를 준비하며 GitHub 자동 후보 빌드/공개 게시를 대신 실행하지 않는다. 후보 workflow는 수동 요청만 지원한다. 기존 `.5` Git 작업트리를 덮어쓰지 않고 원격 `.6` 브랜치에서 새 작업트리를 준비한다. 기존 Windows Git 저장소에서 아래 순서로 진행한다(새 경로가 이미 있으면 다른 빈 경로 사용).

```powershell
git fetch origin
git worktree add --detach ..\noahai_client_release_3926 origin/release/v3.9.2.6-20261006
Set-Location ..\noahai_client_release_3926
# 기존 Windows 가상환경/Node 및 x86 Python을 준비한 뒤 실행
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
# 자동 검사·산출물 확인 후 DEPLOY_CHECKLIST의 설치/운영 인수를 진행
# 현재 상태만으로 즉시 공개하지 않으며, 인수 결과 확인 후 사용자가 게시
powershell -ExecutionPolicy Bypass -File .\scripts\release_windows.ps1
```

`reports/v3926-candidate-source.json`은 Codex 로컬 인계 기록이며 Git 저장소의 필수 파일이 아니다. Windows 작업트리의 실제 소스 신원은 다음 명령으로 확인하고 인계 커밋/지문과 대조한다.

```powershell
git rev-parse HEAD
.\.venv\Scripts\python.exe .\scripts\release_source_fingerprint.py --root .
```

검사를 생략하지 않고 미확정 주문·원장·기존 키/설정·전략을 보존한다. 로컬 검사 통과를 Windows 산출물 통과로 승계하지 않는다. 수동 검사가 끝나기 전 새 Windows 설치본/공개 게시를 완료로 표시하지 않는다.

Mac 로그인 이후 전체 사용자 과업도 아직 인수하지 않았다. 후보 빌드가 가능한 상태와 일반 공개 배포 준비 완료는 구분하며 [상태 재확인](UPDATE_PLAN.md#v3926-autonomous-studio-release)과 [인수 목록](DEPLOY_CHECKLIST.md)을 확인한다.

### .6 깨끗한 Windows 환경의 재현 빌드

GitHub Windows runner와 새 PC는 이전 설치기가 없는 경우 `scripts/restore_previous_release_asset.py`로 공개 .5 설치기를 확보합니다. `config/published_release_baselines.json`의 버전·파일명·크기·SHA-256과 대조한 뒤 원자적으로 보관하며 기존 파일이 다르면 덮어쓰지 않습니다. 이미 게시된 .5 자산이나 manifest를 수정하지 않습니다. Python 자료·시험·생성 JSON의 UTF-8 인코딩을 명시해 한국어/영어 Windows 기본 인코딩 차이를 제거합니다. 시험·엔진·x86 호스트·PE·bootstrap/IPC 검사를 생략하지 않습니다.

## 2026-10-05 — v3.9.2.5 생활금융 비교·후속 관리 (공개 Windows 릴리스)

현재 소스 기준: v3.9.2.5 · updater 3.9.205. 현재 공개 기반: v3.9.2.5 (2026-10-05 공개 게시·2026-10-06 GitHub latest 재확인).
현재 소스 기준 버전: **v3.9.2.5**

현행 Windows 실행 명령은 `powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`와 검증 후 `scripts/release_windows.ps1`입니다. 아래 v3.9.1.45 등 버전별 설명은 과거 기록이며 현행 버전은 이 상단과 `config/app_version.py`를 따릅니다. Windows에서 사용자 담당자가 검증 후 게시할 때 stable/latest를 갱신하며 수동 OCX 로그인·실계좌·설치/롤백·외부 서비스 인수는 자동 빌드/게시와 별도로 미검증 상태를 유지합니다.

공개 v3.9.2.4 이후 수정입니다. 상황별 진입, 목적 필터, 관심 보험 근거 설명, 비상금·보장·대환·사용 날짜 비교, 암호화 계획과 공통 조건, 자료 피드 갱신/복구, 상담 회신 견적, 기록 수정·가져오기를 구현합니다. [반영 범위·검증·운영 연결 인수](V3925_LIFE_FINANCE_COMPLETION.md). **3.9.2.5 Windows 설치기·blockmap·latest.yml·release-manifest.json은 2026-10-05 공개 게시되었습니다.** 아래 날짜별 후보/미게시 문장은 당시 이력입니다.


2026-10-06 공개 신원 대조: [GitHub 릴리스](https://github.com/nwsoft/ai-trading-client/releases/tag/v3.9.2.5)의 latest·게시 시각·4개 자산 digest를 보관된 게시 보고서와 대조했습니다. 설치본 게시와 실제 금융사·상담사 연결, 기관별 실계좌·장시간 인수는 별도입니다. [거래 화면·전략·문서 재감사](TEST_STATUS.md#v3925-trading-document-audit-20261006).

## 2026-10-04 — Windows 아이콘 누락 재발 방지

Windows/NSIS 아이콘은 추적된 루트 `icon.ico`, Mac 아이콘은 루트 `icon.png`를 사용합니다. 무시되는 `webui/build` 자산은 빌드 입력으로 사용하지 않습니다. 기존 NoahAI 파랑·보라·분홍 로고를 그대로 사용하며 새 로고를 생성하지 않습니다.

`scripts/verify_branding.py`는 빌드 전 파일 존재·정본 SHA-256·이미지 디코딩·ICO의 16/32/48/256 크기·패키징 경로를 검사합니다. Electron beforePack에서도 같은 검사를 실행하므로 직접 패키징도 누락 시 실패합니다. 소스 fingerprint에는 두 루트 아이콘, public PNG, 검사기와 Electron hook이 포함됩니다.

빌드 후 `win-unpacked/NoahAI.exe`와 버전별 Setup.exe의 실제 PE 아이콘 그룹 및 모든 이미지 payload를 정본 ICO와 대조합니다. 기본 Electron/NSIS 아이콘이나 잘린 리소스이면 빌드와 게시가 실패합니다. 증거는 `deploy/branding-verification.json`과 release-manifest의 `verification.branding`에 기록하며 게시 직전 다시 검사합니다. `python -m pytest -q tests/test_branding.py`는 누락·잘못된 이미지·기본 아이콘·패키징 경로·fingerprint 변경을 검사합니다.

전체 Python 및 Node 회귀, Web typecheck/build와 dependency audit, x64 엔진·x86 키움 호스트 빌드/스모크는 생략하지 않습니다. OCX 로그인·실계좌·설치 업그레이드·장시간 운용은 별도 실제 증거가 있을 때만 통과로 기록합니다. 이전 3.9.2.3 게시 자산은 교체하지 않습니다.

## 2026-10-04 — Mac 로컬 실행 복구

3.9.2.3 소스에 3.9.2.2 화면이 남아 실행이 종료되던 경로를 수정했다. 로컬 실행기가 설치된 호환 Node로 오래된 화면을 자동 재빌드하고 검증한 뒤 실행한다. Mac 의존성은 기존 lockfile로 복원했다. 바탕화면 `NoahAI.app`은 현재 작업본 실행기에 연결했다. 실제 Electron 화면 준비 이벤트·엔진 health 3.9.2.3, 누락 빌드 자동 복구, Node 계약 73개 통과. Finder/아이콘 시각 인수는 native UI 도구 장애로 미검증. [상세 원인·검증](V3923_MAC_LOCAL_LAUNCH_FIX.md). 공개 설치기·거래 정책·계정 자료는 변경하지 않았다.

## 2026-10-03 — v3.9.2.3 Windows 릴리스 후보

현재 소스 후보 버전: **v3.9.2.3** · updater **3.9.203**. 현재 공개 기반: v3.9.2.2. 공개 v3.9.2.2 자산은 보존하며 새 설치본은 전체 자동 검증 후 게시한다. 수익성 재진단·생활금융 조건 계산·암호화 보관·상담 연결 준비를 포함한다. 실계좌·OCX 로그인·전문가·실제 공급사/상담사 인수와 설치 업그레이드·장시간 운용은 미완료다. 아래 후보·미게시 설명은 작성 당시 이력이다.

## 2026-09-24 - v3.9.1.47 Strategy Repair and Reconciliation Diagnostics Patch (미배포 소스 후보)

현재 소스 후보 v3.9.1.47 / updater 3.9.147 · 공개 v3.9.1.46. 전략 등록·기존 버전 보완 및 손익 대조 차단 안내 개선. 원문 실행값의 저장 단계 변형을 제거하고 미완성 초안 보관과 기존 버전의 원문 재분석/명시적 기본 AI 진입 전환을 제공합니다. 기존 성과는 새 버전에 승계하지 않습니다. 손익 확인 실패의 일반 409/워커 장애 안내를 구체화하고 복구 대상과 위험 검사 대상의 불일치를 보강하며 거래별 미확정 사유를 표시합니다. 미확정 손익 무시·자동 LIVE 재개는 제공하지 않습니다.

소스 검증: 전체 회귀 3,736 통과·9 제외·3 subtests 통과. 코인/증권 브라우저 신규 등록·명시적 기존 버전 전환·미완성 초안 보관 6경로 통과(실제 로컬 컴파일러/검증기, 저장 API fixture). 숫자 30.0/30 직렬화 차이의 오차단과 기존 고정 TP/SL 불러오기 충돌도 수정했습니다. Windows 설치본·실계좌·9월 24일 미대조 1건은 미검증입니다. 현재 data/Teayu-001이 없어 고객 사본 회귀 1개도 제외됐습니다. 설치기 빌드·게시를 하지 않았고, 미확정 손익의 조건부 LIVE 재개는 구현하지 않았습니다. 상세 범위는 TEST_STATUS와 최신 V39147 검증 원장을 따릅니다. 아래 이전 수치는 이력입니다.

## v3.9.1.46 빌드 후보 — 2026-09-23

제품 3.9.1.46 / updater 3.9.146. 설치기 예정명 NoahAI-3.9.1.46-Setup.exe. 공개 v3.9.1.45 자산·manifest는 덮어쓰지 않습니다. 아래 이전 버전 명령은 이력이며 현재 package.json과 config/app_version.py를 정본으로 사용합니다. Windows 설치본·기관별 시작→관찰→실채널 수신은 미검증입니다. 이번 작업에서는 설치기를 만들거나 게시하지 않았습니다.

# NoahAI 빌드·릴리즈 가이드 — 현재 v3.9.1.45

현재 제품 **3.9.1.45**, Electron updater **3.9.145**, 설치기 **NoahAI-3.9.1.45-Setup.exe**. 공개 기반은 **v3.9.1.44**(사용자 확인 및 로컬 공개 manifest)이며 게시 직전에 원격 최신 상태를 다시 확인합니다.

오늘 지표 저장·조회·UI 안내 및 시장국면·알림 변경을 새 빌드에 포함합니다. `trading/indicator_evidence.py`, 두 거래 엔진의 학습 기록, `query_services`, 평가기, 알림·국면 관련 소스, 새 버전 package/lock/inventory, 재추출한 11탭 매뉴얼을 같은 소스 fingerprint로 묶습니다. [최신 변경](CHANGELOG.md) · [시험 경계](TEST_STATUS.md).

공개 v44의 `deploy/release-manifest.json`, `deploy/version.txt`, 해시와 기존 릴리스 자산은 덮어쓰지 않습니다. Windows에서 실제 v45 설치기·blockmap·latest.yml을 만든 후 자산 생성 도구로 새 manifest와 해시를 생성합니다. 기존 EXE의 이름·버전만 바꿔 배포하지 않습니다. 이 Mac 작업에서는 Client 설치기 빌드·게시를 하지 않으며 사용자가 수행합니다.

추가 Windows 확인: v43/v44 계정 업데이트 → 기존 학습 기록 보존 → 새 분석 생성 → RSI·MACD·추세와 모드/기관 확인 → 재시작 후 재조회. 기술점수 미산출은 별도 안내로 구분하고, 매매 정책·PnL 보호·국면 기본 300초/2회/600초가 유지되는지 확인합니다. 실제 메신저 전달·기관 계좌·장시간 운용은 로컬 모의시험과 별도입니다.

아래 v44 이하 인계는 상속 기능과 당시 기록입니다. 버전·자산 이름은 위 v45 기준 및 `config/app_version.py`/`webui/package.json`이 우선합니다.

## 과거 v44 복구 추가 인계

새 빌드에는 `binance_history_recovery`, `record_recovery`, `record_recovery_adapters`, 복구 UI·체결 상세·최신 매뉴얼을 함께 포함합니다. [추가 검증 보고](../reports/v39144-recovery-completion-verification.md)를 확인하고 Windows 설치본에서 설정 창 닫기 후 계속 진행, 앱 종료·재시작 이어하기, 기존 캐시 이관, 분할 청산과 계정 격리를 확인하세요. 이 버전은 Binance 전체 구간 복구를 증권사 지원으로 확대했다고 주장하지 않습니다.

## 당시 인계: 3.9.1.44 / updater 3.9.144

v44는 증거 보존형 학습 저장소·판단 DB 인덱스·공통 이벤트·유지관리 변경입니다. [v44 계획](V39144_STORAGE_TEST_PLAN.md)과 [검증 보고](../reports/v39144-storage-verification.md)를 먼저 확인하세요. 아래 v42/v43 자료는 상속 기능이며 해당 버전의 과거 미완료 게이트를 통과로 승계하지 않습니다. 고객 원본 DB는 수정하지 않았습니다. Client 설치기 빌드·배포는 사용자가 수행합니다.

v44 추가 게이트: Windows에서 기존 계정 업데이트 → 유지관리 저장소 최적화 → 재시작 → 학습·XAI·리포트 확인, 7기관 장시간 실행, 절전·강제 종료·디스크 부족·백신 잠금 시험. `deploy/release-manifest.json`과 `deploy/version.txt`는 이전 v43 산출물 증거이므로 이 소스 변경에서 수정하지 않습니다. 새 Windows 빌드가 v44 이름·실제 해시·fingerprint를 재생성해야 합니다. 공개 기반 상수 v42 및 문서의 과거 공개 설명은 현재 GitHub 게시 상태를 재확인한 결과가 아닙니다.

## v3.9.1.44 빌드 인계 — 2026-09-21

영어 베타 추가 이후의 소스로 빌드합니다. `webui/src/i18n/*.json`, `web_platform/display_preferences.py`, `web_platform/english_guide.py`와 재생성된 한국어 매뉴얼을 포함해야 합니다. [언어 범위/시험](V39142_ENGLISH_IMPLEMENTATION_PLAN.md) 및 [최종 보고](../reports/v39142-english-verification.md)를 확인합니다. Windows에서 기본 한국어 → English → 재시작 → 한국어, 계정별 보존, 100/125/150% 배율, 전략 입력/모드/손익 불변을 확인합니다. 번역은 표시만 변경하며 엔진 알림·고급 설명 전체 완역은 아닙니다.

언어 UI 후속도 포함합니다: 로그인 폼 하단, 설정 → 일반 → 표시 언어. Electron main/preload의 시스템 언어 전달 변경은 개발 앱 완전 종료 후 재실행해야 반영됩니다. 저장값 없는 한국어/영어 OS 첫 실행, 명시 선택 우선, 미지원 OS 언어의 한국어 fallback을 각각 확인합니다. 국가/IP 조회는 없습니다.

제품 3.9.1.44 / updater 3.9.144. 공개 v3.9.1.43 설치기·태그·latest.yml·manifest는 보존합니다. **이번 작업에서는 Client 설치기 빌드·릴리스를 하지 않으며 사용자가 수행합니다.** [V39142_REMOTE_CONTROL_PLAN.md](V39142_REMOTE_CONTROL_PLAN.md)의 최종 소스 시험과 미완료 Windows/실기관 게이트를 확인하세요. `web_platform/remote_control.py`, 원격 monitor/gateway/UI, 승인·명령 회귀 및 재생성한 매뉴얼을 포함한 fingerprint로 새 Windows 빌드를 식별합니다. daltrading 서버 배포 완료는 설치본 제어 검증 완료가 아닙니다.

# NoahAI 빌드·릴리즈 가이드

현행 소스 후보: **3.9.1.45** / Electron updater: **3.9.145**. 공개 stable/latest의 실제 버전은 게시 직전 원격에서 재확인하며, 기존 자산·태그·manifest는 불변입니다. 과거 설명은 [보존본](archive/build/BUILD_GUIDE_PRE_V39135.md)에 있으며 아래 명령만 현행입니다.

**v45 신규 빌드 필요:** [v45 검증 계획](V39145_INDICATOR_TEST_PLAN.md) 및 상속 원격 기능의 [검증 계획](V39142_REMOTE_CONTROL_TEST_PLAN.md)을 따릅니다. 기존 v42/v43 자산을 이름만 바꾸거나 재사용하지 않습니다. 현재 Mac 동기화 작업본에는 Git 이력과 Windows 도구가 없으므로 검토된 소스 커밋을 정식 Windows 빌드 환경에 전달해야 합니다. 이전 PnL 미완료 검증도 완료로 승계하지 않습니다.

## 공통 원칙

### 상속 기능의 입력 및 서버 선행 조건

[KPI·원격 실행 계획](V39141_REMOTE_KPI_IMPLEMENTATION_PLAN.md)과 [검증 보고](../reports/v39141-remote-kpi-verification.md)를 함께 확인합니다. `api/telemetry_batch.py`, `web_platform/remote_monitor.py`, `trading/remote_entry_pause.py`, 새 설정 UI 및 재생성한 매뉴얼을 포함한 **새 소스 fingerprint**로 빌드합니다. 시장 트렌드만 들어 있던 이전 v42 fingerprint는 재사용하지 않습니다.

**추가 배포 차단 게이트:** [DB 기반 PnL 조사](V39141_PNL_GUARDRAIL_FEEDBACK.md). `trading/binance_close_evidence.py`, `trading/daily_risk_basis.py`와 새 계산 경로가 포함된 소스를 다시 식별합니다. 특정 사용자 과거 40건 복구는 필수 조건이 아니지만 기존 미대조 기록을 가진 사용자의 안전한 업데이트 처리·실기관/Windows·계좌 일별 대조는 미완료입니다. 빌드 성공은 이 게이트를 해제하지 않습니다.

daltrading 서버의 `docs/V39141_REMOTE_KPI_DEPLOYMENT.md`에 따라 DB 분리/복원과 relay를 먼저 검증합니다. Client는 구형 서버에 개별 KPI로 호환하지만 원격 베타는 서버 활성화가 필요합니다. Windows에서 모바일 로그인과 PC 인증 공존, 오프라인/만료, 신규 제출 정지·보호 청산 유지·PC 재개를 확인한 뒤 20→100→300명으로 확대합니다. 소스 통과가 Windows 설치본·운영 DB 이관 완료를 뜻하지 않습니다.

- **v3.9.1.37부터 태그 대상 필수:** 빌드 입력을 검토·비밀정보 제외 후 Git에 커밋하고 해당 커밋을 원격에 게시합니다. 기본 브랜치의 오래된 HEAD에 태그를 자동 생성하지 않습니다. 기존 v37 이하 태그·설치 파일은 보존합니다.
- 매뉴얼·기관 레지스트리 생성 결과도 커밋에 포함한 뒤 새 체크아웃에서 빌드합니다. `.gitattributes`의 LF 줄바꿈을 적용해 커밋 내용과 실제 빌드 입력 바이트가 일치해야 합니다. `git add .`로 계정 데이터·자격증명·로그·DB·설치기를 일괄 공개하지 마세요.
- 게시 전 `verify_release_provenance.py`가 manifest의 source_revision=HEAD, 커밋/로컬/빌드 fingerprint 일치, 원격 커밋 존재, 기존 태그 불충돌, 커밋 날짜를 검사합니다. 미커밋·미추적·삭제된 빌드 입력도 차단합니다. 관련 없는 생성 산출물은 소스 변경으로 간주하지 않습니다.
- Windows와 macOS 모두 검증된 `--target`으로만 새 태그를 만들고 업로드 전에 태그를 다시 대조합니다. 이미 있는 태그가 다르면 자동 이동·삭제하지 않습니다.
- stable 게시 후 공개 목록 첫 항목·Atom 첫 항목·Latest·latest.yml/설치기 이름이 같은 버전인지 확인합니다. 전파 지연 등으로 불일치하면 **게시되었지만 검증 미완료**로 실패 처리하며 삭제/재태깅하지 않습니다. `python scripts/verify_release_provenance.py --phase published`로 읽기 전용 재확인합니다.

- `config/app_version.py`, `webui/package.json`·lock의 updater 버전, Windows 리소스 버전이 일치해야 합니다. 변환식은 `A.B.C.D → A.B.(C*100+D)`입니다.
- 소스 테스트 통과, 패키지 실행, 실제 계정 연결, 장시간 PAPER 검증은 서로 다른 증거입니다. [v3.9.1.45 검증 계획](V39145_INDICATOR_TEST_PLAN.md)의 실제 확인한 행만 `[x]`로 표시합니다.
- 소스 fingerprint는 `scripts/release_source_fingerprint.py`로 계산합니다. 변경된 소스에 이전 바이너리·해시를 재사용하지 않습니다.
- 사용자 `data/Teayu`·API 키·원장은 빌드 입력이나 공개 릴리즈에 포함하지 않습니다. 빌드되는 data는 공개 금융상품 카탈로그뿐입니다.
- `deploy/release-manifest.json`은 Windows 산출물 명세입니다. macOS는 `deploy/mac-release/release-manifest-mac.json`을 사용하며 서로 덮어쓰지 않습니다.
- 이미 게시된 파일은 덮어쓰지 않습니다. 일반 사용자 배포는 stable/latest, 별도 테스트 후보만 명시적인 prerelease를 사용합니다. 외부 실계정·장시간 검증이 남아 있어도 자동 회귀·엔진·키움 x86·해시 검증을 통과한 운영자 배포는 pending 상태를 manifest에 남기고 stable/latest로 게시합니다. macOS 무서명 파일은 계속 수동 테스트용입니다.
- 서명 없는 macOS 파일에 Gatekeeper 우회나 격리 속성 제거를 권장하지 않습니다. Developer ID 서명·공증 완료 전에는 일반 사용자용 정식 설치본으로 안내하지 않습니다.

## 자동 업데이트 계약

- 3.9.1.45 일반 설치본은 GitHub stable/latest만 조회하고 prerelease·다운그레이드를 허용하지 않습니다. 앱의 Beta 명칭은 사전공개 채널 선택을 뜻하지 않습니다. 테스트 prerelease는 수동 설치용입니다. Windows에는 `latest.yml`, macOS에는 `latest-mac.yml`과 해당 플랫폼 설치 자산을 같은 버전·같은 Release에 함께 게시해야 합니다.
- `백그라운드 업데이트 확인`이 ON이면 로그인 후 15초 뒤 첫 확인을 하고, 이후 사용자가 저장한 1~72시간 주기로 확인합니다. OFF여도 `지금 버전 확인`은 사용할 수 있습니다.
- `업데이트 자동 다운로드`가 ON이면 새 버전을 발견한 뒤 다운로드합니다. OFF이면 알림만 표시하고 사용자가 다운로드 버튼을 눌러야 합니다.
- Windows에서 `종료 시 자동 설치`가 ON이고 다운로드가 완료된 상태라면, 정상 종료 시 거래 엔진·기록의 안전 종료가 성공한 뒤 설치합니다. OFF이면 업데이트 화면의 `설치·재시작`을 사용합니다. 안전 종료 실패 시에는 설치하지 않습니다.
- macOS 자동 업데이트는 앱 코드서명이 필요합니다. 현재 서명 없는 테스트 DMG/ZIP은 같은 Release에서 수동 다운로드·설치만 가능하며, 설정 스위치만으로 이 제약을 우회할 수 없습니다.
- 이미 게시된 `v3.9.1.35` 자산에는 게시 후 수정한 종료 설치·prerelease 조회 패치가 들어 있지 않습니다. 다만 stable/latest 전환으로 v3.9.1.34 Windows 설치본은 v3.9.1.35를 확인·다운로드할 수 있습니다. 같은 버전 자산을 교체하지 말고 다음 제품 버전으로 패치를 빌드·게시한 뒤 이전 설치본에서 1회 실제 업데이트를 검증합니다.
- v3.9.1.45은 새 x64 엔진·x86 키움 호스트·Electron 설치기로만 빌드합니다. 공개 v3.9.1.44의 설치기·blockmap·`latest.yml` 이름이나 해시를 복사·교체하지 않습니다.

## Windows PC 준비

1. 프로젝트 폴더에서 `git rev-parse --show-toplevel`, `git status --short`로 저장소와 사용자 변경을 확인합니다. 동기화 폴더의 복사본을 사용할 경우 원본 소스·fingerprint를 담당자와 대조하세요. 다른 PC의 `.venv`·`node_modules`를 재사용하지 않습니다.
2. Windows 10/11 x64, Python 3.11 x64, Python 3.11 x86, Node >=22.12, Git, GitHub CLI, Visual Studio Build Tools/VC143 CRT를 준비합니다.
3. 개발 환경을 설치합니다. 아래는 프로젝트 루트에서 실행합니다.

```powershell
py -3.11-64 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements_windows.txt
py -3.11-32 -m pip install -r requirements_kiwoom_x86.txt
npm --prefix webui ci --include=optional
gh auth status
```

`py -3.11-32` 대신 별도 x86 환경을 쓸 때는 `NOAHAI_PYTHON_X86`에 해당 python.exe의 절대경로를 지정합니다. 일반 사용자는 x86 Python을 설치할 필요가 없습니다. 호스트 EXE가 설치기에 포함됩니다.

## Windows 빌드 → 자동 검증 → 릴리즈

```powershell
# 1. 전체 자동 검사와 두 아키텍처 빌드
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1

# 2. 일반 사용자용 stable/latest 게시
powershell -ExecutionPolicy Bypass -File .\scripts\release_windows.ps1

# 3. 빌드와 stable/latest 게시를 한 번에 수행
powershell -ExecutionPolicy Bypass -File .\scripts\build_and_release_windows.ps1
```

일반 사용자용 빌드·stable/latest 게시를 한 번에 수행하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_and_release_windows.ps1
```

`build_and_release_windows.ps1`은 전체 회귀, Web 빌드와 감사, x64 엔진 smoke, 키움 x86 PE·인증 IPC, NSIS 설치기, 해시·업데이트 메타데이터와 Git provenance가 모두 통과해야 게시합니다. 실계좌 주문, 키움 OCX 로그인, 실제 업그레이드 조작과 장시간 운용은 빌드 시스템이 재현할 수 없는 external validation으로 manifest에 기록하지만 stable 릴리즈를 차단하지 않습니다. 별도 확인·override 옵션은 필요하지 않습니다. `SkipTests`, `SkipEngineBuild`, `AllowMissingKiwoomHost`는 공식 릴리즈에서 사용하지 않습니다.

산출물:

```text
deploy/web-engine/NoahAIEngine.exe                 x64
deploy/web-engine/NoahAIKiwoomHost.exe             x86, PE 0x14c
deploy/web-release/NoahAI-3.9.1.47-Setup.exe
deploy/web-release/NoahAI-3.9.1.47-Setup.exe.blockmap
deploy/web-release/latest.yml                      updater 3.9.147
deploy/release-manifest.json
```

빌드 전 `deploy/release-manifest.json`이 v3.9.1.43을 가리키는 것은 정상입니다. 이 파일은 공개 증거이며 Windows v44 빌드가 성공해 새 해시를 계산하기 전 문서 편집만으로 v44 값이나 가짜 해시를 넣지 않습니다. 빌드 스크립트가 새 산출물에서 v45 manifest를 생성한 뒤 설치기·blockmap·`latest.yml`과 함께 검증합니다.

### v3.9.1.45 추가 확인

**현재 배포 보류:** [v45 검증 계획](V39145_INDICATOR_TEST_PLAN.md)의 Windows 외부 게이트와 [거래 기록 복구 계획](V39143_RECORD_RECOVERY_PLAN.md)의 미완료 항목을 확인합니다. 버튼/자동시험 통과를 과거 40건 복구 또는 전 기관 일별 계좌 대조 완료로 해석하지 않습니다. 로컬 공개 manifest는 v44이며 이번 작업에서 설치기 생성·게시를 수행하지 않았습니다.

v44 추가 인수시험: 유지관리의 한/영 설명·기록 충돌 경고·보관 로그 용량·압축 실패 재시도를 확인합니다. 테스트 계정의 닫힌 로그 압축 전후 내용이 같고 활성 로그는 유지되며, 예산 초과 후 공간 확보 시 기록이 재개되어야 합니다. 증권/ETF의 청산 XAI에 주문 ID와 실행 모드가 연결되는지, 타임아웃을 실주문 없음으로 잘못 표시하지 않는지도 확인합니다. 기존 고객 원본으로 파괴 시험을 하지 않습니다.

유지관리 시험: 설정 → 업데이트에서 거래 기록 점검·복구를 실행하고 진행/실패/이어하기/미확정 사유, 한국어·영어, 재시작 후 상태, 최초 백업과 변경 기록을 확인합니다. 실제 주문은 제출하지 않으며 PAPER/통계 표시 기준/손실 한도가 유지되어야 합니다. 실행 중 워커는 복구된 근거로 기존 정책을 재평가하므로 결과 확인 전 신규 거래를 원하지 않으면 기존 신규 진입 일시정지를 사용합니다.

Binance 시험: 청산 ID 누락뿐 아니라 기존 ID의 분할 청산·수량 불일치를 포함합니다. 주문·체결·Algo·income 수집 구간이 증가하고, 조회량 제한 후 설정 창을 닫아도 앱 실행 중 추가 클릭 없이 이어지는지 확인합니다. 독립된 진입·청산 구간이 증명되면 원래 거래 행·체결 원장·순손익이 일치해야 합니다. 음수 손익을 양수로 바꾸거나 미대조를 삭제하지 않아야 하며, 타임아웃/혼합 진입/포지션 변경/보존기간 초과는 구체적 사유가 남아야 합니다. 사용자 API 키는 개발자에게 전달하지 않고 설치된 연결로 조회합니다. 최신 회귀와 고객 DB 사본 시험은 [추가 검증 보고](../reports/v39144-recovery-completion-verification.md)를 따르며 실제 고객 API 정산 완료와 구분합니다.

먼저 [v42 필수 점검](V39142_REMOTE_CONTROL_TEST_PLAN.md)의 기간별 시장 트렌드·데이터 경계·화면 근거 XAI·빈 상태와 Windows DPI를 확인합니다. v41의 AlphaArena·전략 스튜디오/설정 및 아래 거래·검증 항목도 회귀 확인합니다.

1. Strategy Studio 과거재생에서 검증 캔들, 모든 진입·청산 화살표, 선택 거래 이름·원본 가격, 청산 기준 수익률 곡선과 거래표를 확인합니다.
2. 코인과 주식·ETF 각각 500봉 검증을 실행하고 기관·자산·통화·비용·전략 버전이 결과와 일치하는지 확인합니다. 국내 현물 신규 SHORT는 계속 차단되어야 합니다.
3. 7개 코인 거래소와 4개 증권사에서 PAPER는 `가상 포지션`·`가상 거래 통계`, LIVE는 상품에 맞는 `포지션/보유자산`·`실거래 통계`를 표시하는지 확인합니다.
4. 기관별 거래내역은 PAPER/LIVE 모두 기본 접힘이며 모드·기관 전환 시 다시 접혀야 합니다. LIVE 탭 선택만으로 실행 모드가 바뀌어서는 안 됩니다.
5. LIVE 종료 원장의 확정·미확정·외부·가져오기·통화 불명·조회 실패를 구분하고 PAPER/LEARNING 기록이나 다른 기관·계정 기록이 섞이지 않는지 확인합니다.
6. Binance TP/SL 청산 직후 해당 거래의 주문 ID·실현손익·수수료가 확정 대조되는지, 같은 종목 연속 2건의 첫 손익이 유지되는지 확인합니다. 모호한 수동 체결을 섞으면 자동 연결되지 않아야 합니다.
7. 시장 트렌드에서 코인/주식 각각 오늘·7일·30일을 전환하고 시장 폭 원형 그래프, 미니 추세선, 거래량·변동성, 데이터 누락 안내와 두 AI 질문 버튼을 확인합니다. 주식 장기 기간은 선택 증권사 일봉을 순차 조회하며 실패 종목을 당일 수익률로 대체하지 않아야 합니다.
8. 공개 v3.9.1.44 설치본에서 v3.9.1.45을 확인·다운로드하고 거래 엔진 안전 종료 뒤 설치·재시작되는지 확인합니다. 설정, 계정 자격정보, 전략 버전, 검증 결과와 PAPER/LIVE 원장을 대조합니다.

### 키움 10054 확인 순서

1. 패키지 호스트의 PE x86·버전·SHA를 manifest와 대조합니다. x64 엔진 성공은 x86 호스트 연결 성공이 아닙니다.
2. 설치본에서 연결하고 사용자 logs의 `kiwoom_host_events.jsonl`을 확인합니다. `adapter_import → adapter_ready → rpc_connect → activex_registry → activex_construct → activex_ready` 중 마지막 단계가 중단 지점입니다. API 키·비밀번호·계좌 응답을 이 로그에 쓰지 않습니다.
3. `activex_registration_missing`이면 동일 PC의 32비트 OpenAPI+ 등록과 KOA Studio 로그인부터 확인합니다. `activex_construct`에서 프로세스가 종료되면 Windows 이벤트 뷰어의 응용 프로그램 오류에서 종료 시각·오류 모듈·코드를 수집합니다.
4. 준비 완료 응답 전 타임아웃, 로그인 실패, RPC 종료를 구분합니다. 10054만 보고 인터넷 장애나 재설치로 단정하지 않습니다.
5. 주문 응답 미확정은 자동 재전송하지 않습니다. PAPER로 로그인·시세·잔고·종료/재시작을 검증한 뒤 LIVE 권한을 별도로 확인합니다.

## macOS arm64 빌드

이 스크립트는 현재 Python/Node 아키텍처가 arm64인 Apple Silicon Mac에서 실행합니다. Intel/universal 빌드를 검증한 것으로 표시하지 않습니다. 키움 OpenAPI+는 macOS에서 지원하지 않습니다.

```bash
# 새 환경은 Python 3.13 arm64로 생성합니다. Windows의 NumPy/Pandas 고정값을 Mac 3.13 환경에 혼용하지 않습니다.
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements_macos.txt
# Node >=22.12가 PATH에 있어야 합니다.
.venv/bin/python scripts/build_macos.py
```

고정 의존성/OCR·PDF·자료 가져오기 사전 검사·전체 Python 회귀·매뉴얼/문서 검사·locked npm 설치·Web 빌드·PyInstaller 엔진·bootstrap smoke·Electron DMG/ZIP·패키지 엔진 smoke를 순서대로 수행합니다. macOS 엔진은 `deploy/mac-engine/noahai-engine`이며 Windows 엔진 폴더를 참조하지 않습니다.

```text
deploy/mac-release/NoahAI-3.9.1.45-arm64.dmg
deploy/mac-release/NoahAI-3.9.1.45-arm64.zip
deploy/mac-release/latest-mac.yml
deploy/mac-release/release-manifest-mac.json
```

기본은 서명 없는 로컬 테스트 후보입니다. 정식 서명 빌드는 Developer ID를 Keychain에 설치하고 `CSC_NAME` 및 Apple 공증용 환경을 준비한 뒤 `--signed`로 실행합니다. 인증서·Apple 비밀값은 문서·로그·명령행에 넣지 않습니다. `codesign --verify --deep --strict` 및 `spctl --assess`를 통과하지 않으면 서명 배포로 인정하지 않습니다.

Windows와 macOS는 같은 제품 버전의 **공용 GitHub Release 태그 `v3.9.1.45`**를 사용합니다. Windows는 `latest.yml`, macOS는 `latest-mac.yml`을 읽으므로 플랫폼별 자동업데이트 자산이 충돌하지 않습니다. DMG·ZIP과 두 blockmap, `latest-mac.yml`, Mac manifest를 Windows 설치기와 같은 릴리즈에 게시합니다.

`scripts/publish_macos.py`는 공용 릴리즈가 이미 있으면 Mac 자산만 추가하고 원격 SHA-256을 검증합니다. Windows 릴리즈가 아직 없으면 같은 `v3.9.1.45` 태그의 draft를 만들며, 별도 `-macos-candidate` 태그는 만들지 않습니다. 같은 이름의 원격 자산이 다르면 덮어쓰지 않고 새 제품 버전을 요구합니다. 새 릴리즈에서 서명 없는 Mac 자산을 stable 릴리즈에 추가하는 작업은 스크립트가 차단합니다. v3.9.1.42 이하의 기존 Mac 자산은 과거 공개·수동 테스트 기록이며 v3.9.1.45 자동업데이트 증거로 승계하지 않습니다.

```bash
.venv/bin/python scripts/publish_macos.py
```

## 검증 문서 업데이트

`docs/TEST_STATUS.md`, `docs/DEPLOY_CHECKLIST.md`, 현재 버전 TEST_PLAN, 인앱 매뉴얼을 함께 갱신합니다. 문서 체크 표시를 빌드 통과를 위해 임의로 바꾸지 않습니다. `python scripts/doc_consistency_check.py`와 매뉴얼 재추출을 다시 실행하고, 패키지 입력이 바뀌었으면 재빌드합니다.
