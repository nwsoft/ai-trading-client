# v3.9.1.3 Settings Persistence Verification Patch 검증 계획

공개 v3.9.1.2에서 재현된 설정 저장 원복과 API 연결확인 실패의 Windows 실설치 검증 원장이다. 소스 테스트와 macOS Web 빌드는 이 항목을 대신하지 않는다.

## 필수 게이트

- [ ] `WIN-BUILD` — Windows x64에서 전체 테스트와 `build_web_ui_windows.ps1`을 옵션 없이 실행하고 Setup·blockmap·`latest.yml`·engine SHA-256·source fingerprint를 기록한다.
- [ ] `UPGRADE-3912-3913` — 공개 v3.9.1.2가 updater SemVer 3.9.103을 감지해 안전 종료·설치·재시작하고 동일 계정 데이터를 로드한다.
- [ ] `SAVE-VERIFY` — Teayu 데이터 복사본과 신규 계정에서 일반/고급 설정을 각각 변경하고 저장→닫기→재열기→앱 재시작 후 값과 검증 영수증 revision이 유지된다.
- [ ] `CREDENTIAL-CHECK` — Binance와 AI Provider의 새 키 입력 후 연결확인을 눌렀을 때 저장 검증이 먼저 완료되고 실제 읽기 조회가 성공하며 비밀값이 화면·감사·로그에 노출되지 않는다.
- [ ] `LEGACY-AI-KEY` — v3.9.0.x/3.9.1.x 기존 공통 키 설정을 복사해 OpenAI·DeepSeek 각각 Provider별 등록 상태가 맞고, 키 재입력 없이 모델 조회가 성공하며 다른 Provider 키를 빌려 쓰지 않는다.
- [ ] `AI-SDK-BUNDLE` — 설치된 `NoahAIEngine.exe`에 `openai`, `httpx`, `jiter`가 포함되고 키 없음·SDK 누락·클라이언트 초기화 실패·인증 실패를 서로 다른 안내로 표시한다.
- [ ] `NETWORK-CHECK-LABEL` — 키 또는 SDK가 없어 요청을 보내지 못한 경우 `외부 API 요청 전 단계에서 중단됨`, 실제 모델 API를 호출한 경우에만 `외부 API 요청 실행됨`으로 표시한다.
- [ ] `NO-AUTO-RESTORE` — 코인 재선정·분석·최적화가 실행되는 동안 설정을 반복 저장해도 `.backup` 자동 복구나 사용자 미요청 백업 복구 이벤트가 발생하지 않는다.
- [ ] `ORPHAN-ENGINE` — v3.9.1.2 업데이트·비정상 종료 뒤 남은 `NoahAIEngine.exe`가 v3.9.1.3 시작 시 정리되고 sidecar가 정확히 1개만 실행된다.
- [ ] `REVISION-LOG` — 실시간 시스템 로그와 계정 감사 원장에 비밀값 없이 저장 항목 수와 전후 revision이 기록되고 실패 사유가 구분된다.
- [ ] `FULL-SETTINGS-UI` — 8개 설정 탭에서 원본 사용자 항목 55개, 탭별·전체 기본값 불러오기, 고급 JSON, 보호 항목 설명을 확인하고 100회 저장·닫기·재열기에서 값 혼합이나 원복이 없다.
- [ ] `ASSISTANT-CONTEXT` — 일반 안내는 외부 호출 0회이고, 심층분석은 저장된 saver/standard/premium 출력 상한과 최근 대화 문맥을 적용하며 사용량·캐시·예상 비용을 구분한다.
- [ ] `AI-CUSTOM-PROFILE` — 초보자 Level 1, 일반 Level 2, 고급·실험실 Level 3 기본값과 `lab` 저장 유지, 입력 초기화·저장 비활성 사유·XAI 근거 분리를 재시작 후 확인한다.
- [ ] `CHART-VISION` — 지원 Provider의 비전 모델로 PNG/JPG/WEBP 8MB 이하 차트를 분석하고 OCR 근거·비전 결과·불확실성·사용량을 분리하며 주문 제출 0건을 확인한다.
- [ ] `ROLLBACK` — v3.9.1.3 설치/시작 실패 시 v3.9.1.2로 복구하고 사용자 설정·자격증명·전략·DB를 보존한다.
- [ ] `PAPER-SOAK` — 동일 후보로 24~72시간 PAPER 실행 중 설정 저장을 반복하고 값 원복·중복 엔진·설정 파일 손상이 0건임을 확인한다.

## 게시 판정

- 모든 체크가 완료된 동일 산출물만 `windows_verified_release_candidate`로 변경한다.
- manifest, Setup, blockmap, `latest.yml`, GitHub Release 원격 digest가 일치한 뒤에만 게시한다.
