# v3.9.0.7 Fix Patch 3 통합 장애 원인과 검증 경계

## 결론

이번 변경은 제보 문구별 예외처리가 아니라 다음 공통 경계를 수정한다.

1. UI 생명주기: 동적 탭 제거는 callback 정리와 실제 Tcl 위젯 파괴를 한 연산으로 수행한다.
2. 시장 데이터 출처: 분석 요청의 거래소를 스레드 로컬 컨텍스트로 유지하고 다른 거래소로 폴백하지 않는다.
3. 런타임 범위: 활성 범위에 없는 거래소의 전용 REST/WebSocket 클라이언트를 만들지 않는다.
4. 현물 포지션 원장: 실제 잔고, 앱 관리수량, 진입 전 baseline, 거래소 최소주문금액을 분리한다.

## 설정창·거래소 화면

이전 패치는 숨은 화면의 반복 `after()` 작업, 오래된 UI 결과 적용, 설정창 생성 실패 복구를 해결했다. 이번 제보는 별도 경로다. CustomTkinter 5.2.2의 `CTkTabview.delete()`는 내부 목록과 grid에서 탭을 제거하지만 탭 프레임을 destroy하지 않는다. 서비스/거래소 화면을 반복 재구성하면 프레임 아래의 ComboBox/OptionMenu와 callback이 Tcl 자식으로 남고, 설정창이 많은 메뉴를 새로 만들 때 Windows USER 메뉴 한도 오류가 먼저 드러난다.

Fix 3는 모든 동적 탭 삭제를 공통 `delete_ctk_tab()`으로 통일해 자식 cleanup hook을 children-first로 실행한 뒤 프레임을 실제 파괴한다. Windows에서는 전환 전후 USER/GDI 수를 기록한다.

## Bitget 화면의 Binance 호출

초기 Binance 전용 Analyzer/Evaluator/MarketSentiment 구조 위에 다중 거래소 어댑터가 추가되면서 일부 후보 수집은 Bitget을 사용해도 후속 AI 평가·펀딩비·OI·시장심리와 앱 시작 WebSocket은 Binance 기본값을 유지했다. 따라서 로그 라벨 혼선이 아니라 실제 Binance API 호출이었다.

Fix 3는 비바이낸스 K라인·티커를 ExchangeManager로만 조회하고, Binance 전용 파생지표는 중립값으로 처리한다. Binance가 회원의 활성/학습/실주문 범위에 없으면 BinanceClient와 WebSocket을 만들지 않는다. 토큰화 주식은 코인 후보에서 제외한다.

## Bithumb/Upbit 잔여수량

최소주문금액 아래 잔여수량은 거래소 수량 정밀도·수수료·이전 보유량 때문에 정상적으로 남을 수 있다. 문제는 이를 앱의 신규 포지션처럼 세거나, 반대로 기존 중요 보유량을 무시하고 같은 종목에 다시 진입하는 것이다.

Fix 3는 PAPER/LEARNING에서는 개인 잔고를 조회하지 않는다. LIVE 현물만 주문 전에 실제 잔고를 확인하고, 앱 원장에 없는 최소주문금액 이상 동일 종목 보유는 차단한다. 다른 종목의 중요 보유자산은 전체 최대 포지션 수에 합산하고 최소주문금액 미만 dust는 슬롯으로 세지 않는다. 청산 수량은 `min(앱 관리수량, 실제수량 - 진입 전 baseline)`으로 제한한다.

## UI 기술 선택

Fix 3에서 CustomTkinter를 다른 프레임워크로 교체하지 않는다. 현재 기능 전체를 한 번에 이전하면 거래·권한·설정 회귀 위험이 더 크다. 현재 구조는 안정된 셸과 제한된 동적 탭으로 유지한다.

차트·대량 표·Windows 증권 COM을 포함한 다음 세대 UI는 PySide6/Qt가 우선 후보이며, Kiwoom PyQt5/QAx 경로는 별도 Windows 프로세스로 격리하는 단계적 이전이 적절하다. Tk와 Qt 또는 PyQt5와 PySide6 이벤트 루프를 한 프로세스에서 혼합하는 전환은 하지 않는다. 웹 UI는 차트에는 유리하지만 로컬 서버·IPC·업데이트·보안 범위가 커 별도 제품 버전에서 평가한다.

## 배포 전 외부 게이트

- Windows 10/11에서 서비스·거래소 전환 100회와 설정창 반복 진입 후 USER/GDI 수가 기준선으로 복귀하는지 확인
- 제보 PC에서 Binance PAPER 장시간 실행 및 dump 미발생 확인
- Bitget-only 레퍼럴 PAPER에서 네트워크 로그/프록시 기준 Binance REST/WebSocket 0건 확인
- Bithumb/Upbit LIVE 소액으로 기존 dust 보존, 동일 종목 중복 차단, 앱 관리수량만 청산 확인
- 모든 회원 등급과 LEARNING/PAPER/LIVE 권한 매트릭스 재확인
