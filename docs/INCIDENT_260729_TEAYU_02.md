# 2026-07-29 Teayu_02 사용자 피드백 조사

기준: NoahAI Client v3.9.0.3 후보 사용자 압축본 `data/260729_Teayu_02`  
조사일: 2026-07-29  
반영 대상: v3.9.0.4 Windows 재빌드 전 소스

## 결론

`keyring` 경고와 전 거래소 탭의 잔고·포지션 로딩 문제는 같은 원인이 아니다.

- `keyring` 경고: v3.9.0.3 멀티 AI Provider 작업에서 AI 키만 Windows 자격 증명 관리자로 옮긴 정책 변경과 안전 빌드 누락이 겹친 문제. 거래소·증권사 키의 기존 로컬 정책 및 무설치 원칙과도 일치하지 않았음
- 전 거래소 탭 로딩: 메인 KPI는 로컬 DB·로그를 읽지만 거래소 탭은 별도 비동기 private API 갱신을 사용한다. 숨겨진 CTk 탭에서 최초 예약이 `winfo_viewable=False`로 종료된 뒤 자식 Map 이벤트가 다시 오지 않아 조회 자체가 시작되지 않았고, 거래 화면이 실거래 연결과 다른 Unified adapter를 볼 수 있는 경로도 남아 있었음
- TP/SL 반복 경고: `0.18/0.2`는 각각 0.18%/0.2%인 구버전 퍼센트 포인트 표현이다. 내부 fraction으로 정상 변환됐지만 구값이 다시 주입·저장되어 시작할 때마다 같은 WARNING이 반복됐음
- 실행 중 불안정: 거래 직후 지연 잔고 갱신 함수가 지역 `import time` 스코프와 충돌하여 반복 종료. 설정의 실제 AI 기능 검증도 닫힌 CustomTkinter 입력창을 다시 읽을 수 있었음
- 거래소별 반복 오류: ExchangeManager의 OHLCV는 Binance 배열 형식으로 정규화되는데 일부 Unified 분석 코드는 dict만 가정했다. Evaluator가 문자열 심볼을 반환하는 경우도 실행 루프가 dict로 가정했다.

따라서 사용자가 `pip install keyring`을 실행할 문제는 아니다. v3.9.0.4는 필수 keyring 정책 자체를 철회하며 추가 패키지 없이 기존 로컬 설정 방식으로 동작한다. 다만 이후 읽기 전용 실연결 점검에서 거래소별 허용 IP·인증·권한 문제도 별도로 확인됐으므로 해당 거래소 설정은 교정해야 한다.

## 2026-07-29 실연결 재점검

- Upbit·Bithumb·Bybit·Bitget: API 허용 IP 또는 접근 정책으로 인증 실패
- OKX: API 인증 정보 검증 실패
- Binance: 계정 정보 빈 응답으로 자격 검증 실패
- 위 결과는 주문을 보내지 않은 잔고·계정 정보 읽기 전용 점검이다.
- 어댑터가 인증 오류를 빈 dict로 삼키고 상위 계층이 성공으로 캐시하던 결함을 수정해, 이제 실패가 최종 상태로 표시되고 성공 캐시에 들어가지 않는다.
- Teayu_02의 DeepSeek·OpenAI는 v3.9.0.3 참조만 남아 실제 키 재입력 전 AI 커스텀 Provider 분석과 AI 어시스턴트 호출이 준비되지 않는다.
- 전체 판정과 남은 게이트는 `INTEGRATED_AUDIT_v3.9.0.4_20260729.md`를 따른다.

## 압축 로그 증거

- `runtime_stability.jsonl`: `delayed_balance_update`의 `NameError` 90건
- `runtime_stability.jsonl`: 정상 종료 표식이 없는 이전 실행 감지 4건
- `runtime_stability.jsonl`: 파괴된 설정 입력창 접근 `TclError` 1건
- `runtime_faulthandler.log`: 세션 시작 기록만 있고 native fatal stack은 없음
- `ui_perf_metrics.jsonl.1`: 과거 숨은 AI 학습 탭 callback 누적으로 1,393,277줄, 약 166MB
- 2026-07-29 07시대 `trading.log`: 배열/dict OHLCV 혼용 77건, OKX 문자열 계약 오류 21건, Binance 변동성 형식 오류 10건
- 같은 구간: 최적화 결과의 `datetime` JSON 저장 오류 1건, Binance 포지션 동시 제거 `KeyError` 1건
- 거래 로그에는 Binance 진입·청산과 여러 거래소 분석이 계속 남아 있음. 이는 메인 KPI가 보이는데 거래소 카드만 멈춘 화면과 부합한다.

`previous_unclean_shutdown_detected`는 프로세스가 정상 종료 표식을 남기지 않았다는 증거다. 이번 압축본에는 native fatal stack이 없어 위 Python 예외 하나만을 전체 프로세스 종료의 단일 원인이라고 단정하지 않는다. 다만 반복 예외·대용량 로그·파괴된 위젯 callback은 모두 제거 대상이다.

## v3.9.0.4 반영

1. 자격증명·Windows 빌드
   - `requirements*.txt`, 안전·정적 PyInstaller spec에서 필수 keyring 및 Windows 보안 저장소 의존성 제거
   - AI 키를 거래소·증권사 키와 같은 사용자별 로컬 설정 정책으로 통일
   - v3.9.0.3 `credential_ref`만 남은 설정은 일반 설정 저장을 막거나 참조를 자동 삭제하지 않음
   - 사용자가 해당 Provider 키를 다시 입력하면 로컬 키를 정본으로 저장하고 과거 참조를 제거
   - 과거 설정 백업을 자동 소거하지 않아 구버전 롤백 단서를 보존
2. 전 거래소·증권사 대시보드
   - Binance·Upbit·Bithumb·Bybit·OKX·Bitget은 실거래 루프가 사용하는 기존 `ExchangeManager`를 잔고 조회의 정본으로 재사용
   - 거래소·증권사 탭 선택 시 숨은 자식 섹션의 갱신 예약을 명시적으로 재개
   - 비동기 조회 12초 제한을 두고, 느린 호출이 끝나기 전 중복 worker를 만들지 않도록 수명주기를 고정
   - 조회 전에는 `탭 열면 조회`, 조회 후에는 값·API 키 없음·인증 실패·연결 실패·빈 응답·시간 초과 중 하나를 표시
3. 런타임 안정성
   - 거래 직후 지연 잔고 갱신을 `Trader._schedule_delayed_balance_update` 한 경로로 통합
   - 설정 AI preflight와 모델 새로고침은 살아 있는 창·입력 위젯에만 결과 전달
   - 포지션 제거는 원자적 `pop(..., None)`으로 처리
4. 거래소 데이터 계약
   - 배열/dict OHLCV 공통 정규화
   - 문자열 선택 종목을 `{symbol: ...}`로 정규화
   - dict가 아닌 분석 응답은 실주문으로 넘기지 않고 HOLD 격리
   - 최적화 결과의 `datetime`을 ISO 8601로 저장
5. Binance 보호주문
   - 실제 열린 포지션이 확인될 때까지 제한적으로 기다린 뒤 TP/SL 제출
   - 포지션이 이미 없으면 `-4509` 주문을 반복하지 않고 안전하게 중단
6. TP/SL 설정 단위
   - 구버전 `0.18/0.2`를 `0.0018/0.002`로 최초 로드 시 변환하고 설정 파일에 저장
   - 정상적인 레거시 단위 이전은 INFO, 실제 비정상 입력의 안전값 복구만 WARNING으로 구분
   - 반복 원인은 균형 전략 프리셋의 표시 단위가 시작 직후 Trader에 다시 전달된 것이며, 프리셋에 단위 메타데이터를 명시하고 주문 엔진 전달 전에 한 번만 fraction으로 변환
   - Binance Trader와 UnifiedTrader가 같은 최종 TP/SL 정규화 계약을 사용해 거래소별 해석 차이를 차단

## 사용자 안내

- v3.9.0.3 후보 설치본에서는 Python·pip·requirements·keyring을 직접 설치하지 않는다.
- v3.9.0.4 공식 설치본으로 업데이트한다. AI 키 입력란에 `v3.9.0.3 키 재입력 필요`가 표시된 Provider만 키를 한 번 다시 입력한다.
- 단순 keyring 경고만으로 AI·거래소·증권사 키를 재발급하지 않는다. 개발 진단 콘솔이나 전달한 로그에 키 값 자체가 실제로 표시된 계정만 기존 키를 폐기하고 재발급한다.
- 설정과 설정 백업에는 API 키 등 민감정보가 포함될 수 있으므로 지원용 로그 압축에 포함하지 않는다.
- 각 거래소 탭은 연 뒤 12초 안에 값, API 키 없음, 인증 실패, 연결 실패, 빈 응답, 조회 실패 중 하나를 표시해야 한다.
- 새 Windows EXE는 키 저장·재시작 복원, 선택한 각 거래소의 잔고·포지션, 실제 AI preflight, 24~72시간 실행을 별도로 검증해야 한다.
- 현재 소스는 `pending_windows_rebuild`이며 Windows 설치본 검증 전에는 배포 완료가 아니다.
