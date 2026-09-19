# v3.9.1.35 전략 범위·자산·대화 연속성 검증 계획

제품 3.9.1.35 / updater 3.9.135. 실제 관측한 증거만 VERIFIED로 바꿉니다. 플랫폼별 산출물은 분리하며 다른 버전 결과를 이 버전의 통과로 승계하지 않습니다.

## 소스·자동 검증

- [x] VERIFIED SOURCE: Python 2,458 passed / 8 skipped / 3 subtests passed (2026-09-16 macOS arm64, 35.98초 재빌드 시 재실행); 신규 범위/예수금/모드/호스트·검증 종료 후 가상 청산 회귀 포함. Windows 결과 아님.
- [x] VERIFIED WEB: TypeScript·production build 52 modules; 브라우저 fixture 탭 왕복/자산 목록/복수 선택/다음 버전 제출값/PAPER 선택/자산통합 4탭의 과거 LIVE 근거/시나리오 자산 필터 PASS. reports/v39135-ui/ 화면, tests/webui_v39135_smoke.cjs 재현.
- [x] VERIFIED DOCS: 문서 정합 PASS·11개 인앱 매뉴얼 재추출; PowerShell 10개 구문 검사, 미완료 게시 거부 및 플랫폼별 게이트 분리 검사 PASS.

## macOS

- [x] VERIFIED MAC-BUILD: 과거 LIVE 추가 수정 포함 재빌드 완료 (2026-09-16). arm64 엔진 bootstrap 4 routes·실제 패키지 로그인 화면·Electron 3.9.135/엔진 3.9.1.35·DMG checksum·ZIP 무결성 PASS. 패키지 안의 과거 LIVE UI 번들과 빌드 JS 일치 확인. fingerprint b64fe0ec19ec8f1a43402be8012527bf1d50ab4c2857c2e47aebc693d149be6b. deploy/mac-release/release-manifest-mac.json 참조. Developer ID 서명/공증 아님.
- [ ] MAC-SIGN: Developer ID 서명·Apple 공증·Gatekeeper 평가
- [ ] MAC-E2E: 설치·실행·계정 전환·탭 왕복·종료·업데이트·원장 보존

## Windows PC 필수 검증

- [ ] WIN-BUILD: 전체 자동 회귀·x64 엔진·x86 호스트·설치기·해시·소스 fingerprint
- [ ] WIN-UPGRADE: v3.9.1.34 → v3.9.1.35 설치·업데이트·설정/자격증명/원장 보존
- [ ] ROLLBACK: v3.9.1.34 복구 및 사용자 데이터 보존
- [ ] KIWOOM-E2E: 실제 OCX 등록·로그인·잔고·시세·PAPER·호스트 종료/복구·미확정 주문 차단
- [ ] BROKER-E2E: KIS/키움/신한/미래에셋 주식·ETF 범위/후보 수/기본 후보 확인형·독립형 동작
- [ ] CRYPTO-E2E: 7개 거래소 복수 범위·원장 모드·동일 기간/통화 성과 대조
- [ ] STRATEGY-E2E: 검증 완료 후 신규 검증 진입 없음·기존 포지션 청산 유지·재시작 후 권한 일치
- [ ] KIS-E2E: KIS 실제 로그인·국내 주식/ETF·PAPER·로그
- [ ] BITHUMB-E2E: 빗썸 시세·인증·PAPER·재접속
- [ ] RECONCILE-E2E: 주문 ID·수량·비용·미확정 제외 기준 대조. 과거 LIVE 참고 표시와 체결 대조 완료 성과를 분리하고, 실제 사용자 PC의 과거 원장 건수/통화/누락값 확인
- [ ] SPOT-FUTURES-PAPER: 현물·선물 동일 기간/기관/통화 가상 원장 대조
- [ ] REPORT-E2E: 자산·시나리오 모드 전환·기관별 잔고·대화 유지 실제 화면
- [ ] SOAK: 24~72시간 PAPER·기관 전환·재접속·알림·계정 격리

macOS 미완료를 Windows 통과로, Windows 미완료를 macOS 통과로 바꾸지 않습니다. Windows 게시 스크립트는 공통 소스·Web·문서 및 Windows 필수 행을 검사합니다. MAC-* 행은 Windows 승격 근거도 차단 조건도 아니며, macOS 안정판은 별도로 MAC-* 검증을 모두 완료해야 합니다.

## 배포 후 실환경 피드백 (2026-09-16)

- [x] USER-OBSERVED CONNECT: v3.9.1.35 사용자 환경에서 키움 OpenAPI+ API 연결 성공 피드백을 받았습니다. 이는 해당 사용자 환경의 연결 관찰이며 전체 Windows·계정 E2E 완료를 뜻하지 않습니다.
- [x] USER-OBSERVED DUPLICATE LOGIN: 19:20:57 RPC connect 타임아웃 뒤 전용 호스트 재시작과 KHOpenAPI 중복 로그인 해제 알림이 함께 관찰됐습니다. 제보 화면에는 19:21 중복 로그인으로 기존 접속을 해지한다는 경고가 표시됐습니다.
- [x] SOURCE HOTFIX: RPC 타임아웃·EOF·응답 불일치 시 세션 상태를 잠그고 60초 워커 재시도가 새 호스트를 만들지 못하게 했습니다. 동일 잠금 알림은 반복 발송하지 않고, 사용자가 증권 거래 실행을 중지한 뒤 다시 시작해야 잠금이 해제됩니다. 주문 결과 미확정 차단은 유지합니다.
- [x] REGRESSION: 키움 호스트 생명주기·주문 미확정·증권 실행 관련 집중 회귀 66건 PASS (macOS 소스 테스트, Windows OCX E2E 아님).
- [ ] NEXT WINDOWS PATCH: 이 소스 수정이 포함된 새 버전의 x64 엔진·x86 키움 호스트·설치기 빌드, v3.9.1.35 업데이트, 실제 로그인·잔고·시세·PAPER·중지/재시작을 검증합니다. 이미 게시된 v3.9.1.35 자산은 교체하지 않습니다.
