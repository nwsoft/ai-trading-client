# 로그인 직후 백그라운드 부하 완화 설계 노트 (2026-06-28)

## 1) 배경
- 로그인 직후 대시보드가 올라올 때 여러 위젯이 동시에 `after()`/스레드 기반 작업을 시작하면서 체감 지연이 발생할 수 있음.
- 특히 시장 트렌드 위젯은 REST 호출 + 지표 계산을 즉시 시작해 초기 부하를 키우는 경향이 확인됨.

## 2) 이번 변경 범위
- 대상 파일: `ui/widgets/market_trend_widget.py`
- 적용 내용:
	- 가시성 기반 실행: 위젯이 실제로 화면에 보일 때만 자동 수집 진행.
	- 인메모리 TTL 캐시(기본 180초): 동일 서비스 컨텍스트 재진입 시 캐시 우선 반영.
	- 강제 새로고침 분리:
		- 자동 주기(10분) 갱신은 `force_refresh=True`로 실제 재수집.
		- 사용자 수동 새로고침도 `force_refresh=True`로 실제 재수집.

- 대상 파일: `ui/widgets/ai_report_widget_real.py`
- 적용 내용:
	- 비가시 상태에서 자동 리포트 생성 억제.
	- 인메모리 TTL(180초) 내 중복 자동 생성 억제.
	- 탭 진입(Map) 시 1회 강제 갱신으로 최신성 보강.

- 대상 파일: `ui/widgets/ai_learning_widget.py`
- 적용 내용:
	- 비가시 상태에서는 초기 로드/자동 새로고침을 실행하지 않음.
	- 인메모리 TTL(180초) 내 중복 새로고침 억제.
	- 탭 진입(Map) 시 1회 강제 새로고침.

## 3) 설계 의도
- 목표 A: 로그인 직후 불필요한 네트워크/연산 부하 완화.
- 목표 B: 실시간성 훼손 최소화.
- 균형점:
	- "항상 즉시 수집" 대신 "보일 때 수집 + 짧은 TTL 캐시" 전략 사용.
	- 데이터 최신성은 주기 갱신/수동 갱신에서 강제 재수집으로 보완.

## 4) 기대 효과
- 초기 화면 진입 시 체감 반응성 개선.
- 백그라운드 스레드 경쟁 및 API burst 완화.
- 탭 재방문 시 캐시 기반 즉시 렌더링으로 체감 지연 감소.

## 5) 잠재 부정 영향 (Known Trade-off)
- 탭을 오랫동안 열지 않았다가 진입한 순간, 첫 렌더가 캐시값(최대 180초 이내)일 수 있음.
- 단, 이후 주기 갱신 또는 수동 새로고침에서 실데이터로 갱신됨.

## 6) 관찰 지표 (운영 체크)
- 로그인 직후 30초 내:
	- 시장 트렌드 관련 API 호출 횟수
	- `_gather_market_trend_data` 시작 로그 빈도
	- `AIReportWidgetReal` 자동 생성 호출 빈도
	- `AILearningWidget` 초기/새로고침 호출 빈도
	- UI 프리즈/메인스레드 경고(`main thread is not in main loop`) 발생 빈도
- 사용자 체감:
	- 로그인 후 대시보드 표시 시간
	- 시장 트렌드 탭 최초 진입 후 데이터 표시까지의 시간

## 7) 롤백/재조정 기준
- 아래 중 하나라도 관찰되면 TTL/트리거 정책 재조정:
	- 데이터 신선도 불만이 반복 보고됨
	- 탭 진입 직후 stale 데이터로 의사결정 오해가 발생
	- 성능 개선 효과가 미미하거나 다른 위젯 병목이 더 큼
- 조정 우선순위:
	1. TTL 단축 (180초 -> 120초 -> 60초)
	2. 탭 진입 시 즉시 1회 강제 재수집
	3. 캐시는 유지하되 핵심 지표만 별도 단기 주기로 분리

## 8) 연관 문서
- `docs/CHANGELOG.md` (변경 이력 기록)
- `docs/README.md` (문서 인덱스)
- `docs/AI_API_ARCHITECTURE.md` (OpenAI 호환 API 설계 참고)

## 9) 누가 어디서 확인하는가 (운영 절차)
- 사용자(테스터): 앱 사용만 수행하고 로그 파일을 전달.
- 관리자/개발자: 전달받은 성능 로그를 집계해 TTL 조정(180/120/60초) 판단.

확인 파일:
- UI 성능 전용 로그(JSONL): `logs/ui_perf_metrics.jsonl`
- 일반 런타임 로그: `logs/trading.log`

경로 규칙:
- 개발 환경: `noahai_client/data/<user_id>/logs/`
- 배포(Windows exe): `Documents/NoahAI/<user_id>/logs/`

수집 대상 이벤트(예):
- `market_trend`: `cache_hit`, `cache_miss`, `fetch_done`, `map_force_refresh`
- `ai_report`: `ttl_hit`, `ttl_miss`, `generate_done`, `skip_invisible`
- `ai_learning`: `ttl_hit`, `ttl_miss`, `refresh_done`, `initial_defer_not_visible`

운영 권장:
- 3~7일 기간 동안 테스터별 `ui_perf_metrics.jsonl` 파일 제출
- 관리자/개발자는 테스터별 이벤트 빈도와 `elapsed_ms` 분포를 비교해 TTL 조정
- 개인정보/입력값은 기록하지 않고 위젯 동작 메트릭만 기록
