# v3.9.1.19 전략 검증 여권·패키지 무결성 검증 원장

기준일: 2026-09-03  
제품 후보: NoahAI Client v3.9.1.19 / updater SemVer 3.9.119  
상태: v3.9.1.19 Windows 공개판 (`publish_ready=true`), 외부 장시간 E2E는 별도 운영 관찰

## 수정 계약

1. `execution_scope`는 거래를 실행한 엔진, `strategy_scope`는 전략 버전이 저장된 소유 범위로 분리한다.
2. UNIFIED 전략을 Binance 네이티브 엔진이 실행해도 Binance PAPER 청산은 그 UNIFIED key/version에 귀속한다.
3. v3.9.1.18의 구형 행은 같은 key/version이 한 저장소에만 존재할 때만 복구한다. 양쪽 저장소에 중복되면 추정하지 않는다.
4. `.noahstrategy`는 서버가 만든 UTF-8 JSON 문자열을 브라우저가 그대로 저장한다. 브라우저 재직렬화로 숫자형과 해시를 바꾸지 않는다.
5. 구형 브라우저 내보내기 파일은 스키마상 소수인 위험 필드만 복원한 뒤 IR 해시와 전체 패키지 해시가 모두 일치할 때만 허용한다. 해시 검사를 생략하지 않는다.
6. PAPER 여권은 `원문 구조화 전략`과 `NoahAI 기본 진입 + 사용자 위험·청산값`을 구분한다. 후자를 원문 전체 전략의 성과로 표시하지 않는다.
7. 컴파일러가 실행 진입조건을 만들지 못한 새 원문은 명시적 사용자 재선언 전 승인·PAPER·적용을 차단한다.

## 자동 검증

- [x] 실제 사용자 `01_STRUCTURE.noahstrategy` 구형 숫자 직렬화 복구 후 IR·전체 해시 재검증
- [x] Binance 실행 행을 고유 UNIFIED 버전으로 복구·집계
- [x] 검증 대상(`validation_subject`) 저장·API·화면 표시
- [x] 기존 Binance/통합 PAPER 포지션·원장·통화 분리 회귀
- [x] 전체 Python 회귀 (`1,995 passed, 8 skipped`)
- [x] Web TypeScript/Vite production 빌드

## 비즈니스·외부 사이트 정합 및 배포

- [x] daltrading 전략 허브·이용 가이드에 `세계 최초의 전략 검증 여권 생태계`라는 한정된 범주 비전과 `원문 의미 -> 실행 규칙 -> 거래소별 검증 여권` 기준, 검증 근거 중심 탐색·랭킹 설명 반영
- [x] daltrading 패키지 수신부에 클라이언트와 같은 제한적 구형 직렬화 복구·이중 해시 검증 적용
- [x] daltrading 전체 회귀 (`83 passed, 3 subtests passed`) 및 EC2 운영 배포·DB 마이그레이션·공개/인증 경로 검증 (`2628b73`)
- [x] NoahAI Labs 전략 스튜디오·로드맵·검색/LLM 안내에 동일한 범주 비전, 수익 보장 금지, v3.9.1.18 공개/v3.9.1.19 소스 후보 경계 반영
- [x] NoahAI Labs production build (`225 pages`) 및 Cloudflare Pages 운영 배포 확인 (`39e45d1`)
- [x] `info.noahai.net`·`ip.noahai.net` 판매/IP 설명·기술 위키·`llms.txt`에 동일한 범주와 상태 경계 반영, production build (`45 pages`) 및 EC2/PM2 운영 배포 확인 (`e176de7`)
- [x] 클라이언트 대시보드 메뉴얼 원본·Web 메뉴얼 JSON·AI 어시스턴트 지식·릴리스 노트에 동일한 명칭과 상태 경계 반영, 집중 회귀 `46 passed` 및 문서 정합 검사 통과

외부 사이트 배포와 별도로 v3.9.1.19 Windows 설치 파일·blockmap·`latest.yml`이 2026-09-03 게시됐습니다. 아래 항목 중 산출물 확인은 완료됐고 실제 계정·장시간 관찰은 공개 뒤에도 별도 증거로 유지합니다.

## Windows·실환경 배포 게이트

- [x] `WIN-BUILD`: Windows 엔진과 Web UI를 같은 소스에서 새로 빌드
- [ ] `WIN-UPGRADE`: 공개 v3.9.1.18 → v3.9.1.19 업데이트·재시작·설정/전략/PAPER 원장 보존
- [ ] `KIWOOM-E2E`: 키움 조회 연결·거래 워커·안전 종료 대조
- [ ] `KIS-E2E`: 한국투자 토큰 재사용·호출 제한·안전 종료 대조
- [ ] `BITHUMB-E2E`: Bithumb KRW 현물 PAPER 방향·손익·비용 대조
- [ ] `RECONCILE-E2E`: Binance 전용/UNIFIED 전략을 각각 Binance PAPER에서 진입·청산하고 올바른 버전에 귀속
- [ ] `SPOT-FUTURES-PAPER`: Upbit·Bithumb KRW 현물과 Binance·Bybit·Bitget·OKX USDT 선물의 방향·손익·비용·전략 버전 대조
- [ ] `REPORT-E2E`: 전략 여권, PAPER 거래 상세, 일·주·월 리포트 체크섬 대조
- [ ] `SOAK`: Windows 장시간 운용·안전 종료·재시작 복구
- [x] `ARTIFACTS`: `NoahAI-3.9.1.19-Setup.exe`(413,039,285 bytes), blockmap, `latest.yml`의 이름·크기·SHA-512 일치

v3.9.1.19는 게시됐지만 위 미완료 외부 E2E를 소급 완료로 표시하지 않습니다. 후속 v3.9.1.20은 새 Windows 산출물과 검증 없이 공개 자산을 덮어쓰지 않습니다.
