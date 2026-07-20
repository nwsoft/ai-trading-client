## 문서 동기화 메모 (2026-07-19)

- 소스/문서 버전 단일 소스(`config/app_version.py`) 기준 최신 릴리스 후보는 `v3.8.9.29` (2026-07-19)
- Windows stable manifest는 실제 3.8.9.28 EXE의 SHA-256을 유지하며, 3.8.9.29 Windows 빌드·서명·업로드 후 교체한다.
- 전체 자동 테스트 최신 실행: `967 passed, 6 skipped, 3 warnings` (2026-07-19, macOS/Python 3.13)
- 경고 3건은 기존 `scripts/test_coin_selection*.py` 테스트가 assert 대신 list를 return한다는 pytest 경고이며 실패는 아니다.
- 신규 대상 테스트: 거래통계 높이/KPI, Pine·텍스트 전략 추출, 실행검증, 신규사용자 제한운용, 거래소별 임계값, 설정 닫기, GPT-5.6 모델 카탈로그.

---

## 최신 테스트 결과 (2026-07-19 v3.8.9.29)

- 전체 회귀: **967 passed, 6 skipped, 0 failed, 3 warnings**
- v3.8.9.29 집중 + 커스텀/고급계층 게이트: **34 passed**
- 문서/버전 정합성: **PASS**
- Python 문법 검사: 수정 Python 파일 전체 **PASS**
- 남은 외부 게이트: Windows EXE 빌드/서명/manifest, 각 실제 거래소 장시간 또는 최소단위 검증

---

## 최신 점검 결과 (2026-07-05 거래소 진단/정합)

### 2026-07-05 반영
- 운영 진단(5m x 50 캔들, 상위 10심볼)
   - 결과: Bitget 10/10, Upbit 10/10, Bithumb 10/10, Bybit 0/10(Unmatched IP), OKX 0/10(연결 실패)
   - 해석: 다중 거래소 미체결 이슈를 전략 로직 단일 원인으로 보지 않고, 인증/권한/IP 화이트리스트 계층으로 분리 진단 가능
- 정적 오류 점검(`get_errors`) 핵심 수정 파일
   - 대상: `trading/unified_trader.py`, `trading/recorder.py`, `trading/exchanges/adapters/bitget_futures_adapter.py`, `trading/exchanges/adapters/bybit_futures_adapter.py`, `trading/exchanges/adapters/okx_futures_adapter.py`, `ui/settings_modern.py`
   - 결과: **No errors found**
   - 해석: 2026-07-05 거래소 진단 UX 및 Unified 게이트 정합 패치 기준 신규 오류 없음

---

## 최신 테스트 결과 (2026-06-05 v3.8.9.21)

**후속 안정화 검증: PASS**

### 2026-06-05 반영
- `python3 scripts/multi_exchange_stability_check.py`
   - 결과: **PASS**
   - 해석: 전역 전체시작 제거 정책과 거래소별 상태/코인 분리 불변조건 통과
- 정적 오류 점검(`get_errors`) 핵심 파일
   - 대상: `trading/unified_trader.py`, `trading/evaluator.py`, `ui/dashboard_modern.py`, `ui/login_modern.py`
   - 결과: **No errors found**
   - 해석: v3.8.9.21 후속 핫픽스 반영 파일에 신규 오류 없음

---

## 최신 테스트 결과 (2026-05-29 v3.8.9.20)

**패치 검증: 2건 완료**

### 2026-05-29 반영
- `python -m py_compile trading/unified_trader.py`
   - 결과: **성공 (문법 오류 없음)**
   - 해석: 실시간 청산 net PnL 산식 정합화 패치의 기본 문법 안정성 확인
- 정적 오류 점검(`get_errors`) 핵심 수정 파일
   - 대상: `trading/unified_trader.py`, `ui/widgets/user_manual_widget.py`
   - 결과: **No errors found**
   - 해석: 코드/인앱 공지 반영 파일에 신규 오류 없음

---

## 최신 테스트 결과 (2026-05-21 v3.8.9.20)

**추가 검증: 3 passed**

### 2026-05-21 반영
- `pytest -q tests/test_fl_rl_data_adapter.py tests/test_federated_learning_manager.py tests/test_federated_learning_preparation.py`
   - 결과: **3 passed**
   - 해석: FL/RL 사전 준비 구조(전이 변환/배치 관리/오케스트레이터) 기본 동작 정상
- 정적 오류 점검(`get_errors`) 신규/수정 파일
   - 결과: **No errors found**
   - 해석: 버전 상향/문서 동기화 포함 변경 파일 문제 없음

---

## 최신 테스트 결과 (2026-05-07 검증 동기화)

**추가 검증: 102 passed** (경고 0건)

### 2026-05-07 반영
- `python -m pytest tests/test_dashboard_full_button_e2e.py tests/test_menu_regression.py tests/test_service_tab_policy_snapshot.py tests/test_settings_backup.py -q --tb=short`
   - 결과: **102 passed**
   - 해석: 대시보드 전수 버튼/탭 E2E(44) 신규 추가 후 기존 핵심 회귀와 충돌 없이 통과
- `python3 scripts/verify_stock_broker_connection.py --all_brokers --no_save`
   - 결과: **kiwoom/shinhan/miraeAsset 18/18 OK**
   - 해석: 브로커 연결 검증 스크립트 정상 동작(조합검증/어댑터생성/연결/잔고/계좌/포지션)

---

## 이전 기준선 (2026-05-04 안정화)

**전체: 813 passed, 6 skipped** (경고 0건)

### 2026-05-04 품질 고도화 반영
- `python -m pytest tests/ -q`
   - 결과: **813 passed, 6 skipped, 0 warnings**
   - 해석: 음성 배포 안정화 + 경고 제거 패치 반영 후 전체 회귀 통과
- 경고 제거 항목
   - `api/backend_api.py`: `websockets.client.connect` deprecated import 제거
   - `tests/test_tp_sl_validation.py`: `PytestReturnNotNoneWarning` 제거 (pytest 테스트/스크립트 함수 분리)
   - `trading/recorder.py`: sqlite datetime 바인딩을 ISO 문자열로 정규화

---

## 이전 기준선 (2026-05-03 9차)

**전체: 814 passed, 6 skipped** (신규 85개 추가)

| 테스트 파일 | 결과 | 내용 |
|------------|------|------|
| test_tax_calculation_service.py | **53 passed** (신규) | 세무계산, 연말정산, 금투세, ISA/IRP 비교 |
| test_fraud_detection_service.py | **32 passed** (신규) | 보이스피싱, 이상거래, 약탈적대출 탐지 |
| test_stock_symbol_search.py | 43 passed | 종목 검색/자동완성/즐겨찾기/최근검색 |
| test_asset_correlation_service.py | 44 passed | 자산 상관관계 분석, 리밸런싱 제안 |
| test_life_finance_goal_service.py | 45 passed | 목표 관리, 시뮬레이션, 예산 배분 |
| test_mock_live_boundary.py | 32 passed | Mock/Live 경계, allow_live_order |
| test_asset_mode_etf_stock_branch.py | 44 passed | ETF/주식 분기 로직 |
| test_community_qna_chat.py | 36 passed | 커뮤니티 QnA/Chat |
| test_alpha_arena_readiness.py | 26 passed | AlphaArena 준비도 |
| test_menu_regression.py | 42 passed | 메뉴 회귀 |

> flaky 1건: `test_ai_assistant_context.py::test_restore_default_strategy_applies_loaded_settings`
> — 단독 실행 시 통과, 전체 실행 시 전역 상태 충돌. 이번 변경과 무관.

---

# 테스트 현황 요약 — 2026-05-03 (최신)

본 문서는 현재까지 확인된 실행/기능 테스트 결과를 요약합니다.
문서 설명보다 실제 코드 동작 범위를 우선 표기합니다.

## 중요 정리 (주식/ETF / 해외선물 관련)
- 주식/ETF UI 경로와 어댑터 라우팅은 동작합니다.
- 주식/ETF 실증권사 연동 상태: 키움(pykiwoom 골격), **신한(REST 완성 + 401 자동갱신 + health_check)**, **미래에셋(REST 완성 + 401 자동갱신 + health_check)**
- 주식/ETF 통합 테스트 `tests/test_stock_integration.py`의 PASS는 대부분 Mock 어댑터 기준입니다.
- 해외선물(증권사) 전용 어댑터/실주문 경로는 현재 코드에 구현되어 있지 않습니다.
- 현재 실운영 선물 경로는 암호화폐 futures(예: binance/bybit/okx/bitget)입니다.

## 환경
- OS: macOS
- 실행 방식: 소스 직접 실행 (python3 main.py)
- Python: 3.13

## 추가 확인 결과 (2026-05-03 9차 당시)
- `python -m pytest tests/ -q`
   - 결과: **595 passed, 6 skipped**
   - 해석: 전체 테스트 스위트 통과 (ETF 실시간 지표 연동 +11, AlphaArena readiness +26, 메뉴 회귀 +42, 커뮤니티 QnA/Chat +36 신규 추가)

### 신규 추가 테스트 그룹 (2026-05-03 6차)
- `tests/test_etf_adapter_indicators.py`: **67 passed** (+11, 신한/미래에셋 trade_value/expense_ratio 필드매핑, get_etf_realtime_metrics 통합)
- `tests/test_alpha_arena_readiness.py`: **26 passed** (신규 생성, start/stop/주문게이트/예외복구/readiness 체크리스트)
- `tests/test_menu_regression.py`: **42 passed** (신규 생성, 서비스명 정규화/탭 보호/구조 불변성/새로고침 경로/컨텍스트 동기화)
- `tests/test_community_qna_chat.py`: **36 passed** (신규 생성, QnA 목록/상세/등록, 답변 등록, 채팅 조회/전송, 공지사항 7개 API)

## 추가 타겟 검증 (2026-05-03 최신) — 수익성 검증/워크포워드 자동화
- `python -m pytest tests/test_profitability_validation.py tests/test_stock_analysis_service.py -q`
   - 결과: **74 passed**
   - 해석: ProfitabilityValidator 단위 25건 + StockAnalysisService 통합 2건 추가로 `profitability_blocked`/`insufficient_trades bypass` 동작 검증

## 추가 타겟 검증 (2026-05-03 최신) — UI/AlphaArena/문서 정합성
- `python -m pytest tests/test_service_tab_policy_snapshot.py -q`
   - 결과: **4 passed**
   - 해석: 블록체인/증권 서비스 보호 탭 정책(snapshot) 정상
- `python -m pytest tests/test_alpha_arena_guardrails.py -q`
   - 결과: **6 passed**
   - 해석: AlphaArena 틱 주기/TP·SL/리스크캡/쿨다운/동시포지션 가드레일 정상
- `python scripts/stock_supported_mode_matrix_check.py`
   - 결과: **PASS** (11개 조합 확인, 키움 Windows 필요 2건 경고)
- `python scripts/doc_consistency_check.py`
   - 결과: **PASS** (dashboard/manual/user_guide/policy 핵심 표기 일치)

## 추가 타겟 검증 (2026-05-03) — 어댑터 로버스트니스
- `python -m pytest tests/test_stock_adapter_robustness.py -v`
   - 결과: **23 passed**
   - 해석: 신한/미래에셋 토큰 자동갱신(401 재시도), health_check, api_type/api_version 실행경로 방어검증


## 추가 타겟 검증 (2026-05-02) — ETF 지표 어댑터 연동
- `python -m pytest tests/test_etf_adapter_indicators.py -v`
   - 결과: **56 passed**
   - 해석: StockMockAdapter/ShinhanStockAdapter/MiraeAssetStockAdapter get_etf_list 필드매핑 검증 (`isuSrtCd→code`, `trcErrRt→tracking_error`, `bchidxNm→base_index` / `stck_shrt_cd→code`, `trc_errt→tracking_error`, `bchm_nm→base_index`), is_etf() 코드 범위 판별, ETFMetrics risk_level(ok/warn/alert)/nav_gap/summary/to_dict, score_etf() 점수 계산, StockAnalysisService.get_etf_analysis() Mock 통합 전체 통과

## 추가 타겟 검증 (2026-05-02) — Phase F 생활금융 회귀
- `python -m pytest tests/test_life_finance_phase_f.py -v`
   - 결과: **27 passed**
   - 해석: LifeFinanceQualityTracker.build_quality_report() 리스크 판정, FinanceProductAdvisor 외부 JSON 카탈로그 로드/갱신/사용자 태그 매칭 전체 통과

## 최신 확인 결과 (2026-04-24)
- `python -m pytest tests/ -q`
   - 결과: **125 passed, 6 skipped** (당시 기준)
   - 해석: 전체 테스트 스위트 통과
- `python -m pytest tests/test_kiwoom_backend_adapter.py -q`
   - 결과: 6 passed
   - 해석: 키움 어댑터 fake backend — 연결/잔고/보유종목/시세/미체결/주문 파싱 골격 검증
- `python -m pytest tests/test_shinhan_backend_adapter.py -q`
   - 결과: 8 passed
   - 해석: 신한 SOL Trading API REST 어댑터 — connect/balance/positions/open_orders/place_order/is_etf/account_info 검증
- `python -m pytest tests/test_mirae_asset_backend_adapter.py -q`
   - 결과: 10 passed
   - 해석: 미래에셋 Open Trading API REST 어댑터 — connect/balance/positions/open_orders/trade_history/place_order/cancel_order/is_etf/account_info 검증
- `python -m pytest tests/test_stock_analysis_service.py -q`
   - 결과: 27 passed
   - 해석: StockAnalysisService (ETFMetrics, score_stock, summarize_portfolio, AI context, symbol analysis, 분석 로그 이벤트) 전체 커버
- `python -m pytest tests/test_stock_integration.py -q`
   - 결과: 46 passed, 6 skipped
   - 해석: Live 테스트는 `LIVE_STOCK_TEST=true`에서만 동작하며, 키움 Live는 Windows + pykiwoom 조건 미충족 시 명시적으로 skip 처리

## 추가 검증 결과 (2026-04-24)
- 상위 메뉴 `🤖 AI애널리스트` 클릭 시 `switch_service("ai_analyst")` 경로 동작 확인
- 서비스 전환 시 정보 탭 보호 정책 서비스별 적용 확인
   - `blockchain` 모드: `🪙 코인 정보` 유지
   - `stock` 모드: `🪙 종목 정보` 유지
- AI 애널리스트 화면이 준비중 플레이스홀더가 아니라 카드형 분석 UI로 렌더링되는 코드 경로 확인
- 시장 트렌드/AI 학습 위젯의 `set_service_context()` 존재 및 대시보드 전환 시 동기 호출 경로 확인
- STT 배포 의존성 정합성 확인
   - `requirements.txt`: `SpeechRecognition`, `pyaudio` 포함
   - `aiautotrade.spec` hiddenimports: `speech_recognition`, `pyaudio` 포함

## 런타임 장애/제약 점검 (2026-04-24 추가)
- `python3 main.py` 실행 시 발생하던 메뉴얼 위젯 들여쓰기 오류 수정 완료
   - 원인: `ui/widgets/user_manual_widget.py`의 `create_multi_exchange_tab` 블록 들여쓰기 불일치
   - 조치: 클래스 메서드 들여쓰기 정렬 후 import 스모크 및 main.py 재실행 확인
- 실행 상태: import 단계 크래시 해소, 로그인 창 진입까지 확인
- 시장 트렌드 상단 칩 정합성 개선
   - `ui/widgets/market_trend_widget.py`: 데이터 미수집 상태를 `0.0000`처럼 표시하지 않고 `수집 대기`로 표시
   - 주식 컨텍스트에서 코인 전용 심리(펀딩비/공포탐욕) 강제 표시를 피하고 일반화 칩으로 전환
- 아직 남은 제한 경로(코드 기준)
   - AlphaArena `qwen3-max`는 DashScope 전용 클라이언트 경로가 미구현(주석/미지원 표기 존재)
    - 자산 통합/생활금융은 더 이상 준비중 화면만 있는 상태는 아님
       - 자산 통합: 통합 자산 현황/비중/리스크 요약/추천 액션 표시
       - 생활금융: 수입/고정비/변동비 입력과 저축 가능액 계산 제공
    - 다만 두 영역 모두 DB 저장, 자동 분류, 심화 추천까지 완료된 상태는 아님
   - 커뮤니티 QnA/Chat은 플레이스홀더 성격(실시간 연동 미완료)

## 추가 타겟 검증 (2026-04-27)
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **74 passed, 6 skipped**
   - 해석: 종목 검색/분석과 증권 통합 경로의 핵심 회귀는 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_alpha_arena_guardrails.py -q`
   - 결과: **38 passed**
   - 해석: 주식/ETF 표시 모드 필터, 증권 AI 컨텍스트 분기, AlphaArena 틱 주기/TP·SL/리스크 캡/쿨다운/동시 포지션 가드레일 회귀 통과
- 코드 기준 정정 사항
   - 자산 통합/생활금융: "안내만 존재" 문구는 최신 빌드와 불일치
   - AlphaArena: 설정 화면에는 Qwen 관련 항목이 남아 있지만, 대시보드 실행 위젯은 DeepSeek 우선 경로 기준
   - 주식/ETF: 사용자용 `통합/주식만/ETF만` 표시 모드는 추가되었지만, 증권 자동주문 경로는 아직 암호화폐처럼 완성되지 않음

## 추가 타겟 검증 (2026-04-27 Phase 1-2)
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_order_guardrails.py tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **86 passed, 6 skipped**
   - 해석: 증권 가드레일(시장시간/모드불일치/한도초과/최소주문단위/정상) + 종목분석 + 통합 경로 전체 회귀 통과

## 추가 타겟 검증 (2026-04-28 D0)
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py -q`
   - 결과: **47 passed, 6 skipped**
   - 해석: 주문 결과에 `execution_mode`, `api_type`, `success` 메타데이터 추가 후 증권 통합 계약 유지
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **79 passed, 6 skipped**
   - 해석: 주식/ETF 분석 결과에 `analysis_type`, `score_model`, `reasoning`을 추가한 후 분석 분기와 주문 경로 회귀가 함께 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py tests/test_stock_order_guardrails.py -q`
   - 결과: **91 passed, 6 skipped**
   - 해석: 대시보드 증권 주문 호출을 `qty` 우선 재시도에서 `quantity` 계약 우선 호출로 정규화한 후 핵심 증권 회귀 전체 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py -q`
   - 결과: **48 passed, 6 skipped**
   - 해석: 실주문 feature flag 기본값(`enable_stock_live_order`, `allow_live_order`) 추가 후 증권 통합 계약 테스트 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py -q`
   - 결과: **35 passed**
   - 해석: 증권 자동매매 1차 로직(`evaluate_trade_signal`, `run_auto_trade_cycle`) 단위 검증 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **84 passed, 6 skipped**
   - 해석: 자동매매 1차 루프 + 설정 기본값 + 실주문 차단 분기까지 증권 핵심 회귀 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
   - 결과: **84 passed, 6 skipped**
   - 해석: 자동매매 경로에서 심볼 단위 XAI 저장 및 성공 주문 즉시 `trade_log` 기록 보강 후에도 회귀 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **85 passed, 6 skipped**
   - 해석: 종목 검색 고도화 1차(최근검색/즐겨찾기/원클릭 재검색)와 템플릿 기본값(`stock_search_profile`) 추가 후 회귀 통과
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **85 passed, 6 skipped**
   - 해석: 종목 검색 고도화 2차(자동완성/부분일치 추천/원클릭 제안 검색) 반영 후에도 증권 핵심 회귀 유지
- `/Users/playone/SynologyDrive/Works/noahai_client/.venv/bin/python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
   - 결과: **85 passed, 6 skipped**
   - 해석: 자산 통합 확장(상관계수/리밸런싱 제안) 반영 후에도 증권 핵심 회귀 유지
- 코드 기준 정정 사항
   - 증권 주문 결과는 이제 UI 상태 라벨에서 `모의주문 경로` 또는 `실주문 경로(api_type)`를 함께 표시한다.
   - `StockAnalysisService.analyze_symbol()`은 주식과 ETF에 대해 서로 다른 판단 근거 문자열을 생성한다.
   - `ui/dashboard_modern.py`의 증권 주문 호출은 이제 stock adapter 계약(`quantity`)을 우선 사용하고, 예전 호출 방식은 안전망으로만 유지한다.
   - `ui/dashboard_modern.py`는 mock이 아닌 주문 경로에서 feature flag가 꺼져 있으면 주문을 사전에 차단한다.
   - `StockAnalysisService.run_auto_trade_cycle()`가 주식/ETF 분석 신호를 기반으로 주문 실행(또는 live 차단)까지 1회 사이클로 처리한다.
   - `ui/dashboard_modern.py`는 `stock_auto_trading` 설정이 활성화되면 주식 서비스에서 주기적으로 자동매매 사이클을 실행한다.
   - 자동매매 각 심볼의 의사결정은 `stock_auto_trade_symbol` XAI로 저장되며, 사이클 요약은 `stock_auto_trade_cycle`로 저장된다.
   - 자동매매 성공 주문은 대시보드 수동주문과 동일하게 `trade_log`에 즉시 기록된다.
   - 종목 검색은 `stock_search_profile`에 최근검색/즐겨찾기를 저장하며, 검색 탭에서 즉시 재검색 버튼으로 재실행 가능하다.
   - 종목 검색은 자동완성 제안을 통해 코드/종목명 부분일치 검색을 지원한다.
   - 자산 통합 탭은 crypto/stock 일별 손익 기반 상관계수와 집중도 지표를 계산해 동적 리밸런싱 액션을 제시한다.
- Phase 1-2 정합 반영
   - 증권 탭은 분석/설명 중심 흐름으로 정리
   - 증권 가드레일은 시스템 경로에서 계속 적용(`trading/stock_order_guardrails.py`)
   - 브로커별 최소주문단위 검증(최소수량/수량단위) 유지
   - `config/settings_template.json` 의 `stock_order_guardrails` 기본값 유지

## 증권 개발 마스터 실행 순서 (1 → 2 → 3)

이 섹션은 지금부터 실제 개발을 마무리할 때까지의 기준 문서다.
목표는 "국내 주식/ETF를 실제로 문제 없이 연결하고, AI/설정/어시스턴트까지 일관되게 작동시킨 뒤, 해외를 별도 확장"하는 것이다.

### 1단계. 국내 주식/ETF 완성 (최우선)

#### 목표
- 키움을 기준 브로커로 먼저 완성한다.
- 국내 주식/ETF의 연결, 잔고, 보유종목, 시세, 주문, 미체결, 로그, 통계가 실제 계정 기준으로 동작해야 한다.
- Mock 없이도 사용자가 설정 저장 후 대시보드에서 실제 상태를 확인할 수 있어야 한다.

#### 현재 상태
- UI/설정/어댑터 라우팅은 이미 존재한다.
- 키움 어댑터는 pure placeholder에서 한 단계 올라가 backend 기반 연결/파싱 구조를 갖췄다.
- 다만 실계좌 Live 검증과 실제 pykiwoom/키움 REST 운영 검증은 아직 남아 있다.
- 따라서 지금은 "증권 구조와 키움 연동 골격은 있으나 실거래 완성은 아님"으로 판단한다.

#### 구현 대상 모듈
- 설정/UI: `ui/settings_modern.py`
- 대시보드/증권 탭: `ui/dashboard_modern.py`
- 팩토리/라우팅: `trading/exchanges/exchange_factory.py`
- 인터페이스: `trading/exchanges/interfaces/stock_exchange.py`
- 증권 어댑터: `trading/exchanges/adapters/kiwoom_stock_adapter.py`
- 후속 어댑터: `trading/exchanges/adapters/shinhan_stock_adapter.py`, `trading/exchanges/adapters/mirae_asset_stock_adapter.py`

#### 필수 데이터 (국내 주식/ETF)
- 사용자 인증 정보: ID, 비밀번호, 인증서/추가 비밀번호, 계좌번호
- 계좌 정보: 예수금, 주문가능금액, 총자산, 평가손익
- 보유 종목: 종목코드, 종목명, 수량, 평균단가, 현재가, 평가손익, 수익률
- 시세 데이터: 현재가, 전일대비, 등락률, 거래량, 거래대금
- ETF 추가 데이터: NAV, 괴리율, 추적오차, 기초지수/섹터
- 주문 데이터: 매수/매도, 주문가, 주문수량, 체결수량, 미체결수량, 주문상태, 주문시간
- 일봉/분봉 데이터: AI 분석과 시장 분석 위젯에서 사용할 OHLCV

#### 사용자 계정 연결 방식
- 사용자는 설정창에서 증권사별 `api_type`, `api_version`, 계정정보를 입력한다.
- 저장 시 `stock_broker_configs` 아래에 증권사별 설정이 저장된다.
- 대시보드는 `_get_stock_adapter()`를 통해 선택 증권사 어댑터를 가져오고 연결한다.
- 연결 성공 시 증권 탭 잔고/보유종목/통계/로그가 실제 계정 기준으로 새로고침되어야 한다.

#### API 활용 방식
- 1차 기준은 키움 공식 REST/OpenAPI에서 가능한 범위를 우선 사용한다.
- 연결 API: 로그인/세션/토큰 발급 또는 OpenAPI 로그인
- 조회 API: 계좌조회, 잔고조회, 보유종목조회, 종목정보조회, 시세조회, 미체결조회
- 주문 API: 현금 매수/매도, 정정/취소
- ETF는 별도 상품군이 아니라 주식 주문 경로와 동일하되, 분석/표시에서 ETF 메타데이터를 추가 사용한다.

#### 키움 인증 방식 결정안 (2026-04-24)
- 기본 운영안: `api_type=openapi`, `api_version=pykiwoom`
- 적용 환경: Windows 실계좌 운용 환경
- macOS 개발 환경: 키움 Live 직접 연결은 제외하고 mock 또는 REST 기반 증권사(신한/미래에셋)로 검증
- 전환 조건: 키움 REST가 계좌/주문/미체결/체결까지 안정적으로 동일 커버되는 것이 확인되면 `api_type=rest` 분기 추가 검토

#### 완료 조건
- [x] 키움 `connect()` backend 연동 골격 구현
- [x] 키움 `get_balance()` 응답 표준화 골격 구현
- [x] 키움 `get_positions()` 응답 표준화 골격 구현
- [x] 키움 `get_realtime_price()` 응답 표준화 골격 구현
- [x] 키움 `place_order()` 호출 골격 구현
- [x] 키움 `get_open_orders()` 응답 표준화 골격 구현
- [x] 대시보드 주식 정보/통계 플레이스홀더 제거
- [x] 신한 `shinhan_stock_adapter.py` REST SOL Trading API 전면 구현
- [x] 미래에셋 `mirae_asset_stock_adapter.py` REST Open Trading API 전면 구현
- [x] `tests/test_shinhan_backend_adapter.py` fake backend 8개 테스트 추가
- [x] `tests/test_mirae_asset_backend_adapter.py` fake backend 10개 테스트 추가
- [ ] Live 테스트가 skip이 아니라 실제 통과로 전환

#### 개발 체크리스트
- [x] 키움 API 인증 방식 1차 확정 (현재 운영안: OpenAPI+ / pykiwoom)
- [x] 운영 OS 제약 확인 (키움 OpenAPI+ 직접 연결은 Windows 전용, macOS는 mock/타 증권사 REST 중심)
- [ ] `kiwoom_stock_adapter.py`의 남은 TODO 제거
- [x] 응답 필드를 내부 표준 포맷으로 매핑하는 기반 추가
- [ ] 주문 실패/세션 만료/장외시간 예외 처리
- [ ] 실계좌 전 미니 검증용 모의/테스트 모드 분리
- [x] fake backend 기반 어댑터 테스트 추가
- [ ] `tests/test_stock_integration.py`의 LIVE 구간을 실제 검증 가능 상태로 보강

### 2단계. AI/시장분석/어시스턴트/환경설정 일체화

#### 목표
- 주식/ETF가 단순 조회/주문만 되는 것이 아니라, NoahAI 엔진과 AI 어시스턴트가 실제로 증권 데이터를 활용해야 한다.
- 사용자는 설정, 분석, AI 설명, 로그, 거래 상태를 하나의 흐름으로 이해할 수 있어야 한다.

#### 현재 상태
- AI 어시스턴트는 stock 모드에서 증권사/보유 ETF 문맥을 읽는다.
- ETF 보유 시 추적오차/NAV 괴리/거래대금 문맥이 들어간다.
- 주식 종목 정보 탭과 주식 거래 통계 탭은 연결된 증권사 데이터 표시로 1차 전환되었다.
- 다만 아직 AI 분석 점수화/시장분석 서비스 모듈 분리는 미완이다.

#### AI가 실제로 해야 할 일
- 시장 분석: 국내 시장 장중/장마감 상태, 지수, 섹터, 거래대금, 변동성 확인
- 종목 분석: 가격, 거래량, 추세, 최근 변동성, 리스크 요인 요약
- ETF 분석: NAV 괴리, 추적오차, 거래대금, 섹터/지수 성격 요약
- 사용자 설명: 왜 이 종목/ETF가 위험한지 또는 유리한지 설명
- 설정 연동: 공격형/보수형 등 투자 성향에 따라 설정 제안
- 로그 연동: 분석 결과와 실제 주문/미체결/체결 결과를 분리 기록

#### 필요한 데이터 파이프라인
- 시세/호가/분봉/일봉 데이터 수집 모듈
- ETF 메타데이터 수집 모듈
- 장 상태/휴장일/시장시간 모듈
- 종목/ETF 공통 분석 모델 + ETF 전용 분석 보강 모듈
- AI 어시스턴트 컨텍스트 생성기
- 기록/환류 저장소 (판단 근거, 결과, 사후평가)

#### 위젯 및 모듈 분리 원칙
- 어댑터: 브로커 API 통신만 담당
- 분석 모듈: 시장/종목/ETF 분석만 담당
- 대시보드 위젯: 표시와 사용자 액션만 담당
- AI 어시스턴트: 설명/권장/설정 변경 지원만 담당
- 기록 모듈: 판단/결과/오류/이벤트 로그 저장만 담당

#### 완료 조건
- [x] `ui/dashboard_modern.py`의 주식 정보 탭 플레이스홀더 제거
- [x] `ui/dashboard_modern.py`의 주식 통계 탭 플레이스홀더 제거
- [x] 주식/ETF 분석용 서비스 모듈 분리 (`trading/stock_analysis_service.py` 완성, 27개 테스트)
- [x] AI 어시스턴트가 실제 종목/ETF 분석 결과를 콘텍스트로 사용 (`StockAnalysisService.build_ai_context()` 연동)
- [ ] 설정 변경이 증권 모드에서도 유효하게 반영
- [x] 판단 근거/리스크/결과가 로그에 남음 (`StockAnalysisService`가 portfolio/etf/trade/analyze 이벤트를 `stock_analysis` 카테고리로 기록)

#### 개발 체크리스트
- [ ] `show_stock_content()`와 관련 탭 갱신 흐름 재점검
- [ ] stock 전용 분석 서비스(`services` 또는 `trading` 하위) 설계
- [ ] 종목/ETF 점수화 기준 정의
- [ ] 주식용 위험관리 규칙 정의 (장마감, 변동성, 주문가능금액, 종목당 비중)
- [ ] AI 어시스턴트 프롬프트를 주식/ETF 기준으로 고도화
- [ ] 설정 UI와 어시스턴트 JSON 변경 경로 점검

### 3단계. 해외 확장 (국내 완성 후)

#### 원칙
- 해외는 국내 주식/ETF가 완성된 뒤 진행한다.
- 해외선물과 해외주식은 같은 문제가 아니므로 분리한다.
- "지원 가능성"과 "현재 코드 구현"을 반드시 구분한다.

#### 키움 해외선물 현재 확인 상태
- 저장소 내부 문서에는 "키움 해외선물 어댑터를 별도로 둘 수 있다"는 계획이 있다.
- 현재 코드에는 키움 해외선물 전용 어댑터/주문/조회 구현이 없다.
- 공개 확인 기준으로 `https://openapi.kiwoom.com/` 첫 화면에서 확인되는 범위는 국내주식 주문, 시세, 계좌 현황 중심이며, 이번 점검에서는 해외선물 API 지원을 공식적으로 확인하지 못했다.
- 따라서 현 시점 문서 기준 상태는 `확인 필요`로 둔다.

#### 해외 확장 분기
- A안: 국내 증권사 경유 해외선물/해외주식 API가 실제 가능하면 별도 어댑터 추가
- B안: 한국인이 이용 가능한 해외 브로커/해외 증권사 API가 안정적이면 별도 브로커 어댑터 추가
- C안: 암호화폐 futures 엔진 구조를 재사용하되, 자산/심볼/거래시간/증거금 규칙만 분리

#### 해외 단계 착수 조건
- [ ] 국내 주식/ETF 실거래 경로 완료
- [ ] 주식/ETF 분석/AI/로그 일체화 완료
- [ ] 키움 해외선물 공식 API 문서 또는 실제 지원 근거 확보
- [ ] 해외 브로커 후보군별 한국 사용자 이용 가능성, 법적/운영상 제한 점검

#### 해외 단계 개발 체크리스트
- [ ] 키움 해외선물 공식 지원 여부 재확인
- [ ] 별도 `FuturesExchange` 기반 증권사 해외선물 어댑터 필요 여부 결정
- [ ] 심볼 규칙, 거래시간, 만기, 롤오버, 증거금, 통화 처리 정의
- [ ] 해외주식과 해외선물의 UI/분석/주문 규칙 분리

## 오늘 기준 결론
- 지금 바로 완성해야 하는 것은 국내 주식/ETF다.
- 키움을 먼저 완성하는 전략은 타당하다.
- 다만 "키움이 해외선물을 지원한다"는 이유만으로 현재 앱이 바로 그 경로를 쓸 수 있는 상태는 아니다.
- 해외는 국내 주식/ETF 완성 후, 공식 지원 근거와 API 스펙을 확보한 뒤 별도 단계로 진행한다.

## 실행/런타임
- 직접 실행 (python3 main.py): PASS — Exit Code 0 (개발용 로그인 우회 NOAHAI_SKIP_LOGIN로 신속 검증 완료)
   - 진단 로그: 경로/토큰/설정 출력 OK, trading.log 초기화 OK
   - 참고: docs/TROUBLESHOOTING.md (권한/경로/Tk 포함 여부/네트워크 등)
   - 로그 소음 최소화: API 키 미입력 거래소는 비활성 처리되어 불필요한 인증/심볼 오류 로그가 생성되지 않음
   - 업데이트: BinanceClient에 API 키 가드를 전면 적용했고, WS unsubscribe가 서버에도 반영되도록 개선하여 무키 환경 소음을 더 줄임
   - 추가: WebSocket 경로의 "Invalid symbol" 로그는 최초 1회만 경고로 출력, 이후 동일 심볼은 디버그로 억제됨 (중복 소음 방지)

## UI — ModernDashboard (CustomTkinter)
- 상단 콘텐츠 CTkTabview 초기화/배치: PASS (정적 점검)
- 기본 탭 “📊 실시간 거래 로그” 생성 보장: PASS (정적 점검)
- 서비스 전환 시 하위 탭(블록체인/주식/부동산/기타/AI 애널리스트) 정리 및 재구성: PASS (정적 점검)
- 블록체인 서비스 내 거래소 하위 탭 라이프사이클(활성화된 거래소만 생성, 비활성화 시 제거): PASS (정적 점검)
- 커뮤니티 탭(👥 커뮤니티) + 내부 QnA/Chat 플레이스홀더: PASS (정적 점검)
- ‘클래식 보기’(classic_view) 토글: PASS — true일 때 시작 시 📚 AI 학습/📊 AI 리포트 탭 자동 생성·선택 확인(정적/런타임 점검 병행)

주의: 위 항목들은 코드 수준/정적 점검(린트/구조 확인) 기준 PASS입니다. 직접 실행이 복구되는 즉시 화면 렌더링과 전환 동작을 런타임에서 재확인합니다.

## 타입/정적 점검
- main.py 주요 경로 타입 오류 해소: PASS (이전 사이클)
- dashboard_modern.py 수정 후 타입/린트 오류: 없음 (PASS)

## 멀티 거래소/거래 파이프라인
- 거래소별 섹션(제어/잔고/포지션/통계/로그) 생성 경로 일관성: 준비됨 (정적 점검 OK)
- 단일 비바이낸스 모드(예: Bybit만 활성) UI 동일성: 미수행 (다음 단계)
- 다중 거래소 동시 활성(예: Binance+OKX+Bitget) UI 동일성: 미수행 (다음 단계)

## 주식/ETF 실제 코드 상태 (중요)
- 대시보드 주식 서비스 탭 생성/연결: 구현됨
- 대시보드 주식 정보/거래 통계 탭: 플레이스홀더 제거, 연결 데이터 1차 표시 구현
- 증권사 설정 `api_type`/`api_version` 선택 및 동적 제한: 구현됨
- 팩토리에서 `api_type-api_version` 유효 조합 보정 후 어댑터 전달: 구현됨
- 키움 어댑터: backend 주입 기반 connect/get_balance/get_positions/get_realtime_price/place_order/get_open_orders 골격 구현
- **신한 어댑터**: REST SOL Trading API 전면 구현 완료 — OAuth 토큰/계좌조회/잔고/보유종목/주문/취소/미체결/거래내역 (8개 테스트 통과)
- **미래에셋 어댑터**: REST Open Trading API (UAPI) 전면 구현 완료 — OAuth2 토큰/잔고/보유종목/주문/취소/미체결/거래내역, ETF 코드 범위 105000~115999 (10개 테스트 통과)
- `trading/stock_analysis_service.py`: ETFMetrics, score_stock, summarize_portfolio, StockAnalysisService, build_ai_context(), 분석 로그 이벤트 — 27개 테스트 통과
- Mock 어댑터(`stock_mock_adapter.py`): 계좌/잔고/포지션/주문/ETF 지표(nav, tracking_error) 시뮬레이션 구현

## AI 연동 상태 (주식/ETF)
- AI 어시스턴트는 주식 서비스 컨텍스트를 읽고 증권사 보유/ETF 여부를 요약함
- ETF 보유 시 추적오차/NAV 괴리/거래대금 지표를 조건부로 문맥에 주입함
- `StockAnalysisService` 분석 로그 이벤트 추가: portfolio/etf/trade/analyze/ai_context 결과를 `stock_analysis` 카테고리로 기록
- 주의: 이 기능은 "설명/분석 보조" 경로이며, 실증권사 주문 자동화 완성과는 별개임

## AI 어시스턴트 음성 모듈 (베타 운영)
- 신규 모듈: `ui/widgets/ai_voice_module.py`
   - OS 기본 TTS 래퍼(초기): macOS `say`, Windows `powershell` 지원
   - STT 2차: `speech_recognition`이 설치된 환경에서 마이크 음성 인식 지원 (`transcribe_microphone`)
   - 미설치/비활성 환경에서는 `not_available` + 사유 코드(`voice_disabled`, `speech_recognition_not_installed`, `pyaudio_not_installed`) 반환
   - 기본값은 비활성(기존 UX 영향 없음)
- 위젯 연동: `ui/widgets/ai_assistant_widget.py`
   - 설정 키 `assistant_voice`(enabled/auto_tts/rate) 기반 초기화
   - `auto_tts=true`일 때 AI 메시지 출력 후 TTS 호출
   - `🎤 음성입력` 버튼 추가: STT 결과를 입력창에 주입
- 테스트: `tests/test_ai_voice_module.py`, `tests/test_assistant_voice_settings.py`, `tests/test_stock_analysis_service.py` 로그 검증 케이스

### 음성 배포 의존성 정합 (2026-05-04)
- `requirements.txt`: `SpeechRecognition` 유지, `PyAudio`는 Windows 전용 마커 적용
- `requirements_windows.txt`: `SpeechRecognition`, `pyaudio`, `pipwin` 포함
- `build_safe.py`: 음성 의존성 보정 설치 경로 추가
   - Windows: `pip install pyaudio` 실패 시 `pipwin install pyaudio` 재시도
   - 비-Windows: PyAudio 미설치 허용(마이크 STT만 비활성), TTS/텍스트 기능 정상 유지

## 테스터 배포 전 동시 검증 (AI 어시스턴트 포함)
아래 3개는 라이브 테스터 배포 전 필수 수행:
1) 핵심 회귀
   - `python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
2) AI 어시스턴트 + 음성 모듈
   - `python -m pytest tests/test_ai_voice_module.py tests/test_assistant_voice_settings.py -q`
3) 라이브 검증(테스터 환경)
   - Windows 키움 실계좌: `LIVE_STOCK_TEST=true python -m pytest tests/test_stock_integration.py -v -k "live and kiwoom"`
   - macOS/일반 테스터: 신한/미래에셋 중심 검증 + 키움 live skip 확인

### 스모크 테스트 결과 (직접 실행 스크립트)
- test_unified_system.py: PASS
   - 지원 거래소: {'futures': ['binance', 'bybit', 'okx', 'bitget'], 'spot': ['upbit', 'bithumb']}
   - 연결된 거래소: [] (API 키 미입력 시 의도된 동작)
   - 레버리지 clamp: 요청 200 → 적용 20
   - 최소 노셔널 보정: 0.000050 → 0.001000
   - 주문 성공 판정 샘플: [True, True, True, False]
- test_paper_flow.py: PASS
- test_multi_exchange_runtime.py: PASS
   - 케이스: ['bybit'], ['binance','okx'], ['binance','okx','bitget'] 모두 예외 없이 초기화/잔고/현재가 조회 OK
   - 페이퍼 주문 성공: status=success, simulated=True, symbol=BTCUSDT, qty=0.001, price≈27k
   - 활성 포지션: 빈 딕셔너리(예상 동작)

## 스크린샷(자리표시자)

아래 이미지는 캡처 완료 후 추가됩니다. 파일은 `docs/images/`에 저장됩니다. 상세 목록은 `SCREENSHOTS_CHECKLIST.md`를 참고하세요.

- ModernDashboard 메인: ![placeholder](images/modern_dashboard_main_dark.png)
- Classic View ON 설정: ![placeholder](images/settings_general_classic_view_on.png)
- Classic View 시작 후 AI 탭 자동 생성: ![placeholder](images/classic_view_ai_tabs_auto_created.png)
- 거래소 필터/Trend Summary: ![placeholder](images/blockchain_exchange_filter_trend_summary.png)
- 멀티 거래소 탭 라이프사이클: ![placeholder](images/multi_exchange_tabs_lifecycle.png)
- 커뮤니티 탭(플레이스홀더): ![placeholder](images/community_tab_placeholder.png)

## AI 어시스턴트/설정 흐름
- 어시스턴트가 설정 변경 → 대시보드/매니저에 반영: 코드 경로 준비됨, 런타임 검증 미수행 (다음 단계)

## 알려진 이슈/제약
- 일부 기능은 플레이스홀더(커뮤니티 QnA/Chat): “업데이트 준비중”, FastAPI/WebSocket 연동 주석 템플릿 포함

## 다음 단계 (즉시 수행)
1) 단일 거래소 모드 런타임 검증
   - settings.enabled_exchanges: ["bybit"] 같은 구성으로 실행 → Binance 탭이 생기지 않는지, 동일 섹션과 파이프라인으로 동작하는지 확인
2) 멀티 거래소 모드 런타임 검증
   - ["binance", "okx", "bitget"] 등 조합에서 각 거래소 탭이 동일 섹션으로 생성/갱신되는지 확인
3) 커뮤니티 탭 UI 동작 확인
   - 렌더링/탭 전환 시 예외 없음 확인, FastAPI/WebSocket 연동 시나리오 준비
4) AI 어시스턴트 설정 변경 흐름 검증
   - 어시스턴트에서 설정 변경 → refresh_after_settings_change → 잔고/상태/탭 갱신 경로 확인
5) 스모크 테스트 실행
   - test_unified_system.py, test_paper_flow.py를 paper 모드로 수행하여 거래 가드/파이프라인을 빠르게 검증

업데이트: 추후 테스트가 완료되는 즉시 본 문서에 “PASS/FAIL 및 로그 링크”를 추가하겠습니다.
