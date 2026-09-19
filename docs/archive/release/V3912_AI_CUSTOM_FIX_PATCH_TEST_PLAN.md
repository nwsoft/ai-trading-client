# v3.9.1.2 AI Custom Scope & UX Fix Patch 검증 계획

이 문서는 v3.9.1.2 Windows 자산 게시를 막는 필수 실행 원장이다. 소스 테스트나 macOS Web 빌드는 Windows 설치·업데이트·외부 계정 검증을 대신하지 않는다. 모든 항목이 실제 동일 후보 자산으로 완료되기 전에는 `publish_ready=false`를 유지한다.

## 필수 게이트

- [ ] `WIN-BUILD` — Windows x64에서 전체 테스트와 `build_web_ui_windows.ps1`을 옵션 없이 실행하고 Setup·blockmap·`latest.yml`·engine SHA-256과 source fingerprint를 기록한다.
- [ ] `UPGRADE-3911-3912` — 공개 v3.9.1.1 설치본이 updater SemVer 3.9.102를 감지하고 사용자 승인 다운로드 → 안전 종료 → 설치 → 재시작 → 동일 계정 데이터 재로드를 완료한다.
- [ ] `SCOPE-CRYPTO` — Binance 전용 전략은 Binance에서만, 통합 거래소 전략은 연결된 Binance/Bybit/OKX 등 각 대상에서 평가되며 데이터·성과·주문 감사가 대상별로 분리됨을 PAPER에서 확인한다.
- [ ] `SCOPE-STOCK` — 주식 전략이 연결·선택된 키움 또는 KIS 등 증권사에서 `asset:stock` 범위로 평가되고 다른 자산군에 적용되지 않음을 PAPER에서 확인한다.
- [ ] `XAI-LEVELS` — 같은 분석에서 Level 1 자료 범위·누락·위험, Level 2 규칙·엔진값·국면, Level 3 원문 추적·전체 IR·고급 편집이 표시되고 전환만으로 저장·승인·적용되지 않음을 확인한다.
- [ ] `RESET-REANALYZE` — 초기화가 미저장 초안만 지우고 저장 전략은 보존하며, 파일→URL→텍스트 변경 시 이전 파일/분석이 남지 않고 새 소스를 다시 분석·버전 저장할 수 있음을 확인한다.
- [ ] `SAVE-IMPORT-LIMITS` — 저장 잠금 사유, 계정 기본 전략 저장소, PDF/YouTube 처리 한도와 로컬 12단계 무과금 안내가 Windows 설치 화면에 표시됨을 확인한다.
- [ ] `SETTINGS-TEAYU` — 제보 계정 데이터의 복사본으로 일반 설정과 write-only 연결 정보를 함께 변경한 뒤 저장 후 닫기 → 앱 재시작 → 설정 재열기에서 값이 유지되고, 런타임 반영 실패를 저장 실패 503으로 표시하지 않으며 백그라운드 Trader가 이전 값으로 되돌리지 않음을 확인한다.
- [ ] `SETTINGS-DUAL-PROCESS` — 레거시 `AITrading.exe`와 Web UI 설치본의 동시 실행을 차단하거나 명시적으로 종료시킨 뒤, 두 프로세스가 같은 계정 `settings.json`을 교차 저장하지 않음을 확인한다.
- [ ] `CHART-ANALYSIS` — AI 어시스턴트에서 PNG/JPG/WEBP 차트를 선택하고 미리보기 → 명시적 비전 호출 → 근거/위험/참고 플랜 표시, 비용·예산 기록, 주문 0건, 임시 이미지 삭제와 미지원 Provider·잘못된 형식 안내를 확인한다.
- [ ] `ROLLBACK` — v3.9.1.2 설치 실패와 앱 시작 실패 조건에서 v3.9.1.1 복구 절차, 사용자 데이터 보존, 잔류 프로세스 0개를 확인한다.
- [ ] `EXTERNAL-E2E` — 실제 허용 계정에서 최소 주문·조회·취소/청산·체결 귀속과 24~72시간 PAPER를 완료한다.

## 게시 판정

- 모든 체크가 완료된 동일 산출물만 `windows_verified_release_candidate`로 변경한다.
- manifest, Setup, blockmap, `latest.yml`, GitHub Release 원격 digest가 일치한 뒤에만 게시한다.
- Authenticode 미서명 정책, SmartScreen 안내, 다중 모니터/DPI 결과를 릴리스 기록에 남긴다.
