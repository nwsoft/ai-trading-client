# v3.9.1.0 Web UI 테스터 실행표

대상: 내부 Windows 설치 후보  
선행 조건: `scripts/build_web_ui_windows.ps1` 성공, 설치본·`latest.yml`·engine SHA-256 기록  
현재 상태: `v3.9.1.0` 정식 GitHub Release 공개 완료. 외부 장시간·실계정 시험 항목은 별도 운영 검증으로 계속 추적

> 설치기 SHA-256 `0354c712e7d5be7bf7ef87e0d9901cb9a8f301267d82cb24a31190d6096abc5e` 후보로 이 외부 게이트를 수행한다. 다른 SHA의 설치기는 같은 후보로 간주하지 않는다.

## 2026-08-20 로컬 사전 검증

| 게이트 | 결과 | 증거와 제한 |
|---|---|---|
| 설치 | PASS | 격리 경로 자동 설치 exit 0, `NoahAI.exe`와 `resources/engine/NoahAIEngine.exe` 생성, 레거시 `AITrading.exe` 없음 |
| 덮어쓰기 업그레이드 | PENDING | 이번 SHA의 기존 사용자 데이터 보존 덮어쓰기 시나리오는 별도 외부 시험 대상 |
| 패키지 실행 | PASS | 내장 engine SHA 일치, `/api/v1/health`, `/platform`, `/session`, `/features`, `/runtime/snapshot`과 `noahai://app` CORS 응답 통과. 기존 `/features` 500 재현 원인인 feature inventory 누락 수정 |
| PAPER/LIVE 코드 게이트 | PASS | AlphaArena PAPER 외부 주문 0·`order_submitted=false`, LIVE 외부 게이트 전 차단을 포함한 집중 테스트 10개 통과 |
| 자동업데이트 | PENDING | 원격에 v3.9.1.0보다 새 Electron bundle이 없어 다운로드·재시작 경로를 검증할 수 없음 |
| 원자적 롤백 | PENDING | v3.9.0.10은 레거시 portable EXE이므로 이전 Electron bundle로 자동 복귀하는 시나리오가 없음 |
| 안전 종료·제거 | PASS | 안전 종료 후 Electron/engine 잔류 프로세스 0개, `Uninstall NoahAI.exe /S /currentuser` exit 0, 설치 디렉터리 제거 확인 |
| UI·실계정·PAPER soak | PENDING | 인앱 Browser runtime 부재, 실제 계정/다중 모니터/24~72시간 시험 미수행 |

이 표는 깨끗한 외부 Windows 10/11 시험을 대체하지 않는다. 특히 덮어쓰기 업그레이드·자동업데이트·롤백·PAPER soak PENDING이 해소되기 전에는 `publish_ready=true`로 바꾸지 않는다.

## 역할과 인계 기준

- **개발 완료 범위**: 12개 Web 기능 이전, UI-neutral engine, 안전 종료/업데이트 계약, 전체 자동 테스트, Web build·dependency audit, 충돌 소스·레거시 bundle 감사 도구다.
- **Windows 빌드 담당자 범위**: Node 22.12 이상과 프로젝트 Python 환경에서 `scripts/build_web_ui_windows.ps1`을 실행한다. 이 한 명령이 전체 테스트, Web build, `NoahAIEngine.exe` 레거시 UI 0개 TOC 검사, `NoahAI-3.9.1.0-Setup.exe`, `latest.yml`, blockmap과 SHA-256 manifest를 생성한다.
- **테스터 범위**: SHA가 확정된 같은 설치 후보로 아래 설치·업그레이드·업데이트·롤백·실계정 조회·PAPER 장시간 시험을 수행한다. 테스터가 소스 이전이나 빌드 감사를 대신하지 않는다.
- **공개 담당 범위**: 모든 외부 게이트가 통과한 뒤에만 `scripts/publish_web_ui_windows_release.ps1 -ConfirmExternalGates`로 동일 SHA 자산을 공개한다.

## 1. 설치와 업데이트

- 깨끗한 Windows 10/11에서 `NoahAI-3.9.1.0-Setup.exe`를 설치한다.
- 설치 뒤 사용자가 실행하는 파일은 `NoahAI.exe`이며 `NoahAIEngine.exe`는 `resources/engine`에서 셸이 관리하는 내부 sidecar다. 사용자가 engine을 직접 실행하지 않는다.
- 작업 관리자와 설치 bundle 검사에서 `AITrading.exe`, `main`, `ui.*`, `tkinter`, `customtkinter`가 새 제품 경로에 포함되지 않았는지 확인한다.
- v3.9.0.10 사용자는 설정·전략·거래 DB·로그를 백업한 뒤 업그레이드한다.
- 앱 제목/화면에 v3.9.1.0이 보이고 작업 관리자에 NoahAI 앱 인스턴스 하나가 정상인지 확인한다. Electron과 PyInstaller one-file 구조상 `NoahAI.exe`와 `NoahAIEngine.exe` 하위 프로세스가 여러 개 보이는 것은 정상이며, 독립 앱 인스턴스가 중복 기동되거나 종료 뒤 프로세스가 남으면 실패다.
- 업데이트가 있으면 `다운로드`와 `설치·재시작`을 각각 사용자가 눌러야 한다. 열린 주문·포지션 안전검사가 실패하면 설치가 차단돼야 한다.
- 종료 handshake를 고의로 실패시켰을 때 업데이트 적용과 앱 종료가 모두 취소되는지 확인한다.
- 실패 설치를 강제로 중단해 이전 버전 복귀와 사용자 데이터 보존을 확인한다.

## 2. 공통 UI 반복

- 100/125/150/200% 배율, 1080p 이상, 1~3 모니터에서 확인한다.
- 블록체인 → 주식/증권 → 자산 통합 → 생활금융 → AI애널리스트를 100회 왕복한다.
- 설정을 100회 열고 닫고, Escape와 바깥 영역 클릭으로도 닫는다.
- 매뉴얼·설정·업데이트 버튼, 현재 서비스/기능 탭, 하단 엔진 상태가 숨거나 순서가 바뀌지 않아야 한다.
- 빈 회색 창, 분리 native 창, 빈 본문, 탭 혼합, 가로 스크롤, 예기치 않은 종료가 한 번이라도 나오면 실패다.

## 3. 설정과 자격증명

- AI 엔진/API, 거래소, 증권사, AI Custom 난이도, 고급 매매 계층의 설명·현재값·기본값을 확인한다.
- 일반 설정 1개를 바꿔 변경 개수와 적용 범위를 검토하고 저장한다. 재시작 뒤 값이 유지돼야 한다.
- 중요/LIVE 설정은 추가 확인이 떠야 하며 저장만으로 거래를 시작하지 않아야 한다.
- 거래소·증권사·AI 키를 저장한 뒤 값 자체는 다시 표시되지 않고 `연결됨`만 보여야 한다.
- UI-only 저장으로 실행 중 워커 전체가 중지되거나 모든 거래소 API를 재조회하면 실패다.

## 4. 계좌·차트·자산

- 활성화한 6개 거래소와 4개 증권사를 하나씩 선택해 잔고·포지션·미체결을 명시 새로고침한다.
- 일부 연결 실패가 다른 계정 결과를 0으로 지우지 않고 거래소별 오류로 남아야 한다.
- Binance/Upbit/Bithumb/Bybit/OKX/Bitget 차트와 키움/신한/미래/KIS 일봉을 조회한다.
- 심볼·주기·시장 유형 변경, 오류 후 `다시 시도`, 진입·청산·XAI 마커를 확인한다.
- KRW와 USDT를 환율 기준 없이 합산하지 않고 자산 snapshot 시각을 표시해야 한다.

## 5. AI Custom

- 자연어, Pine, URL, PDF, 이미지, 영상 중 사용 가능한 표본을 각각 불러온다.
- 모호하거나 미지원인 규칙이 자동 보완되지 않고 질문/차단으로 남는지 확인한다.
- 새 버전 저장 → diff 확인 → 승인 → 자동 과거재생 → PAPER 순서를 지킨다. 과거검증만으로 적용되면 실패다.
- `.noahstrategy`를 내보내고 다시 가져온다. 가져온 전략은 비활성 검토 상태여야 한다.
- 수정본/rollback과 버전 삭제를 확인한다. 활성 전략 전체 삭제는 차단돼야 한다.
- PAPER 체결 뒤 전략 key/version별 거래 수·순PnL·수수료·MDD·7/30일 관측이 자동 갱신되는지 확인한다.

## 6. 새 Web 고급 기능

- 블록체인/주식 금융 인텔리전스의 근거·데이터 시각·빈 상태를 확인한다. 명시 갱신 전 네트워크 호출이나 직접 주문이 발생하면 실패다.
- 자산 인사이트·배분·리스크·성과 네 화면에서 같은 계좌 snapshot을 사용하고 KRW/USDT를 임의 합산하지 않는지 확인한다.
- 생활금융 분석·상품·세금 화면에서 저장 기록 반영, 상품 비교의 `신청 아님`, 세금 결과의 `참고용` 표시를 확인한다.
- AI 요약 리포트와 금융 인텔리전스 허브가 계정 근거와 부족한 데이터를 구분하고 주문을 만들지 않는지 확인한다.
- AlphaArena는 PAPER 시작·정지·이벤트를 시험한다. 실제 거래소 주문이 0개여야 하며, LIVE 설정에서는 `LIVE_BLOCKED_PENDING_EXTERNAL_GATE`가 표시돼야 한다.

## 7. AI 가이드와 분석

- 같은 질문을 초보자·일반·고급으로 물어 설명 밀도 차이를 확인한다.
- `로컬 제품 가이드`는 Provider 사용량을 늘리지 않아야 한다.
- `외부 AI 심층분석`은 버튼을 누른 질문 1건만 호출하고 일/월 예산·토큰·예상비용·캐시 여부를 표시해야 한다.
- 설정 변경이나 거래 주문을 AI 답변만으로 바로 실행하면 실패다.

## 8. 거래 안전

- LEARNING은 분석/기록만, PAPER는 가상체결만, LIVE는 별도 범위 확인 뒤 실제 주문만 수행해야 한다.
- NoahAI 소유 포지션만 자동청산하며 사용자 수동 포지션은 위험 한도에는 포함하되 청산하지 않아야 한다.
- Upbit/Bithumb SHORT 신규 주문, 중복 명령, 모호한 체결 재주문은 차단돼야 한다.
- 먼저 거래소별 PAPER를 수행하고 일반 거래 엔진의 최소 위험 LIVE는 별도 승인된 계정에서만 진행한다. AlphaArena LIVE는 이번 후보에서 시험하지 않고 차단 상태를 확인한다.

## 9. 장시간과 피드백 제출

- 24~72시간 PAPER에서 메모리 증가, sidecar 재시작, WebSocket 복구, AI 호출 예산, 로그 회전을 확인한다.
- 피드백에는 설치본 SHA 앞 12자리, Windows 버전·배율·모니터 수, 계정 ID가 아닌 테스트 별칭, 발생 시각, 직전 5개 행동, 화면, 마스킹 로그를 포함한다.
- API 키·secret·token·계좌번호·이메일·UID는 첨부하지 않는다.
- 통과/실패는 `docs/WEB_UI_MIGRATION_STATUS_v3.9.1.0.md`의 외부 게이트에 반영하고 실제 증거 없이 체크하지 않는다.
