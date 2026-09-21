# 현재 소스 후보 v3.9.1.44 · 공개 자산 기준 v3.9.1.43

2026-09-21 저장 계약 보강: 신규 입력은 정규화 전에 기관·모드 모순을 검사하고 `contract_rejections`에 원문·사유를 보존하여 정상 학습 조회와 분리합니다. 과거 불확실한 근거를 임의 수정하지 않습니다. 공유 Recorder 기관 변경 및 학습 입력 기관 덮어쓰기를 제거했습니다. 증권 청산 XAI는 해당 실행 모드·주문 결과를 전달하며 타임아웃을 ‘실제 주문 없음’으로 단정하지 않습니다.

계정 진단 로그는 닫힌 날짜형 회전 파일만 제한된 백그라운드 작업으로 gzip·해시 검증 후 대체합니다. `log_archives`는 진단 hot 예산과 별도 집계합니다. 중요 원장·학습 근거까지 포함한 전체 디스크 hard cap은 아닙니다. [상세 검증 및 Windows 경계](../reports/v39144-storage-verification.md). 아래 과거 버전 설명은 당시 구현 범위입니다.

## v3.9.1.42 원격 실행 경계

PC가 승인한 모드/설정/전략 digest와 승인 세대를 서버 명령에 결합합니다. 서버는 소유권·CSRF·재인증·최신 상태를 확인해 TTL 120초 명령을 중계하고, PC는 명령 예약을 먼저 영속화한 뒤 회원·설정·위험을 재검사해 기존 시작 경로를 호출합니다. 불확실한 실행은 자동 재시도하지 않습니다. 주문/키/전략 원문은 서버에서 실행·보관하지 않습니다. [검증](V39142_REMOTE_CONTROL_PLAN.md).

# NoahAI 시스템 아키텍처 (현재 소스 후보 v3.9.1.41 · 공개 안정판 v3.9.1.40)

## 현재 버전 기준 · v3.9.1.41 검증 후보

현재 소스 후보 버전: **v3.9.1.41** · updater **3.9.141**. 현재 공개 stable/latest는 **v3.9.1.40**입니다.

시장 트렌드는 계좌·주문 상태와 분리된 읽기 전용 공개 시세/증권 일봉을 사용합니다. 코인·주식별 대표 표본과 기간·수집 시각·누락 항목을 구조화된 화면 근거로 만들고, 로컬 XAI가 그 근거만 설명합니다. 이 경로는 관찰 후보를 개인화 추천이나 주문으로 승격하지 않습니다. [v3.9.1.41 검증 계획](V39141_MARKET_TREND_XAI_TEST_PLAN.md).

## v3.9.1.41 KPI·원격 실행 경계

- PC `RemoteMonitor`가 명시적 동의 후 별도 스레드에서 상태를 60초 전송합니다. API 키·전략·거래 실행은 PC에 유지하고 손익/포지션 상세는 공유하지 않습니다.
- daltrading은 auth/metrics/remote DB를 분리할 수 있고 기기 토큰 해시·PC 세션·사용자·인증 버전을 검증합니다. 모바일 쿠키 세션은 PC 로그인 세션을 교체하지 않습니다.
- 원격 명령은 허용된 기관의 신규 주문 제출 일시정지 하나입니다. TTL·순서·중복 ID·확인 응답을 사용하며 `EntryPause`가 제출 중 작업과 다음 진입을 구분합니다. 거래소 기제출 주문 취소나 보호/청산 정지가 아닙니다. PC 재개 후 지연 중복 명령은 재적용하지 않습니다.
- 학습·AI 추론 성공 KPI는 지원 협상 후 60초 묶음, 서버 5분 버킷·가중 통계로 저장합니다. 체결/위험 원장을 집계/보관 정리 대상에 포함하지 않습니다. 30일 초과 성공 텔레메트리만 외부 검증 후 일별 요약으로 유지합니다.
- [실행/검증 상태](V39141_REMOTE_KPI_IMPLEMENTATION_PLAN.md) · [사용자 경계](REMOTE_MANAGEMENT_GUIDE_V39141.md). 실제 EC2 분리·Windows·실계정·운영 성능은 미완료입니다.

## v3.9.1.39 PnL 대조 계약 (계속 유지)

LIVE 성과 원장은 NoahAI 종료 행과 거래소 체결을 분리합니다. 실제 청산 주문 ID가 있는 LIVE 행만 exact-order 근거로 방향·수량·귀속·비용 통화를 대조합니다. 주문 ID 없는 시간/수량 후보는 미확정으로 남깁니다. [PnL 재감사](V39139_PNL_TRUST_AUDIT.md).

## v3.9.1.38 과거재생·기관별 거래내역 (공개 기록)

현재 소스 후보 버전: **v3.9.1.38** · updater **3.9.138**. 현재 공개 stable/latest는 **v3.9.1.37**입니다. Electron/Web UI와 x64 엔진은 UI·서비스를 소유하고 PyQt5/QAxWidget·pykiwoom은 전용 x86 키움 호스트에만 포함합니다.

[v3.9.1.38 검증 게이트](V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md). 과거재생은 저장된 검증 snapshot을 읽고, 기관별 LIVE 이력은 계정 DB의 해당 기관 종료 원장을 읽는 조회 경로입니다. 둘 다 실행 모드·주문·전략 상태를 변경하지 않습니다. 패키징은 PE x64/x86과 SHA를 자동 확인하고 실제 OCX·기관 계좌 동작은 외부 Windows 증거로 분리합니다.

## 현재 소스 후보 v3.9.1.32 · 런타임 관측·데이터 계약

추가 점검 계약: `market_observation.py`는 관측 유효성과 마지막 확정 국면을 분리한다. 실패는 `unknown`이며 신규 진입을 보류한다. `RegimeStabilizer`는 미확인 표본을 확정·연속 확인 횟수에 사용하지 않는다. 증권 실행은 빈 후보로도 보유 관리 서비스를 호출한다. 미래에셋 `candles`와 `stock_list`는 서로 다른 기능이다.

알림 큐는 `(account generation, message)`를 보유하고 세대 검사와 수신 설정 복사를 같은 락에서 수행한다. 네트워크 I/O는 락 밖에서 수행하되 불변 복사본만 사용한다. 재시도·다음 채널 전송 전 세대를 재검사한다. 기존 in-flight 요청의 취소나 외부 서비스 exactly-once는 보장하지 않는다. 기관 설정은 중앙 등록부에서 생성하고 별칭은 `normalize_venue`로 통합한다. LIVE 위험 이벤트는 기존 위험 판정에 근거하며 미확인 손익/손실률은 창작하지 않는다.

v3.9.1.32는 국면 재선정 대기를 실제 변경 알림과 분리하고, 저장한 업데이트 확인 주기를 앱 공통 타이머로 실행합니다. Coinone의 미제공 활성 상태를 중단으로 오해하던 후보 수집을 수정하고, KIS·미래에셋의 주식/ETF 목록을 공식 공개 마스터로 분리합니다. 네 증권사 워커의 후보 없음·분석 완료·오류를 해당 기관 로그로 전달합니다. 주문 권한·TP/SL·점수 없는 진입 차단은 유지합니다.

`publish_market_regime_change`는 같은 상태·초기 관찰을 거릅니다. `update-scheduler.cjs`는 Electron 단일 주기 확인을 소유하고 React는 캐시 상태를 읽고 구독을 해제합니다. `kis_market_master.py`는 KRX 공개 종목 메타데이터만 소유하며 증권사 주문 API·회원 권한과 분리됩니다. `runtime_observability.py`는 기관별 상태 변화와 5분 요약을 공통 로그로 전달합니다.

[계약과 외부 게이트](V39132_RUNTIME_RECOVERY_TEST_PLAN.md). 공개 기준 v3.9.1.31.

미래에셋 제휴 `stock_list`/`etf_info`의 프로필 매핑이 있으면 기존 목록·NAV·추적오차를 우선 사용한다. KIS는 해당 프로필 라우터를 우회하므로 개별 시세 API를 목록으로 호출하지 않고 공개 마스터를 사용한다. 명시적 KIS ETF 목록은 보존한다.

## 이전 아키텍처 변경 기록 (당시 기준)

## v3.9.1.31 사용자 메뉴얼 정본 계약

인앱 사용자 메뉴얼의 내용 정본은 `ui/widgets/user_manual_widget.py`이며 `scripts/export_legacy_manual_sections.py`가 UI 중립 JSON `docs/USER_MANUAL_SECTIONS.json`을 생성한다. Web UI는 이 11개 섹션 전체를 축약하거나 별도 사본으로 다시 작성하지 않고 문서 구조로 렌더링한다. 검색은 모든 섹션 본문의 실제 발생 위치를 순회한다.

배포 전에는 정본과 JSON의 완전 일치, 11개 고유 섹션, UTF-8 무손실, 현재 기관 등록부, 소스 후보/공개 버전, 최신 업데이트 순서를 자동 검사한다. 거래 기능이 바뀌면 해당 기능 정본·사용자 가이드·인앱 메뉴얼·변경 이력·배포 체크리스트를 같은 변경에서 갱신하고, 누락 시 소스 빌드 게이트를 실패시킨다. v3.9.1.31의 메뉴얼 UI 변경은 v3.9.1.30 거래 수량·신호·가드레일·원장 계약을 변경하지 않는다.

## v3.9.1.30 기관·통계·시간봉 공통 계약

PAPER 카드는 `_paper_statistics_snapshot`과 동일한 집계기를 사용한다. JSONL은 재무/학습 원장 정본으로 보존하고, 기관·기간 필터 후 조회 상한을 적용한다. 캐시는 inode·mtime·size·조회 범위로 분리하고 변경 시 무효화한다. 결과 스칼라에 KRW와 USDT를 합산하지 않는다.

`strategy_timeframe_contract`는 저장된 `decision_timeframe`/`execution_timeframe`과 선언형 지표의 필요 시간봉을 해석한다. 과거 재생 공급자와 런타임 지표 문맥은 같은 선언을 사용한다. 과거 재생은 완성 캔들·시간 순서·기관/봉 응답 일치를 검사한다. 상위봉은 그 봉이 닫힌 시각 이후에만 노출한다. 증권사 분봉 또는 서로 다른 판단/실행봉 미지원은 명시적 중단으로 표현한다.

기관 추가 시 `CRYPTO_VENUES`/`STOCK_VENUES` 등록뿐 아니라 공개 캔들 공급·정렬·종료 시각·기관별 통계 테스트를 통과해야 한다. Coinone은 [공개 chart V2](https://docs.coinone.co.kr/reference/chart)를 사용한다. Bithumb 15m/4h는 [공식 분봉 API](https://apidocs.bithumb.com/v2.1.0/reference/분minute-캔들-조회)로 직접 조회한다. 구형 candlestick의 200봉 응답을 15분봉으로 재구성하면 표본이 부족해지므로 사용하지 않는다. Bithumb 2h만 완전한 1h 묶음으로 집계하며 실제 반환 표본 수를 기록한다.

키움 OpenAPI+는 Windows에서 호출 출처에 관계없이 process proxy를 사용한다. COM 소유 프로세스는 유휴 중에도 Qt 이벤트를 처리한다. timeout 채널을 폐기하고 자동 주문 재시도를 금지한다. KIS 인증 성공과 실제 계좌 조회 성공은 별도 상태다. [v3.9.1.30 검증 계획](V39130_STRATEGY_VENUE_CONSISTENCY_TEST_PLAN.md)이 배포 게이트다.

## v3.9.1.29 전략 공용계층·회원 운용용량·Coinone 온보딩 계약

- AI Provider 진단은 `(credential, requested_model, capability)`에 대해 카탈로그 조회와 실제 생성 호출을 별도 증거로 보존한다. 텍스트 진단은 비민감 고정 문장을 한 번 호출하며 `requested_model`, Provider 응답의 `actual_model`, 토큰, 응답 ID, 정규화 오류를 반환한다. `/models` 누락이나 정적 호환 목록은 실제 호출 성공을 덮어쓰지 않는다.
- 대화형 AI usage 정본은 화면에서 선택한 별칭이 아니라 성공 응답의 실제 모델 ID를 사용한다. 화면 초안은 `변경 대기`, 저장된 라우트는 `실행값`으로 구분하고 진단 호출도 비용 원장에 포함한다. Provider 청구 대조는 같은 Organization·Project·UTC 기간에서 수행한다.
- GPT-6 reasoning 모델은 `max_completion_tokens`와 지원되는 reasoning 옵션만 전송하며 `temperature`, `top_p`, `logprobs`, `top_logprobs`를 Provider 경계에서 제거한다.
- Strategy Studio의 제작·로컬 분석·PAPER 전진검증·내보내기·공유 준비는 상품 공용계층이다. 회원등급은 전략 IR, Level, 검증 판정, 허브 증거등급과 점수에 개입하지 않는다.
- 실제 계정 운용용량은 전략 권한과 별도다. 집중운용은 1개, 관리형 다중포지션은 국내 무료/레퍼럴 확인 해외 무료가 기관별 최대 3개, 코인 유료가 최대 5개다. 계좌·시장·성과·전략 요청·하드 가드레일의 `min()` 결과가 최종값이며 용량을 채우기 위해 주문하지 않는다.
- 국내 무료 기관과 해외 레퍼럴 기관을 분리한다. Upbit·Bithumb·Coinone은 UID 귀속 없이 열고, 해외 무료는 서버가 서명한 제휴 확인 집합만 허용한다. 이 정책은 거래 권한이며 전략 제작이나 PAPER 검증 권한이 아니다.
- Coinone은 `ccxt_hybrid`로 공통 시세·정규화 기능은 CCXT를 사용하고 시장가 주문·주문상세·완료체결·캔들 공백은 공식 V2.1 계약으로 보완한다. 등록부의 `paper_supported=true`, `live_supported=false`를 실행 시작과 어댑터 주문 양쪽에서 검사한다.
- 새 기관은 등록부 추가만으로 LIVE가 되지 않는다. mock 회귀 후 실제 계정 주문·부분체결·취소·수수료·재시작 대조를 통과해야 `live_supported`를 승격한다.

## v3.9.1.28 체결·성과 원장 계약

- `trade_log`는 NoahAI가 소유한 진입 lot와 청산 성과의 정본이고 `exchange_execution_log`는 수동 거래도 포함할 수 있는 기관 확인 체결 원장이다. 체결 동기화가 새 완료 거래를 임의 생성하지 않는다.
- 두 원장은 정규화한 기관 ID, 종목, 정확한 청산 주문 ID로만 대조한다. 주문 ID 누락, 수량 불일치, 공급자 실현 PnL 미제공, 수수료 통화 변환 불가는 각각 상태로 보존하며 추정값으로 확정하지 않는다.
- `gross_pnl`은 거래소/기관 실현손익 또는 명시된 주문연결 계산, `entry_fee`·`exit_fee`는 기관 비용, `net_pnl`은 같은 결제통화로 환산 가능한 비용을 차감한 성과다. 승패·승률·누적·최대/최소는 `net_pnl` 우선이다.
- 파생상품 부분체결과 주식/ETF 부분매도는 완료되지 않은 원래 lot의 잔여수량을 유지하고 청산된 수량만 별도 성과 행으로 기록한다.
- `exchange_trade_stats`와 `stock_trade_stats`는 운영 캐시일 뿐 기간별 성과 화면의 정본이 아니다. 새 기관도 반드시 같은 체결/lot/비용/대조 계약을 구현해야 한다.
- 통계 UI는 헤더와 스크롤 본문을 하나의 고정 Grid 행에 두고 성공·오류·레거시 안내를 항상 존재하는 상태 행에 표시한다. 비동기 결과가 화면 최상위 행 수와 스크롤 기준점을 바꿀 수 없다.
- 사용자 표시 버전은 `config/app_version.py`와 패키지 `buildVersion`의 제품 버전을 사용한다. Electron 런타임의 `app.getVersion()`이 개발 실행에서 의존성 버전을 반환해도 이를 제품명으로 노출하지 않으며, `Web UI`는 내부 구현 분류로만 남긴다.
- 설정의 빠른 시작은 별도 설정 스키마나 실행 엔진이 아니다. 기존 허용 필드의 PAPER 안전안만 renderer 변경 대기에 놓고 저장 revision/diff, 중요 설정 확인, write-only 자격증명, 사용자의 명시적 서비스 시작 계약을 그대로 통과한다.

## v3.9.1.27 설정 문맥·AI 모델·비용 경계

- 설정 도움말 요청은 `service=settings`와 9개 허용값의 `settings_section`을 함께 사용한다. renderer의 한글 질문에서 현재 탭을 추측하지 않으며 Gateway가 알 수 없는 탭 값을 거부한다.
- Settings 내부 안내와 전체 AI 어시스턴트는 같은 구조화 탭 ID를 사용한다. 탭 이동은 이전 요청 ID를 무효화하고 전체 어시스턴트도 `service + settings_section`별로 새 대화 상태를 만들어 교차 탭 응답 오염을 막는다.
- 일반 안내는 버전 관리된 로컬 제품 정본으로 답하고 외부 Provider를 호출하지 않는다. 심층분석만 사용자 명시 동작으로 Provider·역할 모델·일/월 예산·캐시 계약을 사용하며 설정 저장이나 주문 실행 권한을 갖지 않는다.
- `model_registry.py`는 NoahAI 어댑터가 지원하는 제공사별 정적 모델·상태·기능을, `provider_catalog.py`는 기준일 공개 단가·용도·장단점을 관리한다. 제공사 계정의 실제 사용 가능 모델은 사용자 요청형 네트워크 점검의 결과이며 정적 목록과 합치되 동일한 증거로 취급하지 않는다.
- 비용 카드는 사용자 요청형 외부 호출 원장과 공개 단가를 이용한 예상값이다. 무료 토큰·캐시·프로모션·세금·같은 키를 쓰는 다른 앱은 Provider 콘솔만 확인할 수 있으므로 NoahAI 예상액을 청구서로 사용하지 않는다.
- OpenAI 데이터 공유는 외부 조직 설정이고 NoahAI가 읽거나 변경하지 않는다. `openai`와 `openai_shared` 자격증명을 분리하며 기본 라우트는 항상 `protected_default`다. `public_general`은 사용자 명시, 기능 설정 ON, 공유용 키 존재가 모두 충족될 때만 `openai_shared_public_general`로 간다.
- `public_general` 요청은 단일 질문 외에 최근 대화·runtime·workspace·settings·strategies·life-finance 문맥을 직렬화하지 않는다. 미설정·불명확 분류는 기본 보호 경로로 닫고, 보호 경로가 공유용 키를 사용하는 역방향 fallback은 금지한다. 캐시 키와 사용량 원장에도 privacy route를 포함한다.
- OpenAI Chat Completions에는 `store=false`를 명시하지만 이를 Zero Data Retention, 학습 비동의, 무료 사용의 증거로 취급하지 않는다. 조직 공유 상태와 무료량은 Provider 콘솔의 외부 정본이다.
- 이 계층은 UI·설명·외부 AI 요청에만 적용된다. 거래 신호, 전략 IR, 주문 수량, 가드레일, PAPER/LIVE 원장과 거래소·증권사 어댑터는 변경하지 않는다.

## 기관 온보딩 불변 계약 (거래소·증권사 공통)

새 거래소나 증권사를 추가하는 작업은 어댑터 한 개를 연결하는 일이 아니다. 아래 계약을 한 릴리스에서 함께 충족하고 자동·패키지·실환경 게이트를 통과해야만 제품에서 `지원`으로 표시한다.

- 기관 식별과 시장 의미의 코드 정본은 `trading/exchanges/venue_capabilities.py`의 `_VENUES`다. `CRYPTO_VENUES`, `STOCK_VENUES`, 통화·현물/선물·SHORT·레버리지·주문 단위는 이 등록부에서 파생한다.
- `config/web_ui_feature_inventory.json`은 Web UI가 읽는 기관·기능 정본이고 `webui/src/venueSources.ts`는 화면 공통 목록이다. 둘은 코드 등록부와 정확히 일치해야 하며 Python 런타임·통계나 개별 Web 화면에 기관 목록을 다시 복사하지 않는다.
- 기관 ID, 서비스(`blockchain/stock`), 시장 유형, 기준통화, 주문 수량 단위, contract size, 포지션 모드, 보호주문, 체결 대조, client order ID, 비용, 시간 동기화, 호출 제한, 자격증명 별칭을 명시한다.
- 실행모드 `LIVE/PAPER/LEARNING`, 청산 원장, 외부 확인 체결, 열린 포지션, PAPER 포지션·성과, 알림·로그 소유권, Strategy Studio의 `strategy_key + version_id + venue + execution_mode + event_id` 귀속을 모두 구현한다.
- 통계 표시 기준은 `account + service + source`별 비파괴 기준시각이다. 거래·학습·PAPER·위험 원장을 삭제하지 않으며 전체 보기와 개별 기관 보기를 별도 범위로 관리한다.
- 서로 다른 기준통화는 절대 합산하지 않는다. 가격·비용·PnL이 불확실하면 정확한 0으로 바꾸지 않고 `미확정/조회 실패`로 닫는다.
- 시작·중지·PAPER 일시정지·재개·새 검증·재시작 복구·안전 종료와 조회용 어댑터까지 하나의 수명주기 계약으로 검증한다.
- CCXT는 전송 계층의 출발점일 뿐이다. `validate_venue_onboarding_profile()`의 기관별 계약과 native escape hatch, mock 회귀, 해당 OS/계정의 PAPER·소액 LIVE 검증 없이는 지원 완료가 아니다.
- 알 수 없는 기관이나 서비스가 다른 기관 ID를 받으면 Binance 또는 현물/선물 기본값으로 추정하지 않고 실패 폐쇄한다.
- 실제 사용자 지원 폴더는 테스트 fixture나 마이그레이션 대상이 아니다. 재현에는 비식별 합성 fixture만 사용하며 실계정 readiness는 명시한 QA 계정에서만 수행한다.

기관 추가 회귀는 `tests/test_v39116_market_execution_contract.py`가 코드 등록부, 런타임·통계 집합, Web UI inventory와 허용 범위의 드리프트를 차단한다. 자격증명 화면·어댑터·패키지·실환경 검증은 자동 드리프트 검사와 별개의 필수 게이트다.

## 2026-09-07 v3.9.1.23 LIVE 통계·표시 기준 경계

- LIVE 청산 수·승률·실현손익·비용의 정본은 `trade_log`, 외부 거래소 확인 체결은 `exchange_execution_log`, 현재 포지션은 최신 계좌 조회다. `exchange_trade_stats`와 증권 요약은 재생성 가능한 운영 캐시다.
- 출처 없는 구형 `trade_log` 행은 보존하지만 특정 거래소나 대표 LIVE 성과로 추정 귀속하지 않고 미확정 근거로만 노출한다.
- `execution_mode`는 신규 기록에서 LIVE/PAPER/LEARNING 실행 경계만 저장한다. 과거 Binance의 `optimized/manual`은 LIVE 호환 별칭이고 전략·실행 방식은 별도 필드가 소유한다.
- 기간은 거래 통계 화면에서만 오늘·7일·30일·전체·사용자 지정을 제공한다. 청산은 `exit_time`, 확인 체결은 `executed_at`을 사용하며 KRW와 USDT를 합산하지 않는다.
- 계정별 `statistics_view_state.json`은 비파괴 표시 기준시각만 저장한다. 거래·학습·PAPER·위험 원장을 수정하지 않으며 가드레일·성과회복 계산 입력으로 사용하지 않는다.
- 운영 KPI의 열린 포지션은 활성 기관 전체의 계좌 조회가 성공했을 때만 최신 합계를 사용하고, 일부 실패하면 저장 원장 참고 상태를 명시한다.

## 2026-09-06 v3.9.1.22 투자금·성과회복·병행검증 경계

- `position_sizing_policy.py`가 계좌 마스터 위험, Strategy Studio 요청 위험, 시장·성과 배수에서 승인 Notional/증거금/수량과 동시 포지션 상한을 계산하며 Binance, Unified, 4개 증권사 경로가 같은 결과 의미를 사용한다.
- 신규 계정은 `account_risk`, 구형 공통 정책 미보유 계정은 `legacy_venue`, 수동 목표액은 `manual_notional`이다. 마이그레이션은 기존 LIVE 노출을 자동 확대하지 않는다.
- 전략은 계좌 상한 안에서 위험·레버리지·동시 포지션을 요청할 수 있으나 계좌 상한과 하드 가드레일을 높이거나 해제할 수 없다. Level 4는 이 제한 자율성의 편집 화면이며 Level 5 가드레일 해제 단계는 없다.
- 신규 거래소는 `CCXT core + venue capability profile + native escape hatch` 원칙을 사용한다. CCXT 연결 성공만으로 주문·보호·재시작 적합성이 증명되지 않는다.
- `profitability_validation.py`는 거래별 순수익률로 Sharpe/MDD/기대값/구간 안정률을 계산하고 통화별 현금 손익 합계와 분리한다.
- `parallel_strategy_paper.py`는 거래소·증권사 어댑터와 주문 API를 받지 않으며 LIVE 활성 전략과 분리된 PAPER 관찰 버전별 가상 포지션만 저장한다.
- 소스 회귀는 Windows 설치본, 실계정 수량, 실제 contractSize/정밀도, 장시간 LIVE/PAPER 병행 운용을 증명하지 않는다.

## 2026-09-04 v3.9.1.21 PAPER 평가·비용·소유권 경계

- 암호화폐 Binance/Unified와 증권 `StockAnalysisService`는 실행 계층이 다르지만, 활성 PAPER 포지션에는 현재가·gross/net PnL·비용·기준통화·계산 상태를 제공한다.
- 국내 주식·ETF PAPER는 `trading/stock_paper_valuation.py`의 결정형 비용 계약을 사용한다. 세금·수수료·슬리피지는 추정치로 분리하며 실제 증권사 체결·청구 데이터로 표시하지 않는다.
- `paper_strategy_ledger.py`는 암호화폐 KRW/USDT와 국내 증권 KRW를 거래소/증권사별로 기록한다. PAPER 성과 정책은 동일 소유자·PAPER 원장만 읽고 LIVE 체결 경로와 분리한다.
- 공유 Recorder는 mutable 현재 탭이 아니라 호출이 전달한 실제 실행 거래소·증권사를 로그 소유자로 사용한다.
- 소스 회귀 통과는 Windows 설치본·실제 증권사 계정·장시간 PAPER 검증을 대체하지 않는다.

## 2026-08-14 v3.9.1.0 Web UI Internal Integration Candidate

- `config/web_ui_feature_inventory.json`: 5개 서비스·6개 거래소·4개 증권사·플랫폼 기능의 이전 범위와 순서를 관리하는 기계 판독 정본
- `web_platform/contracts.py`: schema `1.0.0`의 엄격한 플랫폼, 런타임 snapshot, 캔들, 이벤트 계약
- `web_platform/application_services.py`: 계정별 설정 revision/diff·write-only 자격증명·프라이빗 전략·생활금융·마스킹 로그와 런타임 브리지의 단일 UI 경계
- `web_platform/gateway.py`: loopback 전용 조회/명령 API, 강한 실행 토큰, Origin·명시 intent 제한, WebSocket 최초 메시지 인증
- `web_platform/market_data.py`: Binance·Upbit·Bithumb·Bybit·OKX·Bitget spot/futures 캔들의 allowlist·정규화·짧은 캐시
- `trading/stock_runtime_controller.py`: 4개 증권사 계좌·일봉·PAPER/LIVE worker의 UI-neutral 경계
- `webui/`: React/Vite 서비스 셸, 전체 설정, 전략 스튜디오, AI 가이드/심층분석, 자산·생활금융·로그, Lightweight Charts, sandboxed Electron/NSIS/updater 셸
- 현행 경계: Electron sidecar는 `NOAHAI_ENABLE_WEB_RUNTIME=1`로 기동되며 인증 사용자의 최초 명시적 시작 명령에서 UI-neutral `HeadlessTradingRuntime`을 지연 생성한다. `main.py`, `ui.*`, `tkinter`, `customtkinter`는 Web sidecar import·bundle 금지 대상이다. 암호화폐는 Binance/Unified 실행 계층, 증권은 `StockRuntimeController`를 사용하며 인증 전·엔진 초기화 실패·미지원 소스는 실패 폐쇄한다. 런타임 구조와 기능 원장의 `read_first` 12개 Web 소스 이전은 완료했지만 Windows 설치·실계정·PAPER E2E가 남아 제품 전체 배포 완료는 아니다.

## 2026-08-13 UI 플랫폼 전환 결정

### 결론

NoahAI의 매매·AI 엔진은 Python으로 유지하고, 최종 사용자 UI는 **웹 우선 프런트엔드 + 데스크톱 셸**로 전환한다. CustomTkinter 화면을 PySide6 위젯으로 그대로 번역하지 않는다. 먼저 UI와 엔진 사이에 애플리케이션 서비스 계약을 만들고, 같은 계약을 기존 UI와 새 UI가 함께 사용하면서 화면 단위로 전환한다.

```text
브라우저 SaaS ───────────────┐
                             ├─ Web UI (동일 디자인 시스템·화면 계약)
Windows/macOS 데스크톱 셸 ───┘
                │ REST 조회·명령 / WebSocket 이벤트
                ▼
로컬 Gateway (localhost 전용, 실행별 인증 토큰, Origin 제한)
                │
                ▼
Python Application Services
  ├─ 설정·프로필·회원 권한
  ├─ 거래소 상태·잔고·포지션·성과 조회
  ├─ AI 커스텀 IR·검증·버전·XAI
  ├─ OMS 명령·중복 방지·위험·주문 승인
  └─ 로그·감사·업데이트 상태
                │
                ├─ Binance/Upbit/Bithumb/Bybit/OKX/Bitget 어댑터
                └─ Windows Kiwoom Worker (PyQt5/QAxWidget, 별도 프로세스)
```

### 왜 PySide6 전체 전환이 아닌가

- PySide6는 Qt 6의 공식 Python 바인딩이며 복잡한 데스크톱 화면, model/view, 신호/슬롯, 네이티브 창 관리에는 CustomTkinter보다 강하다.
- 그러나 현재 키움 어댑터는 Windows ActiveX를 위해 `PyQt5.QAxContainer.QAxWidget`을 사용하고 Windows 빌드는 PyQt5를 포함하면서 PySide6/PyQt6를 제외한다. PyQt5와 PySide6를 같은 프로세스에 혼합하는 전환은 런타임·플러그인·배포 충돌 위험을 만든다.
- PySide6로 주 UI를 만들면 데스크톱 UI와 daltrading/SaaS 웹 UI를 각각 구현해야 한다. NoahAI가 원하는 동일한 사용 경험과 빠른 사용자 피드백에는 웹 우선 UI가 더 적합하다.
- Qt가 필요한 키움/ActiveX 경계는 삭제하지 않고 별도 worker로 격리한다. 주 UI와 broker worker는 타입이 정해진 제한 IPC만 사용한다.

### 현재 구조에서 확인된 위험

- `ui/dashboard_modern.py` 약 1.4만 줄, `ui/settings_modern.py` 약 1만 줄의 대형 화면 클래스에 생성·상태·실행·정리 책임이 집중돼 있다.
- 동적 탭 파괴·재생성, `after/after_idle`, background thread, Toplevel 소유권이 여러 위젯에 분산되어 저장 전략 수나 탭 전환 횟수가 UI 자원과 타이밍을 바꿀 수 있다.
- UI 모듈이 거래·설정 객체를 직접 읽고 일부 작업을 직접 실행한다. 이 구조에서는 화면 수정이 엔진 재초기화나 연결 점검으로 번질 수 있다.
- 이는 Python 언어 자체의 한계가 아니다. 단일 GUI 스레드와 native Tk 자원 제약 위에 화면·도메인·수명주기 책임이 결합된 구조적 문제다.

### 전환 중 불변 계약

1. 거래소 API 키·Secret·Passphrase는 브라우저 DOM, WebSocket payload, SaaS 서버로 보내지 않는다.
2. UI는 거래소 SDK를 직접 호출하지 않고 `Application Services → OMS/Guardrails → Adapter`만 사용한다.
3. 조회와 명령을 분리한다. 모든 명령에는 `command_id`, 사용자 의도, 대상 계정·거래소, 설정/전략 버전, 멱등성 키와 감사 결과가 있어야 한다.
4. 보존된 v3.9.0.10 CustomTkinter 클라이언트와 새 UI가 별도 설정·포지션·전략 저장소를 만들지 않는다. 전환 기간에도 원본 상태는 하나다.
5. 새 UI가 health/parity gate에 실패하면 실행 중 bundle 내부에서 레거시 UI를 불러오지 않고, 설치 관리자가 보존된 직전 승인 버전으로 원자적으로 되돌려야 한다.
6. 원격 SaaS에서 로컬 LIVE 주문을 직접 제어하는 기능은 초기 전환 범위가 아니다. 초기 SaaS는 설명·설정 초안·읽기 전용 동기화부터 시작한다.
7. CustomTkinter는 v3.9.1.0 Web bundle과 sidecar에서 제외한다. 다만 직전 v3.9.0.10 설치본·소스 백업은 외부 동등성 게이트가 끝날 때까지 독립 롤백 자산으로 보존한다.

### 기술 판단 근거

- [Qt for Python 공식 문서](https://doc.qt.io/qtforpython-6/) — PySide6는 Qt 6의 공식 Python 바인딩이다.
- [Qt Model/View 공식 문서](https://doc.qt.io/qt-6/model-view-programming.html) — 화면과 데이터 모델 분리, 여러 view 동기화에 적합하다.
- [Qt ActiveQt 공식 문서](https://doc.qt.io/qt-6/activeqt-index.html) — Windows COM/ActiveX 위젯 경계의 근거다.
- [Electron 공식 문서](https://www.electronjs.org/docs/latest/) — Chromium과 Node.js를 묶어 동일 웹 화면을 데스크톱 앱으로 제공한다.
- [Tauri 공식 문서](https://v2.tauri.app/start/) — 시스템 WebView와 Rust host를 사용하며 작은 배포 크기가 장점이지만 플랫폼 WebView·sidecar 운영 검증이 필요하다.
- [TradingView Desktop 공식 안내](https://www.tradingview.com/support/solutions/43000671618-what-is-tradingview-desktop/) — 웹 플랫폼과 데스크톱의 기능·경험을 맞추는 제품 방향을 확인할 수 있다. 공식 문서가 내부 데스크톱 프레임워크를 공개하지 않으므로 NoahAI 문서에서 특정 구현을 단정하지 않는다.
- [TradingView Lightweight Charts 공식 저장소](https://github.com/tradingview/lightweight-charts) — Apache-2.0 기반 HTML5 금융 차트와 확장 플러그인을 제공하며 NOTICE/attribution 의무를 지킨다.
- [TradingView Advanced Charts 공식 안내](https://www.tradingview.com/charting-library-docs/latest/introduction/) — 고급 지표·드로잉을 제공하지만 비공개·paywall 환경은 별도 라이선스 검토가 필요하고 시장 데이터는 제품이 제공해야 한다.
- [Binance 공식 WebSocket 문서](https://developers.binance.com/en/docs/introduction) — 공식 market stream과 API만 사용하고 문서화되지 않은 동작에 의존하지 않는다.

### 차트·전략 허브 확장 경계

- `trading/exchanges/venue_capabilities.py`의 버전 관리 기관·기능 등록부가 Strategy Studio와 daltrading 탐색 범위의 정본이다. `scripts/export_strategy_venue_registry.py`가 Web UI TypeScript와 daltrading JSON 산출물을 생성하고 `--check`가 드리프트를 차단한다.
- 허브 탐색은 거래소별 고정 카테고리를 만들지 않고 자산군·상품 유형·기관·시장국면·증거 단계 필터를 독립 구성한다. 전략 실행 대상도 같은 등록부의 capability에서 `전체 호환 기관` 또는 개별 기관으로 생성한다.
- 새 기관은 등록만으로 LIVE가 되지 않는다. PAPER·LIVE 지원, 주문 단위, SHORT·레버리지, 비용, 체결 대조, 멱등성 및 승인된 소액 LIVE를 포함한 온보딩 상태가 `live_ready`인 경우만 LIVE/E5 배지를 허용한다.
- `.noahstrategy`에는 개인 상세 거래를 넣지 않고 정확한 전략 버전의 제한된 기관·통화별 집계 여권만 포함한다. E0은 성과 없음, E1은 제작자 로컬·서버 미확인, E2~E5는 서버 서명·계정 연동·기관 확인 단계다. 모든 기관·통화·PAPER/LIVE 성과는 별도로 표시한다.

- Web chart는 `MarketDataService`가 정규화한 과거 snapshot과 versioned realtime event만 소비한다. 화면별로 거래소 REST/WebSocket 연결을 새로 만들지 않는다.
- 차트 마커는 임의 UI 좌표가 아니라 `strategy_version + command_id + order_id + fill_id`에 연결해 XAI·체결 감사와 같은 사실을 표시한다.
- 가격·지표·포지션·PAPER/LIVE·비용의 계산 원본은 Python 엔진이다. JavaScript는 표현과 사용자 상호작용을 담당하고 주문/손익 정본을 다시 계산하지 않는다.
- 전략 랭킹은 daltrading의 서버 검증 계층이며 로컬 실행 엔진과 분리한다. 랭킹 장애가 로컬 보유 포지션·주문·전략 실행에 영향을 주지 않아야 한다.
- private 전략 원문·API 자격증명·개인 계좌 데이터는 공개 동의와 최소화 계약 없이 랭킹 서버로 보내지 않는다.

## 🚀 최신 버전 정보

**현재 소스·문서 기준**: v3.9.1.0 (2026-08-14)  
**배포 상태**: `pending_windows_rebuild`; Windows bundle·SHA·설치/업데이트/롤백 시험 전에는 배포 완료로 보지 않음  

**v3.9.0.5 계좌 상태·소스 정합**:

- `ui.controllers.account_state_controller`가 현물 보유자산과 선물 포지션, PAPER 가상 포지션, 정상 빈 상태와 조회 실패를 서로 다른 계약으로 정규화한다.
- PAPER 표시는 Binance `paper_active_positions`과 통합 거래소 `paper_positions`만 사용하며 실계정 저장소·실잔고를 혼합하지 않는다.
- 대시보드는 Upbit·Bithumb에서 계좌 잔고 캐시를 사용해 양수 보유자산을 표시하고, 선물 거래소에서만 포지션 API를 사용한다.
- 활성 소스 구문·금지 변형·대시보드 정의 전용 메서드·격리 해시·증권 계약·필수 문서는 `scripts/active_source_audit.py`로 검증한다.
- 미사용/손상/레거시 소스는 활성 패키지 밖에 보존하고 `config/source_quarantine_manifest.json`을 복원 정본으로 사용한다.

**v3.9.0.5 증권 실행 정본**:

- 키움 `openapi_plus/pykiwoom`, 신한 `partner_rest/shinhan_openapi_v2`, 미래에셋 `partner_rest/mirae_partner_profile`, 한국투자 `rest/kis_openapi_v1`
- 구 API 선택지는 설정 로드 시 정본으로 이전하며, 신한에 잘못 연결된 LS XingAPI 계정은 신한 활성/LIVE만 안전하게 해제한다.
- 실행 모드는 `PAPER 우선 → (NOT PAPER AND 전역 LIVE AND 증권사 LIVE AND 어댑터 준비 AND 주문 가드레일)일 때만 LIVE → 그 외 LEARNING`이다.
- 소스 계약과 회귀는 완료됐지만 Windows EXE·키움 OCX·증권사 실계정 주문은 배포 후 검증 대상이다.
- 세부 계약은 `docs/STOCK_BROKER_CONTRACTS_v3.9.0.5.md`를 정본으로 사용한다.

**v3.9.0.2 신규 구조**: AI 커스텀 시장국면 추천과 NoahAI 어시스턴트 안전 작업 경계

**v3.9.0.7 IP 라이선스·레퍼럴 UID 귀속 권한 구조 (2026-08-05)**:

```text
daltrading 관리자 설정
  ├─ 회원등급: referral / pro_coin / pro_stock / premium
  ├─ 레퍼럴 거래소: Binance / Bybit / OKX / Bitget
  ├─ 거래소별 활성 여부·공식 HTTPS 가입 URL·레퍼럴 코드
  └─ 사용자별 암호화 UID + pending / verified / rejected / expired
              ↓ 로그인 + 1분 상태 확인
membership_policy (allowed_exchanges = 전역 활성 ∩ 사용자별 verified)
              ↓
NoahAI Client
  ├─ token.json은 캐시이며 서버 응답이 원본
  ├─ 미승인 API 입력·연결 확인·분석/실주문 선택 비활성화
  ├─ 거래소 시작 직전 실행 게이트 재확인
  ├─ 정책 축소 시 신규 주문 루프 정지, 열린 포지션 유지
  └─ 인증된 exchange_runtime_snapshot 전송
              ↓
daltrading KPI
  └─ 사용자별 최신 스냅샷 1건으로 동시 실행 1~6개 분포
```

- 레퍼럴 코드는 배포 클라이언트에 넣지 않고 서버 DB에서 관리한다.
- 신규 서버의 네 거래소는 기본 비활성으로 시작하고 관리자가 제휴 승인·코드·URL 확인 후 활성화한다.
- daltrading JWT는 환경변수 또는 권한 600 서버 로컬 랜덤 비밀파일을 사용하며 관리자 변경은 JWT와 DB의 현재 관리자 상태를 함께 검증한다.
- 레퍼럴 정책이 누락·변조되면 거래소 실행은 fail-closed 한다.
- UI 비활성화는 안내 계층이고 실제 강제 지점은 설정 정리와 거래소 시작 직전 실행 게이트다.
- 주문은 사용자 PC에서 거래소 API로 직접 전달된다. 공식 클라이언트의 일반적인 로컬 설정 조작은 막지만 재작성된 바이너리까지 서버가 절대 차단한다고 표현하지 않는다. 완전한 서버 최종 차단은 주문 프록시·원격 증명·서명된 단기 실행권한 중 별도 아키텍처가 필요하다.
- 사용자가 제출한 UID는 서버에서 암호화되고 운영자가 Affiliate Portal과 대사해 `verified`로 승인한다. Affiliate 공식 API 자동 대사와 UID-API Key 소유 계정의 기계적 일치 검증은 후속 보강 대상이다.

**v3.9.0.2 UI 후속 구조 (2026-07-27)**:

- 본문은 한 개의 주 스크롤 소유자만 둔다. 거래 통계는 고정 본문 안에서 코인별 표만 스크롤해 중첩 스크롤과 빈 공간을 막는다.
- 최상위 기능 탭은 공통 고정 스킨을 사용하고, 거래소·증권사 운영 소스 탭만 서비스별 보조 강조색과 테두리로 구분한다.
- `utils.fixed_colors.build_widget_palette`가 기능 탭의 `content_bg → card → card_alt/input → border` 시각 계층을 만든다. `MarketTrendWidget`, `AILearningWidget`, `AIAssistantWidget`은 생성 시 이 팔레트를 받아 블록체인·주식/증권에서 동일하게 렌더링한다.
- 공용 `AIReportWidget`과 안전 대체 위젯도 생성 지점에서 같은 팔레트를 받으며, 주식 거래 통계·생활금융 월간 재무 요약은 동일 카드 계층을 명시적으로 사용한다.
- AI 어시스턴트의 모델 선택·실행 상태는 내부 설정으로 유지하되 서비스별 대화 화면에는 모델명을 상시 노출하지 않는다.
- 기능 위젯이 CustomTkinter 기본색이나 개별 레거시 색으로 되돌아가지 않도록 대시보드 생성 지점에서 `_FIXED_COLORS`를 명시적으로 전달한다.
- 금융 인텔리전스와 생활금융의 내부 탭도 `ui.visual_system.style_tabview`의 공통 글꼴·높이·선택 대비를 사용한다.
- 금융 인텔리전스 각 기능은 화면 안의 초보자 절차와 컨텍스트형 AI 도움말을 함께 제공한다. AI API가 없으면 로컬 제품 도움말이 역할·입력·결과·주문 경계를 답한다.
- `코인 정보`는 계좌/선택 자산 운용 컨텍스트, `코인 탐색`은 시장 후보 검색으로 도메인을 분리한다.
- 거래 통계·AI 리포트 운용 지표는 사용자별 로컬 `trade_log`를 공통 원천으로 사용한다. 체결금액은 기록된 체결가×체결수량을 `USDT`·`KRW` 등 결제통화별로 분리하고, 평균 보유시간은 `exit_time > entry_time`인 청산만 포함한다.
- 동일 시각으로 생성된 구형·모의 스냅샷과 시각 누락 기록은 평균에 포함하지 않는다. 유효 청산이 없으면 UI는 `0분`을 만들지 않고 `수집 대기`와 유효 건수를 표시한다.
- 실행 스냅샷은 시작·중지와 1분 상태 확인 성공 시 전송한다. 서버는 1일·7일·30일·90일 각각에서 사용자별 최신 한 건만 선택해 0개~6개·7개 이상 분포를 계산한다.
- KRW 거래량은 Upbit·Bithumb의 학습·AI 판단이 아니라 실제 `trade_order_executed`의 결제금액이다. CCXT 시장가 응답은 `average·filled·cost`를 우선 정규화하고 체결 가격이 없을 때만 주문 시점 시세를 보조값으로 사용한다.

```text
영상·문서·Pine·텍스트
  → strategy_source_ingestor: 근거·규칙·명시 국면·제외 문맥
  → custom_strategy_widget: XAI·추천 범위·누락 조건·사용자 검토
  → custom_strategy_pipeline: 버전·승인·미지원 조건 fail-closed
  → custom_strategy_validator: 동일 지표·비중첩 포지션·양방향 비용 재생
  → declarative_strategy_engine: 허용 필드/연산자·직전/현재 교차만 평가
  → Trader/UnifiedTrader: 선택 전략 버전·코인 명시 청산 보존
  → 기존 전략·수익성·리스크·주문 가드레일·거래소 체결

사용자 대화
  → 의도 확인·모호한 요청 재질문
  → SETTINGS_ACTION_REGISTRY: 허용 설정·user_confirm
  → 저장 후 재조회·불일치 롤백·사용자별 감사로그
  → PROTECTED_ACTION_REGISTRY: 주문/거래상태/API/출금 미실행
```

- 소스에 명시된 국면은 적용 범위 후보로 추천하며 현재 시장 판정으로 오인하지 않는다.
- 국면 근거가 없으면 전체 범위를 자동 확정하지 않고 사용자 확인을 유지한다.
- 어시스턴트는 화면과 분석 결과를 설명하고 모호한 설정 요청을 재질문한다.
- 실제 변경은 타입형 허용 작업, 현재값 조회, 변경 미리보기, 사용자 확인, 저장 후 재검증을 거친다.
- v3.9.0.2에서는 일부 설정만 이 계약으로 변경한다. 주문·거래 시작/정지·API 키·출금은 보호 작업으로 분류하며 대화 실행 대상이 아니다.
- 설정 감사 이력은 로그인 사용자별 앱 데이터에 분리하고 API 키·전체 설정 스냅샷을 기록하지 않는다.
- AI 애널리스트와 자동검증·코인 런타임은 SMA/EMA 20·50·200, ADX, ATR 등 동일 지표 계산을 공유한다.

**v3.9.0.1 구조**: 금융 인텔리전스 확장

금융 인텔리전스 모듈 경계:

```text
외부/운영 데이터
  ├─ Yahoo Finance / Binance 공개 시세
  ├─ SEC Companyfacts / OpenDART
  ├─ 중앙 뉴스·일정·거시·기관 데이터 공급자
  └─ 기존 포지션·거래 기록
          ↓
trading/financial_intelligence
  ├─ models.py / taxonomy.py          공통 데이터 계약·분류
  ├─ providers.py / market_data.py    공급자·시세 정규화
  ├─ event_calendar.py / news_pipeline.py / narrative_engine.py
  ├─ fundamentals.py / valuation.py / screener.py / technical.py
  ├─ performance.py / backtest.py
  ├─ macro.py / institutional.py
  └─ store.py / service.py            SQLite 재현 기록·공통 파사드
          ↓
ui/widgets/financial_intelligence_widget.py
  ├─ 블록체인        시장·스크리너·지표·백테스트·이벤트
  ├─ 주식/증권       시장·재무·가치·스크리너·지표·백테스트·기관
  ├─ 자산 통합       성과·위험
  └─ AI애널리스트    글로벌 시장·이벤트·뉴스·내러티브·산업·거시
```

경계 원칙:

- 일반 사용자 UI는 JSON·파일 경로·API 키를 받지 않는다. 시장/종목 선택과 숫자 입력만 제공한다.
- 공개 가격·기술지표·백테스트는 클라이언트가 직접 조회·계산할 수 있다.
- 라이선스·자격증명·비밀키·일관된 갱신이 필요한 뉴스·일정·공시·기관·거시 데이터는 중앙/운영 설정에서 공급한다.
- 외부 수치는 출처·기준시각·지연 여부와 함께 저장하며, 실패 시 생성형 AI가 보충하지 않는다.
- UI는 Tk 입력을 UI 스레드에서 캡처하고 네트워크·계산·SQLite 기록만 작업 스레드에서 수행한다.
- `fi_records`, `fi_feature_status`, `fi_analysis_runs`는 기존 사용자 DB에 별도 네임스페이스로 공존한다.
- 분석 결과는 직접 주문 신호를 발행하지 않고 기존 가드레일을 자동 변경하거나 우회하지 않는다.
- SEC·DART·기관 데이터는 공급자 정책과 자격증명을 충족한 경우에만 라이브 호출한다.
- 기능 상태와 운영 검증 정본은 `docs/FINANCIAL_INTELLIGENCE_TEST_CHECKLIST_20260723.md`다.
- 대시보드 하단 업데이트 카드는 `config/app_version.py`의 버전·핵심 문구를 표시하고 인앱 금융 인텔리전스 사용법으로 연결한다.
- CustomTkinter의 운영체제 기본 컬러 이모지는 macOS/Windows에서 동일 렌더링을 보장하지 못하므로 사용자 UI 메뉴·버튼·상태는 텍스트 표기를 기준으로 한다.
- 생활금융 `data/finance_products`는 사용자 데이터와 분리된 읽기 전용 기본 비교 데이터로 빌드에 포함한다. 누락·손상 시 코드 내 예비 데이터로 폴백하며, 최신 실상품 연동은 중앙 공급자 경계에 둔다.

3.9.0.2 AI 커스텀 현행 정본:
- `docs/V38929_IMPLEMENTATION_RECORD_20260719.md`
- `docs/AI_CUSTOM_STRATEGY_ARCHITECTURE.md`

거래소별 시장 데이터/선택/PnL 임계값은 분리되고, 신규 사용자 데이터 부족은 최소단위 제한 운용으로 학습한다. AI 커스텀 소스 추출은 별도 ingestor에서 수행하고 승인·자동 과거재생·가드레일 상태머신을 거친다. `custom_strategy_runtime`이 저장 단위와 주문 단위를 변환하고, 선언형 엔진의 confirm/independent 결과가 Trader/UnifiedTrader/주식 자동매매 경로로 전달된다.

AI 커스텀 선언형 엔진은 SMA/EMA 20·50·200, ADX, ATR, MACD 세부값, 볼린저, 거래량·UTC 시간/요일과 직전·현재 캔들 기반 교차 연산을 허용하며 미지원 조건은 승인 전에 차단한다. 자동검증은 비중첩 단일 포지션과 양쪽 수수료·슬리피지·스프레드를 사용한다. 코인 명시 청산 규칙은 진입 당시 전략 버전과 함께 `Position`에 보존되어 Binance/Unified 모니터에서 평가된다. 주식/ETF는 현재 선언형 진입·신호 임계값까지만 공통 범위다.

전략 엔진의 시장국면 결과는 UTC 판단 시각, 신뢰도, 모멘텀 근거, 현재/후보 국면과 확인 횟수를 포함한다. 원본 시각이 있는 오래된 입력은 차단하며, 최초 판정과 고변동 진입은 즉시 반영하고 일반 국면 전환은 연속 확인하는 히스테리시스를 적용한다.

3.9.0.2 문서 정합 기준:
- 기능 상태값 표준은 `docs/UPDATE_PLAN.md`의 2026-07-19 매트릭스를 단일 기준으로 사용한다.
- 본 문서는 모듈 책임/경계 중심이며, 기능 제공 상태(`현재 제공/제한 제공/업데이트 예정/개발 중`) 판정은 UPDATE_PLAN 우선이다.
**이전 기준**: v3.8.9.9 (2025-12-27), v3.8.8.3 (2025-10-20)

> **버전 정합성**: 배포 앱의 **인앱 메뉴얼 창 제목**과 `CHANGELOG.md`가 **더 최신 패치 버전**(예: v3.8.9.x)을 가리킬 수 있습니다. 모듈 구조·책임 경계는 본 문서를 따르되, **세부 변경 목록은 CHANGELOG**를 우선하세요. 문서 동기화 규칙은 `DOCUMENTATION_POLICY.md` 참고.
>
> 참고: 2025-10-29 기준 UI는 단일 고정 스킨으로 전환되어 테마 시스템은 사용하지 않습니다. 과거 기록은 `archive/history/HISTORICAL_THEME_BASELINE.md`를 참고하세요.

## 2026-06-05 패치 기준선 (v3.8.9.21)

- 전역 전체시작 경로 제거 및 거래소별 개별 실행 UX로 정렬
- 다중 거래소 안정화: 거래소별 코인/상태 오염 방지, 시작 실패 상태 동기화 강화
- 로그 태깅 정합화: 거래소 루프/분석 로그에 거래소 식별값 명시
- 현물 어댑터 호환 경로 보강 및 안정성 점검 스크립트 정책 동기화

## 2026-07-10 패치 기준선 (v3.8.9.28 코인 우선 1단계 정합)

- 코인 우선 흡수 계층 고정
  - 1단계 범위를 코인 선택/진입/리스크/학습/로그 경로로 고정하고, 타 자산 확장은 동일 게이트 재사용 정책으로 분리
- 모듈 책임 경계 명시
  - `trading/evaluator.py`: 코인 선정 책임(목표 달성 시 즉시 반환)
  - `trading/trader.py`, `trading/unified_trader.py`: 거래소별 실행 책임(경로 혼재 금지)
  - `trading/risk_manager.py`, `trading/exchange_learning_manager.py`: 리스크/학습 임계값 및 자동조정 책임
  - `log_system/log_adapter.py`: 중복 억제/요약/비차단 기록 책임
- 가드레일/롤백/게이트 기준 고정
  - timezone 혼용 오류 0건
  - fallback 재진입 0건
  - 중복 로그 폭주 0건
  - 필수 회귀(`test_evaluator_selection_flow`, `test_exchange_learning_manager`, `test_auto_update_manager`) 통과

## 2026-06-17 패치 기준선 (v3.8.9.22)

- 사용자 안내 자동화 강화(지원요약/3분 점검본/즉시 조치 순서)
- SaaS 문서 기준선 정합화(증권 SaaS 4대 판단 기준 반영)
- 빌드/배포 문서와 증권 어댑터 hidden import 기준 동기화

## 2026-07-04 패치 기준선 (v3.8.9.27 시작/정지 응답성 근본 패치)

- 거래소 시작/정지 UI 비동기화
  - 거래소 토글 요청을 백그라운드 작업으로 분리해 UI 스레드 블로킹 제거
  - 처리 중 중복 토글 방지 및 상태 배지(`Starting...`/`Stopping...`) 즉시 반영
- Unified 계층 지연 초기화
  - UnifiedTradingManager를 lazy connect 모드로 전환해 로그인 직후 다중 거래소 동시 연결 제거
  - UnifiedTrader도 시작 대상 거래소만 초기화하도록 변경
- API 신호 수집 초기 동기 호출 제거
  - API 신호 관리 시작 시 동기 1회 수집을 제거해 초기 진입 체감 지연 완화

## 2026-07-01 패치 기준선 (v3.8.9.26 유지보수)

- Unified 포트폴리오 할당 자산분류 정합화
  - `upbit`/`bithumb` 자산군을 `crypto`로 고정하여 자산군 분류 일관성 강화
- 거래소별 학습 필터 정합화
  - RiskManager 이력에 `exchange` 태그 저장 경로 추가
  - Binance/Unified 청산 경로 모두 RiskManager 이력 저장 반영
  - Unified 자동조정에서 메모리 이력 부족 시 Recorder DB 이력 보강
- 로그 중복 포맷 재발 방지
  - `log_adapter`에서 선행 시간/레벨 프리픽스 제거 가드 추가

## 2026-05-29 패치 기준선 (v3.8.9.20)

- 실시간 청산 판단 `net_pnl_percent` 산식을 recorder 기준(화폐단위 순손익 환산)으로 정렬
- 릴리즈노트/거래흐름/사용자가이드/인앱 업데이트 공지 동기화
- 이번 패치는 판단-기록 정합화이며, RR/사이징/집중도 가드는 별도 최적화 과제로 분리

## 2026-05-07 패치 기준선 (v3.8.9.19)

- 대시보드 전수 버튼/탭 E2E 테스트 신규 추가: `tests/test_dashboard_full_button_e2e.py` 44 passed
- 핵심 묶음 회귀 재검증: 102 passed (`test_dashboard_full_button_e2e` + `test_menu_regression` + `test_service_tab_policy_snapshot` + `test_settings_backup`)
- 증권 브로커 연결 검증 도구 추가: `scripts/verify_stock_broker_connection.py` (당시 `--all_brokers` Mock 기준 kiwoom/shinhan/miraeAsset 18/18 OK; 실계정 증거가 아님)
- 설정 자동 백업/복구 흐름 고도화: 저장 전 백업(retention 3), 백업 목록 복구 UI 연동
- 최신 전체 회귀 기준: 864 passed, 6 skipped

## 2026-05-03 패치 기준선 (v3.8.9.18)

- 전략 초기화 경로 안정화: 기본값 복구/초기화 시 민감 설정(API 키·브로커 인증정보·backend_url) 보존
- 키움 연결 장애 진단 강화: QAxWidget 관련 사용자 안내에 원본 예외 포함
- 배포 준비 검증(당시 기준): 전체 회귀 336 passed, 6 skipped / prekey 게이트(TEST_STOCK 140 passed, 6 skipped)

## 2026-04-30 운영 기준선 (증권/거래 공통)

현재 운영 전환은 다음 3단계 게이트로 고정한다.

1. 키 입력 전 완료(`prekey`)

- `python scripts/release_gate.py --profile prekey`
- 목적: 키 없이 완료 가능한 코드/정책/문서/진단 항목을 먼저 닫는다.

1. 키 입력 당일 원샷(`key-day`)

- `python scripts/stock_keyday_one_shot.py`
- 목적: 설정/권한/환경이 준비된 상태에서 실브로커 readiness를 단일 명령으로 최종 판정한다.

1. 배포 직전 엄격 검증(`release`)

- `python scripts/release_gate.py --profile release`
- 목적: 배포 차단 조건을 모두 통과해야만 운영 배포를 허용한다.

위 기준은 "수익 보장"이 아니라 "안전한 실행 가능 경로"를 검증하는 구조다.
판단 품질 개선(백테스트/레짐/슬리피지 최적화 등)은 후속 고도화 트랙으로 분리해 관리한다.

## 📌 문서의 범위와 책임 정의

본 문서는 NoahAI Client(v3.8.x)의 구현 상세를 설명하기 이전에,
이 시스템이 무엇을 책임지고 무엇을 책임지지 않는지를 명확히 정의한다.

NoahAI는 금융상품을 판매하거나, 수익을 보장하거나,
**브로커·당사자 계약의 상대**가 아니다.

클라이언트는 사용자가 연결한 API 키와 설정 범위 안에서 **주문 요청을 전송**할 수 있으나,
**체결·잔고 확정·수수료·강제청산**은 항상 외부 거래소·증권사 규칙과 사용자 계약이 담당한다.

NoahAI의 역할은 다음으로 한정된다.

- 시장·계정·목표 정보를 종합하여 **판단 환경을 구조화**
- 판단 근거, 리스크, 대안 시나리오를 **기록·설명·비교**
- 모든 판단과 결과를 **검증·재현·환류 가능한 로그로 관리**
- 시간이 지날수록 더 신중해지도록 **의사결정 파이프라인을 고도화**

**주문 요청 전송**은 클라이언트가 외부 API를 호출해 수행할 수 있으나,
**체결·예탁·최종 계좌 상태**는 외부 거래소·증권사·금융기관 시스템이 확정한다.

이 문서는 특정 자산군이나 거래소 구현이 아니라,
자산군이 바뀌어도 유지되는 **AI 자산 의사결정 인프라의 구조**를 설명하는 문서다.

## 도메인 분류 체계 (2026-04-25)

아키텍처 설계와 UI/문서 명명은 아래 도메인 기준을 공통 적용한다.

- **Asset Decision Domain**: 암호화폐, 주식/증권, ETF 등 자산군 의사결정
- **Life Finance Domain**: 대출 비교, 보험 선택, 예적금/채권 비교, 개인 재무관리
- **Risk Protection Domain**: 금융사기 탐지, 이상거래 탐지, 고위험 선택 회피 보조
- **Accessibility Domain**: 고령층/디지털 약자 지원, 쉬운 용어·음성 기반 보조
- **Assistant Interface Layer**: 대화형 설명/비교/경고 인터페이스, 질의응답 허브

위 분류는 메뉴 이름보다 우선하는 상위 설계 기준이며,
`글로벌자산` 같은 포괄 명칭 대신 목적 기반 명칭(`자산 통합`, `글로벌 금융 인사이트`)을 우선한다.

이 정의는 이후 등장하는 모든 모듈, 거래소, 증권사, 자산군 설명에
우선 적용되는 최상위 원칙이다.
아래의 어떤 기술 구현도 이 책임 경계를 침범하지 않는다.

## 🚀 v3.8.9.11 주요 변경사항 (2026-01-25)

### TP/SL -2021 오류 근본 수정

- **문제**: GALA, JASMY 등 저가 알트코인에서 TP 주문 실패 (`-2021: Order would immediately trigger`)
- **근본 원인**:
  1. `trader.py`: 키 이름 불일치 (`price_precision` vs `pricePrecision`)로 `price_prec`가 항상 2로 고정
  2. `binance_client.py`: TP 방향 검증 누락 (SHORT 포지션에서 TP > 현재가인 경우 감지 못함)
- **수정 내용**:
  - 키 이름 호환성 처리 (`pricePrecision` 또는 `price_precision` 둘 다 지원)
  - 저가 코인 자동 감지 및 정밀도 강제 조정 (0.001~0.02 범위)
  - TP 방향 검증 추가 (LONG/SHORT 포지션별 올바른 방향 확인)
- **효과**: 모든 저가 알트코인에서 정확한 TP/SL 가격 계산 및 주문 성공

### AI 자산 의사결정 인프라 확장 (진행 중)

- ETF/주식 판단 인프라 확장: 자산 해석·비교·리스크 설명 UI 기본 구조 완료 (2026-01-18)
- StockExchange 인터페이스: 자산군별 판단 로직을 연결하기 위한 표준 판단 인터페이스
- 키움증권 어댑터: 증권사 API와의 집행 연동 계층
- 대시보드 확장: 암호화폐 / ETF / 주식 자산군에 동일한 판단·기록 UX 적용

판단·설명·기록·환류는 NoahAI가 담당하며,
주문·체결·자금 이동은 항상 외부 증권사·거래소 API가 수행한다.

## 🚀 v3.8.8.9 주요 아키텍처 변경사항 (2025-10-29)

## 🚀 v3.8.8.3 주요 아키텍처 변경사항 (2025-10-20)

### 바이낸스 자체 API 전환 완료

- **이전**: CCXT + `binance_extended_api.py` + `legacy_binance_adapter.py` 혼재
- **현재**: `api/binance_client.py` 단일 통합 클라이언트
- **장점**: 성능 향상, 안정성 증대, 유지보수성 개선

### 제거된 중복 파일들

- `trading/binance_extended_api.py` → `api/binance_client.py`로 통합
- `trading/legacy_binance_adapter.py` → CCXT 브리지 불필요

### 새로운 기능

- **동적 코인 재선택**: 1시간마다 시장 상황 분석 후 코인 재선택
- **최적화된 WebSocket**: 포지션 모니터링 전용, API 기반 분석으로 성능 향상
- **통합된 고급 API**: 미체결약정, 롱/숏 비율, 테이커 비율 등
- **WebSocket 아키텍처 개선**: 46초 지연 문제 해결, 즉시 시작 가능
- **AI 학습 데이터 시스템**: 모든 거래 신호 자동 수집 및 패턴 분석
- **실시간 로그 시스템**: 사용자 가시성을 위한 카테고리별 로그 분류

## 🏗️ 전체 시스템 구조

### 📁 프로젝트 구조

```text
noahai_client/
├── main.py                 # 메인 애플리케이션 진입점
├── ui/                     # 사용자 인터페이스
│   ├── dashboard_modern.py  # 전환기 fallback 대시보드 (CustomTkinter)
│   ├── login_modern.py      # 전환기 fallback 로그인 (CustomTkinter)
│   └── settings_modern.py   # 전환기 fallback 설정 (CustomTkinter)
├── trading/               # 거래 로직
│   ├── trader.py          # 메인 거래 엔진 (Binance 전용 - 자체 API)
│   ├── unified_trader.py  # 통합 거래 엔진 (CCXT 거래소 전용)
│   ├── evaluator.py       # 코인 선택 엔진 (AI 기반 과학적 평가)
│   ├── exchange_manager.py # 거래소 관리자 (v3.3 신규)
│   ├── unified_trading_manager.py # 통합 거래 관리자 (CCXT 거래소용)
│   ├── api_signal_manager.py # API 신호 관리자 (v3.3 신규)
│   ├── ai/                # AI 모듈
│   │   ├── ai_manager.py  # AI 관리자
│   │   ├── auto_optimizer.py # 자동 최적화
│   │   └── openai_client.py # OpenAI 클라이언트
│   ├── exchanges/         # 거래소 모듈 (v3.3 확장)
│   │   ├── base_exchange.py # 기본 거래소 클래스
│   │   ├── exchange_factory.py # 거래소 팩토리
│   │   ├── exchange_manager.py # 거래소 관리자
│   │   ├── interfaces/    # 거래소 인터페이스
│   │   │   ├── exchange_interface.py
│   │   │   ├── futures_exchange.py
│   │   │   ├── spot_exchange.py
│   │   │   └── stock_exchange.py         # 증권 거래 인터페이스 (v3.8.9.11+)
│   │   └── adapters/      # 실제 사용되는 거래소 어댑터들
│   │       ├── binance_futures_adapter.py # 바이낸스 선물
│   │       ├── bybit_futures_adapter.py  # 바이비트 선물
│   │       ├── okx_futures_adapter.py    # OKX 선물
│   │       ├── bitget_futures_adapter.py # 비트겟 선물
│   │       ├── bithumb_spot_adapter.py   # 빗썸 현물
│   │       ├── upbit_spot_adapter.py     # 업비트 현물
│   │       └── kiwoom_stock_adapter.py   # 키움증권 주식/ETF (v3.8.9.11+)
│   └── recorder.py        # 거래 기록 관리
├── api/                   # API 연동
│   ├── backend_api.py     # 백엔드 서버 연동
│   └── binance_client.py  # 바이낸스 API 클라이언트 (WebSocket API 명칭 통일)
├── config/                # 설정 파일
│   ├── settings.json      # 메인 설정
│   ├── settings_template.json # 설정 템플릿
│   └── token.json         # 사용자 토큰
└── data/                  # 데이터 저장소
    ├── trading.db         # 거래 데이터베이스
    └── logs/              # 로그 파일
```

## 🔄 시스템 워크플로우

### 1. 애플리케이션 시작 (v3.8 개선)

```text
main.py → 로그인 → 거래소 선택 → API 키 설정 → 대시보드 초기화 → 판단·기록·검증 파이프라인 시작
```

### 2. 거래 실행 플로우 (거래소별 분리 - 혼재 금지)

```text
🔥 바이낸스 전용 경로:
main.py.trading_loop() → AI 분석 → trader.py.execute_trades() → api/binance_client.py → 바이낸스 API

🔥 CCXT 거래소 전용 경로:
main.py._start_unified_trading() → unified_trader.start_trading() → CCXT 어댑터 → 각 거래소 API

❌ 절대 금지: unified_trader.py에서 바이낸스 처리
❌ 절대 금지: trader.py에서 CCXT 거래소 처리
❌ 절대 금지: 바이낸스에서 unified_trader.py 호출
❌ 절대 금지: CCXT 거래소에서 trader.py 호출
```

### 3. 멀티 거래소 관리 (v3.3 → v3.8 고도화)

```text
거래소 선택 → ExchangeManager → 거래소별 클라이언트 생성 → 통합 관리
```

### 3. 사용자 상태 관리

```text
로그인 → 토큰 저장 → 서버 상태 체크 → 중복 실행 방지
```

## 🧩 핵심 모듈

### 🤖 AI 시스템

- **AIManager**: AI 신호 생성 및 분석
- **AutoOptimizer**: 실시간 파라미터 최적화
- **OpenAIClient**: OpenAI API 연동

### 💱 거래소 시스템 (중요: 혼재 금지 가이드라인)

- **Binance 전용**: `trader.py` + `api/binance_client.py` (python-binance)
  - **절대 금지**: `unified_trader.py`에서 바이낸스 처리
  - **특징**: 고성능 실시간 거래, WebSocket, 고급 주문 타입, Binance Algo Order API
  - **TP/SL**: Binance Algo Order API 사용 (v3.8.9.9+), 가격 정밀도 자동 조정 (v3.8.9.11+)
  - **시작/정지**: `main.py.start_trading_loop()` / `main.py.stop_trading_loop()`
- **CCXT 거래소**: `unified_trader.py` + `trading/exchanges/adapters/` (CCXT 라이브러리)
  - **대상**: Bybit, OKX, Bitget, Upbit, Bithumb
  - **특징**: 표준화된 API, 크로스 플랫폼 호환성
  - **시작/정지**: `unified_trader.start_trading(exchange)` / `unified_trader.stop_trading(exchange)`
- **증권/ETF 거래소** (v3.8.9.11+): `StockExchange` 인터페이스 + 증권사 어댑터
  - **책임 분리**: 판단·설명·기록·리스크 분석은 NoahAI 클라이언트가 담당. **주문 API 호출**은 사용자가 연결한 키로 클라이언트가 수행할 수 있으나, **계좌·체결·예탁·분쟁의 법적 1차 주체는 증권사·사용자**이다. (암호화폐 경로의 실행 연계와 같은 원칙.)
  - 연동·실행 가능 여부는 **빌드·설정·상용 공개 단계**에 따라 다르며, 인앱 「📈 증권/주식/ETF」·`CHANGELOG`가 체감 기준이다.
  - **대상**: 키움증권 (주식/ETF), 향후 확장 예정
  - **특징**: 증권사 API와의 집행 연동 계층, 주식/ETF 자산군에 대한 판단·기록 인터페이스
  - **구조**: `trading/exchanges/interfaces/stock_exchange.py` + `trading/exchanges/adapters/kiwoom_stock_adapter.py`
- **ExchangeManager**: 거래소 통합 관리 및 잔고 조회, 설정 반영/재연결
- **UnifiedTradingManager**: CCXT 거래소 통합 관리
- **APISignalManager**: 거래소별 API 신호 교환 및 학습 데이터 생성

#### 🚨 중요 가이드라인 (2025-01-15 업데이트)

1. **바이낸스는 절대 `unified_trader.py`를 사용하지 않음**
2. **CCXT 거래소들은 절대 `trader.py`를 사용하지 않음**
3. **`main.py`에서 거래소별로 올바른 경로로 라우팅**
4. **각 거래소별 어댑터는 해당 거래소만 담당**
5. **중첩이나 중복 없이 계층적 구조 유지**

### 🎛️ 레거시 v3.9.0.10 대시보드 시스템 (롤백 참고)

- **ModernDashboard**: 메인 대시보드 (CustomTkinter)
- **서비스 구조**: 블록체인(암호화폐), 주식/증권(ETF 포함), 부동산 서비스 분리
- **포지션 표시 로직**: 거래소별 분기 처리
  - **바이낸스**: `main_app.trader.active_positions` 참조
  - **CCXT 거래소**: `unified_trader.active_positions[exchange]` 참조
  - **증권사**: `stock_exchange` 인터페이스를 통한 포지션 조회 (v3.8.9.11+)
- **통계 통합**: 바이낸스 + CCXT 거래소 데이터 합산
- **UI 패턴 일관성**: 모든 서비스에서 동일한 2단 레이아웃 구조 유지
  - 좌측: 제어/잔고/포지션/통계
  - 우측: 실시간 로그

### 🎨 레거시 롤백 UI 스타일 및 고정 스킨

- **CustomTkinter 롤백 자산 + 단일 고정 스킨**: v3.9.0.10 운영 화면은 독립 롤백 설치본으로만 보존한다. v3.9.1.0 `NoahAI.exe`/`NoahAIEngine.exe`는 이를 import하거나 패키징하지 않는다.
- **고정 색상/폰트 규칙**: 주요 UI는 고정 색상 상수와 안전한 폰트 폴백을 기준으로 일관성을 유지함
- **과거 테마 시스템은 역사적 참고**: 예전 `ThemeManager` 기반 설계 흔적은 문서/백업 참고용이며, 현재 배포 기준의 핵심 구조는 아님
- **운영 원칙**: 새 위젯은 현재 고정 스킨 톤과 레이아웃 규칙을 따르되, 기능 회귀 없이 붙일 수 있어야 함

### 🔐 보안 시스템

- **UserStatusManager**: 사용자 상태 관리
- **BackendAPI**: 서버 연동 및 인증
- **TokenManager**: 토큰 관리 및 갱신

## 📊 데이터 흐름 (기술 도메인 맥락)

### 코인 선택 시스템 (evaluator.py, 도메인 예시)

```text
거래소 API → 심볼 수집 → 5가지 점수 계산 → 메이저/알트 비율 조정 → 최적 코인 선정
├── 1단계: 거래소별 심볼 수집 (바이낸스/업비트/바이비트 등)
├── 2단계: 다차원 점수 계산 (기술적/변동성/거래량/트렌드/리스크)
├── 3단계: 시장 상황별 비율 조정 (상승장/하락장/횡보장)
├── 4단계: 하이브리드 접근법 (캐싱 + 백업 + 하드코딩)
└── 5단계: 최종 코인 목록 반환
```

### 거래 데이터 (도메인 예시)

```text
시장 데이터 → AI 분석 → 거래 신호 → 거래 실행 → 결과 기록 → DB 저장
```

### 거래소별 데이터 수집 (v3.3 신규, 도메인 예시)

```text
거래소 API → ExchangeManager → 잔고/가격 조회 → 대시보드 표시
거래소 API → APISignalManager → 신호 수집 → 학습 데이터 생성
```

### 멀티 거래소 통합 관리 (도메인 예시)

```text
거래소 선택 → ExchangeFactory → 거래소별 클라이언트 생성 → 통합 인터페이스
```

## 🏛️ 기술 도메인 구조 (UI 메뉴 vs 기술 도메인)

NoahAI는 사용자가 보는 **UI 메뉴 구조**와 백엔드 **기술 도메인 구조**가 다릅니다.

### 사용자가 보는 메뉴 (UI 수준)

```text
📱 대시보드 탭
├── 🚀 암호화폐 (Blockchain/Futures)
├── 📈 주식/증권 (Stocks/Securities)
├── 🧭 자산 통합 (확정, v3.9부터)
├── 💰 생활금융 ✅ (핵심 기능 구현, v3.8.9.19)
├── 🎯 AlphaArena (LLM 기반 모드)
└── 📊 커뮤니티 (예정)
```

### 기술 도메인 구조 (시스템 수준)

#### 1. **의사결정 인터페이스 계층 (Decision Interface Layer)**

- **역할**: AI 판단 신호 생성 및 설명의 일관된 인터페이스 제공
- **구현**: `Decision`, `Recommendation` 기본 객체 정의
- **적용**: 모든 자산군(암호화폐, 주식, 부동산, 생활금융)에서 동일하게 사용

#### 2. **자산 의사결정 도메인 (Asset Decision Domain)**

- **암호화폐 (Blockchain)**
  - 기술 모듈: `trader.py`, `api/binance_client.py`, CCXT 거래소 어댑터
  - 판단 엔진: `evaluator.py` (코인 선택), `ai_manager.py` (신호 생성)
  - 기록/검증: `recorder.py`, 거래 이력 로그
  - 상태: ✅ 실제 운영 중 (6개 거래소)

- **주식/증권/ETF (Securities)**
  - 기술 모듈: `StockExchange` 인터페이스, `kiwoom_stock_adapter.py`
  - 판단 엔진: 자산 해석, 섹터 분석, 위험도 평가
  - 기록/검증: 주식 거래 로그, 포트폴리오 분석
  - 상태: 🚧 혼합 상태 (UI/기록/가드레일 구현 + Mock 검증 완료, 실API 실거래 검증 고도화 진행)

- **글로벌 금융자산 (Global Financial Assets)**
  - 기술 모듈: 부동산/국제 자산 관련 API 어댑터 (향후)
  - 판단 엔진: 자산 추적, 포트폴리오 분석
  - 상태: 📋 기획 단계 (메뉴명 "자산 통합" 확정)

#### 3. **생활금융 도메인 (Daily Life Finance Domain)** ✅ Phase F 완료 (2026-05-03)

- **대출 비교 (Loan Comparison)** ✅
  - 기술 모듈: `trading/life_finance_products.py`, `data/finance_products/loans.json` (20개)
  - 판단 엔진: 금리·수수료·약정 비교, loan_type 필터, 원리금균등 월납입액 계산
  - AI 연동: `LifeFinanceAssistant` → `COMPARE_LOAN` 인텐트
  - 상태: ✅ 구현 완료

- **보험 선택 (Insurance Selection)** ✅
  - 기술 모듈: `trading/life_finance_products.py`, `data/finance_products/insurances.json` (20개)
  - 판단 엔진: 보장 범위·보험료·기간 비교
  - 상태: ✅ 구현 완료

- **예금/적금/채권 (Deposits/Bonds)** ✅
  - 기술 모듈: `trading/life_finance_products.py`, `data/finance_products/savings.json` (20개, ISA형)
  - 판단 엔진: 이율·기간·비과세 여부 분석
  - 상태: ✅ 구현 완료

- **세무 계산 (Tax Calculation)** ✅ NEW (2026-05-03)
  - 기술 모듈: `trading/tax_calculation_service.py`
  - 판단 엔진: 연말정산·금융소득종합과세·금투세·ISA/IRP 절세 비교
  - AI 연동: TAX_SETTLEMENT / CHECK_FINANCIAL_INCOME_TAX / CALC_INVESTMENT_TAX / COMPARE_TAX_ACCOUNTS
  - 테스트: `tests/test_tax_calculation_service.py` 53 passed
  - 상태: ✅ 구현 완료

- **금융사기 탐지 (Fraud Detection)** ✅ NEW (2026-05-03)
  - 기술 모듈: `trading/fraud_detection_service.py`
  - 판단 엔진: 보이스피싱·스미싱 17개 패턴 / z-score 이상거래 / 약탈적 대출 탐지
  - AI 연동: ANALYZE_FRAUD_MESSAGE / DETECT_ABNORMAL_TX / CHECK_PREDATORY_LOAN
  - 테스트: `tests/test_fraud_detection_service.py` 32 passed
  - 상태: ✅ 구현 완료

#### 4. **위험보호 도메인 (Risk Protection Domain)**

- **거래 이상 감지 (Trade Anomaly Detection)**
  - 기술 모듈: 사용자 거래 패턴 분석기
  - 판단 엔진: 비정상 거래 자동 감지 및 경고
  - 상태: ✅ 기본 기능 운영 중

- **포지션 리스크 경고 (Position Risk Alert)**
  - 기술 모듈: 동적 손실한도 계산기, 레버리지 가드레일
  - 상태: ✅ 암호화폐/주식 상시 운영(기본 안전 디폴트 + 사용자 설정 기반 실주문)

#### 5. **접근성 도메인 (Accessibility Domain)**

- **고령층/디지털 약자 지원 (Elderly & Digital Disadvantaged)**
  - 기술 모듈: 음성 UI, 쉬운 용어 번역, 시각 보조
  - 판단 엔진: 초보자 수준의 설명 자동 생성
  - 상태: 🟡 베타 운영 (TTS 사용 가능, STT는 SpeechRecognition+PyAudio 환경에서 선택 사용)

- **다언어 지원 (Multi-language)**
  - 기술 모듈: 메뉴/상담 다국어 지원
  - 상태: 📋 로드맵

#### 6. **기록·검증·환류 도메인 (Audit & Replay Domain)**

- **판단 로그 (Decision Logging)**
  - 기술 모듈: `recorder.py`, 통합 로그 저장소
  - 구조: `판단 근거` + `신호 생성 시각` + `리스크 평가` + `실행 결과`
  - 상태: ✅ 운영 중

- **감시 가능성 (Auditability)**
  - 기술 모듈: 판단 재검증 엔진, 성과 분석기
  - 구조: 사후 검증으로 "AI 판단이 맞았는가" 추적
  - 상태: ✅ 운영 중

- **재현성 (Reproducibility)**
  - 기술 모듈: Replay 엔진 (동일 조건에서 판단 재시뮬레이션)
  - 상태: ✅ 계획 중

### 도메인 간 데이터 흐름

```text
사용자 요청 (UI 메뉴)
    ↓
어느 도메인인가? (의사결정 → 자산/생활금융/위험보호/접근성 분류)
    ↓
해당 기술 모듈 실행 (Adapter/Analyzer/Engine)
    ↓
판단·설명·리스크 평가
    ↓
기록·검증·환류 계층 (Audit & Replay)
    ↓
사용자에게 결과 표시 (UI)
```

### 주의: 메뉴명은 확정이 아닙니다

- "🧭 자산 통합" 메뉴명은 v3.9부터 확정 적용됩니다. 기술 도메인 구조는 메뉴명 변경과 무관하게 일관성을 유지합니다.
- 기술 도메인 구조는 메뉴명 변경과 무관하게 일관성을 유지합니다.

---

## 📊 데이터 흐름

### 코인 선택 시스템 (evaluator.py)

```text
거래소 API → 심볼 수집 → 5가지 점수 계산 → 메이저/알트 비율 조정 → 최적 코인 선정
├── 1단계: 거래소별 심볼 수집 (바이낸스/업비트/바이비트 등)
├── 2단계: 다차원 점수 계산 (기술적/변동성/거래량/트렌드/리스크)
├── 3단계: 시장 상황별 비율 조정 (상승장/하락장/횡보장)
├── 4단계: 하이브리드 접근법 (캐싱 + 백업 + 하드코딩)
└── 5단계: 최종 코인 목록 반환
```

### 거래 데이터

```text
시장 데이터 → AI 분석 → 거래 신호 → 거래 실행 → 결과 기록 → DB 저장
```

### 거래소별 데이터 수집 (v3.3 신규)

```text
거래소 API → ExchangeManager → 잔고/가격 조회 → 대시보드 표시
거래소 API → APISignalManager → 신호 수집 → 학습 데이터 생성
```

### 멀티 거래소 통합 관리

```text
거래소 선택 → ExchangeFactory → 거래소별 클라이언트 생성 → 통합 인터페이스
```

### 사용자 데이터

```text
로그인 → 토큰 생성 → 서버 저장 → 상태 체크 → 세션 관리
```

## 🔧 거래소별 최적화 전략 차이점 (2025-10-21 업데이트)

### 🎯 설계 의도와 아키텍처 분리

**이 시스템은 의도적으로 거래소별로 다른 최적화 전략을 사용합니다:**

#### **바이낸스 (독립 시스템)**

- **API**: python-binance (전용 API)
- **거래 유형**: 선물 거래
- **최적화 시스템**: `optimizer.py`의 완전한 AI 캐싱 시스템 활용
- **특징**:
  - 고급 주문 지원 (OCO, Trailing Stop)
  - 안정적이고 검증된 AI 최적화 시스템
  - `trader.py`에서 `optimizer.optimize_parameters()` 직접 호출
  - AI 캐싱: `_get_cached_ai_decision()`, `_cache_ai_decision()` 활용

#### **CCXT 거래소 (통합 시스템)**

- **API**: CCXT (통합 API)
- **거래 유형**:
  - **선물**: 바이비트, OKX, 비트겟
  - **현물**: 업비트, 빗썸
- **최적화 시스템**: 거래소별 특성에 맞는 자체 최적화 로직
- **특징**:
  - 거래소별 특성 반영 (현물/선물, SHORT 제한 등)
  - 유연한 최적화 전략
  - `unified_trader.py`에서 자체 파라미터 생성
  - AI 강화: `_get_ai_enhanced_parameters_unified()` 메서드

### 📊 왜 다른 최적화 전략을 사용하는가?

#### **1. 거래소별 특성 차이**

```text
바이낸스 (선물):
├── 레버리지 거래 가능
├── SHORT/LONG 모두 지원
├── 고급 주문 타입 지원
└── 안정적인 API

업비트/빗썸 (현물):
├── 레버리지 없음
├── SHORT 거래 제한
├── KRW 페어 거래
└── 현물 특성 반영 필요

바이비트/OKX/비트겟 (선물):
├── 다양한 레버리지
├── SHORT/LONG 지원
├── CCXT 통합 API
└── 거래소별 특성 차이
```

#### **2. API 차이점**

- **바이낸스**: python-binance (전용 라이브러리)
- **CCXT**: 통합 라이브러리 (다양한 거래소 지원)

#### **3. 최적화 요구사항 차이**

- **바이낸스**: 검증된 AI 최적화 시스템으로 안정성 우선
- **CCXT**: 거래소별 특성에 맞는 유연한 최적화 필요

### 🔄 현재 구현 상태

#### **바이낸스 (`trader.py`)**

```python
# optimizer.py의 AI 캐싱 시스템 활용
base_params = self.optimizer.optimize_parameters(symbol, signal_data)
# AI 캐싱: _get_cached_ai_decision(), _cache_ai_decision() 자동 활용
```text

#### **CCXT 거래소 (`unified_trader.py`)**

```python
# 자체 파라미터 생성 (거래소별 특성 반영)
optimized_params = self._get_ai_enhanced_parameters_unified(
    exchange_name, symbol, analysis, pre_entry_analysis
)
# 거래소별 특화 최적화 로직
```

### ✅ 설계의 장점

#### **1. 거래소별 특성 최적화**

- **바이낸스**: 안정적이고 검증된 AI 시스템
- **CCXT**: 거래소별 특성에 맞는 유연한 최적화

#### **2. 유지보수성**

- 각 거래소의 특성을 독립적으로 관리
- 거래소별 업데이트가 다른 거래소에 영향 없음

#### **3. 확장성**

- 새로운 거래소 추가 시 해당 거래소 특성에 맞는 최적화 구현 가능
- 기존 거래소에 영향 없이 확장 가능

### 🚨 개발자 주의사항

#### **절대 금지 사항**

1. **바이낸스에서 CCXT 최적화 방식 사용 금지**
2. **CCXT 거래소에서 바이낸스 최적화 방식 사용 금지**
3. **거래소별 특성을 무시한 통일된 최적화 방식 강제 적용 금지**

#### **올바른 접근 방법**

1. **각 거래소의 특성을 이해하고 그에 맞는 최적화 구현**
2. **기존 설계 의도를 존중하고 거래소별 분리 원칙 준수**
3. **새로운 거래소 추가 시 해당 거래소 특성에 맞는 최적화 전략 선택**

### 📈 향후 발전 방향

#### **1. 거래소별 AI 학습 데이터 분리**

- 각 거래소의 거래 패턴을 독립적으로 학습
- 거래소별 특성에 맞는 AI 모델 개발

#### **2. 거래소별 성능 최적화**

- 각 거래소의 API 특성에 맞는 성능 튜닝
- 거래소별 최적화 알고리즘 개선

#### **3. 통합 모니터링 시스템**

- 거래소별 성능 비교 및 분석
- 전체 시스템 성능 최적화

## 🔧 설정 관리

### 설정 파일 구조

- **settings.json**: 런타임 설정
- **settings_template.json**: 기본 설정 템플릿
- **token.json**: 사용자 인증 정보

### 설정 우선순위

1. 사용자 입력 (UI)
2. settings.json
3. settings_template.json
4. 기본값

## 🌐 네트워크 통신

### 백엔드 서버

- **URL**: <https://daltrading.net>
- **인증**: JWT 토큰 기반
- **주요 API**:
  - `/auth/api_login`: 로그인
  - `/auth/check_status`: 상태 체크
  - `/auth/kpi/event`: 클라이언트 KPI 이벤트 적재
  - `/api/signals`: 거래 신호 수신

### KPI 연동 현황 (클라이언트 → 서버)

- **연동 완료**
  - 로그인 성공/실패 이벤트 전송
  - AI 시장 리포트 생성/실패 이벤트 전송
  - 주문 체결/실패 이벤트 전송
  - 코인·주식·ETF 포지션 진입/부분 청산/전량 청산 이벤트 전송
- **아직 미연동**
  - 실시간 로그 본문 업로드
  - 학습 데이터 원문 업로드
  - 일/주/월 리포트 파일 원문 업로드
- **원칙**
  - 원문 로그/학습/리포트는 기본적으로 로컬 저장
  - 서버에는 집계/운영 KPI 이벤트만 전송

### 공개 KPI와 운영 KPI 해석 기준

- 공개 KPI: 외부 페이지/문서에 노출되는 코호트 기반 정적 공개 스냅샷
- 운영 KPI: 관리자 대시보드에서 확인하는 익명 이벤트 기반 최신 운영 집계
- 따라서 웹사이트 공개 KPI와 관리자 KPI는 숫자 구조가 달라도 이상이 아니다.

### v3.9.0.1 포지션 KPI 계약

- `trade_order_executed` / `trade_order_failed`: 주문 성공률과 거래량 계산용
- `trade_position_opened`: 실제 진입 포지션 생성
- `trade_position_reduced`: 부분 청산과 잔여 수량
- `trade_position_closed`: 전량 청산과 평균·중앙값·P90 보유시간 계산용
- 모든 포지션 이벤트는 고유 `event_id`, `position_id`, 거래소/증권사, 종목, 시간대 포함 UTC 시각을 전송한다.
- `hold_seconds`는 `closed_at - opened_at` 또는 `event_at - opened_at`에서 한 번만 계산하며 계산 실패를 0으로 대체하지 않는다.
- 재시작 때 거래소 포지션만 확인되고 실제 진입시각을 복원하지 못하면 종료 주문은 기록하되 보유시간 KPI는 보내지 않는다.
- 주식·ETF는 매수 로그를 열린 포지션으로 유지하고 매도 체결을 FIFO 로트에 연결한다.
- 서버는 `event_id` 재전송을 중복 저장하지 않고 시각 차이와 다른 `hold_seconds`를 거부한다.
- 과거 구형 이벤트의 0초 값은 신뢰할 수 없어 백필하지 않으며 새 클라이언트 종료 거래부터 누적한다.
- 비즈니스 KPI 집계는 `mock`, `demo`, `paper`, `test` 실행을 제외한다.
- pytest 환경에서는 KPI 전송 워커를 시작하지 않아 운영 서버에 테스트 이벤트를 보내지 않는다.

### 운영 메타 KPI

- 거래 처리/응답시간 계열
- `ai_inference_completed` 및 AI 응답시간 계열

평균 보유시간은 v3.9.0.1 포지션 이벤트가 운영 서버에 도착하기 전까지 `수집 대기`로 보인다. `0.0분`은 데이터 없음의 대체값으로 사용하지 않는다.

### 거래소 API (v3.3 확장)

- **바이낸스**: WebSocket + REST API (python-binance 라이브러리)
- **업비트**: REST API (ccxt 라이브러리)
- **빗썸**: REST API (ccxt 라이브러리)

## 🛡️ 보안 아키텍처

### 인증 시스템

```text
사용자 로그인 → JWT 토큰 발급 → 토큰 저장 → API 요청 시 토큰 사용
```

### 중복 실행 방지

```text
앱 시작 → 토큰 확인 → 서버 상태 체크 → 중복 감지 시 종료
```

### API 키 관리

```text
환경설정 → API 키 입력 → 사용자별 로컬 저장 → 거래소 연동
```

## 📈 성능 최적화

### WebSocket 아키텍처 개선 (2025-10-20 완료)

- **문제**: 코인 선택 시 모든 코인 WebSocket 구독으로 인한 46초 지연
- **해결**: API 기반 분석으로 변경, WebSocket은 포지션 모니터링에만 사용
- **효과**: 시작 시간 46초 → 즉시 시작

### 비동기 처리

- WebSocket 연결을 통한 실시간 포지션 모니터링 (최적화됨)
- 멀티스레딩을 통한 UI와 거래 로직 분리
- 백그라운드에서 AI 분석 및 최적화 실행

### 메모리 관리

- 거래 데이터베이스 최적화
- 로그 파일 자동 정리
- 캐시 시스템을 통한 API 호출 최소화
- WebSocket 구독 최적화로 리소스 절약

## 🔄 확장성

### 새로운 거래소 추가 (v3.8 가이드)

1. `BaseExchange` 상속하여 새 클라이언트 구현
2. `ExchangeFactory`에 새 거래소 등록
3. `ExchangeManager`에 새 거래소 지원 추가
4. UI에 새 거래소 옵션 추가
5. `APISignalManager`에 신호 수집 로직 추가

### 새로운 AI 모델 추가

1. `AIManager`에 새 모델 인터페이스 구현
2. 설정에 모델 선택 옵션 추가
3. 성능 비교 및 자동 선택 로직 구현

### 📌 자산군 확장 공통 원칙

- 자산군이 달라져도 판단·기록·검증 파이프라인은 동일하다
- 암호화폐, ETF, 주식, 해외주식, 선물, 부동산은 모두 같은 판단 계층을 사용한다
- 실행은 항상 외부 금융기관·거래소 API가 담당한다
- NoahAI는 실행 주체가 아닌 AI 자산 의사결정 인프라로만 동작한다

## 🆕 v3.3 신규 모듈 상세

### Evaluator (코인 선택 엔진) - 핵심 모듈

- **역할**: AI가 거래할 최적의 코인들을 과학적으로 선별하는 핵심 엔진
- **주요 기능**:
  - **5가지 차원 점수 계산**: 기술적/변동성/거래량/트렌드/리스크 점수
  - **거래소별 특화 선택**: 바이낸스/업비트/바이비트 등 각 거래소 특성 반영
  - **시장 상황별 동적 조정**: 상승장/하락장/횡보장에 따른 메이저/알트 비율 자동 조정
  - **하이브리드 접근법**: 캐싱 + 백업 + 하드코딩으로 안정성과 성능 동시 확보
- **성능 최적화**:
  - **초기 로딩**: 4분 → 즉시 (99% 개선)
  - **API 의존성**: 100% → 30% (70% 감소)
  - **안정성**: 70% → 99% (29% 향상)
- **사용법**: `evaluator.select_trading_coins(num_alt, num_major, regime, exchange)`

### ExchangeManager (거래소 관리자)

- **역할**: 선택된 거래소의 클라이언트를 동적으로 생성 및 관리 (v3.8: 설정 변경 시 안전 재로딩)
- **주요 기능**:
  - 거래소별 클라이언트 캐싱
  - 잔고 조회 통합 인터페이스
  - 거래소 전환 시 자동 클라이언트 교체
- **사용법**: `exchange_manager.get_exchange_balance()`

### APISignalManager (API 신호 관리자)

- **역할**: 모든 거래소에서 시장 데이터를 수집하여 AI 학습에 활용
- **주요 기능**:
  - 1분 간격 자동 신호 수집
  - 거래소별 데이터 정규화
  - 학습 데이터 자동 생성
- **사용법**: 백그라운드에서 자동 실행

### ExchangeFactory (거래소 팩토리)

- **역할**: 거래소별 클라이언트 인스턴스를 생성하는 팩토리 패턴
- **주요 기능**:
  - 거래소별 클라이언트 생성
  - 설정 기반 클라이언트 초기화
  - 일관된 인터페이스 제공
- **사용법**: `ExchangeFactory.create_exchange(exchange_name, config)`

### BaseExchange (기본 거래소 클래스)

- **역할**: 모든 거래소 클라이언트의 공통 인터페이스 정의
- **주요 메서드**:
  - `connect()`: 거래소 연결
  - `get_balance()`: 잔고 조회
  - `get_current_price()`: 현재가 조회
  - `get_account_info()`: 계정 정보 조회

### 🔄 v3.8 아키텍처 업데이트 요약

- 설정 저장 시 런타임 재초기화 경로 도입: `UnifiedTradingManager.reload_settings()`, `ExchangeManager.update_settings()`로 재시작 없이 반영
- 대시보드가 메인 애플리케이션의 매니저 인스턴스를 재사용하여 상태 불일치 해소 (`ModernDashboard` → `main_app.unified_manager` 재사용)
- `UnifiedTradingManager`가 `refresh_exchange()`를 제공하여 특정 거래소만 선택 재연결 가능
- `ExchangeManager`가 Bybit/OKX/Bitget 키 검증 및 가용성 노출을 포함하도록 확장
- `Analyzer`가 가능한 경우 `ExchangeManager`를 통해 현재가를 조회(폴백: Binance) — 캔들 데이터도 `ExchangeManager.get_klines()`로 단계적 전환
- `UnifiedTrader`가 선물 거래소에서 레버리지/마진 타입을 주문 전 자동 설정하며, CCXT 어댑터에는 심볼 정규화(`BASE/QUOTE`)를 적용
  - 기본 마진 타입은 설정의 `default_margin_type`(기본 `ISOLATED`)을 사용
- 거래소별 시그널 임계값(`exchange_signal_thresholds`)을 설정에서 정의하고, Analyzer가 컨텍스트(거래소)에 따라 임계값을 적용
- 경로 체계 문서화: `docs/STORAGE_PATHS.md`에 개발/배포 환경의 저장 경로 및 계정별 폴더 구조 정리

#### WebSocket API 명칭 통일과 사용 원칙

- 구독: `subscribe_symbol(symbol)`, `unsubscribe_symbol(symbol)`
- 조회: `get_latest_ticker(symbol)`, `get_latest_orderbook(symbol)`
- 접근 가드:

  ```python
  client = getattr(self, 'binance_client', None)
  ws = getattr(client, 'websocket_manager', None) if client else None
  if not ws: return
  ```

#### 구독 유지 정책(retention policy)

- 기본 구독: 메이저 심볼(예: BTCUSDT, ETHUSDT)은 항상 유지
- 유지 조건: 열린 포지션 존재 또는 최근 거래 신호 발생 심볼
- 정리 조건: 상기 조건이 아닌 심볼은 배치 단위로 해제
- 구현: `main.manage_trading_websocket_subscriptions()`와 `_manage_subscription_retention_policy()`

## 📈 대시보드 애널리틱스 (v3.7.6)

- 요약 데이터: sizing_outcomes.csv 기반 전체/거래소별 승률·평균/중앙 PnL·평균 Size 표기
- 자동 새로고침: 설정 `analytics_refresh_interval_minutes`(기본 30분)
- 범위/기간 필터: All/Last 100/500/1000, All/Today/7d/30d

## 🚨 개발자 가이드라인 (중요: 혼재 방지)

### 거래소 처리 분리 원칙

```text
🔥 바이낸스 (Binance):
├── 거래 로직: trader.py 전용
├── API 클라이언트: api/binance_client.py (python-binance)
├── 포지션 관리: trader.py.active_positions
└── TP/SL: trader.py 내부 직접 구현

🔥 CCXT 거래소 (Bybit/OKX/Bitget/Upbit/Bithumb):
├── 거래 로직: unified_trader.py 전용
├── API 어댑터: trading/exchanges/adapters/
├── 포지션 관리: unified_trader.active_positions[exchange]
└── TP/SL: CCXT 어댑터의 place_insurance_tp_sl()
```

### 절대 금지 사항

1. **unified_trader.py에서 바이낸스 처리**: `exchange_name == 'binance'` 조건 금지
2. **trader.py에서 CCXT 거래소 처리**: CCXT 관련 import 금지
3. **중복 메서드 구현**: 같은 기능을 여러 파일에 구현 금지
4. **기능 분산**: 관련 기능을 여러 모듈에 분산 구현 금지
5. **어댑터 기능 무시**: 어댑터에 구현된 메서드를 무시하고 직접 구현 금지
6. **중복 로직**: 어댑터와 unified_trader에서 같은 로직 구현 금지
7. **이중 구조 금지**: trading/exchanges/와 trading/exchanges/adapters/에서 같은 거래소 중복 구현 금지
8. **통일된 경로**: CCXT 거래소는 adapters/ 경로만 사용, exchanges/ 경로 사용 금지

### 수정 시 체크리스트

- [ ] 바이낸스 관련 수정은 trader.py에서만 수행
- [ ] CCXT 거래소 관련 수정은 unified_trader.py에서만 수행
- [ ] 중복 메서드가 생성되지 않았는지 확인
- [ ] 어댑터에 구현된 기능을 먼저 확인하고 활용
- [ ] unified_trader.py에서 어댑터 메서드 우선 사용
- [ ] 직접 구현 전에 어댑터 기능 확인 필수
- [ ] CCXT 거래소는 adapters/ 경로만 사용 (exchanges/ 경로 사용 금지)
- [ ] 이중 구조 확인: 같은 거래소가 두 곳에 구현되지 않았는지 확인
- [ ] 문서 가이드라인 준수 여부 확인
- [ ] 거래소별 분리 원칙 위반 여부 확인
- 성과 색상 힌트: 승률/평균PnL 기준 green/yellow/red
- 국면 표시: 현재 국면(LOW/NORMAL/HIGH) 및 국면 모드(AUTO 또는 MANUAL) 표기
  - 상단 상태 바에도 REGIME/MODE 뱃지를 표시해 전체 상태를 즉시 파악
