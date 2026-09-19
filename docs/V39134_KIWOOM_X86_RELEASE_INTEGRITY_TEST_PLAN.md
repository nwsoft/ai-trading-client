# v3.9.1.34 Kiwoom x86 & Release Integrity 검증 계획

제품 3.9.1.34 / updater 3.9.134. 공개 안정판 v3.9.1.33 자산은 보존한다. 자동 검증과 실제 Windows 외부 검증을 구분하며, 증거를 직접 확인한 행만 `[x] VERIFIED`로 바꾼다.

## 자동 빌드 및 패키지 게이트

- [x] VERIFIED: WIN-BUILD - Python 2,424 passed/8 skipped, Web 51 modules, x64 엔진, x86 키움 호스트, NSIS 설치기, blockmap, latest.yml 생성
- [x] VERIFIED: PACKAGE-HASH - 설치기 `1188b00ed8e3bb4bf4f23f9522740be3fb9f24ee710a6870d5052948f798b8c0`; 로컬 manifest와 GitHub 원격 digest 일치
- [x] VERIFIED: KIWOOM-HOST-SMOKE - Electron/엔진 PE `0x8664`, 호스트 PE `0x14c`; 패키지 호스트 시작·정상 종료 PASS
- [x] VERIFIED: DOCS - 제품 3.9.1.34 / updater 3.9.134 / 공개 안정판 v3.9.1.33 / prerelease 정책 정합 PASS

## 실제 Windows 외부 게이트

- [ ] WIN-UPGRADE: v3.9.1.33 설치본에서 v3.9.1.34 확인·다운로드·안전 종료·재시작·설정 및 사용자 원장 보존
- [ ] ROLLBACK: v3.9.1.33 복구 후 설정·자격증명·PAPER/LIVE 원장 보존
- [ ] KIWOOM-E2E: OpenAPI+ OCX 등록 PC에서 로그인·잔고·시세·PAPER·종료/복구·미확정 주문 차단 확인
- [ ] KIS-E2E: 한국투자 실제 인증·계좌 조회·국내 주식/ETF 시세·PAPER·로그 확인
- [ ] BITHUMB-E2E: Bithumb 인증·공개 시세·PAPER·재접속 상태 표시 확인
- [ ] SPOT-FUTURES-PAPER: 지원 현물·선물 기관의 같은 기간·기관·통화별 PAPER 성과 분리 대조
- [ ] RECONCILE-E2E: NoahAI 원장과 기관 체결의 주문 ID·수량·비용·미확정 제외 기준 대조
- [ ] REPORT-E2E: 통계·자산·AI 리포트·금융 인텔리전스의 실제 화면 근거 및 실패 안내 확인
- [ ] SOAK: 대표 거래소·증권사 전환과 x86 호스트 재시작을 포함한 24~72시간 운용 확인

미완료 외부 게이트가 있으면 `-AllowPendingExternalGates`는 GitHub **prerelease**만 만든다. prerelease는 `latest`로 지정하지 않으며 안정 채널 자동 업데이트 대상이 아니다. 모든 행이 `[x] VERIFIED`이고 해당 증거가 보존된 경우에만 안정판으로 승격한다. API 키·계좌 개인정보는 이 문서에 기록하지 않는다.
