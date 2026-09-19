# v3.9.1.0 Web UI 전환 판정표

기준일: 2026-08-19  
v3.9.1.0 당시 소스 상태: **구조 분리 진행·기존 UI/UX 및 기능 흐름 재작업 중, 외부 E2E 진행 전**  
v3.9.1.0 당시 배포 상태: **`pending_windows_rebuild` · `publish_ready=false` · 공개 배포 금지**  
현행 제품 상태: **v3.9.1.27 Windows 공개 자산 게시·`publish_ready=true`**. 아래 표는 v3.9.1.0 전환 이력이며 현재 릴리스 신원을 대체하지 않는다.

사용자·운영자·외부 사이트에 공개할 현재 기능, 조건부 연결, AI 커스텀 실제 수준과 미완료 범위는 [v3.9.1.0 기능·안내·배포 정합성 정본](archive/release/V3910_CAPABILITIES_AND_RELEASE_GATES.md)을 따른다.

## 2026-08-15 사용자 화면 재판정

첨부 화면과 실제 `python3 main.py` 화면을 다시 대조한 결과, 이전 문서의 “기존 기능 Web 소스 이전 완료”는 **API와 React 컴포넌트 연결**을 뜻했을 뿐 로그인·대시보드·설정·매뉴얼의 화면/동작 동등성을 뜻하지 않았다. 이를 완료로 읽힐 수 있게 기록한 것은 잘못이며 철회한다.

오전 1차 재작업 뒤 정오 사용자 캡처에서 코인 정보·거래소·AI 어시스턴트·AI 커스텀·설정·매뉴얼이 기존 제품과 여전히 다르고, 실시간 로그가 창 전체를 세로로 늘리는 실패가 확인됐다. 따라서 아래 항목 중 실제 나란히 대조하지 않은 `PASS` 표현은 철회한다.

정오 피드백 뒤 다음을 소스에서 다시 수정했다.

- 로그인 창: 450×708 창, 제품 아이콘/Dock·Windows 패키지 아이콘 지정, 카드 높이와 버튼 아래 여백 재조정
- 로그인 도움말: “로그인 후 매뉴얼에서 확인” 문구가 아니라 별도 640×540 창과 `로그인 안내 / 이용·책임 참고 / 공식 안내(웹)` 3개 탭
- 로그인 뒤 첫 화면: `실시간 거래 로그`, 창 높이 고정, 좌/우 패널 내부 스크롤. 임의로 추가했던 `XAI 판단·체결 감사` 중복 탭은 제거하고 관련 근거는 AI 리포트 `실행 품질`과 감사 원장으로 이동
- 상단 범위: 블록체인 `거래소: 6곳 · 기준 BINANCE`, 거래소 6개 탭, 금융 인텔리전스가 거래소보다 앞, 비활성 AlphaArena와 내부 통합 source 메뉴 숨김
- 탭 상태: 기능 탭과 거래소/source 탭을 상호배타로 만들어 `코인 정보 + BINANCE` 동시 선택 제거
- 코인 정보: 공통 차트·엔진 제어·원시 DB 표를 제거하고 기존 심볼 조회·AI 평가 점수표 구조로 분리
- 거래소: 공통 데이터 화면을 제거하고 제어·잔고·포지션·거래 통계·해당 거래소 로그 전용 구조로 분리
- AI 어시스턴트: 기존 대화창·자주 묻는 질문·전체 복사/TXT·전송·음성·설정관리·차트분석 구조로 재작업
- AI 커스텀: 기존 상단 철학·멘토/처음 사용법 차이·안전 순서·원본·XAI·프라이빗 버전 관리 순서로 재배치
- 주식/ETF AI: 합쳐진 단일 허브를 철회하고 기존처럼 `AI 학습 / AI 리포트 / AI 어시스턴트 / AI 커스텀` 독립 탭으로 복원
- 하단 상태: 블록체인 6개와 증권사 4개 실행 범위를 섞지 않고, AI/전략/AlphaArena 감사 원장의 실제 최근 기록 표시
- 종료: 화면 버튼이 Electron 안전 종료 IPC를 거쳐 신규 명령 차단→worker/기록 정리→완료 뒤 종료하도록 연결

위 변경은 현재 `SOURCE PASS`다. macOS 재렌더와 기존 CTk 나란히 대조, 설정·매뉴얼 본문 전수 감사, Windows 시각/E2E와 실제 계정 흐름은 아직 미완료이므로 전체 parity PASS나 배포 가능으로 판정하지 않는다.

2026-08-15 추가 재검증에서 로그인·로그인 전 도움말은 실제 레거시와 macOS Electron을 다시 나란히 대조해 PASS로 올렸다. 이후 저장된 로컬 로그인 정보로 실제 대시보드를 열어 기본 실시간 로그·BINANCE source·주식/증권 내비게이션을 확인했으며 LIVE 명령은 실행하지 않았다. 기본/거래소 로그가 오늘 최신 행으로 자동 이동하고 주식 AI 4개 탭이 독립적으로 보이는 것은 실제 렌더 PASS다. 실제 계좌 잔고·주문·Provider 호출과 설정의 모델 조회·API 검증·프리셋·온보딩·음성, 증권 연결 진단·지원요약, 매뉴얼 본문/딥링크, AI 멘토·음성·심층분석은 여전히 명시적 OPEN이다.

오후 기능 재감사에서는 증권 화면이 블록체인의 선택 source·로그·코인 후보를 재사용하던 원인을 전역 상태와 공통 DB 조회 재사용으로 확정했다. 런타임 snapshot을 서비스별 선택/활성/실행 source로 분리하고 로그 API에 서비스 범위를 강제했으며, 증권 후보 저장소가 없으면 코인 후보를 재표시하지 않는다. 앱 내부 매뉴얼의 Web 전용 축약본은 제거했다. 빌드 시 레거시 `UserManualWidget.show_manual()`이 실제 여는 11개 탭의 본문 전체를 UI-neutral JSON으로 추출하고 Web UI는 이 정본만 읽는다. Windows 설치·업데이트·롤백, 실제 계좌·주문 및 로그인된 전체 탭 E2E는 아직 OPEN이다.

## 현재 결론

v3.9.1.0은 React/Vite Web UI와 Electron 셸을 기본 방향으로 확정했지만, 사용자 화면은 새 디자인이 아니라 기존 `AITrading.exe`/`python3 main.py`의 `ui/login_modern.py`, `ui/dashboard_modern.py`, `ui/settings_modern.py`와 100% 동등해야 한다. 2026-08-15 점검에서 기존 Web UI 초안은 로그인·대시보드·설정창의 시각 구조가 기존 클라이언트와 달라 **배포 불가**로 판정했다. 현재는 기존 CTk 고정 스킨을 기준으로 Web UI parity를 재작업한다.

기술적으로는 Web sidecar가 더 이상 `main.py`, `ui`, `tkinter`, `customtkinter`를 통해 거래 엔진을 생성하지 않도록 `HeadlessTradingRuntime`을 분리하는 방향을 유지한다. 다만 “레거시 UI를 제거했다”는 사실은 사용자 UI가 달라져도 된다는 뜻이 아니다. 사용자가 보는 화면과 조작 흐름은 기존 클라이언트와 같아야 한다.

기능 원장상 연결된 화면도 **기존 UI/UX와 같은 화면이라는 뜻이 아니다**. 오해를 만든 `source_complete` 명칭을 폐기하고 `source_connected_parity_open`으로 하향했다. 배포 승인에는 별도 `legacy_visual_parity`와 `legacy_flow_parity`가 필요하다.

현재 정본 inventory의 제품 기능 35개는 모두 소스 연결 상태이며 `source_connected_parity_open` 32개, `source_connected_external_e2e_open` 3개다. `legacy_parity_in_progress`라는 모호한 상태는 0개로 정리했지만, 이는 **시각·동작 동등성 완료가 아니라 각 기능이 전용 Web 화면과 정본 Application Service에 연결됐다는 뜻**이다. Windows 패키징과 실제 계정뿐 아니라 기존 화면·동작 기능 동등성도 완료되지 않았다. 기능 수와 상태는 `config/web_ui_feature_inventory.json`에서만 집계하며 과거 40/43개 기준은 역사 기록으로만 본다.

이전 소스 기준 `NoahAIEngine.exe`와 `NoahAI-3.9.1.0-Setup.exe` 후보(SHA-256 `a0ecd5bee659cc7bf84bab849493046f8bd870fba09a803cf9c8518d17c0c4bb`)는 생성됐지만, 2026-08-15 parity 재작업 이후 현재 소스와 일치하지 않는 **구후보**다. 현재 manifest는 `pending_windows_rebuild`이며 source fingerprint가 없는 구후보의 게시를 스크립트가 차단한다. 새 Windows 빌드·설치·자동업데이트·원자적 롤백·외부 PAPER 검증 전에는 공개 설치본으로 간주하지 않는다. `dist/AITrading.exe`는 보존된 v3.9.0.10 레거시 실행 파일이다.

## 완료와 미완료 경계

| 영역 | 현재 상태 | 배포 판정 |
|---|---|---|
| Electron/React 셸과 loopback Gateway | 소스 구현 | 기존 UI/UX parity와 Windows 패키지 E2E 필요 |
| 로그인·대시보드·설정창 시각 동등성 | 정오 실화면에서 다수 FAIL, 소스 재작업 중 | 전체 재렌더·나란히 대조·Windows 배율 전 배포 금지 |
| 로그인 창 동등성 | 450x708·제품 아이콘·카드 높이 소스 재작업 | macOS/Windows 캡처 재대조 필요 |
| 거래소·증권사 탭 | 기능/source 활성 상태와 서비스별 선택·실행·로그·후보 저장소 분리 | 6개 거래소·4개 증권사 화면/운영 명령 E2E 필요 |
| UI-neutral 거래 런타임 | `main.py`·레거시 UI import 제거, 실제 EXE TOC 감사 PASS | 외부 실행 E2E 필요 |
| 종료·업데이트 | 신규 명령 차단 → worker 정지 → Recorder/log flush → 완료 응답 후에만 sidecar 종료·업데이트 | Windows 설치/재시작/실패 중단 E2E 필요 |
| 설치 이름 | 설치기 `NoahAI-3.9.1.0-Setup.exe`, 사용자 실행 파일 `NoahAI.exe`, 내부 sidecar `NoahAIEngine.exe` | 후보 생성, 설치 E2E 전 |
| 로그인·설정·write-only 자격증명 | 소스 구현 | 실제 계정/저장 반복 E2E 필요 |
| AI Custom | 원본·IR/XAI·버전·승인·검증·PAPER·삭제·패키지 소스 구현 | 장시간 PAPER/제한 LIVE 필요 |
| 로그·차트·기본 통계·학습/리포트 | Web 화면 소스 구현 | 거래소/증권사별 데이터 E2E 필요 |
| 금융 인텔리전스·자산 고급 분석·생활금융 고급 기능·AI 요약/허브 | 전용 Web UI·서비스·DTO 소스 구현 | 실제 데이터/빈 상태 외부 E2E 필요 |
| AlphaArena | PAPER 주문 미제출·위험게이트·상태/제어 소스 구현, LIVE fail-closed | 패키지 PAPER·소유권·복구 검증 전 LIVE 차단 |
| 전략 랭킹 | `server_later` | v3.9.1.0 기존 기능 동등성 밖의 후속 기능 |
| macOS | 개발용 소스 실행만 가능 | `.app`/`.dmg`, 서명·공증·키움 제외정책 미구현 |

## 기계 판독 완료 조건

다음을 모두 만족하기 전에는 이 문서를 `complete`로 바꾸지 않는다.

- `python3 main.py` 또는 v3.9.0.10 `AITrading.exe`를 기준 화면으로 고정하고 로그인·대시보드·설정창·탭 순서·하단 상태바가 Web UI에서 시각/흐름 동등성 PASS
- `config/web_ui_feature_inventory.json`의 모든 `source_connected_parity_open`, `source_connected_external_e2e_open`, `legacy_parity_in_progress`가 실제 대조/E2E 뒤 `verified`로 전환
- Web sidecar PyInstaller TOC에서 `main`, `ui.*`, `tkinter`, `customtkinter` 0개
- UI → 거래소/증권사 직접 호출 0개, 모든 쓰기 명령 idempotency·권한·감사 통과
- 안전 종료 실패 시 앱 종료와 업데이트 설치가 실제로 중단됨
- Windows 신규 설치·v3.9.0.10 이전·업데이트·롤백·사용자 데이터 보존 통과
- Windows 10/11, 100~200% 배율, 다중 모니터, 100회 서비스/설정 전환 통과
- 실제 거래소/증권사 읽기와 PAPER, 최소 위험 LIVE 경계 검증
- 24~72시간 PAPER soak와 크래시/복구 검증
- installer·`latest.yml`·blockmap·내부 engine의 SHA-256 및 게시 자산 일치

## 설치 파일과 실행 파일

- `NoahAI-3.9.1.0-Setup.exe`: Windows 최초 설치/업그레이드용 NSIS 설치기다.
- `NoahAI.exe`: 설치 후 시작 메뉴·바탕화면 바로가기가 실행하는 사용자용 Electron 앱이다.
- `NoahAIEngine.exe`: 설치 폴더 내부에서 `NoahAI.exe`가 한 개만 실행하는 Python 거래 sidecar다. 사용자가 직접 실행하지 않는다.
- `AITrading.exe`: v3.9.0.10까지의 레거시 단일 실행 파일이다. v3.9.1.0 공개 이름으로 사용하지 않는다.
- macOS는 `.exe`를 사용하지 않는다. 별도의 `NoahAI.app`/`.dmg` 빌드·서명·공증 계약이 필요하며 현재 릴리즈 범위가 아니다.

## 빌드와 릴리즈의 차이

Windows 후보 빌드:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_web_ui_windows.ps1
```

이 명령은 sidecar와 Web UI를 빌드하고 레거시 UI 0개 감사, installer·`latest.yml`·blockmap·SHA manifest를 생성한다. **GitHub 공개 릴리즈를 만들지 않는다.**

외부 게이트를 실제 통과한 뒤 공개:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/publish_web_ui_windows_release.ps1 -ConfirmExternalGates
```

이 명령은 로컬/원격 SHA와 `latest.yml` 참조를 재검증한 뒤 자산을 게시한다. 빌드 성공만으로 실행하면 안 된다.

## 확인할 문서

1. 현재 완료 판정: `docs/WEB_UI_MIGRATION_STATUS_v3.9.1.0.md`
2. 실제 기능 원장: `config/web_ui_feature_inventory.json`
3. 사용자 기능·설정: `docs/USER_GUIDE.md`와 앱 상단 **매뉴얼**
4. 테스트 증거: `docs/TEST_STATUS.md`
5. Windows 빌드: `docs/BUILD_GUIDE.md`
6. 외부 검증·배포: `docs/WEB_UI_TESTER_RUNBOOK_v3.9.1.0.md`, `docs/DEPLOY_CHECKLIST.md`
7. 변경 이력: `docs/CHANGELOG.md`, `RELEASE_NOTES.md`, `deploy/release_notes.md`
