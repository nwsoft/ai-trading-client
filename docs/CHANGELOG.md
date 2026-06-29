## 2026-06-27 - v3.8.9.23 크몽 문서 운영절차 반영 (등급명 정합 + settings.json 변조 대응 절차)

### ✅ 크몽 상세페이지 문서 정합화
- `docs/KMONG_SALES_PAGE_DETAIL.md`
  - 패키지 명칭을 운영 기준에 맞춰 정리
    - `ALL TRADING` -> `프로`
  - CTA 버튼 문구 정합화
    - `ALL TRADING 시작하기` -> `프로 시작하기`

### ✅ 회원등급 운영 절차 문서화
- `docs/KMONG_SALES_PAGE_DETAIL.md`
  - "회원등급 운영 절차 (settings.json 변조 대응 포함)" 섹션 추가
  - 절차 핵심:
    - 서버(DB user_grade) 원본 권한 기준
    - 로그인 직후 등급별 로컬 설정 강제 정합
    - 설정 저장 시 제한 로직 재적용
    - 기능 실행 직전 재검증
    - 세션/활성 상태 서버 주기 검증
  - normal/pro/premium 기준 배포 전/후 점검 체크리스트 추가

## 2026-06-27 - v3.8.9.23 회원등급 3단계 강제 게이팅

### ✅ 회원등급 3단계 적용 (일반 / 프로 / 프리미엄-SIGNATURE)
- `main.py`
  - 등급 정규화 로직 추가: `normal`, `pro`, `premium`
  - 별칭 매핑: `signature`/`signature_federated` -> `premium`
  - 로그인 직후/설정 저장 시점에 등급별 기능 제한 강제 적용
    - `normal`: 코인 중심(증권 브로커/주식 실주문/주식 자동매매 비활성화)
    - `pro`: 코인+증권+ETF 허용, 연합학습 비활성화
    - `premium`: 전체 허용(시그니처 포함)
- `ui/dashboard_modern.py`
  - 상태 배지 3단계 표기 반영
    - `🔵 COIN START`
    - `🟢 프로`
    - `👑 프리미엄/SIGNATURE`

## 2026-06-27 - v3.8.9.23 운영 보강 (Windows 자동업데이트 런타임 구현)

### ✅ 자동업데이트 런타임 구현 완료 (Windows 배포 기준)
- `utils/auto_update_manager.py`
  - 백그라운드 주기 체크(시간 단위), 신규 버전 감지, 자동 다운로드, 종료 시 자동 적용/재시작 로직 추가
  - `release-manifest.json`이 존재하면 exe sha256 검증 수행
  - 외부 PowerShell 적용 스크립트 기반 교체 + 시작 실패 시 롤백 경로 포함
- `main.py`
  - 로그인 후 설정 로드 시 AutoUpdateManager 초기화
  - 대시보드 시작 시 자동업데이트 스케줄러 시작, 종료 시 스케줄러 정리
  - 설정 저장 후 자동업데이트 런타임 설정 동기화
- `ui/dashboard_modern.py`
  - 종료 루틴에서 "다운로드 완료 + 자동적용 ON" 조건이면 업데이트 적용 예약 트리거
- `ui/settings_modern.py`
  - 업데이트 탭에 자동업데이트 옵션 UI 추가
    - 백그라운드 체크 ON/OFF
    - 자동 다운로드 ON/OFF
    - 종료 시 자동 적용 ON/OFF
    - 체크 주기(시간)
  - `지금 업데이트 적용(재시작)` 버튼 추가
- `config/settings_template.json`, `config/settings.py`
  - `ui_settings`에 자동업데이트 기본값 추가
- 테스트
  - `tests/test_auto_update_manager.py` 추가, `3 passed`

## 2026-06-26 - v3.8.9.23 릴리스 (AI 기본 모델 정합화 + 거래소 심볼/시간대 버그 수정)

### ✅ AI 기본 모델 정합화
- `config/settings.py`, `main.py`, `trading/ai/ai_manager.py`, `trading/ai/openai_client.py`, `trading/ai/chart_screenshot_analyzer.py`
  - 새 설치 및 fallback 기본값을 `gpt-4o-mini`로 정리
  - `openai_model` / `assistant_ai_model` / 차트 분석 fallback이 서로 다른 기본값을 갖던 경로를 정렬
  - AI 어시스턴트 프리셋의 빈번 호출 티어를 `gpt-4o-mini`로 통일

### ✅ 거래소 심볼/마진 모드 버그 수정
- `trading/exchanges/adapters/bybit_futures_adapter.py`
  - Bybit trade history / open orders / positions에서 `BTC/USDT:USDT` 같은 CCXT 심볼을 `BTCUSDT`로 표시 정규화
  - `fetch_my_trades` 미지원 시 closed order 기반 폴백으로 거래내역 조회
  - `CROSS` / `CROSSED` / `ISOLATED` 변형 입력을 흡수하는 마진 모드 정규화 추가
- `trading/exchanges/adapters/bitget_futures_adapter.py`, `trading/exchanges/adapters/okx_futures_adapter.py`
  - trade history / open orders / positions 심볼 표시 정규화
  - 마진 모드 문자열 정규화로 `CROSSED` 계열 입력 오류 완화
- `trading/exchanges/adapters/bithumb_spot_adapter.py`
  - `fetchMyTrades` 미지원 시 주문 내역 폴백으로 거래내역 조회
  - 오류 로그 스팸을 줄이고 실제 지원 여부를 명확히 구분

### ✅ 시간 동기화 오류 수정
- `utils/time_sync.py`
  - 바이낸스 서버 시간과 로컬 시간 비교를 timezone-aware UTC로 통일
  - `offset-naive` / `offset-aware` datetime 비교 오류 방지

### ✅ 260626_Teayu 실로그 기반 재발 방지 보강
- `trading/exchanges/adapters/bybit_futures_adapter.py`, `trading/exchanges/adapters/bitget_futures_adapter.py`, `trading/exchanges/adapters/okx_futures_adapter.py`
  - 포지션 파싱 시 `marginType` 키가 없는 거래소 응답에서도 KeyError 없이 동작하도록 안전 파싱으로 변경
  - `contracts`, `side`, `margin_type`를 `info` 폴백까지 포함해 추출하여 거래소별 필드 차이를 흡수
- `trading/exchanges/adapters/mirae_asset_stock_adapter.py`
  - KIS/미래에셋 토큰 발급 경로를 JSON + form-urlencoded 이중 시도로 보강
  - `appkey/appsecret` + `appKey/appSecret` 키 변형을 모두 시도해 브로커 게이트웨이 차이 흡수
  - 브로커별 로그 라벨을 분리해 한국투자증권 장애를 미래에셋 장애로 오인하지 않도록 정리

### ✅ GitHub 기반 수동 업데이트 확인 버튼 추가 (update.exe 없이)
- `ui/settings_modern.py`
  - 설정 `📋 업데이트` 탭에 `업데이트 확인 (GitHub)` / `최신 릴리즈 열기` 버튼 추가
  - GitHub API(`releases/latest`) 기준 최신 버전 확인 로직 추가
  - 저장소 경로 오타/이관 상황을 고려해 복수 저장소를 순차 조회하도록 폴백 구성
  - 최신/업데이트 가능/조회 실패 상태를 탭 내 상태 라벨로 즉시 표시

### ✅ Windows 빌드/업로드 자동화 파이프라인 추가
- `.github/workflows/windows-release.yml`
  - `v*` 태그 푸시 또는 수동 실행 시 Windows 빌드 후 GitHub Release 자동 업로드
  - 업로드 자산: `AITrading.exe`, `version.txt`, `release_notes.md`, `release-manifest.json`
- `scripts/generate_release_assets.py`
  - `config/app_version.py` 기준 `version.txt` 자동 생성
  - `docs/CHANGELOG.md` 최신 섹션을 `release_notes.md`로 자동 추출
  - exe sha256 포함 `release-manifest.json` 자동 생성

## 2026-06-17 - v3.8.9.22 릴리스 (사용자 안내 자동화 + SaaS 기준 정합화)

### ✅ 사용자 안내 자동화 강화
- `ui/widgets/user_manual_widget.py`
  - `지원요약/3분 점검본/사용자 안내문`에 Python 버전·비트수, 다운로드 링크, 즉시 조치 순서를 자동 포함
  - 운영자가 수동으로 문구를 작성하지 않아도 사용자 전달 파일만으로 실행 안내가 가능하도록 보강

### ✅ SaaS 판단 문구 정합화
- `docs/BROKER_EXPANSION_ROADMAP.md`, `docs/UPDATE_PLAN.md`
  - 증권사 확장 판단은 "API 존재"가 아니라 개인 사용/서버 동작/다중계좌/약관 허용 4개 기준으로 설명하도록 정리

---

## 2026-06-16 - v3.8.9.22 릴리스 (Python 런타임 표시 + 키움 32bit 안내 + KIS 상태 정리)

### ✅ 사용자 안내 정합화
- `ui/settings_modern.py`
  - 설정의 `AI 실행 준비도 진단` 주변과 업데이트 탭에 현재 OS, OS 비트수, Python 버전/비트수를 표시
  - 브로커 호환성 예시(바이낸스/업비트/키움)를 함께 보여 원인 파악을 쉽게 보강
  - 키움 OpenAPI+ 연결 실패 시 32bit Python 안내를 "현재 앱 OpenAPI+(ActiveX) 경로 기준 권고"로 표기
  - 버튼: `32bit Python 다운로드`, `설치 가이드 보기`

- `ui/widgets/user_manual_widget.py`
  - 한국투자증권(KIS)을 구현 완료 기준으로 사용자 안내와 상태표에 반영

### ✅ 빌드/문서 동기화
- `build_safe.py`, `aiautotrade.spec`
  - `trading.exchanges.adapters.korea_investment_stock_adapter` hidden import 추가
- `docs/BUILD_GUIDE.md`, `docs/DEPLOY_CHECKLIST.md`
  - 동적 스펙에 증권 어댑터 4종과 키움 32bit 권장 환경 설명 반영

---

## 2026-06-15 - v3.8.9.22 릴리스 (증권 연결 지원요약 전달력 강화 + 3분 점검본 저장 추가)

### ✅ 사용자 전달/점검 UX 개선
- `ui/settings_modern.py`
  - `증권 연결 지원요약` 상단에 `개발자 전달 핵심요약` 섹션 추가
  - 최근 로그 기반 교차 태깅 이력(주식 컨텍스트 + ex=binance) 감지 문구를 원인 후보에 포함
  - `증권사 1차 진단`이 입력값만 보고 "치명 이슈 없음"으로 오판정하던 경로 수정
  - 최근 실행 로그에서 ActiveX/미연결 반복 실패를 감지하면 즉시 `점검` 항목으로 노출
  - 점검 팝업 버튼 추가: `3분 점검본 저장`
  - 저장 파일: `stock_broker_3min_checklist_YYYYMMDD_HHMMSS.txt`

### ✅ 진단 스크립트 정확도 개선
- `scripts/stock_d1_preflight.py`
  - 설정 파일 로딩 우선순위를 계정별 설정(`data/*/config/settings.json`) 중심으로 개선
  - 실제 사용자 설정과 다른 파일을 읽어 잘못 판정하는 가능성 완화

### ✅ 교차 태깅 잔존 경로 수정
- `trading/stock_analysis_service.py`
  - 주입된 Recorder 사용 시 `recorder.exchange`를 `broker_name`으로 강제 동기화
  - 키움 컨텍스트의 XAI 저장 로그가 이전 거래소 값으로 남는 잔존 케이스 보정

---

## 2026-05-01 - v3.8.9.16 릴리스 (증권 자동매매 제어 의미 정합 + 사용자 안내 동기화)

### ✅ 증권 자동매매 제어 의미 정리
- `ui/dashboard_modern.py`
  - 증권 자동매매 실행 제어를 `START/STOP(AUTO)` 상태 기준으로 정리
  - `stock_auto_trading.enabled`는 실행 스위치가 아니라 하위호환 자동예약 키로만 해석
  - 신규 권장 키 `stock_auto_trading.auto_start` 추가(탭 진입 시 루프 예약 시작 옵션)

### ✅ 설정 기본값/호환성 반영
- `config/settings_template.json`, `config/settings.py`
  - `stock_auto_trading.auto_start=false` 기본값 추가
  - legacy `enabled`와 병행 호환 유지

### ✅ 증권 AI 자동매매 로직/XAI 고도화 반영
- `trading/stock_analysis_service.py`
  - 시장 레짐 감지 + 레짐 기반 유효 임계값 반영
  - 거래 피드백(최근 성과) 연결
  - 심볼/사이클 XAI 로그에 `market_regime`, `effective_*_threshold` 확장

### ✅ 사용자 가시성(대시보드/메뉴얼) 동기화
- 대시보드 버전 기준 상향: `v3.8.9.16`
- 사용자 가이드(`docs/USER_GUIDE.md`)에 증권 변경점/제어 의미/사용자 실행 흐름 업데이트
- 인앱 사용자 메뉴얼(`ui/widgets/user_manual_widget.py`) 업데이트 탭에 `v3.8.9.16` 변경 내역 추가

---

## 2026-05-01 - 증권 AI 자동매매 정합성 보강 (배포 버전 변경 없음)

### ✅ 코인 시스템과의 구조 정합성 강화
- `trading/stock_analysis_service.py`
  - KOSPI/프록시 기반 시장 레짐 감지(`bull`/`bear`/`volatile`/`range`) + 5분 캐시 적용
  - 레짐 기반 동적 임계값 조정 연결
    - `bull`: 매수 완화 / 매도 강화
    - `bear`: 매수 강화 / 매도 완화
    - `volatile`: 양방향 보수화
  - `run_auto_trade_cycle()`에서 고정 임계값 대신 유효 임계값(`effective_*_threshold`) 사용
- `trading/stock_analysis_service.py`
  - 종목별 최근 거래 성과 피드백(`trade_log`)을 분석 점수에 반영
  - `StrategyEngine` 기본 활성 정책 적용(레짐/합의점수/쿨다운)
  - `ProfitabilityValidator` 기본 활성 정책 적용(데이터 부족 시 bypass)

### ✅ XAI/로그 일관성 보강
- 심볼 의사결정 로그(`stock_auto_trade_symbol`) 전 분기에 `market_regime`, `effective_*_threshold` 포함
- 사이클 요약 로그(`stock_auto_trade_cycle`, `auto_trade_cycle`)에 레짐/유효 임계값 포함

### ⚠️ 확인된 잔여 과제(코드 기준)
- `ui/settings_modern.py`: 증권 자동매매는 START/STOP(AUTO)로 제어하도록 정리되었고, 설정에는 탭 진입 시 자동 예약 시작 옵션(`stock_auto_trading.auto_start`, legacy `enabled`) 및 실주문 전역 토글(`enable_stock_live_order`)을 직관적으로 조작하는 전용 UI가 추가로 필요함

---

## 2026-04-30 - 배포 게이트 크로스 플랫폼 버그 수정 (배포 버전 변경 없음)

### 🐛 버그 수정
- `scripts/release_gate.py`: venv Python 경로 탐지 로직 크로스 플랫폼 호환 수정
  - **증상**: macOS에서 개발한 코드를 Windows에서 빌드 시 `TEST_STOCK` 게이트 FAIL
    - 오류: `C:\...\Python311\python.exe: No module named pytest`
  - **원인**: venv 경로를 Unix 방식(`bin/python`)으로만 탐지하여 Windows에서 `.venv`를 찾지 못하고
    시스템 Python(`Python311`)으로 폴백, 해당 Python에 `pytest` 미설치
  - **수정**: `Scripts/python.exe`(Windows) → `bin/python`(macOS/Linux) → `sys.executable` 순서로 탐지
  - **참조**: `docs/BUILD_GUIDE.md` > 배포 게이트 > 크로스 플랫폼 주의사항

---

## 2026-04-30 - 수익성/오케스트레이션/실행최적화/전략엔진/운영자동화 구현 + 6번 착수 (배포 버전 변경 없음)

### ✅ 1~5 고도화 구현 및 주문 경로 통합
- `trading/profitability_validation.py` 추가
  - 승률/샤프/MDD/기대값/워크포워드 기반 전략 ON/OFF 판정
- `trading/portfolio_orchestrator.py` 추가
  - 자산군 리스크 버짓/상관관계 기반 자본 배분 및 수량 결정
- `trading/execution_optimizer.py` 추가
  - 주문 타입 선택, 재시도, 타임아웃, 슬리피지 상한 제어
- `trading/strategy_engine.py` 추가
  - 레짐 필터, 신호 합의 점수, 심볼 쿨다운
- `trading/ops_automation.py` 추가
  - 이상 탐지, 롤백 액션 생성, 일일 브리핑 생성
- `trading/stock_analysis_service.py`
  - `run_auto_trade_cycle()`에 1~5 계층 통합 적용

### ✅ 6번 착수 (생활금융 품질 지표)
- `trading/life_finance_quality.py` 추가
  - 추천 정확도/상담 전환율/유지율 집계 리포트 1차 구현

### 🧪 검증
- `python -m pytest tests/test_advanced_trading_layers.py tests/test_stock_analysis_service.py -q --tb=no`
  - 결과: **50 passed**

## 2026-04-30 - 문서 정합성/운영 전환 기준선 동기화 (배포 버전 변경 없음)

### ✅ 증권 운영 전환 기준선 명시
- `scripts/release_gate.py`: `--profile prekey` 추가
  - 키 입력 전 완료 가능한 항목(TEST_STOCK/MODE_MATRIX/MOCK_HARDENING/EXCHANGE_READINESS_REPORT) 필수화
  - 실브로커 readiness는 `release`에서만 필수
- `build_safe.py`: `--gate-profile prekey` 지원
- `scripts/stock_keyday_one_shot.py` 신규
  - 키 입력 당일: readiness report + precheck + 브로커별 strict readiness를 원샷 검증

### ✅ 증권/거래소 진단 고도화 반영
- `scripts/exchange_readiness_check.py`: root_cause/action 분류 및 요약 출력 추가
  - 예: `missing_credentials`, `authentication_failed`, `connection_failed`, `client_unavailable`, `ready`

### ✅ 문서 기준선 정리
- `UPDATE_PLAN.md`: 배포 필수선 vs 후속 고도화선 분리, 6번(생활금융/다음 도메인) 착수 조건 명시
- `ARCHITECTURE.md`: prekey/key-day/release 운영 게이트 경로 반영
- `USER_GUIDE.md`: 사용자 실행 기준(설정 입력 → key-day 검증 → 사용) 및 한계(수익 보장 불가) 명시
- `NOAHAI_TECHNICAL_WHITEPAPER.md`: 운영 전환 기준선(판단/집행 책임 경계 + prekey/key-day) 부록 반영

### 🧪 검증
- `python -m pytest -q --tb=no`
  - 결과: **239 passed, 6 skipped, 5 warnings**


## 2026-04-28 (이어서) - 대시보드 UX 개선 + 가드레일/ETF 신호 분기 강화 (v3.8.9.15)

### ✅ 대시보드 UX 개선

#### 잔고 자동 갱신 (7초 주기)
**파일**: `ui/dashboard_modern.py`
- `create_exchange_balance_section()`: 최초 1회 조회 후 7초 주기로 자동 갱신
- 이전: 탭 진입 시 1회만 조회 → 이후 이후 최신 잔고 미반영

#### 거래소 상태 배지 정확성 개선
- `_check_actual_exchange_status()`: `main_app.state` 및 `_running_exchanges` 에서 실제 실행 여부 조회
- 이전: 항상 `False` 반환 → 항상 "Stopped" 표시 오류 수정

#### 토글 ↔ 전역 상태 동기화
- 개별 거래소 토글 ON/OFF 시 `_running_exchanges` 세트와 `_update_global_status_ui()` 호출 동기화
- 이전: 토글과 상단 전역 상태 UI가 연동되지 않던 버그 수정

#### 설정 저장 시 탭 중복 재빌드 제거
- `refresh_after_settings_change()`: `create_service_sub_tabs('blockchain')` 중복 호출 1회 제거

---

### ✅ 가드레일 테스트 강화 (12 → 14개)
**파일**: `tests/test_stock_order_guardrails.py`
- `test_guardrail_rejects_max_quantity_exceeded`: `max_quantity` 한도(기본 10,000주) 초과 시 차단 검증
- `test_guardrail_rejects_outside_market_hours`: 장외 시간(평일 09:00~15:30 외) 주문 차단 검증

### ✅ ETF/주식 자동매매 신호 분기 강화
**파일**: `trading/stock_analysis_service.py`
- `evaluate_trade_signal()`: `is_etf` 플래그에 따라 분기된 신호 로직 적용
  - 주식: score(모멘텀/수익률) + momentum 방향 → BUY/SELL/HOLD
  - ETF: `etf_risk` 우선 평가 → alert=SELL, ok+고점수=BUY, warn=HOLD
- `analyze_symbol()`: ETF 분석 시 `etf_risk` 필드를 결과 딕셔너리에 추가
**파일**: `tests/test_stock_analysis_service.py`
- `test_evaluate_trade_signal_etf_alert_is_sell`: ETF alert → SELL 검증
- `test_evaluate_trade_signal_etf_ok_high_score_is_buy`: ETF ok + 고점수 → BUY 검증
- `test_evaluate_trade_signal_etf_warn_is_hold`: ETF warn → HOLD 검증

**테스트 결과**: 172 passed (가드레일 +2, ETF 신호 +3), 6 skipped ✅

---

## 2026-04-28 - AI 애널리스트 버그 수정 + 생활금융 Phase 3 UI 프로토타입 구현 + Phase 1 신용도 개인화 (v3.8.9.15)

### ✅ Phase 1 (AI 어시스턴트 강화) 완료 🎉

**기간**: 2026년 4월 28일 (1~2일 소요)  
**목표**: 신용도 기반 개인화 금융 상담  
**완료도**: 100% ✅

#### Step 1 ✅: 신용도/위험도 입력 UI
- 개인화 프로필 섹션 추가 (금융상품 탭 상단)
- 신용도 드롭다운: "좋음 (750~900)" | "보통 (650~750)" | "낮음 (~650)"
- 위험도 드롭다운: "회피형" | "보수형" | "공격형"
- 프로필 변경 시 자동으로 모든 비교 갱신 (`_on_profile_changed()`)

#### Step 2 ✅: 신용도 기반 점수 조정 로직
**파일**: `trading/life_finance_products.py`
- `apply_credit_adjustment_to_loans()`: 신용도별 금리 조정
  - 좋음 🟢: -0.5% (금리 우대)
  - 보통 🟡: 0% (표준)
  - 낮음 🔴: +0.5% (금리 불리)
- `apply_credit_adjustment_to_savings()`: 신용도별 이자 조정
  - 좋음 🟢: +0.3% (이자 우대)
  - 보통 🟡: 0% (표준)
  - 낮음 🔴: -0.1% (이자 불리)

**파일**: `ui/widgets/life_finance_widget.py`
- `_run_loan_compare()` 신용도 적용
- `_run_savings_compare()` 신용도 적용
- 비교 결과 요약에 "신용도 기반 예상 금리" 표시

#### Step 3 ✅: AI 상담 강화 (자연어)
**파일**: `trading/life_finance_assistant.py`
- `FinanceContext`에 신용도/위험도 필드 추가
- `process_command()` 메서드에 신용도/위험도 파라미터 추가
- 3개 금융상품 핸들러 (`_handle_compare_loan`, `_handle_compare_insurance`, `_handle_compare_savings_product`) 신용도 기반 조정 적용
- AI 응답에 "당신의 신용도(좋음 🟢)를 반영한 예상 금리: 3.75%" 포함

**파일**: `ui/widgets/life_finance_widget.py`
- `_process_assistant_command()` 수정: 신용도/위험도를 AI 어시스턴트에 전달
- 사용자 대화 예시:
  ```
  사용자: "신용도가 좋으면 금리가 얼마나 내려?"
  AI: "당신의 신용도(좋음 🟢)를 반영한 KB국민 주택담보는 
       기본 4.05% → 우대금리 3.75% (0.3% 인하) 예상됩니다."
  ```

#### Step 4 ✅: 메뉴얼 업데이트 + 최종 검증
**파일**: `ui/widgets/user_manual_widget.py`
- 버전 정보 업데이트 (v3.8.9.15 Phase 1)
- CHANGELOG 항목 추가 (신용도 기반 개인화 상담)
- 사용자 경고: "현재는 더미 데이터 기반이지만 신용도 반영 로직은 실제 작동"

**테스트 결과**: 170 passed, 6 skipped ✅

---

### ✅ 반영 완료 (이전 항목)

#### 버그 수정
- **AI 애널리스트 `send_message()` 버그 수정** (`ui/dashboard_modern.py`)
  - `_request_ai_analyst()` 메서드에서 `hasattr(aw, 'send_message')` → `hasattr(aw, 'send_ai_message')` 수정
  - `aw.send_message()` → `aw.send_ai_message()` 수정 (실제 메서드명과 불일치로 카드 클릭 시 아무 동작 없던 버그)
  - AI 어시스턴트 연결 전 `set_service_context('ai_analyst')` 호출로 컨텍스트 동기화 추가

#### 🧪 생활금융 Phase 3 UI 프로토타입 구현 (데모·MVP 단계)
**상태**: 본 기능은 R&D 고도화 대상이며, 프로토타입/데모 단계입니다. 실제 금융사 API 연동은 향후 별도 R&D 과제입니다. (상세: [LIFE_FINANCE_PRODUCT_COMPARISON_ANALYSIS_20260429.md](docs/LIFE_FINANCE_PRODUCT_COMPARISON_ANALYSIS_20260429.md))

- **`_setup_products_tab()` 전면 재작성**
  - 상단 조건 입력 패널 추가 (다크 카드 `#0f172a`)
  - 대출: 금액(만원) + 기간(개월) 입력 필드
  - 보험: 월 예산(원) + 종류 드롭다운 (전체/종합/건강/가족)
  - 예적금: 원금(만원) + 기간(개월) 입력 필드
  - 우측 버튼 패널: 개별 비교 버튼 3개 + 전체 비교 버튼 1개
  - 탭 진입 시 자동으로 전체 비교 실행 (`after(200, ...)`)
- **시각적 비교 테이블 `_draw_product_comparison_table()` 신규 구현**
  - 카드 기반 레이아웃 (어두운 테마 `#1e293b`, border `#334155`)
  - 컬러 배지 타이틀 (대출 파랑 `#1d4ed8`, 보험 그린 `#065f46`, 예적금 보라 `#7c3aed`)
  - 헤더 행 + 데이터 행 grid 레이아웃 (col별 비율 균등 배분)
  - 최우수 상품 행 강조: 배경 `#1e3a5f`, 순위번호 `#fbbf24`, 굵은 폰트
  - 하단 🥇 추천 뱃지 + 요약 텍스트
  - 섹션 ID 기반 기존 카드 파괴 후 재생성 (반복 클릭 안전)
- **`_run_loan_compare()`, `_run_insurance_compare()`, `_run_savings_compare()` 신규 추가**
  - 입력 필드 파싱 + 유효하지 않은 입력 시 기본값 fallback
  - 실시간 비교 결과를 테이블로 렌더링
- **하위 호환 메서드 유지**: `_compare_loan/insurance/savings_products()`, `_update_products()`, `_draw_product_result_card()`

#### 금융상품 데이터 현실화 (더미 데이터)
- 더미 A/B/C 은행 → 실제 국내 주요 금융사로 교체 (**데모 목적**):
  - `_load_loan_catalog()`: 8개 상품 (KB국민, 신한, 하나, 우리, 카카오뱅크, 토스뱅크, SC제일, NH농협)
  - `_load_insurance_catalog()`: 7개 상품 (삼성생명, 현대해상, DB손보, 한화생명, KB손보, 메트라이프, 흥국생명)
  - `_load_savings_catalog()`: 8개 상품 (KB국민, 신한, 카카오뱅크, 토스뱅크, 우리, NH농협, 하나, 케이뱅크)
- 정적 메서드 `_load_*_catalog()`로 분리 → 향후 외부 API 연동 시 해당 메서드만 교체
- ⚠️ **주의**: 실제 금리/보험료는 시뮬레이션 데이터이며, 실제 가입 기능은 구현되지 않았습니다.

### 🧪 검증
- `python -m pytest tests/ -q`
  - 결과: **170 passed, 6 skipped** (기존 대비 변동 없음)

---

## 2026-04-28 - 증권 주문 경로 가시화 + 주식/ETF 분석 근거 분리

### ✅ 반영 완료
- 증권 주문 결과 메타데이터 확장
  - `stock_mock_adapter.py`: `execution_mode=mock`, `api_type=mock`, `success=True` 노출
  - `kiwoom_stock_adapter.py`, `shinhan_stock_adapter.py`, `mirae_asset_stock_adapter.py`: `execution_mode=live_api`, `api_type`, `api_version`, `success` 반환
- 대시보드 증권 주문 상태 문구 개선
  - `ui/dashboard_modern.py`: 주문 성공 시 `모의주문 경로` 또는 `실주문 경로(api_type)`를 함께 표시
  - 주문 결과 해석 기준을 비표준 `success` 키 단독 의존에서 `status + success` 조합으로 정규화
  - stock adapter 호출 계약을 `quantity` 우선으로 정규화하고, 구형 호출 방식은 fallback으로만 유지
  - 실주문 1차 안전장치: `enable_stock_live_order`(전역) 또는 증권사별 `allow_live_order`가 꺼져 있으면 live 경로 주문 차단
- 주식/ETF 분석 결과 분기 가시화
  - `trading/stock_analysis_service.py`: `analysis_type`, `score_model`, `reasoning` 필드 추가
  - 주식: 모멘텀/거래량 중심 설명
  - ETF: NAV괴리/추적오차/거래대금 중심 설명
- 설정 템플릿/기본값 확장
  - `config/settings_template.json`, `config/settings.py`에 `enable_stock_live_order=false` 추가
  - `stock_broker_configs.*.allow_live_order=false` 기본값 추가
- 증권 자동매매 1차 루프 연결
  - `trading/stock_analysis_service.py`: `evaluate_trade_signal()`, `run_auto_trade_cycle()` 추가 (신호→주문 사이클)
  - `ui/dashboard_modern.py`: `stock_auto_trading` 설정 기반 주기 실행 루프 추가
  - live 경로는 기존 feature flag(`enable_stock_live_order`/`allow_live_order`)와 연동되어 자동매매에서도 동일하게 차단/허용됨
  - 자동매매 심볼별 결정(`stock_auto_trade_symbol`)과 사이클 요약(`stock_auto_trade_cycle`)을 XAI에 저장
  - 자동매매 성공 주문을 `trade_log`에 즉시 기록하여 수동주문과 동일한 기록 가시성 확보
- 설정 템플릿/기본값 확장(자동매매)
  - `config/settings_template.json`, `config/settings.py`에 `stock_auto_trading` 기본 구조 추가
- 종목 검색 고도화 1차
  - `ui/dashboard_modern.py`: 최근검색/즐겨찾기/원클릭 재검색 UI 추가
  - 분석 카드에서 종목 즐겨찾기 토글 지원
  - `analysis_data`에서 `symbol` 기반 코드 폴백 처리로 카드 표기 안정화
  - `config/settings_template.json`, `config/settings.py`에 `stock_search_profile` 기본 구조 추가
- 종목 검색 고도화 2차
  - `ui/dashboard_modern.py`: 자동완성 추천 영역 추가
  - 브로커 심볼 인덱스 캐시 기반 코드/종목명 부분일치 추천 지원
  - 추천 항목 클릭 시 원클릭 검색 실행
- 자산 통합 확장 1차
  - `ui/dashboard_modern.py`: 자산군 집중도(HHI) 계산 추가
  - crypto/stock 일별 손익 기반 상관계수 계산 추가
  - 집중도/상관계수/비중 조건 기반 리밸런싱 추천 액션 동적 생성

### 🧪 검증
- `python -m pytest tests/test_stock_integration.py -q`
  - 결과: **47 passed, 6 skipped**
- `python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
  - 결과: **79 passed, 6 skipped**
- `python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py tests/test_stock_order_guardrails.py -q`
  - 결과: **91 passed, 6 skipped**
- `python -m pytest tests/test_stock_integration.py -q`
  - 결과: **48 passed, 6 skipped**
- `python -m pytest tests/test_stock_analysis_service.py -q`
  - 결과: **35 passed**
- `python -m pytest tests/test_stock_analysis_service.py tests/test_stock_integration.py -q`
  - 결과: **84 passed, 6 skipped**
- `python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
  - 결과: **85 passed, 6 skipped**
- `python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
  - 결과: **85 passed, 6 skipped**
- `python -m pytest tests/test_stock_integration.py tests/test_stock_analysis_service.py -q`
  - 결과: **85 passed, 6 skipped**

### 🎯 의미
- 사용자는 이제 증권 주문이 Mock인지 실주문 API 경로인지 UI에서 즉시 구분할 수 있음
- 주식과 ETF의 분석이 내부적으로만 다른 것이 아니라, 결과 카드와 AI 컨텍스트에도 차이가 드러남
- 증권 자동매매는 1차로 신호→주문 사이클이 연결되어, AUTO 상태에서 mock 환경 기준 반복 실행이 가능해짐
- API 키/실계좌가 없는 환경에서는 실연동 고도화를 강행하지 않고 기록 후 다음 순서로 이월
- 검색 UX는 최근검색/즐겨찾기 중심으로 1차 개선되어 반복 조회 작업 시간이 단축됨
- 검색 UX는 자동완성/부분일치 추천까지 확장되어 종목 탐색 속도가 추가 개선됨
- 자산 통합 화면은 고정 문구 중심에서 데이터 기반 리스크/리밸런싱 안내로 확장됨

## 2026-04-25 - Phase 1/2/3 실제 기능 구현 완료

### ✅ Phase 1: 주식 종목 검색/분석 기능 - 완료
- **기능**: 증권 탭 내 종목코드 입력 → 분석 카드 표시
- **구현**: 
  - `_ensure_stock_info_tab()`: 검색 UI 프레임 추가 (CTkEntry + CTkButton)
  - `_search_stock_symbol()`: 종목코드 검색 로직 (StockAnalysisService 통합)
  - `_display_stock_analysis_card()`: 분석 결과 카드 렌더링 (가격/등락률/AI점수/브로커)
- **파일**: `ui/dashboard_modern.py` (라인 1888~2250)
- **테스트**: 문법 오류 없음 (get_errors 검증 완료)

### ✅ Phase 2: 자산 통합 실제 데이터 패널 - 완료
- **기능**: "🧭 자산 통합" 탭 준비중 → 실데이터 표시
- **구현**:
  - 통합 자산 현황: DB 쿼리 기반 총 자산/누적 손익 표시
  - 자산군별 비중: 암호화폐/주식 % 진행률 바 표시
  - 포트폴리오 리스크: 집중도/최대손실/회전율 카드
  - 추천 액션: 재균형/상관관계/리스크 관리 3가지 가이드
- **파일**: `ui/dashboard_modern.py` `show_real_estate_content()` (라인 5349+)
- **데이터 소스**: sqlite3 trade_log 테이블 (entry_amount, pnl)
- **테스트**: 문법 오류 없음

### ✅ Phase 3: 생활금융 MVP - 완료
- **기능**: "💳 생활금융 서비스" 탭 준비중 → 월간 재무 분석
- **구현**:
  - 월별 현금흐름 입력: 수입/고정비/변동비 입력 폼 (CTkEntry)
  - 저축 가능액 자동 계산: 수입 - (고정비 + 변동비)
  - 월간 재무 현황: 총 지출/저축 가능액 컬러 코드 표시
  - 투자 여력 분석: 긴급자금/단기/장기 자산 배분 가이드
  - 생활금융 팁: 지출기록/고정비최적화/자산연계 3가지
- **파일**: `ui/dashboard_modern.py` `show_other_investment_content()` (라인 5546+)
- **테스트**: 문법 오류 없음

### 🎨 UI/UX 특징 (공통)
- **색상 시스템**: 긍정(🟢#22c55e)/경고(🟡#fbbf24)/위험(🔴#ef4444)
- **카드 기반**: CTkFrame (fg_color="#1a1f2e", corner_radius=12, border)
- **데이터 기반**: 실제 DB/사용자 입력 (placeholder 아님)
- **언어 정화**: 모든 "향후"/"예정"/"2개월" 제거, 현재 상태만 표시

### 🧪 검증
- **구문**: `get_errors()` 완료 (0 오류)
- **임포트**: `trading.stock_analysis_service` 경로 검증 필요 (런타임 테스트 대기)
- **테스트**: 실제 거래 데이터 기반 통합 테스트 (다음 단계)

### 📋 문서 업데이트
- `UPDATE_PLAN.md`: "현재 구현 상태 (2026-04-25)" 섹션 추가
- `CHANGELOG.md`: 문서 정합성 항목 동기화

---

## 2026-04-24 - 서비스 전환/음성 배포/AI 애널리스트 동기화

### ✅ 반영 완료
- 서비스 전환 시 정보 탭 보호 정책을 서비스별로 분리
  - `blockchain`: `🪙 코인 정보` 유지
  - `stock`: `🪙 종목 정보` 유지
  - 결과: 주식/증권 전환 시 코인 정보 탭 잔존 문제 방지
- 상위 버튼 `🤖 AI애널리스트` 클릭 경로 보강
  - 버튼 클릭 즉시 `switch_service("ai_analyst")` 호출
  - 결과: 화면 전환 누락 방지
- `show_ai_analyst_content()`를 준비중 화면에서 실사용형 카드 UI로 교체
  - 포트폴리오/신호/리스크/조언/성과/뉴스 6개 분석 카드
  - 카드 클릭 시 AI 어시스턴트로 분석 요청 위임
- 서비스 컨텍스트 동기화 보강
  - `MarketTrendWidget.set_service_context()` 추가
  - `AILearningWidget.set_service_context()` 추가
  - 서비스 전환 시 시장 트렌드/AI 학습 위젯 동기 갱신

### 🎤 음성(STT/TTS) 배포 정합
- `requirements.txt`에 STT 의존성 추가
  - `SpeechRecognition>=3.10.0`
  - `pyaudio>=0.2.14`
- `aiautotrade.spec` hiddenimports에 음성 모듈 추가
  - `speech_recognition`, `pyaudio`

### 🧪 검증
- `python -m pytest tests/ -q`
  - 결과: **125 passed, 6 skipped, 2 warnings**

### ⚠️ 현재 남은 범위(의도된 상태)
- `🏠 부동산`, `💎 기타투자`는 여전히 준비중 화면(로드맵 단계)
- 주식/ETF 실증권 live 전구간 자동화는 증권사/운영 환경별 추가 검증 필요

---

## 2026-04-23 - 주식/ETF 통합 검증 기준 정리 (문서 정합 업데이트)

### ✅ 검증 완료된 항목 (코드/테스트 기준)
- 통합 테스트: `tests/test_stock_integration.py` 기준 **46 passed, 6 skipped, 0 failed**
- `ExchangeFactory.create_stock_exchange()`에 `api_type` 분기 반영
  - `mock` 선택 시 `StockMockAdapter` 생성
  - `openapi/rest` 선택 시 증권사 어댑터 경로 유지
- 설정 UI에 증권사별 API 선택 항목 추가
  - `api_type`: openapi/rest/mock
  - `api_version`: 증권사별 버전 선택
- 설정 저장/로드 정합성
  - `ui/settings_modern.py`에서 `api_type/api_version` 저장/로드 연결
  - `data/settings.json`의 `stock_broker_configs`에 `api_version` 기본값 반영
- ETF 판별 회귀 수정
  - 테스트 기준 ETF 코드(`114800` 포함) 판별 이슈 보완

### 🟢 현재 동작 범위 (사용자 체감 기준)
- 코인(블록체인)과 증권(주식/ETF) 모두 설정 → 어댑터 생성 → 서비스 탭 반영의 흐름은 일관된 구조로 동작
- 증권 서비스는 주식/ETF 통합 `stock` 컨텍스트로 동작
- AI 어시스턴트는 서비스 컨텍스트(`blockchain`/`stock`)에 따라 질문/안내 문구가 전환

### 🟡 현재 한계 (미완/주의)
- 일부 실증권 연동은 플레이스홀더 구현이 남아 있어, 빌드/환경에 따라 실주문·실잔고가 즉시 완전 동작하지 않을 수 있음
- 문서 중 과거 단계 계획 문서는 일부 항목이 현재 상태와 다를 수 있으므로, 본 항목(2026-04-23)을 최신 기준으로 우선 적용

### 🔜 다음 우선 개발 항목
1. 키움/신한/미래에셋 실연동 경로(연결, 잔고, 포지션, 주문) 단계별 실장
2. 증권 컨텍스트에 ETF 전용 지표(추적오차/NAV 괴리/거래대금) 조건부 주입
3. 설정 화면에서 `api_type` 선택 시 `api_version` 목록 동적 제한(잘못된 조합 방지)
4. 사용자 매뉴얼/상태 문서의 중복·구버전 체크리스트를 최신 상태 기준으로 정리

### ➕ 당일 추가 반영 (2026-04-23)
- `ui/settings_modern.py`
  - `api_type` 선택 시 `api_version` 후보를 증권사별 유효 조합으로 자동 제한
  - 설정 로드 시 유효하지 않은 `api_version` 값 자동 보정
- `ui/widgets/ai_assistant_widget.py`
  - stock 컨텍스트에서 ETF 보유가 있을 때 추적오차/NAV 괴리/거래대금 지표를 조건부 주입
- `config/settings_template.json`
  - 증권사별 `api_version` 기본값 추가 (`pykiwoom`/`solapi`/`miraemts`)
- 문서 동기화
  - `docs/UPDATE_PLAN.md`, `docs/USER_GUIDE.md`, `docs/DEV_GUIDE.md`, `docs/README.md`, `docs/BUSINESS_PROPOSAL_2026.md`
  - 최신 구현 기준(완료/미완/다음 순서) 반영 및 레거시 중복 정리 기준 명시

---

## 2026-04-28 - v3.8.9.15 전면 고도화 패치

### 🐛 버그 수정
- `ui/dashboard_modern.py`
  - **블록체인↔주식 탭 전환 버그 수정**: `show_blockchain_content()`가 탭 내용을 재빌드하지 않아
    blockchain→stock→blockchain 전환 후 거래통계/시장트렌드에 주식 내용이 잔존하던 문제 해결
    - `show_blockchain_content()` 내에 `_ensure_trading_stats_tab()` 및 `_ensure_trend_tab()` 호출 추가

### ✅ 기능 개선
- `ui/dashboard_modern.py`
  - **주식 증권사 드롭다운**: `enabled_stock_brokers` 미설정 시 kiwoom만 폴백하던 것을
    kiwoom/shinhan/miraeAsset 전체를 폴백으로 표시하도록 변경 (AI학습·서비스전환 소스 드롭다운 동일 적용)
  - 버전 표기 `Beta 3.8.9.14` → `Beta 3.8.9.15` 갱신

- `data/settings.json`
  - `enabled_stock_brokers: []` → `["kiwoom","shinhan","miraeAsset"]` 기본값 설정

- `ui/widgets/market_trend_widget.py`
  - **시장트렌드 AI전략 섹션 '미제공' 제거**:
    - 커스텀 지표 직접 추가 UI: `_custom_indicators` 목록 기반 실시간 표시
    - 기관/고래 활동 연계 분석: long_short_ratio·OI 기반 고래 매수/매도/중립 판단 표시
    - 전략 신뢰도 점수: 가용 지표 수(RSI/MACD/거래량/롱숏비 등) 기반 0~100 점수 및 바 표시

- `ui/widgets/ai_assistant_widget.py`
  - **자산통합(real_estate) 서비스 AI 프로필 추가**: 자산 진단·리밸런싱·리스크·노후준비 퀵질문 9개
  - **생활금융(other_investment) 서비스 AI 프로필 추가**: 대출비교·보험점검·적금추천·현금흐름 퀵질문 9개
  - **AI 애널리스트(ai_analyst) 서비스 AI 프로필 추가**: 시장진단·시나리오·멀티에셋 퀵질문 5개
  - **커스텀 지표 자연어 명령 지원**:
    - `지표 추가 [이름]` → MarketTrendWidget에 즉시 반영
    - `지표 삭제 [이름]` / `지표 목록` 명령 지원

- `ui/widgets/user_manual_widget.py`
  - v3.8.9.15 릴리스 노트 및 업데이트 날짜 갱신

### 📦 테스트/스크립트
- 기존 테스트 모두 통과 (test_stock_nonkey_hardening, test_life_finance_assistant 등)

---

## 2026-04-22 - v3.8.9.14 거래통계-실거래 정합성 패치

### 🔧 핵심 수정
- `trading/recorder.py`
  - `get_trade_history()`의 `SELECT *` 결과 매핑을 실제 `trade_log` 컬럼 순서에 맞게 정정
  - `side/entry_price/pnl/entry_time/exit_time/exchange` 키가 올바른 원본 데이터로 반환되도록 수정
- `ui/widgets/ai_report_widget.py`
  - 최근 거래 집계 SQL에 `exit_time IS NOT NULL` 조건 추가
  - 미청산 포지션이 총거래 수/승률 계산에 포함되던 왜곡 방지
- `trading/unified_trader.py`
  - `_update_trade_stats_unified()`에 `losing_trades` 집계 추가
  - 거래 통계 업데이트 시 `save_exchange_trade_stats()`를 통해 DB 즉시 동기화
  - 청산 AI 분석 결과를 `Recorder.save_ai_trade_analysis()`에 연결하여 다중거래소 XAI 저장 누락 보완
  - 포지션 복구 시 거래소 오픈오더에서 TP/SL 가격을 복원하도록 보강
  - TP/SL 재발주 경로에서 `Position` 객체를 dict처럼 접근하던 수량 참조 버그 수정
- `trading/trader.py`
  - 바이낸스 청산 경로에 익절/손절 AI 분석 호출 추가
  - 청산 AI 분석 결과를 `Recorder.save_ai_trade_analysis()`에 저장하도록 연결하여 바이낸스 경로 XAI 저장 일원화
- `trading/exchange_manager.py`
  - `validate_exchange_connection()` 강화: API 키가 있는 거래소는 인증 포함 잔고 조회까지 통과해야 연결 성공으로 판정
  - 인증 오류 문자열 판별 헬퍼 추가로 `invalid_api_keys` 상태 인식 개선
  - CCXT 잔고 조회 실패 시 `client_unavailable/connection_failed/invalid_api_keys` 상태코드 명시
- `trading/exchanges/adapters/upbit_spot_adapter.py`
  - `validate_credentials()`에서 실제 `fetch_balance()` 인증 호출까지 수행하도록 강화
- `trading/exchanges/adapters/bithumb_spot_adapter.py`
  - `validate_credentials()`에서 실제 `fetch_balance()` 인증 호출까지 수행하도록 강화
- `trading/exchanges/adapters/binance_futures_adapter.py`
  - `get_account_info()` 추가로 ExchangeManager 공통 계정조회 경로와 호환
- `scripts/exchange_readiness_check.py`
  - 국내(업비트/빗썸) → 해외(Bybit/OKX/Bitget/Binance) 순서로 준비도 자동 점검 스크립트 추가

### 🧭 버전/문서 정합
- 대시보드 창 제목 버전: `Beta 3.8.9.14`로 상향
- 인앱 사용자 메뉴얼 버전/업데이트 탭: `v3.8.9.14 (2026-04-22)`로 반영
- `docs/USER_GUIDE.md` 최근 업데이트 섹션에 v3.8.9.14 항목 추가

### ⚠️ 참고 (후속 권장)
- 재시작 후 일부 과거 거래가 `UNKNOWN` 그룹으로 노출되는 케이스는
  `exchange` 누락 레코드 정합성 보정(마이그레이션)과 UI 표시 정책 정리가 추가로 필요함
- 거래소 포지션 복구 시 `tp_price/sl_price=None`으로 시작되는 경로는
  바이낸스 네이티브 경로까지 포함한 복원 로직 정리가 남아 있음
- 재시작 후 `UNKNOWN` 거래소 그룹 노출은 데이터 정합성 보정 정책(마이그레이션) 확정이 남아 있음

---

## 2026-04-21 - AI 어시스턴트 신뢰성 보강

### 🤖 AI 어시스턴트 안정화
- Binance 잔고 조회 결과가 중첩 딕셔너리 구조여도 AI 어시스턴트 컨텍스트에서 안전하게 요약되도록 보강
- Binance 사용 시 기존 trader 경로의 활성 포지션도 AI 어시스턴트가 함께 읽어오도록 개선
- "포지션 늘려줘", "비중 높여줘" 같은 설정 조정형 명령을 더 잘 인식하도록 키워드 확장
- AI API 응답이 불안정하거나 비활성일 때도 현재 앱에서 확인 가능한 거래 현황으로 안전한 로컬 폴백 안내 제공
- OpenAI 호환 API의 base_url 설정이 AI 어시스턴트 초기화 경로에도 반영되도록 보완
- 회귀 방지를 위한 AI 어시스턴트 컨텍스트 테스트 추가

---

## 2026-04-17 - 문서: AI 어시스턴트 가이드 전면 개편

### 📖 문서
- **`docs/AI_ASSISTANT_GUIDE.md`**: `ai_assistant_widget.py` 실제 동작과 정합(전제 조건·컨텍스트·설정 변경 키워드·JSON 자동 적용·채팅으로 불가능한 조작·트러블슈팅·STT/TTS 로드맵 및 관련 문서 링크).
- **`docs/README.md`**: 문서 허브 바로가기에 AI 어시스턴트 가이드 추가.

---

## 2026-04-20 - 문서 정합 및 버전 표기 정상화

### 📖 문서/표기 정정
- 인앱 사용자 메뉴얼에는 사용자용 기능 설명만 남기고, 운영자용 피드백 대응 메모는 별도 문서로 분리
- 2026-03-30, 2026-04-03 버전 표기를 **v3.8.9.12**, **v3.8.9.13** 기준으로 재정렬
- 대시보드 창 제목과 사용자 메뉴얼 제목의 버전 정합 재확인
- 고객 대응용 근거 자료는 별도 피드백 문서에 날짜 기준으로 정리

---

## 2025-12-28 - v3.8.9.9 TP/SL 가격 계산 오류 수정 및 포지션 개수 제한 개선, AI 어시스턴트 개선

### 🔧 TP/SL 가격 계산 오류 수정 및 포지션 개수 제한 개선, AI 어시스턴트 개선

#### 🎯 배경
- **-4006 오류 "Stop price less than zero"**: RSRUSDT, RVNUSDT 등 저가 코인에서 TP/SL 주문 생성 시 오류 발생
- **포지션 개수 제한 불일치**: 설정 파일(max_positions: 3)과 코드(하드코딩된 5) 불일치
- **AI 어시스턴트 거래소 연결 상태 확인 오류**: 거래소가 연결되었음에도 "거래소 연결 불가" 같은 잘못된 답변
- **AI 프롬프트의 모순**: 설정 변경 요청 시 거래소 연결 상태를 혼동하여 잘못된 답변

#### ✅ 주요 변경사항
- **TP/SL 가격 계산 오류 수정**:
  - TP/SL 가격 계산 후 스냅 로직 이전에 유효성 검증 추가
  - SHORT/LONG 포지션별로 올바른 TP/SL 관계 검증
  - 0 이하 값 방지 및 기본값 적용
- **포지션 개수 제한 불일치 수정**:
  - `trader.py`의 `max_positions` 하드코딩값(5)을 설정값(3)으로 변경
  - `unified_trader.py`의 하드코딩된 5 값도 설정값 사용으로 변경
  - **포지션 복구 로직 개선**: 프로그램 재시작 시 `_restore_positions_from_exchange()`에서 `max_positions` 제한 적용
    - 복구 시 최대 3개 포지션만 로드하여 새로운 거래 실행 차단 방지
    - AI 학습 데이터 생성 정상화 (거래 실행 가능 → 학습 데이터 생성 가능)
- **AI 어시스턴트 거래소 연결 상태 확인 개선**:
  - `ExchangeManager.validate_exchange_connection()`에서 BinanceClient의 `is_connected` 속성 확인
  - `is_connected=True`이면 연결 상태로 간주
- **AI 프롬프트 개선**:
  - 설정 변경과 거래소 연결의 관계를 명확히 설명
  - 컨텍스트에 "설정 변경은 거래소 연결 상태와 무관하게 가능" 명시적 안내 추가

#### 🔧 수정된 파일
- `trading/trader.py`:
  - TP/SL 가격 유효성 검증 로직 추가 (2561-2587줄)
  - `max_positions` 기본값 수정 (168줄: 5 → 3)
  - `_restore_positions_from_exchange()` 메서드에 `max_positions` 제한 추가 (5220-5283줄)
- `trading/unified_trader.py`:
  - 포지션 개수 체크 시 설정값 사용 (3602줄)
- `trading/exchange_manager.py`:
  - `validate_exchange_connection()` 개선: BinanceClient의 `is_connected` 속성 확인
- `ui/widgets/ai_assistant_widget.py`:
  - AI 컨텍스트 수집 개선: 거래소 연결 상태 상세 정보 추가
  - AI 프롬프트 개선: 설정 변경과 거래소 연결의 관계 명확화

#### 💡 주요 효과
- ✅ RSRUSDT, RVNUSDT 등 저가 코인에서 -4006 오류 해결
- ✅ 포지션 개수 제한 정상화 (설정값 3개와 코드 로직 일치)
- ✅ 포지션 복구 시 `max_positions` 제한 적용으로 새로운 거래 실행 차단 방지
- ✅ AI 학습 데이터 생성 정상화 (거래 실행 가능 → 학습 데이터 생성 가능)
- ✅ AI 어시스턴트 거래소 연결 상태 확인 정확도 향상
- ✅ AI 답변 정확도 개선 (설정 변경 요청 시 잘못된 답변 방지)
- ✅ 모니터링 데이터 포인트 정상 생성

#### 📋 자세한 내용
- **버그 수정 보고서**: `docs/BUG_FIX_REPORT_20251228.md`
- **AI 어시스턴트 문제 분석**: `docs/AI_ASSISTANT_ISSUES_20251228.md`
- **AI 학습 중단 문제 분석**: `docs/AI_LEARNING_ISSUE_ANALYSIS_20251228.md`
- **포지션 복구 로직 영향 분석**: `docs/POSITION_RESTORE_IMPACT_ANALYSIS_20251228.md`

---

## 2025-12-26 - v3.8.9.8 Binance Algo Order API 마이그레이션 (초기 구현)

### 🔧 Binance 정책 변경 대응: Algo Order API 마이그레이션

**⚠️ 주의**: 이 버전은 초기 구현으로, 서명 생성 규칙 미준수로 `-1022` 오류가 발생했습니다. **v3.8.9.9에서 완전 해결되었습니다.**

#### 🎯 배경
- **Binance 정책 변경 (2025-12-09)**: USDⓈ-M Futures에서 조건부 주문이 Algo Service로 강제 분류됨
- **기존 패치의 한계**: 
  - v3.8.9.6, v3.8.9.7에서 `place_tp_sl_orders()` 사용으로 변경했지만, 내부적으로 여전히 `/fapi/v1/order` 사용
  - Binance 정책 변경으로 인해 조건부 주문이 차단되어 TP/SL 설정 실패 지속

#### ✅ 주요 변경사항
- **조건부 주문 자동 라우팅 구현**: `place_futures_order()`에서 조건부 주문 타입 감지
- **Algo Order API 직접 호출 구현**: `requests.post`를 사용하여 `/fapi/v1/algoOrder` 엔드포인트 직접 호출
- **⚠️ 한계**: 서명 생성 규칙 미준수로 `-1022` 오류 발생 (v3.8.9.9에서 해결)

---

## 2025-01-26 - v3.8.9.7 Binance API 규칙 준수 및 백업 TP/SL 설정 개선

### 🔧 Binance API 규칙 준수 및 백업 TP/SL 설정 개선

#### 🎯 배경
- **Binance API -4120 에러 발생**: "Order type not supported for this endpoint. Please use the Algo Order API endpoints instead."
  - **원인**: `closePosition=True`와 `quantity` 파라미터를 동시에 전송
  - **Binance 공식 규칙**: `closePosition=True`일 때는 `quantity`를 전송하면 안 됨
- **TP/SL 설정 실패 문제**: TP/SL이 설정되지 않아도 거래가 진행되어 즉시 청산
- **백업 TP/SL 값 하드코딩**: 변동성 기반 multiplier가 코드에 고정되어 AI가 조정 불가
- **⚠️ 하드코딩된 경로 문제 (중요)**: 
  - **문제**: `api/binance_client.py`에서 `settings.json` 경로를 하드코딩하여 PyInstaller 패키지 환경에서 설정 파일을 찾지 못함
  - **증상**: 패키지 환경에서 `backup_tp_sl_settings`를 읽지 못해 기본값(고정값)만 사용됨
  - **영향**: 사용자들이 TP/SL이 제대로 설정되지 않는 문제 경험
  - **원인**: `C:\Users\user\AppData\Local\Temp\_MEI29162\data\nwsoft\config\settings.json` 같은 임시 경로를 하드코딩
  - **해결**: `path_utils.get_config_dir()`를 사용하여 올바른 경로 자동 감지
- **⚠️ Binance 정책 변경 미반영**: 
  - 2025-12-09 이후 Binance 정책 변경으로 조건부 주문이 Algo Service로 강제 분류됨
  - 기존 패치(v3.8.9.6, v3.8.9.7)는 내부적으로 여전히 `/fapi/v1/order` 사용
  - **v3.8.9.8에서 완전 해결**: 조건부 주문을 `/fapi/v1/algoOrder`로 자동 라우팅

#### ✅ 주요 변경사항
- **Binance API 공식 규칙 완벽 준수**:
  - `closePosition=True`일 때 `quantity` 파라미터 완전 제거
  - `closePosition=True`는 `STOP_MARKET`, `TAKE_PROFIT_MARKET`에서만 허용
  - `reduceOnly`와 `closePosition` 동시 사용 금지
- **백업 TP/SL 설정을 settings.json으로 이동**:
  - `backup_tp_sl_settings` 섹션 추가
  - 변동성 기반 multiplier (2.0x ~ 3.0x) 설정 가능
  - 안전 범위 제한 (TP: 1.0% ~ 5.0%, SL: 0.8% ~ 3.0%) 설정 가능
  - AI가 시장 상황에 따라 자동 조정 가능
- **TP/SL 역할 명확화**:
  - 실시간 모니터링: 동적 임계값 사용 (주력 청산)
  - 백업 TP/SL: 동적 임계값 × 2~3배 (보험 역할)
  - 실시간 모니터링이 먼저 청산되도록 보장

#### 🔧 수정된 파일
- `api/binance_client.py`:
  - `place_futures_order()`: `closePosition=True`일 때 `quantity` 제거 (line 1941-1964)
  - `closePosition=True`는 `STOP_MARKET`, `TAKE_PROFIT_MARKET`에서만 허용 (line 1930-1934)
  - `reduceOnly`와 `closePosition` 충돌 방지 (line 1936-1939)
  - **`_load_debug_settings()`: 하드코딩된 경로 제거, `path_utils.get_config_dir()` 사용 (PyInstaller 환경 대응)**
- `trading/trader.py`:
  - `execute_single_trade()`: 백업 TP/SL 계산 시 `settings.json` 읽기 (line 2421-2443)
  - `_tp_sl_watchdog()`: 백업 TP/SL 계산 시 `settings.json` 읽기 (line 330-369)
  - **PENDING 상태 처리 개선**: 주문 상태가 PENDING일 때도 성공으로 처리하고 체결 대기 (line 2322-2353)
  - **포지션 관리 개선**: 주문 실패 처리되었지만 실제 포지션이 있으면 성공으로 처리 (line 2412-2431)
- `data/settings.json`: `backup_tp_sl_settings` 섹션 추가
- `config/settings_template.json`: `backup_tp_sl_settings` 섹션 추가
- `config/settings.py`: `get_default_settings()`에 `backup_tp_sl_settings` 추가

#### 💡 주요 효과
- ✅ Binance API -4120 에러 완전 해결
- ✅ TP/SL 설정 실패 문제 해결
- ✅ 백업 TP/SL을 AI가 자동 조정 가능
- ✅ 사용자가 settings.json에서 직접 조정 가능
- ✅ 실시간 모니터링과 백업 TP/SL 역할 분리로 안정성 향상
- ✅ **패키지 환경에서도 settings.json 올바르게 로드 (하드코딩된 경로 문제 해결)**
- ✅ **PENDING 상태 주문 올바르게 처리 (주문 실패로 오인식 문제 해결)**
- ✅ **포지션 관리 정확도 향상 (실제 포지션 확인 후 메모리 업데이트)**

---

## 2025-01-26 - v3.8.9.6 TP/SL Algo Order API 대응 및 핫픽스

### 🔧 Binance Algo Order API 대응

#### 🎯 배경
- 바이낸스가 TP/SL 주문에 대해 Algo Order API 사용을 요구하는 경우 발생
- `-4120` 에러: "Order type not supported for this endpoint. Please use the Algo Order API endpoints instead."
- 기존 코드에서 `client.futures_create_order()` 직접 호출 시 에러 발생

#### ✅ 주요 변경사항
- **BinanceClient.place_tp_sl_orders() 사용으로 통일**:
  - `execute_single_trade()`: `place_tp_sl_orders()` 사용 (기존 `futures_create_order()` 직접 호출 제거)
  - `_retry_tp_sl_setup()`: `place_tp_sl_orders()` 사용
  - `_tp_sl_watchdog()`: `place_tp_sl_orders()` 사용
  - `place_tp_sl_orders()`는 `closePosition=True`와 `workingType='MARK_PRICE'`를 올바르게 처리
- **TP/SL 모듈화 준비 (Phase 6 Step 2)**:
  - `TpSlManager` 클래스 생성 및 초기화
  - `audit_tp_sl_state()` 메서드로 기존 코드와 결과 비교 로그 추가
  - 기존 코드와 공존하여 롤백 가능성 보장

#### 🔧 수정된 파일
- `trading/trader.py`:
  - `execute_single_trade()`: `place_tp_sl_orders()` 사용 (line 2409-2456)
  - `_retry_tp_sl_setup()`: `place_tp_sl_orders()` 사용 (line 518-527)
  - `_tp_sl_watchdog()`: `place_tp_sl_orders()` 사용 (line 341-358)
  - `TpSlManager` 초기화 및 audit 로그 추가 (line 132, 2609-2618)
- `trading/tp_sl_manager.py`:
  - `TpSlManager` 클래스 생성
  - `validate_tp_sl()` 메서드 구현
  - `audit_tp_sl_state()` 메서드 구현 (비파괴적 상태 점검)

#### 💡 주요 효과
- ✅ Binance Algo Order API 대응: `-4120` 에러 해결
- ✅ 코드 일관성: 모든 TP/SL 주문 생성이 `place_tp_sl_orders()`를 통해 처리
- ✅ 모듈화 준비: `TpSlManager` 기반 모듈화 진행 가능
- ✅ 롤백 가능: 기존 코드 유지로 문제 발생 시 즉시 롤백 가능

---

## 2025-01-26 - v3.8.9.5 TP/SL 검증 로직 개선 및 원자성 보장 강화

### 🔧 TP/SL 검증 로직 개선

#### 🎯 배경
- TP/SL 검증 로직에서 주문 타입 필터링이 불일치하여 검증 실패 가능
- 고정 3초 대기로 API 지연 시 검증 실패
- TP/SL 중 하나만 성공 시 원자성 보장 부족
- 재설정 후 재검증이 없어 실패 여부를 알 수 없음
- **TP/SL 검증 실패 시에도 거래가 진행되는 문제**: TP/SL이 설정되지 않아도 거래가 실행됨
- **거래 통계 및 AI 학습 데이터 경로 문제**: 사용자 계정별 경로를 사용하지 않아 데이터 초기화 가능성

#### ✅ 주요 변경사항
- **주문 타입 필터링 통일**:
  - 모든 검증 로직에서 `('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')` 및 `('STOP', 'STOP_MARKET')` 모두 확인
  - 검증 로직과 Watchdog 간 일관성 확보
- **검증 대기 시간 개선**:
  - 고정 3초 → 재시도 로직 (2초, 3초, 4초)으로 변경
  - API 지연 시에도 검증 성공 가능성 향상
- **원자성 보장 강화**:
  - TP/SL 중 하나라도 실패 시 둘 다 롤백
  - 재설정 시에도 원자성 보장 (주문 생성 실패 시 생성된 주문 자동 롤백)
- **재설정 후 재검증 추가**:
  - 재설정 성공 후 즉시 재검증 추가
  - 재검증 실패 시 Watchdog에 의존
- **Watchdog 재검증 개선**:
  - 재설정 후 최대 2회 재검증 (1초, 1.5초 간격)
  - 주문 상태 검증 추가 (개수뿐만 아니라 상태도 확인)
- **TP/SL 검증 실패 시 거래 차단 (v3.8.9.5 핫픽스)**:
  - TP/SL 검증 실패 시 포지션을 즉시 청산하도록 수정
  - TP/SL 주문 생성 실패 시에도 포지션을 즉시 청산
  - 거래 실패로 처리하여 통계에 반영
- **거래 통계 및 AI 학습 데이터 경로 수정 (v3.8.9.5 핫픽스)**:
  - `recorder.py`가 `get_db_file_path()`를 사용하도록 수정하여 사용자 계정별 경로 보장
  - 로그 경로도 `get_log_dir()`를 사용하도록 수정

#### 🔧 수정된 파일
- `trading/trader.py`:
  - `execute_single_trade()`: 검증 로직 개선 (2408-2450줄)
  - `execute_single_trade()`: TP/SL 검증 실패 시 포지션 즉시 청산 로직 추가 (2643-2700줄)
  - `execute_single_trade()`: TP/SL 주문 생성 실패 시 포지션 즉시 청산 로직 추가 (2711-2751줄)
  - `_retry_tp_sl_setup()`: 원자성 보장 강화 (460-519줄)
  - `_tp_sl_watchdog()`: 재검증 로직 개선 (253-411줄)
- `trading/recorder.py`:
  - `__init__()`: `get_db_file_path()`, `get_log_dir()` 사용하도록 수정하여 사용자 계정별 경로 보장
- `trading/tp_sl_manager.py`:
  - `TpSlManager` 도입으로 TP/SL 생성·검증·재설정·감시 로직을 단일 모듈에서 관리할 준비
  - `audit_tp_sl_state()`: TP/SL 상태를 변경 없이 점검하는 비파괴 audit 헬퍼 추가
- `docs/UPDATE_PLAN.md`:
  - Phase 6 "TP/SL 및 거래 엔진 모듈화" 상세 설계 및 검증용 로그·사용자 체크리스트 추가

#### 💡 주요 효과
- ✅ 검증 안정성 향상: 재시도 로직으로 API 지연 대응
- ✅ 원자성 보장: TP/SL 중 하나 실패 시 자동 롤백
- ✅ 일관성 개선: 모든 검증 로직에서 동일한 필터링 사용
- ✅ 모듈화 준비: TP/SL 관련 책임을 `TpSlManager`로 집중시켜 Trader/AlphaArena에서 재사용 가능
- ✅ 디버깅 용이성: `[TP_SL_AUDIT]`, `[TP_SL_VERIFY]` 등 세분화된 로그로 문제 위치를 빠르게 추적 가능
- ✅ **TP/SL 필수 보장**: TP/SL이 설정되지 않으면 거래가 실행되지 않음
- ✅ **데이터 영구성 보장**: 사용자 계정별 경로를 사용하여 거래 통계 및 AI 학습 데이터가 올바르게 저장됨

---

## 2025-12-10 - v3.8.9.4 TP/SL Watchdog 안정성 개선

### 🛡️ TP/SL Watchdog 안정성 개선

#### 🎯 배경
- TP/SL watchdog가 비정상 상태 감지 시 `cancel_all_orders`를 사용하여 모든 오픈오더를 취소하는 문제
- 다른 유효한 주문까지 취소될 수 있어 거래에 방해가 될 수 있음
- TP/SL 주문 생성 실패 시 재시도 로직 부족으로 안정성 저하
- 코드 중복으로 인한 유지보수성 저하

#### ✅ 주요 변경사항
- **TP/SL만 선별 취소로 변경**:
  - `trading/trader.py`의 `_tp_sl_watchdog()` 메서드 개선
  - 기존: `cancel_all_orders()` 사용 (모든 오픈오더 취소)
  - 개선: TP/SL 주문만 선별 취소, 다른 유효한 주문 보호
  - TP/SL watchdog가 비정상 상태 감지 시에도 다른 주문에 영향 없음
- **TP/SL 주문 생성 재시도 로직 추가**:
  - 최대 3회 재시도로 주문 생성 안정성 향상
  - 각 재시도 간 1초 대기로 API 부하 방지
  - 실패 시 상세 로그 출력으로 디버깅 용이성 향상
- **코드 중복 제거 및 최적화**:
  - 중복된 오픈오더 정리 코드 제거
  - 포지션 없음 감지 시 이미 정리되므로 중복 제거
  - 코드 가독성 및 유지보수성 향상

#### 🔧 수정된 파일
- `trading/trader.py`:
  - `_tp_sl_watchdog()`: TP/SL만 선별 취소로 변경 (281-292줄)
  - TP/SL 주문 생성 재시도 로직 추가 (339-377줄)
  - 중복된 오픈오더 정리 코드 제거 (3968-3989줄)

#### 💡 주요 효과
- ✅ TP/SL watchdog가 다른 주문에 영향을 주지 않음
- ✅ TP/SL 주문 생성 실패 시 자동 재시도로 안정성 향상
- ✅ 코드 중복 제거로 유지보수성 향상
- ✅ 전체적인 시스템 안정성 개선

---

## 2025-11-29 - v3.8.9.3 통합잔고 및 거래통계 오류 수정, 수수료 고려 청산 시스템

### 🔧 통합잔고 및 거래통계 오류 수정

#### 🎯 배경
- TP/SL 청산 시 `trade_log` 테이블의 `exit_time`이 설정되지 않아 거래 통계가 누락되는 문제
- `exchange_trade_stats`와 `trade_log` 동기화 불일치
- 통합잔고 합계가 표시되지 않아 여러 거래소 사용 시 전체 자산 파악 어려움
- 거래 후 잔고 갱신 지연 (캐시 문제)

#### ✅ 주요 변경사항
- **TP/SL 청산 시 trade_log 업데이트 추가**:
  - `trading/trader.py`의 `_monitor_position()` 메서드에서 TP/SL 청산 감지 시 `update_trade_log()` 호출 추가
  - `exit_time` 설정으로 거래 통계 정확도 향상
  - `exchange_trade_stats`와 `trade_log` 동기화 개선
- **거래통계 조회 로직 개선**:
  - `ui/dashboard_modern.py`의 `_refresh_trading_summary()` 메서드 개선
  - `exchange_trade_stats` 테이블 우선 조회
  - 폴백: `trade_log`에서 완료된 거래만 집계 (`exit_time IS NOT NULL`)
  - 모든 거래소 통계 합산 표시
- **통합잔고 합계 표시 추가**:
  - `ui/dashboard_modern.py`의 `_display_unified_balances()` 메서드 개선
  - 여러 거래소 USDT 잔고 합계 계산 및 표시
  - 여러 거래소 KRW 잔고 합계 계산 및 표시
  - 거래소별 잔고는 거래소 탭에 개별 표시 (`create_exchange_balance_section()`)
- **거래 후 잔고 즉시 갱신**:
  - `ui/dashboard_modern.py`의 `update_balance_on_trade_completion()` 메서드 개선
  - 거래 완료 시 캐시 무시하고 즉시 잔고 갱신 (`force_refresh=True`)
  - `trading/exchange_manager.py`의 잔고 캐시 시간 단축 (60초 → 30초)

#### 🔧 수정된 파일
- `trading/trader.py`: TP/SL 청산 감지 시 `update_trade_log()` 호출 추가
- `ui/dashboard_modern.py`: 통합잔고 합계 표시, 거래통계 조회 로직 개선, 거래 후 잔고 즉시 갱신
- `trading/exchange_manager.py`: 잔고 캐시 시간 단축

#### 💡 주요 효과
- ✅ 거래 통계가 정확하게 표시됨 (TP/SL 청산도 포함)
- ✅ 통합잔고 합계로 전체 자산 파악 가능
- ✅ 거래 후 즉시 잔고 반영
- ✅ 여러 거래소 사용 시 전체 자산 한눈에 확인

---

### 💰 수수료 고려 청산 시스템

#### 🎯 배경
- 일부 사용자가 청산이 너무 빨리되어 수수료도 못 건진다는 문제
- 바이낸스 선물 수수료: 진입 0.02% + 청산 0.02% = 총 0.04%
- AI 조기 청산 최소 수익 0.14%에서 수수료 0.04%를 제외하면 실제 수익 0.10%만 남음
- 동적 수익 임계값 최소값 0.05%는 수수료 고려 시 손실

#### ✅ 주요 변경사항
- **수수료를 고려한 최소 수익 임계값 조정**:
  - AI 조기 청산 최소 수익: 0.14% → 0.20% (수수료 0.04% 고려)
  - 동적 수익 임계값 최소값: 0.05% → 0.10% (수수료 고려)
  - 최소 보유 시간: 1분 → 2분 (수수료 회수 시간 고려)
- **청산 우선순위 명확화**:
  1. AI 모니터링 중심 청산 (주력): `_get_ai_exit_decision()`, `_check_ai_early_exit()`
  2. 동적 임계값 기반 청산: `_calculate_dynamic_thresholds()` (변동성/보유시간/코인 특성 반영)
  3. TP/SL 안전장치 (최후의 보호막)

#### 🔧 수정된 파일
- `trading/trader.py`:
  - `_check_ai_early_exit()`: 최소 수익 임계값 0.20%로 상향, 최소 보유 시간 2분으로 증가
  - `_calculate_dynamic_profit_threshold()`: 최소값 0.10%로 상향 (수수료 고려)

#### 💡 주요 효과
- ✅ 수수료를 고려하여 최소 수익 보장
- ✅ 수수료 못 건지는 문제 해결
- ✅ AI 기반 동적 조정으로 시장 상황에 맞는 청산
- ✅ 변동성/보유시간/코인 특성에 따른 스마트한 청산

---

## 2025-11-14 - v3.8.8.8 거래 차단 문제 해결 및 설정 보존 강화

### 🚨 거래 차단 문제 해결 (Trading Blocking Issue Fix)

#### 🎯 배경
- 거래 신호는 발생하지만 실제 거래가 실행되지 않는 문제 발생
- 데이터 부족 시 0.75 임계값 강제로 인한 순환 문제 (Chicken and Egg Problem)
- 첫 거래가 실행되지 않으면 데이터가 쌓이지 않고, 데이터가 없으면 거래가 실행되지 않는 모순

#### ✅ 주요 변경사항
- **첫 거래 허용 로직 추가**: 전체 거래 이력이 0인 경우 완화된 조건 적용
- **데이터 부족 시 임계값 완화**: `user_signal_threshold` 기반으로 동적 조정 (최대 0.70)
- **"초기 거래를 위한 조건 완화" 로직 구현**: 주석의 의도대로 작동하도록 수정
- **동적 임계값 계산**: `user_signal_threshold = 68` → `dynamic_confidence_threshold = 0.68` → `conservative_threshold = 0.73`

#### 🔧 수정된 파일
- `trading/trader.py`: `_perform_pre_entry_analysis()` 메서드 개선
  - 전체 거래 이력 확인 로직 추가
  - 첫 거래인 경우 완화된 조건 적용 (`dynamic_confidence_threshold` 사용)
  - 데이터 부족 시 `min(dynamic_confidence_threshold + 0.05, 0.70)` 적용
  - 상세 디버깅 로그 추가

#### 📝 문서 업데이트
- `docs/TRADING_BLOCKING_COMPLETE_ANALYSIS.md`: 구조적 모순 및 해결 방안 상세 분석
- `docs/DATA_INSUFFICIENT_ANALYSIS.md`: "데이터 부족" 의미 명확화
- `docs/TRADING_BLOCKING_ROOT_CAUSE.md`: 근본 원인 분석

#### 🎯 기대 효과
- ✅ 첫 거래 실행 가능 (순환 문제 해결)
- ✅ `user_signal_threshold` 설정 존중
- ✅ 데이터 부족 시에도 거래 가능 (약간의 조정으로 통과)
- ✅ 거래 실행 안정성 향상

---

### 🔒 설정값 보존 강화 (Settings Preservation Enhancement)

#### 🎯 배경
- 사용자가 설정값을 수정해도 프로그램 재시작 시 다시 원래대로 돌아가는 문제
- 템플릿 병합 시 중첩 딕셔너리 내부 값이 덮어씌워지는 문제
- 2단계 이상 중첩된 설정 항목이 보존되지 않는 문제

#### ✅ 주요 변경사항
- **중첩 딕셔너리 재귀 처리 개선**: 2단계 이상 중첩도 완벽하게 처리
- **보호된 설정 항목 리스트 추가**: 중요한 설정 항목 명시적 보호
- **경로 추적 시스템**: `parent_key` 파라미터로 전체 경로 추적
- **사용자 설정 보존 강화**: 템플릿 병합 시에도 사용자 값 우선 보존

#### 🔧 수정된 파일
- `config/settings.py`: `deep_merge_settings()` 함수 개선
  - `parent_key` 파라미터 추가로 경로 추적
  - 재귀적 병합으로 2단계 이상 중첩 처리
  - `PROTECTED_SETTINGS` 리스트 추가
  - 보호된 설정 항목 확인 로직 추가

#### 📋 보호되는 설정 항목
- `analyzer_settings.user_signal_threshold`
- `ai_trading_preferences.risk_tolerance`
- `ai_trading_preferences.balance_utilization_limit`
- `ai_trading_preferences.risk_levels.conservative.balance_utilization`
- `exchange_risk_overrides.binance.max_position_size`
- 기타 중요한 거래 설정 항목

#### 📝 문서 업데이트
- `docs/SETTINGS_RESET_ISSUE_ANALYSIS.md`: 설정값 리셋 문제 분석 및 해결 방안

#### 🎯 기대 효과
- ✅ 사용자가 수정한 설정값 영구 보존
- ✅ 템플릿 병합 시에도 사용자 설정 우선
- ✅ 새로운 설정 항목만 자동 추가
- ✅ 설정 관리 안정성 향상

---

## 2025-10-31 - v3.8.8.8 시간 동기화 시스템 추가

### ⏰ 시간 동기화 자동화 (Time Synchronization)

#### 🎯 배경
- 바이낸스 API는 요청 타임스탬프가 서버 시간과 5초 이상 차이나면 거래를 거부합니다
- Windows 시스템 시간이 자동으로 동기화되지 않거나 NTP 서비스가 꺼져있는 경우 문제 발생
- 사용자가 수동으로 설정을 변경해야 하는 번거로움 해소

#### ✅ 주요 변경사항
- **자동 시간 동기화 시스템 추가**: 앱 시작 시 Windows 시간을 자동으로 동기화
- **시간 차이 자동 감지**: 로컬 시간과 바이낸스 서버 시간 비교
- **NTP 강제 동기화**: w32tm 명령어로 time.windows.com과 강제 동기화
- **재시도 메커니즘**: 최대 3번까지 자동 재시도
- **사용자 안내**: 실패 시 수동 설정 방법 안내

#### 📂 신규 파일
- `utils/time_sync.py`: 시간 동기화 유틸리티
  - `sync_windows_time()`: Windows 시간 서비스 시작 및 NTP 동기화
  - `get_binance_server_time()`: 바이낸스 서버 시간 조회
  - `check_time_sync()`: 로컬 vs 서버 시간 차이 확인
  - `ensure_time_sync()`: 자동 동기화 메인 함수 (최대 3회 재시도)

#### 🔧 수정된 파일
- `main.py`: 계정 정보 로드 후 시간 동기화 추가
  - 로그인 후 자동으로 `ensure_time_sync()` 호출
  - 동기화 실패 시에도 프로그램 계속 실행 (warning만 표시)
- `aiautotrade.spec`: utils 폴더 빌드에 포함
  - `('utils', 'utils')` 라인 추가
  - time_sync.py가 EXE에 포함되도록 설정

#### 📝 문서 업데이트
- `docs/USER_GUIDE.md`: 시간 동기화 기능 안내 추가
  - 핵심 차별점에 "자동 시간 동기화" 항목 추가
  - 시작 과정에 시간 동기화 단계 설명 추가
  - 문제 해결 섹션에 시간 동기화 오류 해결 방법 추가

#### 🛡️ 안전성 보장
- **예외 처리**: 동기화 실패해도 앱은 계속 실행
- **관리자 권한 불필요**: subprocess로 w32tm 실행
- **타임아웃 설정**: API 호출 5초 타임아웃
- **로그 상세 기록**: 모든 동기화 과정 로그 기록

#### 🎯 기대 효과
- ✅ "Timestamp for this request is outside of the recvWindow" 오류 방지
- ✅ 사용자 수동 설정 불필요
- ✅ 거래 실행 안정성 향상
- ✅ API 호출 성공률 향상

---

## 2025-10-30 - UI 베이스라인 통합 및 회귀 방지 조치

### 🎯 배경
- 대시보드에서만 corner_radius가 각지게 보이고 텍스트 안티앨리어싱이 거칠었던 문제를 근본적으로 해결하기 위해 UI 렌더링 경로를 재정비하고 문서를 단일 기준으로 통합했습니다.

### ✅ 변경 요약
- CustomTkinter 내부 monkey patch 전면 제거 (라운드/AA 렌더링 회복)
- 투명색(`transparent`) 사용 최소화 시작 → 고정 스킨의 일관된 배경색으로 대체(점진 적용)
- 레거시 테마/레이아웃 문서 일괄 삭제 → 단일 가이드(`docs/UI_DESIGN_GUIDE.md`)로 통합
 - 상단 서비스 메뉴/우측 액션 버튼 크기 축소 및 통일(높이 36, 폰트 13)
 - 상단 타이틀을 하단 상태 줄 프리픽스로 이동하여 서비스 메뉴 공간 확보(“🤖 AI애널리스트” 가시성 개선)
 - 상단 좌측 사용자 영역 좌측 여백 +5px 적용 및 Quick Actions 버튼군 좌우 대칭 정렬
 - 메인 탭바(실시간 거래 로그~시장 트렌드) 대비 강화: 탭 바 배경/선택/비선택 색상 구분 명확화
 - 탭바 스타일 재적용기 보강 및 Hover 효과 추가, 비선택 버튼 배경=탭 바 배경으로 통일, 탭 텍스트 명도 상향
 - 실시간 로그 레이아웃 최적화: 상단 헤더 제거로 표시 영역 확대, 거래소/카테고리 드롭다운을 하단 "로그 레벨" 옆으로 이동
 - 로그인 모달: "? 도움말" 버튼을 "로그인 정보 저장" 체크박스 오른쪽으로 이동(푸터는 여백만 유지)

### 📄 문서 변경 사항
- 추가: `docs/UI_DESIGN_GUIDE.md` (Root Cause, 베이스라인, 컴포넌트 스펙, Do/Don’t, 폴리싱 체크리스트, 작업 로그 포함)
- 삭제: 다음 레거시 문서를 제거하여 혼선 방지
   - THEME_APPLICATION_COMPLETE.md, THEME_FILES_LOCATION.md, THEME_REMOVAL_DETAILED_CHANGELOG_20251030.md, THEME_SYSTEM.md, THEME_SYSTEM_GUIDE.md
   - DASHBOARD_BUTTONS_ANALYSIS.md, DASHBOARD_DESIGN_IMPROVEMENTS_20251030.md, DASHBOARD_DESIGN_MODIFICATION.md, DASHBOARD_POSITION_SYSTEM.md, DASHBOARD_REDESIGN_PLAN.md, DASHBOARD_RIGHT_PANEL_LOCATION.md
   - HISTORICAL_THEME_BASELINE.md, UI_FIXED_SKIN_PLAN.md, UI_FIXED_SKIN_TODO.md, UI_FIXED_SKIN_WORK_SUMMARY_20251029.md, UI_FIXED_SKIN_WORK_SUMMARY_20251030.md
   - WIDGETS_HARDCODED_COLORS_ANALYSIS.md, WIDGET_COLORS_FIX_PLAN.md, WIDGET_USAGE_ANALYSIS.md

### 🧩 코드 변경 사항
- 제거: `ui/dashboard_modern.py`의 `_patch_customtkinter_methods` 함수 및 호출부
- 제거: `ui/widgets/market_trend_widget.py`의 `_patch_customtkinter_methods` 함수 및 호출부
- 치환(안전 범위): `MarketTrendWidget` 내부 일부 `fg_color="transparent"` → `#0b1120`

### 🔎 영향도/리스크
- 기대 효과: 라운드/텍스트 렌더링 품질 개선, 버전 업그레이드 호환성/유지보수 리스크 감소
- 잠재 리스크: 기존 투명 의존 레이아웃 일부에서 배경 톤 차이 가능(점진 치환으로 관리)

### 🔁 롤백 가이드(필요 시)
- monkey patch 복원은 권장하지 않음(렌더링 품질 저하/회귀 위험). 만약 실험 목적 복원이 필요하면, 별도 브랜치에서만 수행 후 시각/성능 회귀 확인 필수.

### 🧪 회귀 방지 체크
- `test_button_minimal.py` 실험 스크립트로 CTkButton 둥근 렌더 확인
- 대시보드 스크린샷 점검 포인트: 상단 버튼, 서비스 탭, 카드형 패널의 라운드 유지 및 텍스트 가독성

## 2025-10-21 - v3.8.8.9

### 🎨 테마 시스템 안전성 강화 및 폰트 폴백 시스템 구현

#### 주요 변경사항
- **폰트 시스템 안전성 강화**: 테마 파일이 비어있거나 키가 누락되어도 애플리케이션이 죽지 않도록 개선
- **기본 폰트 구성 추가**: ThemeManager에 누락 방지용 기본 폰트 구성 상수 추가
- **안전한 정규화 로직**: 폰트 설정을 안전하게 정규화하여 누락된 키를 기본값으로 자동 보완
- **강화된 예외 처리**: 폰트 객체 생성 실패 시에도 최소한의 폰트라도 반환하도록 개선

#### 기술적 개선사항

**1. 기본 폰트 구성 추가**
```python
# ThemeManager 클래스에 추가된 기본 폰트 구성
DEFAULT_FONT_CONFIG = {
    "fonts": {"primary": "맑은 고딕", "monospace": "Consolas"},
    "sizes": {"h1": 20, "h2": 18, "h3": 16, "h4": 14, "body": 12, "caption": 11, "small": 10, "code": 12},
    "weights": {"normal": "normal", "medium": "normal", "semibold": "bold", "bold": "bold"}
}
```

**2. 안전한 정규화 로직 구현**
- `get_current_fonts()` 메서드에서 폰트 설정을 안전하게 정규화
- `font_config_raw`가 `None`이거나 키가 누락되어도 기본값으로 메움
- 딕셔너리 병합을 통한 안전한 폴백 처리

**3. 강화된 예외 처리**
- 첫 번째 예외 발생 시에도 `CTkFont` 객체를 반환하도록 개선
- 최후의 수단으로 빈 딕셔너리 반환 (대시보드가 기본 Tk 폰트 사용)

#### 해결된 문제들
- ✅ **"폰트 객체 생성 오류" 메시지 사라짐**: 테마 파일 문제로 인한 오류 완전 해결
- ✅ **테마 파일 비어있어도 정상 동작**: 기본 폰트 구성으로 안전하게 처리
- ✅ **키 누락 시에도 안전한 동작**: 누락된 키를 기본값으로 자동 보완
- ✅ **폰트 객체 생성 실패 시에도 안전**: 최소한의 폰트라도 반환하여 UI 유지

#### 안전성 보장
- **테마 파일이 비어있어도** → 기본 폰트 구성 사용
- **키가 누락되어도** → 기본값으로 자동 보완
- **폰트 객체 생성 실패해도** → 최소한의 폰트라도 반환
- **모든 것이 실패해도** → 빈 딕셔너리로 안전하게 처리

#### 수정된 파일
- `theme_system/theme_manager.py`: 폰트 시스템 안전성 강화 및 폴백 로직 구현

#### 사용자 경험 개선
- 대시보드 로그와 글자들이 완전히 달라져 더 나은 가독성 제공
- 테마 관련 오류로 인한 애플리케이션 중단 완전 방지
- 안정적인 UI 렌더링으로 사용자 경험 향상

## 2025-10-21 - v3.8.8.8

### 🔧 하드코딩된 값들을 설정 파일로 이동하여 동적 조절 가능하도록 최적화

#### 주요 변경사항
- **시장 분석 임계값 동적화**: RSI, 트렌드, 볼륨, 변동성 임계값을 설정 파일로 이동
- **코인 선택 비율 동적화**: 시장 상황별 알트코인/메이저코인 비율을 설정 파일로 이동
- **실시간 조절 가능**: 시장 상황 변화에 따라 즉시 파라미터 조정 가능

#### 설정 파일 업데이트 (`data/nwsoft/config/settings.json`)
- **`coin_selection_ratios`**: 시장 상황별 코인 비율 설정
  - Bull Market: 알트코인 80%, 메이저코인 20%
  - Bear Market: 알트코인 40%, 메이저코인 60%
  - Volatile Market: 알트코인 60%, 메이저코인 40%
  - Normal Market: 알트코인 70%, 메이저코인 30%
- **`market_analysis_thresholds`**: 시장 상황별 분석 임계값 설정
  - 트렌드 임계값, 볼륨 비율 임계값, 변동성 임계값, RSI 임계값
- **`market_regime_coins`**: volatile, normal 시장 상황 추가

#### 코드 최적화
- **`main.py`**: 하드코딩된 알트코인 비율(70%) 제거, 설정 파일 기반 동적 비율 적용
- **`trader.py`**: 하드코딩된 시장 분석 임계값 제거, 설정 파일 기반 동적 임계값 적용
- **빠른 분석과 상세 분석**: 각각 다른 민감도로 설정 파일 값 활용

#### 동적 조절의 실제 이점
- **시장 상황별 최적화**: 강세장에서는 알트코인 비중 높여 수익 극대화
- **리스크 관리**: 약세장에서는 메이저코인 비중 높여 리스크 최소화
- **실시간 적응**: 시장 변동성 변화에 따라 즉시 파라미터 조정
- **백테스팅 지원**: 최적 파라미터 도출을 위한 설정값 조정 가능

#### 기술적 개선
- **유연성 확보**: 하드코딩 제거로 시장 변화에 대한 적응성 향상
- **사용자 맞춤화**: 개인 투자 성향에 따른 파라미터 조정 가능
- **AI 학습 연동**: 향후 AI 기반 동적 파라미터 조정 기반 마련

## 2025-10-21 - v3.8.8.7

### 📚 거래소별 최적화 전략 차이점 문서화

#### 주요 변경사항
- **아키텍처 설계 의도 명확화**: 거래소별 다른 최적화 전략이 의도된 설계임을 문서화
- **설계 근거 설명**: 각 거래소의 특성과 API 차이점에 따른 최적화 전략 차이 설명
- **개발자 가이드라인**: 거래소별 분리 원칙과 주의사항 명시

#### 문서 업데이트
- **`docs/ARCHITECTURE.md`**: 거래소별 최적화 전략 차이점 섹션 추가
- **설계 의도 설명**: 바이낸스와 CCXT 거래소의 서로 다른 최적화 전략이 의도된 설계임을 명확히 설명
- **거래소별 특성**: 선물/현물, API 차이점, 최적화 요구사항 차이점 상세 설명

#### 기술적 근거
- **바이낸스**: python-binance 전용 API, 선물 거래, 고급 주문 지원 → `optimizer.py` AI 캐싱 시스템 활용
- **CCXT 거래소**: 통합 API, 현물/선물 혼재, 거래소별 특성 차이 → 자체 최적화 로직 사용
- **설계 장점**: 거래소별 특성 최적화, 유지보수성, 확장성 확보

#### 해결된 오해
- 거래소별 다른 최적화 전략이 일관성 없음이 아닌 의도된 설계임을 명확히 설명
- 각 거래소의 특성에 맞는 최적화 전략이 올바른 아키텍처임을 문서화
- 개발자가 거래소별 분리 원칙을 올바르게 이해할 수 있도록 가이드라인 제공

## 2025-10-21 - v3.8.8.6

### 🤖 AI 학습 기반 동적 임계값 시스템 구현

#### 구현된 기능
- **AI 학습 데이터 기반 임계값 조정**: 거래 결과를 분석하여 동적으로 임계값 조정
- **승률 기반 자동 최적화**: 높은 승률 시 더 관대한 조건, 낮은 승률 시 더 엄격한 조건
- **거래소별 일괄 적용**: 바이낸스(`trader.py`)와 CCXT 거래소(`unified_trader.py`) 모두 적용

#### 수정된 파일들

**1. trading/trader.py**
```python
def _get_dynamic_entry_thresholds(self, symbol: str, market_conditions: Dict) -> Dict:
    """시장 상황 기반 동적 진입 임계값 계산 (바이낸스용) - AI 학습 기반"""
    # AI 학습 데이터 기반 임계값 계산 우선
    learned_thresholds = self._get_ai_learned_thresholds(symbol)
    if learned_thresholds:
        return learned_thresholds
    
    # 기본 임계값 (AI 학습이 부족할 때 사용)
    # 하드코딩된 값들은 AI가 학습할 기준점으로 사용

def _get_ai_learned_thresholds(self, symbol: str) -> Optional[Dict]:
    """AI 학습 데이터 기반 임계값 계산"""
    # 최근 30일 거래 결과 분석
    # 승률 > 0.7: 더 관대한 조건 (신뢰도 0.3, 손실률 40%)
    # 승률 < 0.3: 더 엄격한 조건 (신뢰도 0.6, 손실률 60%)
```

**2. trading/unified_trader.py**
```python
def _get_dynamic_entry_thresholds_unified(self, exchange_name: str, symbol: str, market_conditions: Dict) -> Dict:
    """시장 상황 기반 동적 진입 임계값 계산 (Unified) - AI 학습 기반"""
    # 바이낸스와 동일한 AI 학습 로직 적용

def _get_ai_learned_thresholds_unified(self, exchange_name: str, symbol: str) -> Optional[Dict]:
    """AI 학습 데이터 기반 임계값 계산 (Unified)"""
    # 거래소별 학습 데이터 분석
```

#### 시스템 동작 방식

**1. 초기 단계 (학습 데이터 부족)**
- 하드코딩된 기준점 사용 (`0.02`, `0.01`, `0.7`, `0.3` 등)
- 이 값들은 AI가 학습할 기준점으로 사용

**2. 학습 단계 (거래 결과 수집)**
- 모든 거래 신호와 결과를 `ExchangeLearningManager`에 저장
- 승률, 손실률, 신뢰도 등 지표 수집

**3. 적응 단계 (동적 조정)**
- 최근 30일, 10회 이상 거래 데이터가 있을 때 AI 학습 결과 적용
- 승률이 높으면 더 관대한 조건으로 거래 빈도 증가
- 승률이 낮으면 더 엄격한 조건으로 리스크 감소

**4. 최적화 단계 (지속적 개선)**
- 지속적인 거래 결과 분석으로 임계값 자동 조정
- 시장 상황 변화에 따른 적응형 거래 전략

#### 기술적 특징

**AI 학습 기준점 (하드코딩된 값들)**
- `0.02`, `0.01`: 변동성 임계값 (AI가 학습할 기준점)
- `0.7`, `0.3`: 승률 임계값 (AI가 학습할 기준점)
- `0.8`, `1.2`: 조정 계수 (AI가 학습할 기준점)

**동적 조정 로직**
- 높은 승률 (>70%): 신뢰도 요구사항 완화, 더 적극적 거래
- 낮은 승률 (<30%): 신뢰도 요구사항 강화, 더 보수적 거래
- 학습 데이터 부족: 기본 기준점 사용

#### 아키텍처 일치성
- **바이낸스**: `trader.py`에서 자체 API 기반 학습
- **CCXT 거래소**: `unified_trader.py`에서 거래소별 학습
- **완전 분리**: 서로 간의 호출 없이 독립적 동작
- **일괄 적용**: 동일한 AI 학습 로직으로 일관성 보장

---

## 2025-10-21 - v3.8.8.5

### 🔧 추가 AttributeError 해결: get_active_positions 및 stop_trading 메서드

#### 해결된 문제
- **AttributeError**: `'Trader' object has no attribute 'get_active_positions'`
- **AttributeError**: `'Trader' object has no attribute 'stop_trading'`
- **거래 사이클 실행 오류**: 거래 실행 중 메서드 누락으로 인한 오류

#### 원인 분석
1. **누락된 메서드**: `Trader` 클래스에 `get_active_positions` 메서드가 없었음
2. **누락된 메서드**: `Trader` 클래스에 `stop_trading` 메서드가 없었음
3. **아키텍처 불일치**: `UnifiedTrader`에는 있지만 `Trader`에는 없는 메서드들
4. **거래 제어 실패**: 거래 중지 요청 시 메서드 누락으로 인한 오류

#### 해결 과정

**1단계: 메서드 추가**
```python
# trading/trader.py에 추가된 메서드들
def get_active_positions(self) -> Dict[str, Position]:
    """활성 포지션 조회 (바이낸스용)"""
    return self.active_positions

def stop_trading(self):
    """바이낸스 거래 중지"""
    # 모든 모니터링 플래그 중지
    # 모든 모니터링 스레드 종료 대기
    # 모니터링 관련 데이터 정리
```

**2단계: 아키텍처 일치**
- **바이낸스**: `Trader` 클래스에서 처리 (올바름)
- **CCXT 거래소**: `UnifiedTrader` 클래스에서 처리 (올바름)
- **메서드 일치**: 두 클래스 모두 동일한 인터페이스 제공

**3단계: 기능 검증**
- **포지션 조회**: 활성 포지션 정보 반환
- **거래 중지**: 모든 모니터링 스레드 안전하게 종료
- **데이터 정리**: 메모리 누수 방지

#### 해결 결과
✅ **거래 사이클 정상 실행**: `get_active_positions` 메서드 추가로 해결
✅ **거래 중지 정상 작동**: `stop_trading` 메서드 추가로 해결
✅ **아키텍처 일치**: 바이낸스와 CCXT 거래소 간 일관된 인터페이스
✅ **안전한 종료**: 모든 스레드와 리소스 정리

#### 수정된 파일
- `trading/trader.py`: 누락된 메서드 추가
- `docs/CHANGELOG.md`: 변경 이력 기록

---

## 2025-10-21 - v3.8.8.4

### 🔧 Trader 클래스 AttributeError 해결 및 초기화 과정 완성

#### 해결된 문제
- **AttributeError**: `'Trader' object has no attribute '_load_trade_stats_from_db'`
- **연쇄 오류**: `'NoahAIClient' object has no attribute 'trader'`
- **초기화 실패**: 누락된 메서드로 인한 전체 시스템 초기화 실패

#### 원인 분석
1. **누락된 메서드**: `Trader` 클래스에 `_load_trade_stats_from_db` 메서드가 없었음
2. **누락된 메서드**: `Trader` 클래스에 `_restore_positions_from_exchange` 메서드가 없었음
3. **초기화 실패**: `Trader.__init__`에서 누락된 메서드 호출로 인한 `AttributeError`
4. **연쇄 실패**: `trader` 객체 초기화 실패로 인한 `NoahAIClient.trader` 속성 누락

#### 해결 과정

**1단계: 메서드 추가**
```python
# trading/trader.py에 추가된 메서드들
def _load_trade_stats_from_db(self):
    """DB에서 바이낸스 거래 통계 로드"""
    # recorder를 통해 DB에서 바이낸스 거래 통계 로드
    # self.trade_stats 업데이트

def _restore_positions_from_exchange(self):
    """거래소에서 실제 포지션 조회하여 복구"""
    # binance_client.get_positions() 호출
    # Position 객체 생성 및 self.active_positions에 추가
```

**2단계: 아키텍처 검증**
- **바이낸스**: `Trader` 클래스에서 처리 (올바름)
- **CCXT 거래소**: `UnifiedTrader` 클래스에서 처리 (올바름)
- **문서 일치**: `docs/TRADING_STATS_PERSISTENCE_SYSTEM.md`에 명시된 설계 의도

**3단계: 기능 검증**
- **거래 통계 영구 저장**: DB에서 로드하여 메모리에 복구
- **포지션 복구**: 실제 거래소에서 포지션 조회하여 복구
- **통계 관리**: 거래 통계 업데이트 및 DB 저장

#### 해결 결과
✅ **모든 초기화 정상 완료**: 로그에서 확인된 정상 초기화 과정
✅ **AttributeError 해결**: 누락된 메서드 추가로 해결
✅ **아키텍처 일치**: 바이낸스는 `Trader`, CCXT는 `UnifiedTrader`에서 처리
✅ **기능 완성**: 거래 통계 영구 저장 및 포지션 복구 시스템 완성

#### 초기 실행 과정 검증
**1단계: 사용자 상태 관리 및 경로 설정**
- 사용자 계정: `nwsoft`
- 데이터 디렉토리: `data/nwsoft`
- 설정 파일 존재 여부 확인

**2단계: 로그인 및 인증**
- API 토큰 유효성 확인
- OpenAI API Key 상태 확인
- 사용자 정보 설정 완료

**3단계: 거래소 연결 및 WebSocket 설정**
- WebSocket 연결 성공
- 바이낸스 선물 연결 성공
- API 클라이언트 초기화 완료

**4단계: 트레이딩 컴포넌트 초기화**
- AI Manager: `gpt-3.5-turbo` 모델
- UnifiedTrader: 바이낸스 거래소 설정
- TP/SL 설정: `tp=0.001800`, `sl=0.002000`
- Trader: 고급 주문 기능 포함

**5단계: 대시보드 초기화**
- 대시보드 창 생성: `1400x900+580+270`
- 컴포넌트 연결 완료
- 메인 루프 진입 정상

#### 예방 조치
1. **문서 기반 개발**: 새로운 기능 추가 시 관련 문서 먼저 확인
2. **아키텍처 준수**: 바이낸스와 CCXT 거래소 간 명확한 역할 분리
3. **초기화 검증**: `__init__` 메서드에서 호출하는 모든 메서드 존재 여부 확인
4. **로그 모니터링**: 초기 실행 과정의 각 단계별 로그 확인

#### 수정된 파일
- `trading/trader.py`: 누락된 메서드 추가
- `docs/TROUBLESHOOTING.md`: 초기 실행 과정 및 문제 해결 가이드 추가
- `docs/CHANGELOG.md`: 변경 이력 기록

---

## 2025-10-20 - v3.8.8.3

### 🚀 바이낸스 자체 API 전환 및 아키텍처 최적화

#### 주요 변경사항
- **바이낸스 자체 API 완전 전환**: CCXT 의존성 제거, `api/binance_client.py` 독립 사용
- **중복 파일 제거**: `binance_extended_api.py`, `legacy_binance_adapter.py` 삭제
- **WebSocket 아키텍처 개선**: 46초 지연 문제 해결, 즉시 시작 가능
- **시장 분석 통합**: 바이낸스와 CCXT 거래소 간 일관된 시장 분석 로직
- **코인 재선택 로직**: 시장 상황 변화에 따른 동적 코인 선택 시스템

#### WebSocket 최적화 (2025-10-20 완료)
- **문제**: 코인 선택 시 모든 코인 WebSocket 구독으로 인한 46초 지연
- **해결**: API 기반 분석으로 변경, WebSocket은 포지션 모니터링에만 사용
- **효과**: 시작 시간 46초 → 즉시 시작
- **수정 파일**: `main.py`, `trading/trader.py`, `trading/evaluator.py`

#### 기술적 개선사항
- **WebSocket 관리**: 포지션 모니터링 전용, API 기반 분석으로 성능 향상
- **API 통합**: 모든 바이낸스 고급 API를 `api/binance_client.py`에 통합
- **로깅 시스템**: 통일된 로그 포맷, 디버그 로그 제어
- **에러 처리**: 강화된 예외 처리, 재시도 로직

#### 제거된 기능
- `trading/binance_extended_api.py` - `api/binance_client.py`로 통합
- `trading/legacy_binance_adapter.py` - CCXT 브리지 불필요
- `BASIC_SYMBOLS` 하드코딩 - 동적 코인 선택으로 대체
- **WebSocket 코인 분석 구독** - API 기반 분석으로 대체

#### 새로운 기능
- **동적 코인 재선택**: 1시간마다 시장 상황 분석 후 코인 재선택
- **최적화된 시장 분석**: 빠른 시장 분석 (20 klines, 단축된 지표 기간)
- **통합된 고급 API**: 미체결약정, 롱/숏 비율, 테이커 비율 등
- **즉시 시작**: WebSocket 최적화로 46초 지연 문제 해결
- **AI 학습 데이터 시스템**: 모든 거래 신호 자동 수집 및 패턴 분석
- **실시간 로그 시스템**: 사용자 가시성을 위한 카테고리별 로그 분류
- **AI 시스템 문서화**: 거래 진행부터 청산까지 전체 과정 상세 설명

## 2025-01-15

### 거래소별 시스템 분리 가이드라인 수립 🚨
**문제**: 바이낸스와 CCXT 거래소 간의 시스템 혼재로 인한 "거래소 클라이언트 없음" 오류

**원인 분석**:
- `unified_trader.py`에서 바이낸스 처리 시도
- `main.py`에서 거래소별로 올바른 라우팅 부족
- 거래소별 시스템 간 명확한 분리 원칙 부재

**해결 방법**:

#### 1. 거래소별 시스템 완전 분리
- **바이낸스**: `trader.py` + `api/binance_client.py` (python-binance) - 독립 시스템
- **CCXT 거래소**: `unified_trader.py` + CCXT 어댑터 - 통합 시스템
- **절대 금지**: 바이낸스에서 `unified_trader.py` 사용, CCXT 거래소에서 `trader.py` 사용

#### 2. main.py 라우팅 개선
- **바이낸스 시작**: `_start_binance_trading()` → `start_trading_loop()`
- **CCXT 거래소 시작**: `_start_unified_trading(exchange)` → `unified_trader.start_trading(exchange)`
- **바이낸스 정지**: `_stop_binance_trading()` → `stop_trading_loop()`
- **CCXT 거래소 정지**: `_stop_unified_trading(exchange)` → `unified_trader.stop_trading(exchange)`

#### 3. unified_trader.py에서 바이낸스 완전 제거
- `get_exchange_client()`: 바이낸스 처리 완전 제거
- 바이낸스 관련 설정값들 모두 제거
- 바이낸스 관련 주문 실행 코드 제거
- 바이낸스 관련 필터링 로직 제거

#### 4. 가이드라인 문서 생성
- **`docs/EXCHANGE_SEPARATION_GUIDELINES.md`**: 거래소별 시스템 분리 가이드라인
- **`docs/ARCHITECTURE.md`**: 아키텍처 문서 업데이트
- **`docs/TRADING_FLOW.md`**: 거래 실행 흐름 문서 업데이트
- **`docs/MASTER_DOCUMENTATION.md`**: 마스터 문서 업데이트

**수정된 파일**:
- `main.py`: 거래소별 올바른 라우팅 구현
- `trading/unified_trader.py`: 바이낸스 관련 코드 완전 제거
- `docs/EXCHANGE_SEPARATION_GUIDELINES.md`: 새로운 가이드라인 문서
- `docs/ARCHITECTURE.md`: 아키텍처 문서 업데이트
- `docs/TRADING_FLOW.md`: 거래 실행 흐름 문서 업데이트
- `docs/MASTER_DOCUMENTATION.md`: 마스터 문서 업데이트

**결과**:
- ✅ "거래소 클라이언트 없음" 오류 완전 해결
- ✅ 바이낸스와 CCXT 거래소 간 명확한 분리
- ✅ 향후 유사한 문제 발생 방지
- ✅ 개발자 가이드라인 수립

### 거래 통계 및 포지션 관리 시스템 완전 개선 🔧
**문제**: 거래 통계와 포지션이 앱 재시작 시 초기화되는 문제

**원인 분석**:
- 거래 통계가 메모리에만 저장되어 앱 재시작 시 손실
- 포지션 정보가 메모리에만 저장되어 실제 거래소와 불일치
- 바이낸스와 CCXT 거래소의 서로 다른 아키텍처로 인한 복잡성

**해결 방법**:

#### 1. 거래 통계 영구 저장 시스템 구축
- **`trading/recorder.py`**: `exchange_trade_stats` 테이블 추가
- **`trading/trader.py`**: 바이낸스 거래 통계 DB 저장/로드 기능 추가
- **`trading/unified_trader.py`**: CCXT 거래소 통계 DB 저장/로드 기능 추가

#### 2. 포지션 복구 시스템 구축
- **바이낸스**: `Trader._restore_positions_from_exchange()` 메서드 추가
- **CCXT 거래소**: `UnifiedTrader._restore_positions_from_exchange()` 메서드 추가
- 앱 시작 시 실제 거래소에서 포지션 조회하여 복구

#### 3. 대시보드 통계 표시 최적화
- **`ui/dashboard_modern.py`**: DB + 메모리 통합 통계 표시
- **`ui/widgets/market_trend_widget.py`**: 포트폴리오 통계 DB 기반으로 개선

**수정된 파일**:
- `trading/recorder.py`: 거래 통계 저장/로드 기능 추가
- `trading/trader.py`: 바이낸스 통계/포지션 영구 저장 및 복구
- `trading/unified_trader.py`: CCXT 거래소 통계/포지션 영구 저장 및 복구
- `ui/dashboard_modern.py`: 통합 통계 표시 로직
- `ui/widgets/market_trend_widget.py`: DB 기반 통계 표시

**결과**:
- 앱 재시작 후에도 거래 통계 유지
- 실제 거래소 포지션과 앱 내 포지션 동기화
- 바이낸스와 CCXT 거래소 모두 정상 작동
- 대시보드에서 정확한 통계 표시

---

### 바이낸스 포지션 표시 문제 해결 🔧
**문제**: 바이낸스 거래 후 포지션이 대시보드에 표시되지 않는 문제

**원인 분석**:
- 바이낸스는 `Trader` 클래스 사용 → 포지션은 `main_app.trader.active_positions`에 저장
- CCXT 거래소는 `UnifiedTrader` 클래스 사용 → 포지션은 `unified_trader.active_positions`에 저장
- 대시보드는 `UnifiedTrader`만 참조하여 바이낸스 포지션이 누락됨

**해결 방법**:
1. **대시보드 포지션 표시 로직 수정** (`ui/dashboard_modern.py`)
   - 바이낸스: `main_app.trader.active_positions` 참조
   - CCXT 거래소: `unified_trader.active_positions[exchange]` 참조

2. **거래 현황 통계 통합** (`ui/dashboard_modern.py`)
   - 바이낸스와 CCXT 거래소 포지션 수 합산
   - 모든 거래소 손익 통합 계산

3. **시장 트렌드 위젯 수정** (`ui/widgets/market_trend_widget.py`)
   - 포트폴리오 통계에서 바이낸스 포지션 포함

**수정된 파일**:
- `ui/dashboard_modern.py`: 포지션 표시 및 통계 통합 로직
- `ui/widgets/market_trend_widget.py`: 포트폴리오 통계 수정
- `docs/MASTER_DOCUMENTATION.md`: 아키텍처 설명 업데이트
- `docs/ARCHITECTURE.md`: 시스템 구조 문서 업데이트
- `docs/DASHBOARD_POSITION_SYSTEM.md`: 개발자 가이드 신규 작성

**결과**:
- 바이낸스 거래 후 포지션이 대시보드에 정상 표시
- 거래 현황 패널에 바이낸스 포지션 수 포함
- CCXT 거래소들은 기존대로 정상 작동
- 향후 동일 문제 방지를 위한 문서화 완료

---

## 2025-01-15

### 시스템 설계 원칙 재확인 🔍
**목표**: 리스크 관리 원칙에 따른 올바른 시스템 설계 확인

**중요한 발견**:

1. **시스템이 올바르게 작동하고 있음**
   - 거래 이력이 없을 때 손실률 70%는 "데이터 부족"을 의미하는 보수적 가정
   - 이는 리스크 관리 원칙에 따른 올바른 설계

2. **AI 학습 기반 점진적 조정**
   - 거래 이력이 쌓이면서 더 정확한 판단
   - AI가 학습하면서 점진적으로 임계값 조정
   - 사용자가 직접 임계값을 조정하지 않음

3. **올바른 접근 방법**
   - 초기에는 보수적으로 접근
   - 데이터가 쌓이면서 점진적으로 더 정확한 판단
   - 리스크 관리 원칙 준수

**기술적 세부사항**:
- 거래 이력이 없을 때 보수적 기본값 사용 (손실률 70%)
- AI가 학습하면서 점진적으로 더 정확한 임계값 적용
- 사용자 개입 없이 시스템이 자체적으로 최적화

---

## 2025-10-14

### API 검증 기능 확장 🔐
**목표**: 모든 주요 거래소에 API 키 검증 기능 제공

**주요 개선사항**:

1. **다중 거래소 검증 지원**
   - 바이낸스: 시간 동기화 + 계정 정보 확인
   - 업비트: CCXT 기반 API 키 유효성 검증
   - OKX: API 키 + Passphrase + 계좌 모드 확인
   - 실시간 검증 상태 표시

2. **사용자 친화적 인터페이스**
   - 각 거래소별 "검증" 버튼 추가
   - 검증 진행 중 "🔄 검증 중..." 표시
   - 성공 시 "✅ 검증 완료" 표시
   - 실패 시 구체적인 오류 메시지 제공

3. **오류 메시지 개선**
   - 바이낸스: `-1021` (시간 동기화), `-2014/-2015` (키/권한), `403` (네트워크 제한)
   - 업비트: `401` (API 키/권한), `403` (접근 제한)
   - OKX: `401` (API 키/권한), `403` (접근 제한), Passphrase 오류

4. **백그라운드 처리**
   - UI 블로킹 없이 비동기 검증 처리
   - threading을 활용한 안전한 백그라운드 실행
   - 검증 완료 시 UI 자동 업데이트

**기술적 구현**:
- `ui/settings_modern.py`: 검증 버튼 및 상태 표시 UI 추가
- `_verify_upbit_keys_worker()`: 업비트 API 키 검증 로직
- `_verify_okx_keys_worker()`: OKX API 키 검증 로직
- 각 거래소 어댑터의 `connect()` 메서드 활용

**기술적 구현**:
- `ui/settings_modern.py`: 검증 버튼 및 상태 표시 UI 추가
- `_verify_upbit_keys_worker()`: 업비트 API 키 검증 로직
- `_verify_okx_keys_worker()`: OKX API 키 검증 로직
- 각 거래소 어댑터의 `connect()` 메서드 활용

**문서 업데이트**:
- 사용자 메뉴얼에 검증 기능 사용법 추가
- 각 거래소별 검증 가능 여부 명시
- 검증 실패 시 해결 방법 안내

---

### OKX 거래 오류 처리 개선 🔧
**목표**: OKX 특화 오류 상황에 대한 명확한 안내와 자동 처리

**주요 개선사항**:

1. **계좌 모드 오류 처리**
   - "You can't complete this request under your current account mode" 오류 감지
   - 사용자 친화적 메시지로 해결 방법 안내
   - 계좌 모드 변경 필요성 명시

2. **최소 주문 수량 자동 조정**
   - 마켓 정보에서 최소 주문 수량 자동 조회
   - 수량 미달 시 자동으로 최소 수량으로 조정
   - 수량 정밀도 자동 반올림 처리

3. **OKX 특화 오류 메시지**
   - 오류 코드별 구체적인 해결 방법 제시
   - 사용자가 직접 조치할 수 있는 명확한 안내

**기술적 구현**:
- `trading/exchanges/adapters/okx_futures_adapter.py`: 오류 처리 로직 강화
- 최소 주문 수량 검증 및 자동 조정
- OKX 특화 오류 코드별 메시지 처리

**근본적 해결**:
- `trading/unified_trader.py`: 거래소별 최소 포지션 크기 설정
- OKX: 1.0개, Bybit/Bitget: 0.1개, Binance: 0.001개
- 포지션 크기 계산 시 거래소별 특성 반영

**문서 업데이트**:
- 사용자 메뉴얼에 OKX 계좌 모드 설정 방법 추가
- 자주 발생하는 오류와 해결 방법 안내

---

### 업비트 현물 거래소 오류 해결 🔧
**목표**: 업비트 심볼 형식 오류와 API 호환성 문제 해결

**주요 개선사항**:

1. **심볼 정규화 개선**
   - BTCUSDT → KRW-BTC (올바른 변환)
   - USDT 마켓을 KRW 마켓으로 자동 변환
   - 안전한 심볼 변환 로직 구현

2. **현재가 조회 안정화**
   - NoneType 오류 방지
   - 안전한 티커 데이터 추출
   - 다중 가격 필드 지원 (last, close, price)

3. **거래 내역 조회 호환성**
   - CCXT 미지원 함수 처리
   - 안전한 빈 리스트 반환
   - 오류 로그 개선

4. **마켓 심볼 검증**
   - 업비트 전용 심볼 형식 적용
   - 존재하지 않는 마켓 요청 방지

**기술적 구현**:
- `trading/exchanges/adapters/upbit_spot_adapter.py`: 업비트 심볼 정규화 및 안전한 API 호출
- `trading/exchanges/adapters/bithumb_spot_adapter.py`: 빗썸 심볼 정규화 및 안전한 API 호출
- `trading/unified_trader.py`: 중복 심볼 정규화 로직 제거 (각 어댑터에서 처리)
- `_normalize_upbit_symbol()`: 업비트 전용 심볼 변환 메서드
- `_normalize_bithumb_symbol()`: 빗썸 전용 심볼 변환 메서드

**해결된 오류들**:
- "현재가 조회 실패: 'NoneType' object has no attribute 'get'"
- "upbit does not have market symbol KRW-BTCUSDT"
- "upbit fetchMyTrades() is not supported yet"
- "upbit klines 조회 오류: upbit does not have market symbol BNB/USDT"

---

### 현물 거래소 지원 및 설정 파일 동기화 🔧
**목표**: 현물 거래소 특성 반영 및 설정 파일 일관성 확보

**주요 개선사항**:

1. **현물 거래소 특성 반영**
   - 업비트/빗썸: 롱/숏 없음, 레버리지 없음, 포지션 개념 없음
   - 실제 매수량 기반 거래 로직 구현
   - 원화 잔고 기반 매수 비율 계산

2. **거래소별 포지션 크기 계산 분기**
   - 현물: 잔고 비율 기반 매수량 계산
   - 선물: 레버리지 기반 포지션 크기 계산
   - AI 신뢰도에 따른 동적 비율 조정

3. **설정 파일 동기화**
   - `data/settings.json`: 사용자 설정 파일
   - `config/settings_template.json`: 배포용 템플릿
   - `config/settings.py`: 설정 로드/저장 로직
   - 누락된 설정 항목 추가 및 동기화

**기술적 구현**:
- `trading/unified_trader.py`: 현물/선물 거래소 분기 처리
- `_calculate_spot_position_size()`: 현물 거래소용 매수량 계산
- 설정 파일들: `verbose_trade_logging` 등 누락 항목 추가

**현물 거래소 특징**:
- **업비트**: KRW-BTC 형식, 원화 잔고 기반 매수
- **빗썸**: BTC/KRW 형식, 원화 잔고 기반 매수
- **AI 설정**: 신뢰도에 따른 매수 비율 조정 (5%~20%)
- **TP/SL**: 현물은 서버사이드 TP/SL 없음 (AI 모니터링만)

---

## [2025-10-14] 거래 시스템 전면 개선
**목표**: 모니터링 중심의 지능형 거래 시스템으로 전환

**주요 개선사항**:

1. **모니터링 중심 전환**
   - AI 모니터링을 주력으로, TP/SL을 안전장치로 변경
   - 향상된 AI 청산 결정 (`_get_enhanced_ai_exit_decision`)
   - 동적 임계값 기반 실시간 모니터링 청산
   - TP/SL은 최후의 보호막 역할

2. **학습 데이터 확장**
   - 최근 거래 분석: 10회 → 50회로 확장
   - 시장 상황별 분석: 상승장/하락장/횡보장별 승률 분석
   - 시간대별 분석: 오전/오후/저녁/밤 시간대별 패턴 분석
   - 성과 추세 분석: 최근 10회 vs 이전 10회 비교

3. **동적 임계값 조정**
   - 시장 변동성 기반 진입 조건 동적 조정
   - 높은 변동성: 더 엄격한 조건 (손실률 40%, AI 신뢰도 60%)
   - 낮은 변동성: 더 관대한 조건 (손실률 60%, AI 신뢰도 30%)
   - 최소 거래 이력 요구사항도 변동성에 따라 조정

4. **동적 TP/SL 조정**
   - 시장 변동성 기반 TP/SL 범위 동적 조정
   - 높은 변동성: TP/SL 확대 (1.5x/1.3x)
   - 낮은 변동성: TP/SL 축소 (0.8x/0.9x)
   - 최근 거래 패턴 기반 추가 조정

5. **AI 패턴 분석 활성화**
   - Dead Code 문제 해결: AI 패턴 유사성 분석 활성화
   - 보수적 조정: 수량 20% 감소, 레버리지 20% 감소
   - 패턴 기반 스킵 기능

6. **일괄성 확보**
   - `trader.py` (바이낸스)와 `unified_trader.py` (기타 거래소) 동일한 개선사항 적용
   - 모든 거래소에서 일관된 거래 경험 제공

### 로그 시스템 대폭 개선 🔍
**목표**: 사용자가 원하는 상세한 거래 분석 로그 제공

**주요 개선사항**:

1. **상세 분석 로그 확대**
   - 멀티타임프레임 RSI (5m, 10m, 14m, 21m)
   - 상세 트렌드 분석 (slope, strength, confirmation, volume_confirmed)
   - 리스크 분석 (position_ratio, leverage, liquidation_distance, tp/sl)
   - WebSocket 데이터 체크 (depth, ticker)

2. **로그 카테고리 체계화**
   - `analysis`: 시장 데이터 수집, RSI 계산, 트렌드 분석
   - `strategy`: 신호 상세 정보 (conf, trend, vol, entry, tp, sl, lev)
   - `monitor`: 포지션 모니터링 진행률, 데이터포인트 수집
   - `exit`: 포지션 종료 이유 및 결과

3. **사용자 제어 기능**
   - 설정창에 "상세 거래 로그 출력" 토글 추가
   - 거래소 탭에서 "전체 로그" / "간략 로그" 선택 가능
   - verbose 모드에서만 상세 로그 출력

4. **로그 일관성 개선**
   - `log_system.log_adapter`를 통한 통합 로깅
   - 터미널, 대시보드, 파일 저장 동일 포맷
   - 휴리스틱 카테고리 매핑으로 기존 로그 자동 분류

**기술적 개선**:
- `trading/analyzer.py`: 멀티타임프레임 RSI, 상세 트렌드 분석 로그
- `trading/trader.py`: 리스크 분석, WebSocket 체크, 모니터링 상세 로그
- `ui/settings_modern.py`: verbose 로깅 토글 UI 추가
- `ui/widgets/realtime_log_widget.py`: 간소화된 필터링 옵션

**사용자 경험**:
- 거래 과정의 모든 단계를 상세히 확인 가능
- 학습 및 문제 해결을 위한 풍부한 정보 제공
- 필요에 따라 간략/상세 모드 전환 가능

## 2025-10-12

### UI - 사용자 메뉴얼 완전 리팩토링 🎉
**목표**: 기술적이지 않고 사용자 친화적인 메뉴얼 제공

**새로운 구성** (6개 탭 — 당시 스냅샷):

> **2026-04 정합 메모:** 이후 인앱 메뉴얼이 **10개 탭**으로 확대·재정렬되었고, 작동 원리 탭 표기는 `🤖 NoahAI 작동 원리`입니다. 최신 탭 목록·순서는 `ui/widgets/user_manual_widget.py` 및 `docs/DOCUMENTATION_POLICY.md`를 따릅니다.

1. 📚 NoahAI 소개
   - 회사 이야기와 비전
   - AI 트레이딩이란?
   - 핵심 기능 소개
   - 빠른 시작 가이드

2. 🤖 AI 작동 원리 (당시 표기; 현재 `🤖 NoahAI 작동 원리`)
   - 전체 파이프라인 비기술적 설명
   - 7단계 프로세스 상세 설명:
     * 코인 선택 → 시장 분석 → 목표 설정
     * 포지션 진입 → 모니터링 → 청산 → 학습
   - 각 단계를 일상 언어로 쉽게 설명
   - 실제 예시와 함께 설명

3. 📅 업데이트 히스토리
   - v3.7.8부터 v3.8.0까지 주요 업데이트
   - 각 버전의 개선사항 정리
   - 현재 상태 및 향후 계획
   - 업데이트 철학 설명

4. 📊 대시보드 가이드
   - 메인 화면 구성 설명
   - 각 탭 기능 상세 설명
   - 거래소별 탭 사용법
   - 차트 이미지 분석 사용법
   - 효율적인 사용 팁

5. 🏢 다중 거래소 거래
   - 6개 거래소 완전 설명
   - 각 거래소 특징 및 설정 방법
   - 다중 거래소 시작 가이드
   - 독립 제어 및 통합 관리
   - 거래소 선택 가이드

6. 💬 AI 어시스턴트 활용법
   - 기본 사용법
   - 실전 예시 (상황별 대화 70개 이상)
   - 대화 팁 및 주의사항
   - 고급 활용법
   - FAQ

**개선 사항**:
- ✅ 기술 용어 최소화, 일상 언어 사용
- ✅ 실전 예시 대폭 증가 (100개 이상)
- ✅ 이모지와 구분선으로 가독성 향상
- ✅ 단계별 설명으로 이해도 향상
- ✅ 코드 근거 없이 사용자 관점에서 설명
- ✅ 제공된 파이프라인 분석을 비기술적으로 풀어냄

**파일 크기**: 841줄 → 1582줄 (완전 재작성)
**콘텐츠 품질**: 기술 문서 → 사용자 가이드 전환

**정리 작업**:
- ✅ 외부 MD 파일 의존성 제거 (모든 콘텐츠 내장)
- ✅ `manual_update_manager.py` → `legacy/` 폴더로 이동 (더 이상 사용 안 함)
- ✅ import 문 정리 및 코드 간소화

### 빌드 - hiddenimports 추가
**파일**: `build_safe.py`, `aiautotrade.spec`

**수정 내용**:
- `ccxt.bybit`, `ccxt.okx`, `ccxt.bitget` hiddenimports에 명시적 추가
- 이유: 동적 import로 인한 빌드 누락 방지
- 영향: 6개 거래소 모두 정상 작동 보장

**검증**:
- ✅ 빌드 검증 문서 생성: `docs/BUILD_VERIFICATION_2025-10-12.md`
- ✅ 모든 수정 파일 빌드 포함 확인
- ✅ Python 코드, CCXT 모듈, 문서 파일 모두 포함

### 사용자 매뉴얼 - 브랜드명 및 디자인 수정
**파일**: `ui/widgets/user_manual_widget.py`

**수정 내용**:
- ❌ "자람이AI" → ✅ "NoahAI"로 브랜드명 통일
- ✅ 운영 주체·기술 기원 정리: Noah AI Labs(제품) / DAL(AI 디지털케어로그 기원) — 회사 소개 재테크 중심으로 개선
  - "독자 개발한 AI 디지털케어로그 기술 기반으로 의료·교육·돌봄·금융 등 다양한 산업의 데이터 표준화와 인공지능 혁신을 이끄는" 전문적 표현
  - "지능형 데이터 해석 및 의사결정 플랫폼" 기술 설명 추가
  - NoahAI를 "금융 트레이딩 영역에 적용된 대표 사례"로 자연스럽게 연결
  - NoahAI에 적용된 핵심 기술 4가지 명시
  - 멀티모달 AI 분석, 지속 학습, 맞춤형 실행, 데이터 표준화
  - 재테크에 미치는 구체적 효과 설명
- ✅ 사용자 관점에서 이해하기 쉬운 설명으로 개선
  - 의료·돌봄 사업 상세 정보 제거
  - 금융 투자자에게 의미 있는 기술적 장점 강조
- ✅ 디자인 문제 해결
  - 중첩된 `CTkScrollableFrame` 제거
  - 창 크기 조정 (1400x800 → 1000x700)
  - 공간 효율적 활용으로 내부 스크롤바 제거

**영향**: 사용자 매뉴얼의 브랜드 일관성 확보 및 UI/UX 개선

### 수정 - 거래소별 로그 파일 저장 및 표시 문제 해결
**문제**: 거래소별 로그 파일(trading_binance.log 등)이 생성되지만 비어있고, 대시보드에서도 trading.log만 표시됨

**파일**: `main.py`, `ui/widgets/realtime_log_widget.py`

**수정 내용**:
- ✅ 로그 필터 조건 개선: `(ex=binance)` 또는 `binance` 포함 시 해당 거래소 로그 파일에 저장
- ✅ 대시보드 거래소별 탭에서 해당 거래소 로그 파일 직접 읽기
  - 전체 탭: `trading.log` 사용
  - 바이낸스 탭: `trading_binance.log` 사용
  - OKX 탭: `trading_okx.log` 사용
- ✅ 실시간 모니터링도 거래소별 로그 파일 사용

### 개선 - 바이낸스 API 검증 버튼 및 시간 동기화 안정화
**문제**: 일부 사용자 환경에서 Binance -1021(서버 시간과 로컬 시간 불일치), 403/4033(네트워크/IP 제한), -2014/-2015(키/권한), 2022(증거금/계정상태) 오류 보고

**파일**: `ui/settings_modern.py`, `api/binance_client.py`, `trading/binance_extended_api.py`

**수정 내용**:
1. 설정 모달(거래소 API 탭) - 바이낸스 구역에 "검증" 버튼과 상태 라벨 추가
   - 저장 전 수동 검증 가능(키 형식/서명/권한/시간 동기화 간단 점검)
   - 결과를 간단 배지/문구로 표시, 상세 원인은 로그에 기록
2. BinanceClient 시간 동기화/타임스탬프 일관 적용 강화
   - 서버 시간 오프셋 주기 갱신, 모든 서명 요청에 `get_synced_timestamp()+recvWindow` 적용
   - -1021 발생 시 재동기화 후 재시도 경로 강화(내부 공용 로직 재사용)
3. Binance Extended API 일관화
   - `/fapi/v1/time` 기반 오프셋 갱신, 서명 요청에 동기화 타임스탬프와 `recvWindow(5000ms)` 적용

**영향**:
- 사용자 경험 변화 없음(저장 흐름 동일), 필요 시 "검증" 버튼으로 사전 확인 가능
- -1021 재발 확률 감소, 네트워크 지연 환경에서도 안정성 향상
- CCXT를 쓰지 않는 바이낸스 경로에서도 시간/서명 정책이 일관 적용

**영향**: 
- 거래소별 로그가 올바른 파일에 저장됨
- 대시보드에서 거래소별 탭이 해당 거래소 로그만 표시
- 로그 파일 크기 분산으로 성능 향상

### 개선 - 차트 스크린샷 분석 프롬프트 강화 (업비트 진입가/손절가/목표가 미제공 문제 해결)
**문제 분석**:
- 업비트 차트 분석 시 action이 "WAIT"로 설정되면 entry/stop/tp가 null 또는 빈 배열로 반환됨
- 바이낸스는 정상적으로 구체적인 수치 제공
- 원인: AI 프롬프트가 "추정 가능하면 제공"이라고 되어 있어 보수적으로 판단 시 수치를 생략

**수정 내역**:
- `trading/ai/chart_screenshot_analyzer.py`:
  - `_ask_llm()` 프롬프트 개선: **항상 구체적인 수치 제공** 요구
  - action이 WAIT인 경우에도 '참고용' 진입가/손절가/목표가 제시하도록 명시
  - price_median 기반 기본값 계산 공식 제공:
    - entry: price_median
    - entry_zone: [price_median * 0.98, price_median * 1.02]
    - stop(LONG): price_median * 0.95 / stop(SHORT): price_median * 1.05
    - tp[0]: ±3%, tp[1]: ±6%
  - KRW/USDT 기반 심볼별 자릿수 처리 규칙 명확화
  - null/빈 배열 금지 명시

**효과**:
- ✅ 업비트 차트 분석 시에도 항상 진입가/손절가/목표가 제공
- ✅ action이 WAIT이더라도 참고용 수치 확인 가능
- ✅ 거래소별 자릿수 차이(KRW: 171,000,000 vs USDT: 111,147.8) 자동 처리

### 버그 수정 - OKX 거래소 마진 타입 설정 실패 문제 해결
**문제 분석**:
- OKX의 `setMarginMode()` API는 레버리지 파라미터(`lever`)를 필수로 요구
- 기존 코드는 마진 타입만 전달하여 "lever should be between 1 and 125" 에러 발생
- 주문 실행 실패(51010): OKX 계좌 모드 미설정 문제 감지

**수정 내역**:
- `trading/exchanges/adapters/okx_futures_adapter.py`:
  - `set_margin_type()`: 현재 레버리지를 조회하여 params로 전달하도록 수정
  - 레버리지 조회 실패 시 기본값(10배) 사용
  - 51010 에러 감지 시 사용자 친화적 에러 메시지 출력
  - `connect()`: 연결 시 계좌 모드 사전 검증 로직 추가 (Simple mode 경고)
- `trading/exchanges/adapters/bybit_futures_adapter.py`:
  - 방어적 코딩: 레버리지 정보가 있으면 params로 전달 (향후 동일 문제 방지)
- `trading/exchanges/adapters/bitget_futures_adapter.py`:
  - 방어적 코딩: 레버리지 정보가 있으면 params로 전달 (향후 동일 문제 방지)

### 문서 업데이트
- `docs/TROUBLESHOOTING.md`:
  - "OKX 거래소 문제 해결" 섹션 추가
  - 4가지 주요 문제 및 해결 방법 상세 가이드
    1. 마진 타입 설정 실패 (lever 파라미터)
    2. 주문 실행 실패 (51010 - 계좌 모드)
    3. 심볼 조회 오류 (미지원 선물)
    4. 계좌 잔고 조회 실패 (연쇄 오류)
  - Bybit/Bitget 방어적 코딩 적용 안내
- `docs/EXCHANGE_SETUP.md`:
  - OKX 설정에 "계좌 모드 설정" 필수 단계 추가
  - Single-currency margin / Multi-currency margin 선택 가이드
  - Simple mode에서 API 거래 불가 경고
  - OKX 특수 사항 명시 (레버리지 필수, Passphrase 필수)

### 기술적 의의
- **피드백 전 사전 감지**: 연결 시 계좌 설정 검증으로 문제를 조기에 발견
- **방어적 코딩**: Bybit/Bitget도 동일 패턴 적용하여 유사 문제 예방
- **사용자 친화적**: 에러 메시지에 구체적인 해결 방법 포함
- **향후 확장성**: 다른 거래소 추가 시 동일 패턴 재사용 가능

### 버전
- v3.7.8

---

## 2025-09-26

### 개선
- 설정 저장 후 대시보드 AI 상태 배지 즉시 갱신(on_settings_saved에 안전 호출 추가)
- 선택 개선: 설정 저장 완료 토스트/알림이 있으면 표시(getattr로 안전 호출)
- 예외 로깅 표준화: logger.exception 사용으로 스택 자동 포함(UI/메인 일부 경로)
- stdout 기반 예외 출력(traceback.print_exc) 제거 및 구조적 로깅으로 통일

### 안정화
- main.py 내 포지션 조회 로직의 들여쓰기/except 블록 붕괴 수정(구문 오류 해결)
- 활성 UI 위젯의 로그 처리 일관성 유지(이전 작업의 연속)

### 검증
- 스모크 테스트: `noahai_client/test_unified_system.py`, `noahai_client/test_paper_flow.py` 실행 PASS
- 변경 파일 정적 오류 검사 PASS

# Changelog

## [Unreleased]
- Docs/UI Planning
  - DASHBOARD_REDESIGN_PLAN.md Draft v2: 글로벌+개별 Start/Stop 공존(Tri-State), 서비스 전환 destroy, Settings Exchanges/AI 탭 명시, LogStream 단일화 계획 반영
  - 설정 키 입력 경로 및 AI 기본 탭 고정 전략 문서화
  - 향후 feature branch(`feature/dashboard-v2`) 기반 단계적 적용 예정

## v3.8.2 (2025-09-24)
- Runtime/API/WS
  - BinanceClient 전 REST 경로에 API 키 부재 가드 추가 → 무키 환경에서 REST 호출 생략으로 소음 감소
  - WebSocket unsubscribe 시 서버로도 UNSUBSCRIBE 전송하여 잔류 스트림 정리
  - 심볼 정규화 및 구독 라이프사이클 보완
- Docs
  - EXCHANGE_SETUP.md 대폭 보강: TL;DR, 무키 실행, 멀티거래소 예시, 로그 소음 최소화 체크리스트, FAQ 추가
  - TEST_STATUS.md 최신화: 멀티거래소 런타임 스모크 PASS 및 가드/WS 개선 반영
  - SCREENSHOTS_CHECKLIST.md 추가 및 docs/images/ 디렉터리 구성(.gitkeep 포함) — 스크린샷 자산 관리 체계화
- Tests
  - test_multi_exchange_runtime.py 추가: ['bybit'], ['binance','okx'], ['binance','okx','bitget'] 케이스 PASS 확인

## v3.8.1 (2025-09-23)
- UI
  - 상단 CTkTabview 도입 및 기본 “📊 실시간 거래 로그” 탭 보장
  - 서비스/거래소 하위 탭 라이프사이클 정리: 활성화된 거래소만 생성, 비활성 즉시 제거, 서비스 전환 시 안전 재구성
  - ‘👥 커뮤니티’ 탭 추가(QnA/Chat) — 업데이트 준비중 안내, FastAPI/WebSocket 연동 주석 포함
  - ‘클래식 보기(classic_view)’ 토글 추가: 시작 시 📚 AI 학습/📊 AI 리포트 탭 자동 생성·선택
- Runtime
  - 개발용 로그인 우회 환경변수 NOAHAI_SKIP_LOGIN 지원(직접 실행 신뢰성/속도 개선)
  - 무효 API 키/심볼 생성 억제, 파라미터 문자열화, WebSocket 구독 경로 정리로 로그 소음 감소
- Trading Safety
  - 최소 노셔널 보정, 레버리지 클램프, 주문 성공 판별 강화, 수량 정밀도 보정
- WebSocket/API
  - 메서드 명 통일(subscribe/unsubscribe/get_latest_ticker/orderbook), 호출부 정리
- Build
  - build_safe.py: --platform 추가로 Windows/macOS/Linux 크로스플랫폼 산출물 지원(.exe/.app/단일 바이너리), PyQt/Qt 전면 제외 유지
- Docs
  - USER_GUIDE/BUILD_GUIDE/DEPLOY_CHECKLIST/TEST_STATUS 업데이트, STORAGE_PATHS 권한/경로 FAQ 보강

## v3.8.0 (2025-09-22)
- UI/Runtime
  - CustomTkinter-only로 전환, PyQt 계열 완전 제거
  - ModernDashboard에 동적 속성(optimizer/ai_manager/risk_manager/market_state_analyzer/api_signal_manager) 사전 선언으로 정적 경고 감소
  - macOS에서 소스 직접 실행 시 실패 원인 진단(Traceback/CWD/Python 경로/버전) 자동 출력
- WebSocket/API
  - BinanceWebSocketManager API 명칭 통일: subscribe_symbol/unsubscribe_symbol, get_latest_ticker/get_latest_orderbook
  - main.py 구독/데이터 조회 호출부 전면 정리 (fallback 제거)
- Docs
  - README/INSTALLATION 갱신: CustomTkinter-only, 직접 실행 가이드, 진단 지침 추가
  - TROUBLESHOOTING 초안 추가(직접 실행 실패, 권한/경로, 네트워크)
  - TYPE_GUIDE ‘필수 패턴 모음(회귀 방지)’ 추가: Optional 가드, selected_coins 정규화, coin_symbol 기본값, 안전한 UI 업데이트
  - TROUBLESHOOTING에 Pylance 에러별 솔루션 정리: Optional 속성, str.get, unbound 변수, destroyed widget
  - ARCHITECTURE 최신화: CustomTkinter-only 명시, WebSocket 명칭 통일, 구독 유지 정책 문서화, ExchangeManager 역할 확장
  - main.py 타입 안정화: websocket_manager 가드, selected_coins dict 정규화, coin_symbol 기본값, 안전 로깅

## v3.7.6 (2025-09-18)
- Settings/Runtime
  - Runtime reinit on settings save, manager instance reuse (dashboard)
  - Storage paths documented (STORAGE_PATHS.md)
- Multi-Exchange Pipeline
  - Analyzer via ExchangeManager for price/klines (1m/5m/15m/1h)
  - ExchangeManager `get_klines`, Bybit/OKX/Bitget key validation
  - UnifiedTradingManager `reload_settings` / `refresh_exchange`
- Trading/AI
  - Futures leverage/margin auto-set, CCXT symbol normalization
  - Exchange signal thresholds + dynamic thresholds (regime-based)
  - Hysteresis for regime decision; auto/manual mode + manual regime
- Analytics/UI
  - Sizing outcome CSV persistence + summary utility (`analytics/reporting.py`)
  - Dashboard analytics summary with auto-refresh, range/period filters
  - Color hints, current regime + mode labels
- Docs/Deploy
  - Architecture/Guides updated; Deploy checklist + FAQ

## v3.7.7 (2025-09-19)
- Trading guardrails
  - Leverage clamp by exchange overrides and global cap; default margin type enforced with Binance naming compatibility
  - Min-notional auto-adjustment before order based on current price and per-symbol overrides
- Order path/shape normalization
  - Prefer UnifiedTradingManager for standard order result; fallback to CCXT adapter or python-binance client with side mapping
  - Robust success detection across result shapes (status/id/orderId)
- Tests
  - Smoke-test hooks in `test_unified_system.py` to validate clamp/min-notional/success-detection without API keys
## 2025-10-05

- Binance 어댑터 보강: 네이티브 OrderRequest 경로로 주문/청산 위임, 24h 티커/취소 일부 구현. (trading/exchanges/adapters/binance_futures_adapter.py)
- Binance 수량 정밀도 적용: `quantityPrecision` 기반 수량 포맷 적용으로 LOT_SIZE/정밀도 불일치 완화. (api/binance_client.py)
- Binance 주문 정규화 강화: `stepSize`·`tickSize`·`minNotional`를 주문 직전에 보정(+0.5% 여유)하여 -1013(Filter failure) 발생을 추가로 감소. (api/binance_client.py)
- UnifiedTrader 청산 경로 분기: CCXT/바이낸스 네이티브 경로를 안전히 분기해 시그니처 오류 제거. (trading/unified_trader.py)
- UnifiedTradingManager 에러 전달 개선: 하위 에러 메시지를 상위로 원문 전달해 원인 파악 용이. (trading/unified_trading_manager.py)
- 현물(KRW) 코인 선정 정렬 적용: KRW 페어 거래량(quoteVolume) 기준 내림차순 정렬 후 상위 N개 선정. (trading/evaluator.py)
- 설정 템플릿 확장: `exchange_risk_overrides.max_leverage` 추가, `strategy_config`(임계값/가중치/기본점수) 추가. (config/settings_template.json)
- 시그널 임계값 강화: `rsi_oversold` 28, `rsi_overbought` 72 등 보수화, 모멘텀 임계 상향. (config/settings_template.json)
- HIGH 국면 보수화: `rsi_oversold_delta -4`, `rsi_overbought_delta +4`, `momentum_threshold_scale 1.25`, 히스테리시스 `high_enter_mult 1.65`, `high_exit_mult 1.28`. (config/settings_template.json)
- 알트 기본 개수 축소: `num_alt_coins` 기본 10으로 조정(이전 15). (config/settings_template.json)
- 설정 UI 개선: 테마 프리뷰 실시간 반영(텍스트/아이콘 대비 포함), AI 시스템 상태 카드 정리/실시간 배지. (ui/settings_modern.py)
