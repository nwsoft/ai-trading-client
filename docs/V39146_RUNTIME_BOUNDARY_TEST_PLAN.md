# v3.9.1.46 기관별 시작·알림·보호주문 릴리스 검증 원장

공개 v3.9.1.45 이후 소스 후보 / updater 3.9.146. Windows 게시 도구가 요구하는 버전별 단일 QA 원장이다. 이전 패치의 시험 수치나 체크 상태를 실제 환경 검증으로 승계하지 않는다. 아래 미완료 항목이 있으면 배포 승인으로 처리하지 않는다.

## 소스 계약 시험

- [x] WRITE-PRIORITY: Recorder 우선순위/유지관리 시간 예산·커서 보존, 체결·주문·정확한 진입 ID 재처리. 고객 전체 사본 11기관 동시 시험 통과. 프로세스 간 우선순위나 모든 보조 쓰기 복구 보장은 아님.
- [x] POSITION-RESULT: 선물 실제 수량/방향/미실현 근거와 증권 4기관 명시적 조회 결과. 빈 목록/실패/수량 누락 구분. 실제 응답은 별도 게이트.
- [x] ORDER-MONOTONIC: 11기관 공통 원장 완료 상태·원시 근거가 늦은 NEW 응답으로 역행하지 않음. 실제 보호주문 확인과 별도.

- [x] STORAGE-COMPACTION: 큰 XAI 중첩 해시 공유·압축/이전 근거 변환/기존 segment 읽기, 닫힌 과거 JSONL 무손실 전환, 중단·변경·충돌·디스크 실패·재시도. Teayu 1.13GB 파일 사본에서 해제 SHA-256 일치와 물리 사용량 감소 확인. 최근 10건은 10건만 조회.

- [x] SPOT-VALUATION: 실제 잔고→ExchangeManager→마켓/가격→RiskManager→일일 기준 DB 경로에 외부 응답 fixture 공급. 3현물 잔여 자산·환산·조회 실패·관리 귀속·손실 차단·재시작 검증. 전체 평가 함수를 성공 bool로 대체하지 않음. 상세 결과는 reports/v39145-cross-venue-feedback-audit-20260923.md.

- [x] VERIFIED START-CONTRACT: 서비스/브리지는 기관별 모드 판정 사용. 7기관×3모드 브리지 시작·LIVE 확인 유지. 테스트의 런타임 시작 대상은 mock이며 실제 워커 기동 E2E가 아님.
- [x] VERIFIED OBSERVE-CONTRACT: 7코인/4증권×3모드 관찰·안정화·발행 함수에 시험 시세 공급. 함수 직접 호출이며 사용자 시작 경로는 별도.
- [x] VERIFIED TRANSPORT-CONTRACT: 11기관×3모드 실제 publisher/dispatcher→mock Telegram transport. 실제 수신 증거 아님.
- [x] VERIFIED LEDGER-CONTRACT: 신규 전략 key/version 저장→조회, 증권 주식/ETF 부분청산의 진입 lot 귀속 보존. 과거 미기록 추정 없음.
- [x] VERIFIED PROTECTION-CONTRACT: 실제 설치 CCXT 요청 빌더의 Bybit trading-stop·OKX OCO, Bitget 양쪽 접수, Binance 일반/Algo 증거 및 실패 후 중복 발주 금지. 최종 API 전송은 mock.
- [x] VERIFIED UI-CONTRACT: 실제 React 수신 모드 설정·저장 1440/900px 및 전략 배너 290/430/500px. API fixture. 상세 결과는 TEST_STATUS.md.

## 실제 환경 게이트 — 별도 증거 필요

### 남은 구현 게이트 (외부 시험으로 대체하지 않음)

- [x] PARTIAL-AUX-REPLAY: 부분청산/분할진입 청산/위험/증권 실행 품질/주문 명령 재처리·영수증·전략/시각 보존. 진단 정리의 거래/위험 원장 삭제 제거.
- [ ] ALL-WRITE-RECOVERY: 가용 공간 64MiB 미만 신규 진입 차단은 구현. 디스크 전체 고갈·강제 종료·물리 장애 모든 기록 무손실 보장은 완료 아님.
- [ ] STOCK-LOT-RECONCILIATION: 증권 실제 보유와 과거 관리 lot·수동 거래·출금 귀속의 자동 복구.
- [x] COINONE-LIVE-CONTRACT: v46 Coinone 전용 E2E 차단 제거. 공통 LIVE 확인·API 인증·위험 제한 유지. 이전 승인 설정 값은 실행 권한에 영향 없음.
- [ ] COINONE-LIVE-TESTER: 실제 계좌 주문·부분체결·취소·청산·재시작은 테스터 환경 검증. 앱에 별도 승인 스위치/하드코딩 차단을 두지 않으며 자동시험을 실계좌 PASS로 대체하지 않음.
- [x] MULTI-SOURCE-STRATEGY: 여러 파일/로컬 폴더/CSV·TSV·XLSX·DOCX 추출, 출처/중복/포함/누락 범위와 통합 분석. 40개·24MiB/개·64MiB 합계. Drive 폴더 URL 전체 수집 미지원. 실제 AI Provider 답변 품질/Windows 선택기는 별도 시험.

2026-09-24 Coinone 잔고/미체결 조회 시도: 허용 IP 거절. 실주문/취소/청산 없음. 이 결과는 실제 계좌 시험 미완료 기록이며 Coinone만의 제품 실행 차단 사유로 사용하지 않음.

### 설치본·계좌·채널

- [ ] STORAGE-WINDOWS-SOAK: Windows 파일 잠금/강제 종료/백그라운드 장시간 및 50GB 전체 폴더 전환. 성공 시 전체 보관 용량의 무제한 고정 상한을 뜻하지 않음.

- [ ] SPOT-RESIDUAL-E2E: 제보 계정의 실제 잔고·마켓/가격 응답 읽기 대조. APENFT·EMC의 실제 지원 상태나 상장폐지를 fixture 결과로 단정하지 않음. 미평가 자산/고정 기준/알림을 Windows 설치본에서 확인.

- [ ] WIN-BUILD: 46 설치기·sidecar·매뉴얼 버전/해시.
- [ ] WIN-UPGRADE: 45→46 업데이트·재시작·설정/원장 보존·100/125/150% 배율.
- [ ] START-TO-WORKER: 7코인 기관별 시작 버튼→실제 워커 생존→후보·분석 기록. Coinone LEARNING과 PAPER, 이미 실행 중인 Binance LIVE를 서로 구분.
- [ ] REGIME-TO-RECEIPT: 시작 경로와 연결한 지속 실행에서 유효 시세→국면 유지/확정 변화→제외/접수/전송→실제 Telegram 수신 대조. 시각·기관·모드·버전 기록. 최초/동일/unknown 억제 유지.
- [ ] STOCK-E2E: 4증권 연결 프로필·주식/ETF 관찰/알림, 키움 RuntimeError 원본 예외 확인. KIS 수신만으로 다른 기관 완료 처리 금지.
- [ ] KIWOOM-E2E: Windows 키움 연결·분석·주식/ETF 기록과 오류 원문 대조.
- [ ] KIS-E2E: 한국투자 실제 국면·모드·기록과 메시지 대조.
- [ ] BITHUMB-E2E: 국내 현물 실제 후보·시세·분석·저장 근거 대조.
- [ ] RECONCILE-E2E: 기존 PnL 대조·손실 가드레일·원장 보존 불변.
- [ ] SPOT-FUTURES-PAPER: 현물/선물/증권 PAPER·LIVE 원장과 주문 범위 격리.
- [ ] REPORT-E2E: 실제 저장 근거와 화면·리포트·메신저 수치 대조.
- [ ] PROTECTION-E2E: 실제 계정 읽기 응답으로 양쪽 보호·포지션 방향·수량·주문 ID 대조. 실제 주문이 필요한 시험은 별도 명시 승인, 자격증명은 보고서에 기록 금지.
- [ ] SOAK: 다기관 장시간·API 실패·재접속·절전·중단/재개에서 분석/알림 지속과 조회 예산 확인.

기존 부분 보호주문의 안전한 자동 교체, 과거 전략 귀속 복원, 내구성 있는 무기한 알림 재전송을 이번 구현 완료 기능으로 표시하지 않는다. 원인·이전 검증 누락·현재 범위는 reports/v39145-cross-venue-feedback-audit-20260923.md를 따른다.
