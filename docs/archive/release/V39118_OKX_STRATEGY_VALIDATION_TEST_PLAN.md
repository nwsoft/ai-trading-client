# v3.9.1.18 OKX 후보 복구·전략 검증 근거 검증 원장

기준 일자: 2026-09-03  
제품 후보: NoahAI Client v3.9.1.18 / updater SemVer 3.9.118  
공개 기준: v3.9.1.17 Windows 자산 유지  
현재 판정: `pending_windows_rebuild`, `publish_ready=false`

## 1. 이번 버전의 확정 범위

- OKX USDT 선물 ticker에서 CCXT `quoteVolume`이 비어도 원문 `volCcy24h` 기초자산 수량과 현재가로 24시간 USDT 거래대금을 복원한다.
- OKX `vol24h` 또는 CCXT `baseVolume`의 계약 수를 기초자산 수량으로 오인하지 않는다.
- 후보 전체 미산출 복구는 즉시 1회 뒤 거래소별 60→120→240초, 최대 15분의 backoff를 사용하고 동일 실패 세션의 원장 저장을 기본 15분에 한 번으로 제한한다.
- Strategy Studio 저장 버전에서 과거재생의 표본·PnL·수익률·MDD·승률·Profit Factor·OOS·워크포워드·품질 필터·과최적화 위험을 펼쳐 본다.
- PAPER 결과는 거래소와 기준통화별로 유효/과거 미확정 건수, 승패, 승률, 순손익, 비용을 표시한다. KRW와 USDT는 합산하지 않는다.
- 제작 화면에서 국내 KRW 현물과 해외 USDT 선물의 방향·레버리지·주문규격 차이를 저장 전에 확인한다.
- 대표 한국어 자연어·Pine 입력은 정답 코퍼스로 고정한다. 지원 의미는 보존하고 미지원 Pine·단위 없는 TP/SL은 실행 가능 전략으로 축소하지 않는다.

## 2. 소스 자동 검증

- [x] 실제 공개 OKX ticker 필드 계약 점검
- [x] Binance·Bybit·Bitget USDT 선물과 Upbit·Bithumb KRW 현물 거래대금 회귀
- [x] 거래소별 PAPER/기준통화 분리 API 회귀
- [x] 자연어/Pine 의미 보존·실패 폐쇄 코퍼스
- [x] TypeScript 검사와 Vite production build
- [x] 전체 Python 회귀 `1,992 passed, 8 skipped`
- [x] 내장 메뉴얼 스냅샷·활성 소스·Web parity·문서 정합·dev release gate
- [x] Web UI TypeScript/Vite production build 49 modules (macOS Node 20.11.0, Windows 릴리스는 Node 22.12+ 재실행 필요)
- [x] 릴리스 입력 fingerprint `f977adea6f98c237a55c09c91f1d87b4ac0074fd097dc26e021003772abc099c`

## 3. Windows·실환경 필수 게이트

- [ ] `WIN-BUILD`: 요구 Node 22.12+와 Windows 빌드 환경에서 엔진, Web assets, `NoahAI-3.9.1.18-Setup.exe`, blockmap 생성
- [ ] `ARTIFACT-IDENTITY`: 제품 3.9.1.18, updater 3.9.118, 설치기/blockmap/`latest.yml` 이름·SHA-512·크기 일치
- [ ] `WIN-UPGRADE`: 공개 v3.9.1.17→v3.9.1.18 자동 업데이트, 종료·재시작·설정·자격증명·전략·PAPER 원장 보존
- [ ] `OKX-COLD`: 첫 실행의 공개 ticker로 제한시간 안에 숫자 점수 후보 생성
- [ ] `OKX-WARM`: 캐시 갱신·재선정에서도 `fallback_unscored` 반복 세션이 생성되지 않음
- [ ] `OKX-OUTAGE`: 네트워크 장애 중 기존 포지션 보호 유지, 신규 진입 보류, backoff·원장 억제 확인
- [ ] `STRATEGY-UI`: Level 1~4에서 호환성·Validation Lab·거래소별 PAPER 근거가 잘림 없이 표시
- [ ] `PAPER-SOAK`: Upbit/Bithumb KRW 현물과 Binance/Bybit/Bitget/OKX USDT 선물 24~72시간 PAPER
- [ ] `LIVE-SMALL`: 승인된 최소 금액/수량으로 거래소별 조회→주문→체결→보호→청산→재시작 대조
- [ ] `KIWOOM-E2E`: Windows OpenAPI+ 조회·시작·중지·종료 후 NoahAI 소유 COM 자식 0개
- [ ] `KIS-E2E`: 토큰 1분 제한을 지키며 조회·최소 주문·취소·종료 및 재시작 대조
- [ ] `BITHUMB-E2E`: KRW 현물 최소 주문·체결·관리 LONG 청산·PAPER 통계 대조
- [ ] `RECONCILE-E2E`: 거래소 원장·NoahAI 관리 원장·PAPER 원장·화면 집계의 식별 가능한 차이와 합계 대조
- [ ] `SPOT-FUTURES-PAPER`: 국내 KRW 현물 LONG/청산과 해외 USDT 선물 LONG/SHORT 방향 계약 대조
- [ ] `REPORT-E2E`: 일간·주간·월간·실시간 리포트 요약/상세/통화별 체크섬 대조
- [ ] `SOAK`: 6개 거래소·알림·전략 스튜디오·설정·종료를 포함한 24~72시간 지속 운용

## 4. 배포 판정

소스 테스트와 macOS Web 빌드 성공은 Windows 설치본 또는 실제 거래소 운용 완료를 뜻하지 않는다. 위 Windows 산출물과 실환경 게이트가 끝나기 전에는 공개 v3.9.1.17의 `deploy/release-manifest.json`, `webui/release/latest.yml`, `deploy/web-release/latest.yml`을 v3.9.1.18로 덮어쓰지 않는다.

`publish_ready=true`는 새 설치기·blockmap·`latest.yml`의 동일 산출물 검증과 최소 OKX/PAPER E2E가 끝난 뒤에만 선언한다.
