# v3.9.1.36 설치 후 키움 조회 중단 피드백

후속: 사용자 원본 로그를 수령했으며 [v3.9.1.37 로그 분석](V39137_KIWOOM_USER_LOG_ANALYSIS.md)과 [검증 계획](V39137_KIWOOM_BOUNDED_QUERIES_TEST_PLAN.md)으로 이어집니다. 아래 내용은 로그 수령 전 조사 기록입니다.

## 관측과 결론

사용자 제공 Windows 화면은 v3.9.1.36을 표시하며 PAPER 분석 이후
`kiwoom_manual_reconnect_required`가 발생했습니다. 이는 이전 RPC 실패 뒤
자동 재로그인을 차단한 상태입니다. 이 메시지만으로 최초 실패 호출이나
키움 서버/인터넷 장애를 특정할 수 없습니다. 사용자 환경에서 타임아웃의
원인까지 해결됐다는 이전 판단은 할 수 없습니다.

## 소스에서 확인한 결함 및 후속 수정

- pykiwoom의 동기 TR 대기는 제한시간이 없고 `CommRqData`의 즉시 반환 오류를
  전달하지 않습니다. 호스트 내부에서 요청 반환 코드·응답 제한시간·파싱 실패를
  판별하도록 변경했습니다. 로그인 콜백 실패도 성공 이벤트를 무기한 기다리지 않습니다.
- TR마다 요청 이름을 부여하고 화면번호·TR 코드까지 대조해 늦은 응답이 다음
  조회의 결과가 되지 않도록 했습니다. 조회 오류 응답을 받으면 호스트는 유지하고,
  실제 IPC 단절·불명확한 로그인·주문 결과에는 기존 수동 재연결/주문 대조 차단을 유지합니다.
- 계좌번호 조회의 실제 목록 반환을 지원합니다. 잔고는 `계좌평가결과`, 보유종목은
  `계좌평가잔고개별합산`으로 구분합니다. 로그인 비밀번호를 계좌 조회에 보내지 않으며
  별도 계좌 비밀번호가 없으면 OpenAPI에 등록한 계좌 비밀번호 사용 경로로 빈 값을 보냅니다.
- ETF 목록의 실제 목록 반환을 지원하고 목록 수집에서 종목별 TR 호출을 제거했습니다.
  시세는 종목 분석 시 조회합니다.
- 재연결 차단 메시지에 최초 RPC 실패를 보존하고, 호스트 로그에 RPC 완료·TR 시작/
  완료/실패 단계와 TR 코드를 추가합니다. 입력값·계좌번호·비밀번호는 진단 이벤트에 넣지 않습니다.

참조: [pykiwoom 구현](https://github.com/sharebook-kr/pykiwoom/blob/master/pykiwoom/kiwoom.py),
[잔고 예제](https://github.com/sharebook-kr/pykiwoom/blob/master/example_tr/opw00018_s.py),
[보유종목 예제](https://github.com/sharebook-kr/pykiwoom/blob/master/example_tr/opw00018_m.py).

## 검증 및 배포 상태

후속 수정은 로컬 소스 단계입니다. 사용자가 실행한 공개 v3.9.1.36 설치기에는
포함되지 않았고 기존 설치 파일을 교체하지 않았습니다. 다음 새 버전으로 빌드해야 합니다.
로컬 Windows manifest도 v3.9.1.36 stable / 외부 검증 미완료 상태를 확인했습니다.

이번 수정 후 macOS 자동 회귀: 전체 **2,477 passed / 8 skipped / 3 subtests passed**,
키움·프로세스 수명·빌드 관련 집중 회귀 **126 passed / 3 subtests passed**.
Windows ActiveX 및 해당 사용자 세션의 검증 결과는 아닙니다.

회귀는 `tests/test_kiwoom_bounded_backend.py`에서 즉시 거부, 무응답, 파싱 실패,
늦은 응답, 재조회, 로그인 실패, 계좌/ETF 목록, 잔고 출력 계약, 로그인 비밀번호
비전송, 조회 실패 후 호스트 유지, 로그인 불명확 상태의 재로그인 차단을 검사합니다.

Windows 사용자 환경에서는 오류 직전 `logs/kiwoom_host_events.jsonl`의 마지막
`rpc_…` 단계와 최초 `kiwoom_rpc_transport_error:…`가 필요합니다.
후속 설치기의 로그인→잔고→일봉→PAPER 주기→조회 실패→다음 조회 회복을 확인해야
이번 사용자 문제 해결을 확정할 수 있습니다. 키움 ActiveX가 원시 호출 안에서 멈추는
경우에는 내부 이벤트 대기 제한만으로 복구할 수 없어 기존 외부 RPC 차단이 필요합니다.
