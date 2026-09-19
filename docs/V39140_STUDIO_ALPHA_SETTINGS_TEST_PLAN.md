# v3.9.1.40 · 전략 스튜디오 / AlphaArena / 설정 점검

기준일 2026-09-19. **3.9.1.40**, updater **3.9.140**은 Windows stable/latest로 공개됐습니다. 이 문서는 당시 Strategy Studio·AlphaArena·설정 변경의 검증 기록이며, 이후 시장 트렌드/XAI 변경은 [v3.9.1.41 계획](V39141_MARKET_TREND_XAI_TEST_PLAN.md)에서 관리합니다.

## 수정 계약

- 전략 스튜디오 코인/주식·ETF 공통 화면: 본문 14px, 보조 설명 13px, 입력창 최소 220px. 입력 → 이해·보완 → 저장 버전·검증·차트 바로가기. 긴 도움말은 접고 차단 사유는 유지합니다.
- AlphaArena는 Binance 전용 PAPER **판단·조건 점검 실험**입니다. 실제/가상 체결·PnL·여권 검증과 구분합니다. 다른 기관 지원 또는 실전 수익 검증 완료를 주장하지 않습니다.
- 시작뿐 아니라 실행 루프에서도 LIVE 주문 경로를 제거합니다. 전역 PAPER 변경 중 응답이 도착해도 실주문은 제출하지 않습니다.
- 설정 변경 시 실험을 정지합니다. 이전 요청이 끝나기 전 재시작을 거부하고, 다음 시작은 저장된 위험 상한·주기·전용 AI 키로 새 실행기를 만듭니다.
- 비활성화 상태에서도 정지를 허용합니다. 다른 화면 이동 시에도 상단에 실행 상태·정지를 표시합니다. 거래소 탭은 일반 화면 이동이지 AlphaArena 대상 변경이 아닙니다.
- AlphaArena 전용 DeepSeek 키/저장된 Flash 또는 Pro 엔진으로 실행·점검 경로를 통일합니다. 일반 AI 또는 공개 공유 Project 키를 대신 쓰지 않습니다.
- AI 응답·구조화 판단의 payload와 PAPER 점검 결과, 실행/오류 기록을 표시합니다. 없는 가상 PnL을 만들지 않습니다.
- 설정에 실제 호출 점검 버튼을 제공하고 호출 비용을 안내합니다. 자격정보 변경 후 예전 성공 표시를 지우고 일반/공개 질문 Project 모델 목록을 분리합니다. 기관 변경 후 지원 요약과 알림 테스트 실패 후 이전 성공 표시를 지웁니다.

## 자동 검사 및 격리 화면 검사

2026-09-19 소스 검증: 전체 Python **2,635 passed / 8 skipped / 3 subtests**, 집중 **75 passed**, Node **43 passed**, Web **63 modules**, 문서·매뉴얼 **11 sections PASS**. 격리 코인/주식 화면 및 설정·AlphaArena 검사 오류 0건. [상세 근거](../reports/v39140-verification.md).

- 신규 회귀: `tests/test_v39140_alpha_safety.py` (LIVE 전환, 중지/재시작, 전용 키, 설정 갱신).
- 기존 AlphaArena/고급 기능 검사 및 전체 Python 회귀.
- TypeScript / Web production build.
- 브라우저 API fixture: 설명 크기, 단계 이동, AI 원문/결정/PAPER 결과, 비활성화 중 정지, 타 화면 상태표시, 설정 점검과 성공 표시 무효화.
- 모든 검사는 주문·실제 AI·메시지 전송 없이 수행합니다. 가짜 API 성공을 실계정 연결 성공으로 기록하지 않습니다.

## 공개 후에도 별도로 남는 외부 운영 확인

- [ ] WIN-BUILD · 새 x64/x86 설치본과 소스 fingerprint 대조
- [ ] WIN-UPGRADE · v39 → v40 자동업데이트와 설정/원장 보존
- [ ] ROLLBACK · 실패 시 안전 복구와 기존 설정/원장 보존
- [ ] KIWOOM-E2E · Windows OCX 로그인·조회·종료
- [ ] KIS-E2E · 증권 PAPER 연결과 기록
- [ ] BITHUMB-E2E · 현물 PAPER 연결과 기록
- [ ] RECONCILE-E2E · 실제 체결/손익 대조 (이전 미완료 증거 승계 금지)
- [ ] SPOT-FUTURES-PAPER · 현물/선물 및 주식·ETF PAPER
- [ ] REPORT-E2E · 기록/오류 표시와 내보내기
- [ ] SOAK · 장시간 PAPER 안정성

- [ ] 변경 소스·매뉴얼 생성물을 검토하여 Git 커밋/원격 SHA 확정 (동기화 복사본에 `.git` 없음).
- [x] Windows x64 엔진 + x86 키움 호스트 + Electron v40 설치기 신규 빌드·게시.
- [x] PE 수치/문자 버전 3.9.1.40, updater 3.9.140, fingerprint·SHA와 공개 manifest 일치.
- [ ] 설치본 Strategy Studio 1280×800/1600×1000 및 Windows 배율 100/125/150% 확인.
- [ ] 전용 키 명시적 점검(비용 고지), Binance PAPER 시작/정지/설정 변경/재시작 확인.
- [ ] v39 → v40 업데이트, 안전 종료 및 데이터 보존 확인(공개 사실만으로 완료 처리하지 않음).
- [x] stable/latest·목록 첫 항목·latest.yml·설치기 원격 해시 확인.

일반 거래/전략 스튜디오의 기존 주문 권한·여권·손익 대조 정책은 이번 UI 수정으로 변경하지 않습니다. 이전 PnL 감사의 실제 계좌 대조 미완료 사항도 본 수정의 성공으로 완료 처리하지 않습니다.
