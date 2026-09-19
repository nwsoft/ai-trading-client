# v3.9.0.10 설정·탭 렌더·프라이빗 전략 관리 장애 보고서

기준일: 2026-08-13  
대상 설치본: v3.9.0.9 AI Custom Stability Update  
수정 대상: v3.9.0.10 AI Custom Management & Runtime Integrity Update  
배포 상태: `pending_windows_rebuild`

## 결론

이번 제보는 하나의 현상으로 묶어 단일 원인이라고 말할 수 없다.

1. 설정창 `name 'copy' is not defined`는 대시보드 모듈의 import 누락이라는 확정된 Python 회귀다.
2. 영상의 좌측 상단 분리 화면·빈 앱 본문에는 두 생명주기 결함이 함께 있었다. 소스 탭은 오래된 지연 렌더를 취소하지 않았고, AI 커스텀은 저장 전략 수와 무관하게 시작 시 전체 화면을 미리 만든 뒤 탭을 선택할 때마다 같은 대형 화면을 파괴·재생성했다.
3. `AI 커스텀 약 7개 저장 → 재시작` 조건은 두 번째 결함과 직접 연결된다. 7개 저장 행을 복원한 실제 `CustomStrategyWidget`은 한 번에 553개의 Tcl 위젯 명령을 생성한다. 기존 동작은 이를 숨은 상태에서 먼저 생성하고 선택 때 다시 교체했으므로 Windows UI 자원 압박과 영상의 렌더 표면 손상을 설명한다.
4. 앱 자동 종료는 제공 영상만으로 Python 정상 종료인지 Windows native access violation인지 확정할 수 없다. v3.9.0.10 Windows 실행본의 `runtime_stability.jsonl`과 `runtime_faulthandler.log`가 필요하다.
5. 프라이빗 전략을 수정·삭제하지 못한 것은 예외가 아니라 관리 UI가 빠진 제품 기능 공백이었다.

## 확인한 증거

- `ui/dashboard_modern.py`는 `copy.deepcopy(self.settings)`를 호출했지만 파일 상단에 `import copy`가 없었다.
- 48초 영상에서는 대시보드 본문이 비는 동안 이전 거래소 화면 조각이 앱 창 바깥 좌측 상단에 남고, 다른 탭을 누르면 새 화면과 잔상이 함께 바뀐다.
- 기존 구현은 탭 선택마다 `after_idle`로 `_ensure_active_source_tab`을 예약했으며 이전 화면을 먼저 파괴한 뒤 새 화면을 만들었다. 빠른 선택의 오래된 예약을 취소하는 세대 번호가 없었다.
- 기존 `_ensure_custom_strategy_tab()`은 살아 있는 `custom_strategy_widget`을 확인하지 않고 항상 `_clear_tab_children(tab)` 후 `CustomStrategyWidget(...)`을 새로 만들었다. 이 함수는 앱 기본 탭 생성과 AI 커스텀 선택 양쪽에서 호출됐다.
- `CustomStrategyWidget`은 `CTkScrollableFrame`이므로 전달받은 탭은 `widget.master`가 아니라 내부 `_parent_frame.master`에 연결된다. 소유권 판정은 이 합성 구조까지 포함해야 정상 인스턴스를 stale 위젯으로 오판하지 않는다.
- 저장 전략 목록은 승인·검증·적용·내보내기만 제공했고 저장 버전의 범위/국면 편집과 삭제 action이 없었다.

## v3.9.0.10 수정 계약

### 설정창

- 대시보드가 `copy`를 명시적으로 import한다.
- 설정창은 대시보드 소유 `CTkToplevel` controller 하나를 숨김/재사용한다.
- 설정 생성 실패는 traceback과 GUI 자원 스냅샷을 남기고 실패한 빈 창을 보존하지 않는다.

### 거래소·증권사 탭

- 서비스별 예약 렌더는 마지막 선택 하나만 유지한다.
- 예약 시 세대 번호, 실행 직전 현재 서비스와 현재 선택 탭을 다시 확인한다.
- 새 화면의 제어·잔고·포지션·통계·로그가 모두 생성된 뒤 이전 숨은 화면을 정리한다.
- 생성한 각 섹션의 `winfo_toplevel()`이 대시보드와 다르면 `dashboard_widget_owner_mismatch`로 실패 폐쇄한다.
- 렌더 전후 USER/GDI/TK_MENU 자원 로그에 서비스·탭·세대 번호를 남긴다.

### AI 커스텀 화면

- 앱 시작 시 `AI 커스텀` 탭 헤더만 만들고 대형 위젯 트리는 만들지 않는다.
- 최초 실제 선택 때만 `CustomStrategyWidget`을 생성하고 이후 선택은 동일 인스턴스를 재사용한다.
- `CTkScrollableFrame._parent_frame.master`까지 확인해 화면 소유권을 판정한다.
- AI 커스텀 선택 예약은 최신 하나만 남기며 생성 중 재진입을 차단한다.
- 실제 재생성이 필요한 파괴 복구에서만 전후 USER/GDI/TK_MENU를 기록한다.

### 프라이빗 전략 관리

- `수정본 만들기`는 저장 버전의 범위·시장상황·국면 기준·우선순위·역할·위험예산·유니버스·고급 규칙을 편집기에 복원한다.
- 저장하면 같은 `strategy_key`의 다음 버전이 생성된다. 기존 승인·검증·적용 기록은 불변이며 새 버전으로 승계하지 않는다.
- `전략 삭제`는 적용 중이 아닌 전략만 모든 버전과 런타임 목록에서 제거한다.
- 삭제 감사에는 전략 키·버전 ID·행위자·시각만 남기고 규칙·API 키·원문은 남기지 않는다.

## Windows 배포 전 필수 게이트

1. 창 제목과 `deploy/release-manifest.json`이 v3.9.0.10이고 새 EXE SHA와 일치해야 한다.
2. 설정 열기/닫기/재열기 50회에서 `copy` 오류, 빈 창, native 메뉴 누적이 0건이어야 한다.
3. 7개 이상 프라이빗 전략을 저장한 뒤 재시작해 AI 커스텀 최초 진입이 정상이어야 한다. AI 커스텀↔6개 거래소 왕복 100회와 급속 선택 200회에서 AI 커스텀 build 로그는 최초 1회만 발생하고 마지막 선택 화면만 완전하게 남아야 한다.
4. 화면 바깥 분리 native 창, 부분 렌더, `dashboard_widget_owner_mismatch`, 예기치 않은 종료가 0건이어야 한다.
5. 프라이빗 전략 수정본이 다음 버전으로 생성되고 기존 승인본은 변하지 않아야 한다.
6. 적용 중 삭제가 차단되고 적용 해제 후 삭제·재시작 뒤 복원되지 않음을 확인해야 한다.
7. PAPER 2시간 동안 USER/GDI/TK_MENU와 `runtime_faulthandler.log`에 증가 추세나 access violation이 없어야 한다.

## 판정 경계

- macOS 렌더와 자동 테스트 통과는 Windows EXE의 compositor·USER/GDI·native crash 검증을 대신하지 않는다.
- v3.9.0.10이라는 창 제목만으로 설치 완료가 아니다. 현재 EXE SHA와 배포 manifest SHA가 같아야 한다.
- 새 Windows 로그 없이 영상의 자동 종료 원인을 DLL, 메모리, Python 종료 중 하나로 단정하지 않는다.
