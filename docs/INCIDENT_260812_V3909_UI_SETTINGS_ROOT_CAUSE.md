# v3.9.0.9 UI·설정·종료 반복 장애 근본 원인 보고서

기준일: 2026-08-12  
상태: 소스 수정·macOS 실렌더·자동 회귀 완료, Windows 재빌드/실기기 반복시험 대기  
대상 증상: 거래소 탭 부분 렌더, 빈 설정창, 느린 설정 저장, 의도하지 않은 증권 연결 점검, `No more menus can be allocated`, 간헐 종료

## 결론

한 개의 DLL이나 한 개의 버튼 오류가 아니었다. 같은 프로세스 안에서 다음 소유권 경계가 동시에 무너진 복합 장애였다.

1. 활성화된 모든 거래소 화면을 완전 생성하고 계속 보유했다.
2. 설정창의 많은 선택 위젯이 import 경로에 따라 Windows native 메뉴를 영구 보유했다.
3. 설정창이 대시보드의 live 설정 객체를 먼저 바꿔 실제 변경 diff를 잃었고, 저장 때 모든 거래소 런타임을 재설정했다.
4. 설정창과 증권 점검 Toplevel을 본문 생성 전에 표시해 회색/흰색 빈 창을 노출했다.
5. 같은 계정으로 두 프로세스가 겹쳐 Tk·세션 파일·업데이터·WebSocket 상태를 동시에 만졌다.
6. 여러 분석 스레드가 Binance WebSocketApp의 subscribe/send/reconnect를 동시에 수행했다.

따라서 이전처럼 개별 빈 카드나 개별 팝업을 보완하는 것만으로는 해결되지 않는다. 이번 수정은 `프로세스 1개 → 설정 controller 1개 → 현재 source 화면 트리 1개 → WebSocket send 소유자 1개`를 공통 계약으로 둔다.

## 확인한 증거

### Teayu Windows 로그

- `runtime_stability.jsonl`의 다수 오류가 `ModernSettingsWindow.setup_ui → create_exchange_selection_tab → CTkComboBox → DropdownMenu → tk.Menu`에서 `No more menus can be allocated`로 끝난다.
- 2026-08-11 23:37경 두 런타임이 같은 계정 로그 경로를 사용했고 `runtime_session.active.tmp` 교체가 `[WinError 32]`로 실패했다.
- `runtime_faulthandler.log`에는 `Windows fatal exception: access violation`이 있으며 Binance `start_ticker_socket → ensure_ws_for → get_current_price_ws` 구독 경로의 스레드가 함께 기록돼 있다.
- 제공 영상에서는 거래소를 바꿀수록 오른쪽 로그는 남지만 왼쪽 제어·잔고·포지션·통계 카드 내용이 사라졌다. 이는 데이터 조회 실패가 아니라 부분 UI 트리 소실이다.

### nwsoft macOS 로그와 화면

- 2026-08-12 19:11 저장 직후 UI 설정만 저장했는데도 Bitget·Upbit·Bithumb·OKX·Bybit 실행 모드를 중지하고 여러 거래소 잔고를 다시 조회했다.
- 한 번의 사용자 저장에서 설정 저장·템플릿 병합·재저장이 연속 반복됐다.
- 19:13:55와 19:25:46 종료는 runtime stability 기준 `clean_shutdown`이다. 해당 두 건은 네이티브 crash 증거가 아니라 정상 종료 경로가 실행된 기록이다.
- 테스트 자격증명 오류는 이번 UI 생명주기 판정에서 제외했다.

## 수정 계약

### 1. 선택한 거래소 하나만 UI 소유

- 모든 거래소/증권사 탭 버튼과 정본 순서는 유지한다.
- 제어·잔고·포지션·통계·로그의 무거운 트리는 현재 선택 탭 하나에만 만든다.
- 다른 source를 선택하면 이전 트리, 예약된 `after`, 위젯 캐시를 같은 경계에서 폐기한다.
- 다섯 섹션 중 하나라도 비면 `service_tab_partial_render`로 실패 폐쇄한다.

### 2. 설정창 표시·메뉴 소유권

- Windows 메뉴 가드는 `main.py`와 설정 모듈 직접 import 양쪽에서 CustomTkinter보다 먼저 설치한다.
- 설정 Toplevel은 전체 UI·현재값 복원이 완료될 때까지 `withdraw` 상태다.
- 재사용 설정창은 저장/X 뒤 숨기고 같은 controller를 다시 표시한다.
- 생성 실패한 창은 즉시 파괴한다.

### 3. 설정 저장 diff

- 설정창은 대시보드 설정의 deep-copy snapshot을 편집한다.
- 저장 전후 실제 diff를 `logging / AI / exchange / trading / UI`로 나눈다.
- UI-only 저장은 거래 매니저 재초기화, 거래소 실행 중지, 잔고 강제 조회를 하지 않는다.
- 설정창이 디스크 저장을 완료했으면 메인 콜백은 다시 저장하지 않는다.
- 저장 성공은 대시보드 비차단 toast로 알리고 modal 성공창을 띄우지 않는다.

### 4. 증권 연결 점검

- 자동 표시는 기본 OFF다.
- 사용자가 설정에서 명시적으로 동의한 경우에만 저장 뒤 표시한다.
- 점검창도 내용을 완성한 후 표시하며 실패 시 빈 창을 남기지 않는다.

### 5. 프로세스와 WebSocket

- 계정 로그 폴더에 `O_EXCL` 기반 원자적 인스턴스 잠금을 둔다.
- 이미 실행 중이면 두 번째 프로세스가 session marker를 덮기 전에 시작을 중단한다.
- Binance 구독은 심볼별 single-flight로 수행한다.
- WebSocket send·close·reconnect는 동일한 재진입 락을 사용한다.

## 현재 검증 결과

- macOS 설정 실렌더: 설정 읽기 0.003초, 전체 위젯 생성 0.696초, 창 상태 `normal`, 정상 폐기
- macOS source 탭 실렌더: BINANCE → UPBIT → BITHUMB → BINANCE 왕복 모두 완전한 트리 1개만 존재
- 집중 회귀: 설정 diff, 메뉴 import 순서, source 단일 소유, 프로세스 잠금, WebSocket 직렬화 포함 통과
- 전체 자동 회귀: `1,468 passed, 6 skipped, 0 failed`

## 배포 판정

공개된 v3.9.0.8 Fix 4 EXE SHA-256은 `91070a67eb0a86d3eaf0c86c2ee6347defe29daf1480d913f3afb9646fa71ff7`이며 이전 자산으로 보존한다. 이번 근본 수정은 v3.9.0.9로 분리했으므로 이 SHA 또는 Fix 4 제목이 보이면 새 수정이 설치된 것이 아니다.

다음 세 조건이 모두 충족돼야 배포 완료다.

1. Windows에서 새 EXE를 빌드하고 새 SHA-256 manifest를 생성한다.
2. 새 설치본에서 아래 반복시험을 통과한다.
3. 테스터가 전달한 로그에 메뉴 할당, 부분 렌더, 병렬 실행, access violation이 없어야 한다.

## Windows 재빌드 후 필수 시험

1. 창 제목, 설치 EXE SHA, manifest SHA를 함께 기록한다.
2. 앱 실행 중 같은 EXE를 한 번 더 실행해 두 번째 프로세스가 차단되는지 확인한다.
3. 6개 거래소를 활성화하고 BINANCE → UPBIT → BITHUMB → BYBIT → OKX → BITGET 왕복을 100회 수행한다.
4. 매 10회마다 왼쪽 다섯 섹션, 탭 순서, USER/GDI/TK_MENU 로그를 확인한다.
5. 설정을 50회 열고 닫고, 값 변경 없는 저장 20회와 UI-only 저장 20회를 수행한다.
6. UI-only 저장 로그에 다른 거래소 `실행 모드 변경 - 중지`, 전체 잔고 강제조회가 없어야 한다.
7. 사용자가 자동 증권 점검을 켜지 않았다면 `저장 후 증권 연결 점검`이 나타나지 않아야 한다.
8. PAPER로 Binance 심볼 다중 분석을 2시간 수행하고 access violation·중복 구독·예기치 않은 종료가 없는지 확인한다.
9. 실패 시 전체 화면, 정확한 시각, 직전 클릭 순서, runtime stability/faulthandler 로그를 전달한다. API 키·Secret은 제외한다.

## 비판정 항목

- 테스트용 잘못된 API 키의 인증 오류는 UI 생명주기 성공/실패와 별개다.
- macOS 실렌더와 자동 테스트 통과는 Windows EXE 장시간 성공을 대신하지 않는다.
- 창 제목에 `v3.9.0.9 AI Custom Stability Update`가 표시되고 EXE SHA가 v3.9.0.9 manifest와 일치해야 새 소스가 설치된 것이다.
