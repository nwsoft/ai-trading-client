# v3.9.1.26 Strategy Risk Input & Guided Clarification 검증 원장

기준일: 2026-09-10  
소스 후보: v3.9.1.26 / updater 3.9.126  
직전 공개판: v3.9.1.25  
상태: `pending_windows_rebuild`, `publish_ready=false`

## 문제와 근본 원인

v3.9.1.25의 XAI와 AI 안내는 `거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%`를 입력하라고 안내했지만 deterministic source compiler는 `포지션 크기/자산 N%`만 읽었다. 사용자가 정확한 예시를 원문에 넣어도 `position_size`가 계속 누락되는 실제 계약 버그였다. 또한 분석된 위험값을 Strategy Studio 선택 상태에 되돌리지 않아 최종 버전 생성 시 이전 UI 기본값이 분석값을 덮어쓸 수 있었다.

## 수정 계약

- `거래당 계좌 손실 N%`, `거래 한 번에서 계좌의 최대 N%까지 손실`, `1회 위험 N%`, `risk per trade N%`를 `risk_per_trade_percent`로 구조화한다.
- 암호화폐 `증거금 사용/최대 N%`와 주식·ETF `종목당 투자 비중 최대 N%`를 `max_margin_usage_percent` 및 실행 `position_size`로 구조화한다.
- 숫자에 `%`가 없으면 퍼센트로 추측하지 않는다.
- 분석된 위험률·비중·레버리지 상한을 화면에 반영한 뒤 최종 버전을 생성한다.
- `현재 선택값을 보완 근거로 추가`는 사용자가 이미 선택한 위험·시장국면만 별도 확인 근거에 추가하고 재분석한다.
- 전략 만들기 방식을 `원문 그대로 구조화 / 질문으로 함께 완성 / 기본 NoahAI에 맡기기`로 나누되 현재 Level과 설정은 바꾸지 않는다.
- 누락 조건은 실행값이 아닌 질문 카드로 만들고, 사용자가 직접 확정한 답변만 별도 supplemental evidence로 다시 분석한다.
- 사용자 확인 보완은 원본과 별도 SHA-256으로 기록한다. 파일/Pine/PDF 원본은 덮어쓰지 않는다.
- 보완 답변은 누락 필드만 채울 수 있다. 원문에 이미 선언된 진입·청산·방향·TP/SL·위험값과 충돌하면 덮어쓰지 않고 원문 수정과 새 버전을 요구한다.
- 지원하지 않는 Pine 동작과 해석 불가 조건은 보완 답변으로 우회하지 않고 원본 수정 전까지 차단한다.
- 진입·청산·LONG/SHORT·지표·임계값·TP/SL은 자동 생성하지 않는다.
- NoahAI가 진입을 판단하는 경로는 기본 NoahAI 또는 `confirm`으로 표시하며 사용자 원문 독립 전략과 PAPER 근거를 합치지 않는다.

## 소스 자동 검증

- [x] `RISK-KO-EXACT` — 사용자 피드백 문장이 0.5% 거래당 위험, 10% 증거금 상한으로 구조화된다.
- [x] `RISK-KO-VARIANTS` — 거래 한 번/1회 위험과 주식 종목당 비중 표현을 구조화한다.
- [x] `RISK-EN` — `risk per trade`와 `position size`의 명시적 퍼센트를 구조화한다.
- [x] `RISK-UNITLESS` — 단위 없는 위험·증거금 숫자를 실행 퍼센트로 만들지 않는다.
- [x] `UI-SYNC` — 분석된 위험·비중·레버리지가 Strategy Studio 선택 상태에 반영된다.
- [x] `UI-CONFIRM` — 현재 선택값 보완은 위험·시장 필드만 허용하고 AI 추측 문구를 사용하지 않는다.
- [x] `RISK-HASH` — 거래당 위험률이 달라지면 compiler execution contract hash도 달라진다.
- [x] `CLARIFY-CONTRACT` — 누락 조건이 자동 실행값이 아닌 질문으로 반환되고 AI 제안의 실행 가능 플래그가 항상 false다.
- [x] `CLARIFY-EVIDENCE` — 사용자 답변이 원본과 별도 해시·작성 방식으로 기록되고 재분석된다.
- [x] `CLARIFY-FILE` — 파일 원본은 변경하지 않고 사용자 확인 답변만 별도 근거로 결합한다.
- [x] `CLARIFY-CONFLICT` — 보완 답변이 원문에 이미 선언된 실행·위험값을 바꾸면 실행 준비를 차단한다.
- [x] `AUTHORING-MODE` — 허용된 세 가지 작성 방식 외 값과 20,000자 초과 보완 답변을 계약에서 차단한다.
- [x] `WEB-BUILD` — TypeScript 검사와 production build를 통과한다.
- [x] `V39126-FOCUSED` — v3.9.1.26 위험 입력·질문형 보완 전용 회귀 15건을 확인했다.
- [x] `FULL-PYTHON` — 전체 Python 회귀 `2,179 passed, 8 skipped`를 확인했다.
- [x] `WEB-SYNC-GATE` — `webui/src/` 변경도 사용자 노출 변경으로 판정해 문서·인앱 매뉴얼 동기화를 강제한다.
- [x] `DOC-CONSISTENCY` — 문서/버전 정합과 Web UI 전체 표면 계약 `PASS`를 확인했다.
- [x] `PREKEY` — 실제 사용자 폴더를 fixture로 사용하지 않는 offline prekey 게이트를 통과했다. 소스 fingerprint는 Windows 빌드 직전 최종 소스에서 다시 산출한다.

## Windows·사용자 화면 배포 게이트

- [ ] `WIN-BUILD` — v3.9.1.26 설치기·blockmap·`latest.yml`이 같은 버전과 SHA를 가리킨다.
- [ ] `WIN-UPGRADE` — 공개 v3.9.1.25에서 업데이트·안전 종료·재시작 후 설정·초안·전략·원장이 보존된다.
- [ ] `CRYPTO-UI` — 암호화폐 텍스트 원문에 현재 선택 위험값을 추가하고 재분석하면 누락이 해소되며 저장 IR과 값이 같다.
- [ ] `STOCK-UI` — 주식·ETF 텍스트 원문에서 종목당 투자 비중을 읽고 LONG·1배·정수 수량 계약이 유지된다.
- [ ] `SOURCE-FILE` — Pine/PDF/파일 원본은 자동 변경되지 않고 수정·재선택 안내가 보인다.
- [ ] `BOUNDARY` — 진입·청산 조건 누락에는 자동 삽입 버튼이 나타나지 않으며 기본 NoahAI/confirm 전환이 독립 전략으로 오인되지 않는다.
- [ ] `KIWOOM-E2E` — Windows 키움 OpenAPI+에서 주식 전략 위험값·정수 수량·주문 전 XAI를 대조한다.
- [ ] `KIS-E2E` — 한국투자 KIS 승인 QA 계정에서 주식·ETF 위험값과 주문/체결/청산을 대조한다.
- [ ] `BITHUMB-E2E` — Bithumb KRW 현물 PAPER와 승인된 최소 LIVE에서 위험 문장·LONG/청산·비중 단위를 대조한다.
- [ ] `RECONCILE-E2E` — 6개 거래소와 4개 증권사의 승인 위험·최종 수량·원장·화면을 기관별로 대조한다.
- [ ] `SPOT-FUTURES-PAPER` — KRW 현물/주식과 USDT 선물 PAPER가 같은 위험 의미와 서로 다른 주문 단위를 유지한다.
- [ ] `REPORT-E2E` — Strategy Studio 거래 내보내기·거래 통계·AI 리포트가 같은 key/version/기관 근거를 표시한다.
- [ ] `SOAK` — 24~72시간 PAPER에서 재시작·재분석·버전 저장·원장 보존과 메모리/API 사용량을 확인한다.

## 배포 판정

소스 테스트와 Web build는 Windows 설치본, 사용자 DPI, 실제 업데이터, 거래소·증권사 계정의 실행을 증명하지 않는다. 위 Windows 게이트 전에는 v3.9.1.26을 공개 완료로 표시하지 않으며 v3.9.1.25 자산을 덮어쓰지 않는다.
