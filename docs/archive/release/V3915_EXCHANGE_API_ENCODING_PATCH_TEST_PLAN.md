# v3.9.1.5 Windows Exchange API Encoding Patch 검증 계획

`v3.9.1.4` Windows 설치본의 거래소 연결 점검에서 API 요청 전에 `cp949`가 `🔧` 상태 문자를 인코딩하지 못해 모든 거래소 점검이 실패로 오판된 문제를 대상으로 합니다. 소스 회귀나 macOS Web 빌드는 실제 Windows 설치본 및 외부 거래소 계정 게이트를 대신하지 않습니다.

- [ ] `WIN-BUILD` — 현재 소스 fingerprint로 `NoahAI-3.9.1.5-Setup.exe`, `NoahAIEngine.exe`, blockmap, `latest.yml(3.9.105)`를 새로 생성하고 SHA-256을 확정한다.
- [ ] `UPGRADE-3914-3915` — 공개 v3.9.1.4에서 인앱 업데이트 후 v3.9.1.5가 실행되고 동일 계정의 설정과 비밀값이 유지되는지 확인한다.
- [ ] `CP949-REPRO` — Windows 시스템 로캘 cp949에서 기존 제보와 같은 `🔧` 출력 경로를 재현하고, 새 sidecar가 UTF-8로 시작되어 거래소 요청 전 인코딩 예외가 발생하지 않는지 확인한다.
- [ ] `SETTINGS-ENCODING-COMPAT` — UTF-8 BOM·UTF-16·CP949로 저장된 기존 `settings.json`에서 사용자값과 모든 자격증명을 보존해 읽고, 검증 저장 후 BOM 없는 UTF-8 정본으로 바뀌는지 확인한다.
- [ ] `SETTINGS-CORRUPT-PROTECTION` — 해독 불가능한 바이트·잘못된 JSON·객체가 아닌 JSON을 기본값으로 덮어쓰지 않고 `settings_file_unreadable`로 차단하며, 잘못된 백업도 현재 정본을 바꾸지 않는지 확인한다.
- [ ] `CREDENTIAL-SAVE-SIX` — Binance·Upbit·Bithumb·Bybit·OKX·Bitget 각각에서 기존 저장 키 인식과 새 자격증명 저장 → 디스크 재조회 → 앱 재시작 후 등록 상태 유지를 확인한다.
- [ ] `EXCHANGE-CHECK-SIX` — 위 6개 거래소의 실제 계정에서 읽기 권한으로 잔고·보유자산 또는 포지션·미체결 주문 조회를 확인한다. 주문은 제출하지 않는다.
- [ ] `STATUS-VERDICT` — HTTP 성공 안의 `credential_required`, `disabled`, `invalid_api_keys`, `client_unavailable`, `error`를 성공으로 표시하지 않고, `status=success`만 연결 성공으로 표시하는지 확인한다.
- [ ] `SAVE-RESTART` — 일반 설정과 거래소 자격증명을 저장한 뒤 10초 대기, 설정 닫기·재열기, 앱 재시작 후 값과 등록 상태가 유지되는지 확인한다.
- [ ] `ROLLBACK` — 설치 실패 또는 취소 시 v3.9.1.4 실행 파일과 계정별 `settings.json`을 손상하지 않는지 확인한다.

모든 항목에 실제 Windows 및 외부 계정 증거를 첨부해 `[x]`로 바꾸기 전에는 `publish_ready=false`를 유지합니다. API 키·Secret·Passphrase는 증거에 포함하지 않습니다.
