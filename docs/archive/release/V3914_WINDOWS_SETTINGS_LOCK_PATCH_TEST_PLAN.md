# v3.9.1.4 Windows Settings Lock Patch 검증 계획

`v3.9.1.3` 공개 설치본에서 재현된 설정 저장 실패와 잘못된 GitHub 확인 버전 표시를 대상으로 합니다. 소스 테스트나 macOS 빌드는 아래 Windows 설치본 게이트를 대신하지 않습니다.

- [ ] `WIN-BUILD` — 현재 소스 fingerprint로 `NoahAI-3.9.1.4-Setup.exe`, `NoahAIEngine.exe`, blockmap, `latest.yml(3.9.104)`를 새로 생성하고 SHA-256을 확정한다.
- [ ] `UPGRADE-3913-3914` — 공개 v3.9.1.3에서 인앱 업데이트 후 v3.9.1.4가 실행되고 계정 데이터와 비밀값이 유지되는지 확인한다.
- [ ] `LOCK-CONTENTION` — 실행 중 엔진과 설정 저장을 동시에 반복해 `settings.json`이 이전 값으로 되돌아가지 않는지 확인한다. Windows 오류 5/32/33에서 원자 교체만 차단된 경우 원본 방식의 제자리 쓰기 폴백과 바이트 재검증이 성공하고, 실제 쓰기 권한까지 차단되면 실패 영수증을 반환해야 한다.
- [ ] `SAVE-RESTART` — 일반·거래소·증권·AI·고급·AlphaArena·시스템·업데이트 각 탭에서 저장 후 10초 대기, 닫기, 재열기, 앱 재시작 뒤 값이 동일한지 확인한다.
- [ ] `FAILURE-RECEIPT` — 의도적 파일 잠금/권한 차단에서 실시간 로그와 감사 로그에 `settings.write_failed`, `code`, `stage`, `winerror`가 비밀값 없이 남는지 확인한다.
- [ ] `SINGLE-INSTANCE` — NoahAI를 연속 실행해 소유 프로세스 하나와 `NoahAIEngine.exe` 하나만 유지되고 두 번째 프로세스가 sidecar를 시작하지 않는지 확인한다.
- [ ] `UPDATER-VERSION` — 설정의 GitHub 확인 버전이 오래된 releaseName이 아니라 `latest.yml 3.9.104 → 3.9.1.4`로 표시되는지 확인한다.
- [ ] `DPI-LAYOUT` — Windows 100%, 125%, 150% 배율에서 설정 하단 5개 버튼이 한 글자씩 커지거나 겹치지 않고 오류문만 남은 폭에서 줄바꿈되는지 확인한다.
- [ ] `AI-CREDENTIAL` — 기존 OpenAI·DeepSeek 키를 유지한 업그레이드와 새 키 저장 후 실제 연결 점검을 각각 확인한다.
- [ ] `ROLLBACK` — 설치 실패/취소 시 v3.9.1.3 실행 파일과 계정 설정을 손상하지 않는지 확인한다.

모든 항목에 실제 Windows 증거를 첨부해 `[x]`로 바꾸기 전에는 `publish_ready=false`를 유지합니다.
