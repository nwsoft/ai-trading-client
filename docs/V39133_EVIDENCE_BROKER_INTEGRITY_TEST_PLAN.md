# v3.9.1.33 Evidence & Broker Learning Integrity 검증 계획

제품 3.9.1.33 / updater 3.9.133. 공개 v3.9.1.32 자산은 보존한다. 아래 항목은 아직 검증 완료가 아니며 소스 테스트로 체크하지 않는다.

[수정 원인·공유 원장·소스 검증 결과](V39132_USER_FEEDBACK_AUDIT.md)

[시세 누락 원인 추가 점검](V39133_MARKET_DATA_ROOT_CAUSES.md): Coinone 시계열 순서와 30분 변화 계산 변경은 실제 국면에 영향을 줄 수 있다. 수정 전후 동일 시세 PAPER 재생·각 기관 실제 운영 비교를 남겨야 하며, 테스트 통과를 수익 개선으로 해석하지 않는다.

## 배포 및 외부 게이트

- [ ] WIN-BUILD: x64 엔진 + x86 NoahAIKiwoomHost.exe + 새 설치기·blockmap·latest.yml·manifest 버전/해시 확인
- [ ] ROLLBACK: v3.9.1.32 복구와 원장·설정 보존 확인
- [ ] WIN-UPGRADE: v3.9.1.32 → v3.9.1.33 확인·다운로드·안전 종료·재시작·설정 보존
- [ ] KIWOOM-E2E: OCX 등록·32비트 호스트 로그인·잔고·시세·PAPER·종료/복구·미확정 주문 차단
- [ ] KIS-E2E: 국내 주식/ETF 분석 기록 저장·기관별 학습 조회·PAPER·로그
- [ ] BITHUMB-E2E: 인증·시세·PAPER·재접속 표시
- [ ] SPOT-FUTURES-PAPER: 7개 거래소 같은 기간·기관·통화에서 통합/개별 성과 대조
- [ ] RECONCILE-E2E: 최신 Teayu 원장과 PAPER/LIVE 및 미확정 제외 기준 대조
- [ ] REPORT-E2E: 통계·자산·애널리스트·인텔리전스·Project·Provider 실패 안내 실제 화면
- [ ] SOAK: 24~72시간 운영·기관 전환·주기 알림·재시작·호스트 자원 회수

실제 증거를 확인한 항목만 `[x] VERIFIED`로 변경한다. API 키·계좌 개인정보를 검증 문서에 넣지 않는다. 뉴스 공급자 미연결과 해외주식 자동매매 미지원은 이번 수정으로 지원 완료가 되지 않는다.
