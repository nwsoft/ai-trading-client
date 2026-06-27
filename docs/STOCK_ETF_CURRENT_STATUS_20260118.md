# 주식/ETF 서비스 개발 현황 및 다음 단계 계획 (최초: 2026-01-18 / 최신 기준: 2026-04-28)

## 📌 최신 정합 갱신 (정본) — 2026-05-01 증권 AI 자동매매 고도화 반영

이 문서는 과거 이력을 포함한다. 아래 항목은 2026-05-01 기준 최신 상태이며,
하위 섹션의 과거 계획/진행 문구와 충돌할 경우 본 섹션을 우선 적용한다.

### 1) 현재 확정 완료 (증권 자동매매 핵심)
- `run_auto_trade_cycle()`에 시장 레짐 감지 + 임계값 동적 조정 연결 완료
  - 레짐: `bull`/`bear`/`volatile`/`range`
  - 임계값: `effective_buy_threshold`, `effective_sell_threshold`로 신호 판단
- 종목별 거래 결과 피드백 학습 연결 완료
  - 최근 거래 성과를 분석 컨텍스트(`pnl_rate`, 승률, 거래수)로 반영
- `StrategyEngine`, `ProfitabilityValidator`를 증권 자동매매 사이클에 기본 적용
- XAI 로그 일관성 보강 완료
  - 심볼 의사결정(`stock_auto_trade_symbol`)과 사이클 요약(`stock_auto_trade_cycle`)에
    `market_regime` + 유효 임계값 포함

### 2) 코인 시스템 대비 현재 상태
- 레짐 기반 적응형 임계값: **적용 완료**
- 거래 성과 환류(피드백): **적용 완료**
- 설명 가능 로그(XAI) 확장: **적용 완료**
- 남은 차이: 설정 UI에서 증권 자동매매 자동예약 시작 옵션(`stock_auto_trading.auto_start`, legacy `enabled`)과 실주문 전역 토글을 직접 제어하는 전용 UX는 추가 개선 필요

### 3) 현재 잔여 과제(정합 관점)
1. 설정 UX 보강
  - 자동매매 실행은 START/STOP(AUTO)로 제어하고, `stock_auto_trading.auto_start`(legacy `enabled`) + `enable_stock_live_order`를 UI에서 직관적으로 관리 가능하게 통합
2. 회귀 테스트 확장
   - 레짐별 임계값 조정/피드백 반영/XAI 필드 포함 여부를 단위 테스트로 고정
3. 운영 문서 동기화 자동화
   - 변경 시 `CHANGELOG`, 상태 문서, 운영 가이드를 같은 커밋에서 갱신하도록 체크리스트화

## 📌 최신 기준 (정본) — 2026-04-28 검색 고도화 2차 + 자산통합 확장 완료

이 문서는 과거 진행 기록을 포함합니다. 아래 항목은 2026-04-27 기준의 최신 상태이며,
하위의 상세 이력과 충돌할 경우 본 섹션을 우선 적용합니다.

### 1) 현재까지 확정 완료
- 통합 테스트 기준: `tests/test_stock_integration.py` → **48 passed, 6 skipped, 0 failed**
- 가드레일 테스트: `tests/test_stock_order_guardrails.py` → **14 passed**
- 전체 증권 관련 테스트: **85 passed, 6 skipped** (2026-04-28)
- 증권 어댑터 팩토리 분기:
  - `api_type=mock` → `StockMockAdapter`
  - `api_type=openapi/rest` → 증권사 어댑터 경로
- 설정 UI 확장:
  - 키움/신한/미래에셋/한국투자증권 입력 필드 + `api_type` + `api_version` 저장/로드 연결
  - 주문 가드레일 설정 UI 추가 (활성화/장시간/수량·금액·일일한도) 및 저장/복원 연결
- 설정 데이터 확장:
  - `data/settings.json > stock_broker_configs.*.api_version` 반영
  - `config/settings_template.json > stock_order_guardrails` 기본값 추가
- ETF 판별 회귀 보완:
  - 테스트셋 ETF 코드(예: `114800`) 판별 이슈 수정

### 2) Phase 1/2/3 + 1-2 구현 완료 (2026-04-27)

**Phase 1: 주식 종목 검색/분석 기능** ✅
- 증권 탭 내 종목코드 검색 UI 추가 (CTkEntry + 검색 버튼)
- StockAnalysisService 통합: 종목코드 → StockAnalysisService.analyze_symbol()
- 분석 결과 카드 렌더링: 종목명/가격/등락률/AI점수/판단근거/브로커/NAV괴리
- 검색 시 종목코드를 주문 패널 입력창으로 자동 반영
- 파일: `ui/dashboard_modern.py` 
  - `_ensure_stock_info_tab()`, `_search_stock_symbol()`, `_display_stock_analysis_card()`
- 상태: 완료, 테스트 통과

**Phase 1-2: 증권 분석/설명 중심 실행 경로 정리** ✅ (2026-05-01 정합 갱신)
- 종목 정보 탭 내 "🛡️ 증권 주문 (가드레일 적용)" 패널 추가
- 입력 항목: 증권사 선택/종목코드/수량/가격/주문타입(LIMIT·MARKET)
- 매수/매도 버튼 + 가드레일 평가 결과 상태 라벨
- 가드레일 연동: `trading/stock_order_guardrails.py` 의 `evaluate_stock_order_guardrails()` 호출
- DB 기록: 주문 성공 시 `recorder.insert_trade_log()`로 trade_log 저장
- 설정 화면: `ui/settings_modern.py` 에 가드레일 설정 UI 추가 (저장/복원 연결)
- 파일: `ui/dashboard_modern.py`
  - `_submit_stock_order()`, `_get_stock_order_guardrails()`, `_get_today_stock_order_count()`, `_set_stock_order_status()`
- 파일: `ui/settings_modern.py`
  - 가드레일 체크박스·입력 항목 + load/save 연결
- 파일: `trading/stock_order_guardrails.py`
  - `evaluate_stock_order_guardrails()`, `normalize_stock_order_guardrails()`, `is_krx_market_open()`
- 파일: `tests/test_stock_order_guardrails.py`
  - 시장시간/모드불일치/한도초과/정상케이스 단위테스트

**Phase 2: 자산 통합 실제 데이터 패널** ✅
- "🧭 자산 통합" 탭: 준비중 → 실데이터 표시 전환
- 통합 자산 현황: 총 자산/누적 손익 (sqlite3 DB 쿼리)
- 자산군별 비중: 암호화폐/주식 비율 (진행률 바)
- 포트폴리오 리스크: 집중도/최대손실/회전율 지표
- 추천 액션: 재균형·상관관계·리스크 관리 3가지 가이드
- 파일: `ui/dashboard_modern.py` `show_real_estate_content()`
- 상태: 완료

**Phase 3: 생활금융 MVP** ✅
- "💳 생활금융 서비스" 탭: 준비중 → 월간 재무 분석
- 월별 현금흐름 입력폼: 수입/고정비/변동비 (CTkEntry)
- 저축 가능액 자동 계산 + 재무 요약 + 투자 여력 분석
- 파일: `ui/dashboard_modern.py` `show_other_investment_content()`
- 상태: 완료

### 2-1) 기능별 구현 상태 요약

| 기능 | Phase | 상태 | 파일 | 비고 |
|------|-------|------|------|------|
| 종목 검색/분석 | 1 | ✅ 완료 | dashboard_modern.py | StockAnalysisService 통합 |
| 분석/설명 중심 증권 흐름 | 1-2 | ✅ 완료 | dashboard_modern.py, stock_order_guardrails.py | 종목 분석 + AI 어시스턴트 중심 |
| 브로커별 최소주문단위 검증 | 1-2 | ✅ 완료 | stock_order_guardrails.py | 최소수량/수량단위 검사 |
| 가드레일 설정 UI | 1-2 | ✅ 완료 | settings_modern.py | 활성화/수량/금액/일일한도 |
| 주문 DB 기록 | 1-2 | ✅ 완료 | dashboard_modern.py | recorder.insert_trade_log |
| 자산 통합 패널 | 2 | ✅ 완료 | dashboard_modern.py | DB 실시간 쿼리 |
| 생활금융 MVP | 3 | ✅ 완료 | dashboard_modern.py | 월간 현금흐름 계산 |
| 자동완성/즐겨찾기/최근검색 | 1+ | ✅ 완료 | dashboard_modern.py | 검색 고도화 1차+2차 |
| 상관관계 분석 | 2+ | ✅ 완료 | dashboard_modern.py | crypto/stock 상관계수 계산 |
| 리밸런싱 제안 | 2+ | ✅ 완료 | dashboard_modern.py | 집중도/연동성 기반 액션 |
| 지출 자동 분류 | 3+ | ⏳ 계획 | 미정 | Phase 3 확장 |
| 전략 자동매매 루프 | future | ⏳ 계획 | 미정 | 암호화폐 수준 가드레일 |

### 3) 현재 동작 중인 기능
- 코인/증권 서비스 모두 설정 기반 탭 생성 및 서비스 전환 동작
- 증권 서비스는 주식/ETF 통합 `stock` 컨텍스트로 작동
- AI 어시스턴트가 서비스 컨텍스트에 따라 입력 가이드/퀵질문/분석 문맥을 전환
- 종목 검색/자산 통합/생활금융 실제 기능 제공 (placeholder 제거)
- 사용자 화면에서 `통합` / `주식만` / `ETF만` 표시 모드를 선택할 수 있으며, 검색/상단 미리보기/AI 컨텍스트에 반영됨
- 내부 분석은 `is_etf`로 ETF 전용 지표를 분기하며, 증권 자동주문 경로 자체는 아직 암호화폐처럼 완성되지 않음

### 4) 아직 남은 개발 (우선순위)
1. **전략 자동매매 루프**: 신호 → 자동주문 경로를 암호화폐처럼 고도화
2. 생활금융 확장: 지출 자동 분류, 목표 관리, 시뮬레이션
3. 증권사 실연동 완성: 연결/잔고/포지션/주문의 실API 경로 고도화
4. ETF 전용 지표(추적오차/NAV 괴리/거래대금) 컨텍스트 조건부 주입

### 4-0) 48시간 실행 계획 (2026-04-27 정정)

기존의 `1주`, `2주` 식 표현 대신 현재 개발 속도와 AI 자동화를 반영해
이번 사이클은 `오늘(D0)`과 `내일(D1)` 기준으로 운영한다.

**D0 오늘 마감 목표**
- 인앱 사용자 메뉴얼과 핵심 문서 정합화 완료
- 증권 자동매매 루프의 제어 지점, 실주문 진입 조건, Mock 차단 지점 확인
- 브로커 키 정규화, 가드레일, 표시 모드 관련 테스트 보강

**D1 내일 마감 목표**
- Kiwoom 실주문 경로 1차 연결 또는 feature flag 기반 실주문 분기 확보
- ETF/주식 신호 분기 1차 반영
- 회귀 테스트와 수동 검증으로 `실행 가능/불가`를 명확히 판정

**이번 48시간에 하지 않는 것**
- 신한/미래에셋 전체 실거래 완성
- 차액거래 전체 구현
- 보험/대출 비교 서비스 완성

이 항목들은 후속 스프린트로 분리하고, 이번 사이클에서는 배포를 막는 직접 원인만 제거한다.

### 4-1) 우선순위 체크리스트 (2026-04-27)

완료(이번 사이클)
- [x] 인앱 사용자메뉴얼에 `📈 증권/주식/ETF` 탭 실제 생성 연결
- [x] 브로커 키 정규화 통일(`miraeAsset`/`mirae_asset`/`miraeasset`)
- [x] 가드레일 테스트 별칭 키 케이스 반영
- [x] USER_GUIDE 상태 문구 정합화
- [x] TRADING_FLOW 학습 경로 설명 정정
- [x] 주문 패널 입력 단계 실시간 브로커 단위 위반 경고(UI) + 매수/매도 버튼 비활성
- [x] 서비스별 탭 분리 정책 반영(자산통합/생활금융/AI애널리스트 전용 탭)
- [x] 주문 결과에 `mock/live_api` 실행 경로와 `api_type` 노출
- [x] StockAnalysisService 분석 결과에 `analysis_type`, `score_model`, `reasoning` 추가로 주식/ETF 판단 근거 분리
- [x] 실주문 1차 feature flag 분기 연결(`enable_stock_live_order` 또는 증권사별 `allow_live_order` 미활성 시 주문 차단)
- [x] 증권 자동매매 루프 1차 연결(분석 신호→자동주문 사이클, 서비스 계층 + 대시보드 주기 실행)
- [x] 증권 자동매매의 심볼별 XAI 결정 로그 + 사이클 요약 XAI + 성공 주문 즉시 `trade_log` 기록 보강
- [x] 종목 검색 고도화 1차 반영(최근검색/즐겨찾기/원클릭 재검색 + 설정 저장)
- [x] 종목 검색 고도화 2차 반영(자동완성/부분일치 추천/원클릭 제안 검색)
- [x] 자산 통합 확장 1차 반영(crypto/stock 상관계수 + 집중도 기반 리밸런싱 액션)

남은 핵심 우선순위
- [ ] 증권사 실연동 고도화(연결/잔고/포지션/주문 실API 검증)
- [ ] 생활금융 확장(지출 자동 분류/목표 관리/시뮬레이션)

현실적 마감 기준
- 이번 사이클 완료선: `Kiwoom 1차 실행 경로 확보/표시 + ETF 분기 1차 반영 + 실주문 feature flag 분기 + 테스트 통과`
- 후속 사이클 완료선: `신한/미래에셋 실주문 검증 + 검색 고도화 + 자산통합/생활금융 심화`

무API 환경 처리 기록 (2026-04-28)
- 증권사 실연동 고도화(실계좌 연결/주문)는 테스트용 API 키·계정 또는 Windows+pykiwoom 실환경이 없어 이 사이클에서는 실행 불가.
- 대신 무API 환경에서 가능한 범위로 `mock/live 분기`, `실주문 feature flag`, `자동매매 1차 루프`까지 구현/검증 완료.
- 실계좌 검증 항목은 다음 순서에서 API 준비 후 재개한다.

---

## 🗂️ 이하 내용은 단계별 이력 (레거시 기록)

## 📋 개요

주식/ETF 서비스를 블록체인 서비스와 동일한 구조로 추가하는 작업을 진행 중입니다. 현재 기본 UI 구조와 설정 기능이 완료되었으며, 다음 단계로 실제 기능 구현이 필요합니다.

### 🎯 설계 결정 (2026-04-23)

**주식과 ETF 통합 설계 채택**
- **방식**: 단일 "stock" 서비스로 주식과 ETF 함께 관리
- **근거**: 거래 방식/API 동일, 구현 기간 3-4일, 산업 표준
- **상세**: `docs/STOCK_ETF_ARCHITECTURE_DECISION_20260423.md` 참고

---

## ✅ 현재까지 완료된 작업

### 1. 설정 구조 추가 ✅

#### 1.1 `settings_template.json` 확장
- **파일**: `config/settings_template.json`
- **추가 내용**:
  - `enabled_stock_brokers`: 활성화된 증권사 목록
  - `stock_broker_configs`: 증권사별 설정 (키움증권 포함)
- **위치**: 라인 74-84

#### 1.2 `settings.py` 로드/저장 로직
- **상태**: 자동 지원 (기존 구조 활용)
- **설명**: `settings_template.json`에 추가된 항목은 자동으로 로드/저장됨

---

### 2. 설정 UI 확장 ✅

#### 2.1 키움증권 API 입력 필드 추가
- **파일**: `ui/settings_modern.py`
- **위치**: "거래소 API" 탭
- **추가 필드**:
  - ID 입력 필드 (`kiwoom_id_entry`)
  - 비밀번호 입력 필드 (`kiwoom_password_entry`)
  - 공인인증서 비밀번호 입력 필드 (`kiwoom_cert_password_entry`)
  - 계좌번호 입력 필드 (`kiwoom_account_entry`)

#### 2.2 증권사 선택 체크박스 추가
- **파일**: `ui/settings_modern.py`
- **위치**: "거래소 선택" 탭
- **추가 내용**:
  - "📈 주식/증권사 선택" 섹션
  - 키움증권 체크박스 (`stock_broker_vars['kiwoom']`)

#### 2.3 설정 저장/로드 로직
- **`load_current_settings()`**: 라인 1757-1767
  - `enabled_stock_brokers` 로드
  - `stock_broker_configs['kiwoom']` 로드
- **`save_settings()`**: 라인 1907-1926
  - 키움증권 입력 필드 저장
  - 체크박스 상태 저장

---

### 3. 대시보드 서비스 전환 로직 ✅

#### 3.1 `show_stock_content()` 구현
- **파일**: `ui/dashboard_modern.py`
- **위치**: 라인 4222-4242
- **기능**: 주식/증권 서비스 전환 시 기본 탭 선택

#### 3.2 `create_service_sub_tabs('stock')` 추가
- **파일**: `ui/dashboard_modern.py`
- **위치**: 라인 3796-3844
- **기능**: 설정에서 활성화된 증권사별 탭 생성
- **탭 레이아웃**: 블록체인 서비스와 동일한 구조
  - 좌측: 제어, 잔고, 포지션, 거래 통계
  - 우측: 실시간 로그

#### 3.3 `create_broker_*` 섹션 메서드 구현
- **파일**: `ui/dashboard_modern.py`
- **메서드들**:
  - `create_broker_control_section()`: 라인 4070-4090
  - `create_broker_balance_section()`: 라인 4092-4112
  - `create_broker_positions_section()`: 라인 4114-4138
  - `create_broker_stats_section()`: 라인 4140-4161
  - `create_broker_logs_section()`: 라인 4163-4192
- **상태**: Placeholder 구현 (실제 데이터 로드는 다음 단계)

---

### 4. 탭 정리 로직 개선 ✅

#### 4.1 `_destroy_previous_service_tabs()` 수정
- **파일**: `ui/dashboard_modern.py`
- **위치**: 라인 3496-3531
- **개선 내용**:
  - 블록체인과 주식이 모두 `🏦` 패턴을 사용하므로 `service_sub_tabs` 딕셔너리로 구분
  - 현재 서비스의 `service_sub_tabs`에 있는 탭은 보호

---

### 5. 문서 업데이트 ✅

#### 5.1 개발 가이드 작성
- **파일들**:
  - `docs/STOCK_ETF_DEVELOPMENT_GUIDE_20260118.md`: 개발 단계 및 구조
  - `docs/STOCK_ETF_UI_VERIFICATION_20260118.md`: UI 구조 검증
  - `docs/STOCK_ETF_ADDITION_GUIDE.md`: 기술적 추가 가이드
  - `docs/STOCK_ETF_TEST_CHECKLIST_20260118.md`: 테스트 체크리스트

#### 5.2 변경 로그 업데이트
- **파일**: `docs/CODE_CHANGE_LOG.md`
- **위치**: 라인 1488-1582
- **내용**: 주식/ETF 서비스 UI 구조 추가 작업 내역

---

### 즉시 (D0-D1)
1. Phase 1-3 실제 거래 데이터/Mock 경계 통합 검증
  - 암호화폐/주식 거래 기록 기반 검증
  - 실주문 가능 여부와 차단 조건 명확화

2. 증권 자동매매 루프 1차 연결
  - Mock 강제 경로 제거 또는 feature flag 분기 추가
  - 주문 상태/예외 로그 정리

3. ETF 분기 1차 반영
  - 주식/ETF 신호 생성 분기
  - ETF 전용 설명 필드 노출 확인

### 후속 스프린트
1. 종목 자동완성/즐겨찾기/최근검색
2. 자산 통합 상관관계 분석
3. 생활금융 목표 관리/시뮬레이션
4. 부동산/선물 자산 확장

#### 증상
- 주식/증권 서비스 전환 시에도 "🪙 코인 정보", "📈 거래 통계", "📈 시장 트렌드"가 그대로 표시됨
- 이들은 블록체인(코인) 데이터만 표시함

#### 원인
- 기본 탭들이 `create_main_content()`에서 한 번 생성되고 이후 유지됨
- 서비스별로 다른 위젯으로 교체하는 로직이 없음

#### 해결
- **파일**: `ui/dashboard_modern.py`
- **위치**: 라인 1918-2160
- **수정 내용**: 
  1. `_ensure_stock_info_tab()`: "🪙 종목 정보" 탭 생성 메서드 추가
  2. `_ensure_stock_trading_stats_tab()`: 주식 거래 통계 탭 생성 메서드 추가
  3. `_ensure_stock_trend_tab()`: 주식 시장 트렌드 탭 생성 메서드 추가
  4. `show_stock_content()` 수정: 주식 서비스 전환 시 주식용 탭 생성 호출
- **참고**: CTkTabview는 탭을 직접 제거할 수 없으므로, "🪙 코인 정보"와 "🪙 종목 정보"는 별도 탭으로 존재할 수 있음 (향후 개선 가능)

#### 검증 결과
- ✅ 주식/증권 서비스 전환 시 "🪙 종목 정보" 탭이 생성됨
- ✅ 주식 거래 통계 탭이 주식용 내용으로 교체됨
- ✅ 주식 시장 트렌드 탭이 주식용 내용으로 교체됨

---

## 📝 다음 단계 계획 (작성 당시 기준 이력)

### 단계 1: 알려진 문제 해결 (우선순위 높음)

#### 1.1 BINANCE 탭 표시 문제 해결
- **작업**: `switch_service()` 호출 시 블록체인 탭 제거 확인
- **파일**: `ui/dashboard_modern.py`
- **예상 시간**: 1시간

#### 1.2 `enabled_stock_brokers` 저장/로드 확인
- **작업**: 설정 저장 후 실제 값이 `settings.json`에 저장되는지 확인
- **테스트**: 키움증권 체크 후 저장 → `settings.json` 확인
- **예상 시간**: 30분

---

### 단계 2: 기본 탭 교체 로직 구현 (중기)

#### 2.1 주식/종목 정보 위젯 개발
- **파일**: `ui/widgets/stock_info_widget.py` (신규)
- **기능**:
  - 선택된 종목 정보 표시 (주식/ETF)
  - AI 평가 결과 표시
  - 블록체인 `_ensure_coin_info_tab()`와 유사한 구조

#### 2.2 주식 거래 통계 위젯 개발
- **파일**: `ui/widgets/stock_trading_stats_widget.py` (신규)
- **기능**:
  - 주식/ETF 거래 통계 표시
  - 블록체인 `_ensure_trading_stats_tab()`와 유사한 구조

#### 2.3 주식 시장 트렌드 위젯 개발
- **파일**: `ui/widgets/stock_market_trend_widget.py` (신규)
- **기능**:
  - 주식 시장 트렌드 분석
  - 블록체인 `MarketTrendWidget`와 유사한 구조

#### 2.4 `show_stock_content()` 확장
- **작업**: 기본 탭 제거 후 주식용 위젯으로 교체
- **파일**: `ui/dashboard_modern.py`
- **메서드**:
  - `_ensure_stock_info_tab()`: 종목 정보 탭 생성
  - `_ensure_stock_trading_stats_tab()`: 주식 거래 통계 탭 생성
  - `_ensure_stock_trend_tab()`: 주식 시장 트렌드 탭 생성

---

### 단계 3: 키움증권 API 어댑터 개발 (장기)

**✅ 현재 상태**: 기본 구조는 이미 생성됨

#### 3.1 `StockExchange` 인터페이스 정의 ✅ 완료
- **파일**: `trading/exchanges/interfaces/stock_exchange.py`
- **상태**: ✅ 이미 생성됨 (183줄)
- **구현 내용**:
  - `get_stock_list()`: 주식 목록 조회
  - `get_etf_list()`: ETF 목록 조회
  - `is_etf()`: ETF 여부 확인
  - `get_stock_info()`: 주식/ETF 상세 정보 조회
  - `get_realtime_price()`: 실시간 시세 조회
  - `place_order()`: 주문 실행
- **참고**: `docs/STOCK_ETF_ADDITION_GUIDE.md` 라인 60-87

#### 3.2 `KiwoomStockAdapter` 구현 🚧 부분 완료
- **파일**: `trading/exchanges/adapters/kiwoom_stock_adapter.py`
- **상태**: 🚧 기본 구조 생성됨, 실제 API 연동은 미구현 (플레이스홀더)
- **구현 완료**:
  - ✅ 클래스 구조 및 초기화
  - ✅ ETF 코드 패턴 정의 (`etf_code_patterns`)
  - ✅ `connect()` 메서드 (플레이스홀더)
  - ✅ `get_stock_list()` 메서드 (플레이스홀더)
  - ✅ `get_etf_list()` 메서드 (플레이스홀더)
  - ✅ `is_etf()` 메서드 (코드 패턴 기반)
- **미구현**:
  - ⏳ 실제 키움 OpenAPI+ 라이브러리 연동
  - ⏳ 실제 API 호출 구현
  - ⏳ 잔고 조회 구현
  - ⏳ 주문 실행 구현
  - ⏳ 포지션 조회 구현
- **참고**: `docs/STOCK_ETF_ADDITION_GUIDE.md` 라인 89-130

#### 3.3 `ExchangeFactory` 확장
- **파일**: `trading/exchanges/exchange_factory.py`
- **작업**: `StockExchange` 타입 지원 추가
- **참고**: `docs/STOCK_ETF_ADDITION_GUIDE.md` 라인 132-164

#### 3.4 `UnifiedTradingManager` 확장
- **파일**: `trading/unified_trading_manager.py`
- **작업**: 주식/ETF 거래 지원 추가
- **참고**: `docs/STOCK_ETF_ADDITION_GUIDE.md` 라인 166-184

**⚠️ AI API 구조 활용**:
- ETF Trader 구현 시 `AIManager` 활용 (암호화폐 패턴 참고)
- `docs/AI_API_ARCHITECTURE.md` 참고 필수
- 오픈소스 전환 고려 (`base_url` 설정 지원)

---

### 단계 4: `create_broker_*` 메서드 실제 구현 (장기)

**⚠️ 현재 상태**: Placeholder 구현 완료 (라인 4353-4648), 실제 데이터 로드 필요

#### 4.1 `create_broker_control_section()` 구현
- **파일**: `ui/dashboard_modern.py` 라인 4355-4420
- **현재 상태**: Placeholder 구현 완료
- **기능**: 증권사별 시작/정지 버튼
- **데이터 소스**: `UnifiedTradingManager` 또는 `KiwoomStockAdapter`
- **참고**: `create_exchange_control_section()` 패턴 (블록체인)

#### 4.2 `create_broker_balance_section()` 구현
- **파일**: `ui/dashboard_modern.py` 라인 4422-4461
- **현재 상태**: Placeholder 구현 완료
- **기능**: 현금 잔고, 주식/ETF 평가액 표시
- **데이터 소스**: 증권사 API
- **참고**: `create_exchange_balance_section()` 패턴 (블록체인)

#### 4.3 `create_broker_positions_section()` 구현
- **파일**: `ui/dashboard_modern.py` 라인 4463-4518
- **현재 상태**: Placeholder 구현 완료
- **기능**: 보유 종목 리스트 (주식/ETF 구분 표시), 평단가, 현재가, 평가손익
- **데이터 소스**: 증권사 API
- **참고**: `create_exchange_positions_section()` 패턴 (블록체인)

#### 4.4 `create_broker_stats_section()` 구현
- **파일**: `ui/dashboard_modern.py` 라인 4520-4561
- **현재 상태**: Placeholder 구현 완료
- **기능**: 거래 횟수, 승률, 누적 손익 표시
- **데이터 소스**: `trade_log` DB (주식/ETF 필터링)
- **참고**: `create_exchange_stats_section()` 패턴 (블록체인)

#### 4.5 `create_broker_logs_section()` 구현
- **파일**: `ui/dashboard_modern.py` 라인 4563-4648
- **현재 상태**: Placeholder 구현 완료
- **기능**: 증권사별 실시간 거래 로그
- **참고**: `create_exchange_logs_section()` 패턴 (블록체인)

---

## 🎯 완료 기준

### 현재 단계 (옵션 2) 완료 기준
- [x] 설정 UI 완료
- [x] 대시보드 서비스 전환 로직 완료
- [x] 증권사별 탭 생성 로직 완료
- [x] 문서화 완료
- [ ] 알려진 문제점 해결 (다음 단계에서 처리)

### 다음 단계 (기본 탭 교체) 완료 기준
- [ ] 주식/종목 정보 위젯 개발 완료
- [ ] 주식 거래 통계 위젯 개발 완료
- [ ] 주식 시장 트렌드 위젯 개발 완료
- [ ] `show_stock_content()`에서 탭 교체 로직 구현 완료
- [ ] 블록체인 ↔ 주식 전환 시 탭이 올바르게 교체되는지 확인

---

## 📚 관련 문서

### 개발 가이드
- `docs/STOCK_ETF_DEVELOPMENT_GUIDE_20260118.md`: 개발 단계 가이드
- `docs/STOCK_ETF_UI_VERIFICATION_20260118.md`: UI 구조 검증
- `docs/STOCK_ETF_ADDITION_GUIDE.md`: 기술적 추가 가이드
- `docs/STOCK_ETF_TEST_CHECKLIST_20260118.md`: 테스트 체크리스트
- `docs/AI_API_ARCHITECTURE.md`: **AI API 구조 및 오픈소스 전환 가이드** (필수 참고)

### 변경 로그
- `docs/CODE_CHANGE_LOG.md`: 전체 변경 로그

### 코드 참고
- `ui/dashboard_modern.py`: 대시보드 UI 구현
  - 라인 4081-4129: `create_service_sub_tabs('stock')` 구현 완료
  - 라인 4353-4648: `create_broker_*` 메서드들 구현 완료 (placeholder)
  - 라인 4651-4670: `show_stock_content()` 구현 완료
- `trading/exchanges/interfaces/stock_exchange.py`: StockExchange 인터페이스
- `trading/exchanges/adapters/kiwoom_stock_adapter.py`: 키움증권 어댑터
- `trading/ai/ai_manager.py`: AI 분석 API 구조
- `trading/ai/openai_client.py`: OpenAI 클라이언트 (오픈소스 전환 고려)

---

## 💡 참고 사항

### 현재 상태
- **UI 기본 구조**: ✅ 완료
- **설정 기능**: ✅ 완료
- **서비스 전환**: ✅ 기본 완료 (탭 교체 제외)
- **실제 기능**: ⏳ 다음 단계 (API 어댑터 개발 후)

### 블록체인 기능 영향
- **영향 없음**: ✅ 확인됨
- **독립 메서드 사용**: ✅ `create_broker_*` vs `create_exchange_*`
- **설정 분리**: ✅ `enabled_stock_brokers` vs `enabled_exchanges`

### 향후 작업 우선순위
1. **높음**: 알려진 문제 해결 (BINANCE 탭 표시, 설정 저장 확인)
2. **중간**: 기본 탭 교체 로직 구현
3. **낮음**: 실제 API 어댑터 개발 (데이터 소스 필요)

---

**마지막 업데이트**: 2026-01-26
**작성자**: AI Assistant
**상태**: ✅ 현재 단계 완료, 다음 단계 준비 완료

---

## ⚠️ 중요: AI API 구조 활용 및 오픈소스 전환 고려

### AI API 활용 가이드
**참고 문서**: `docs/AI_API_ARCHITECTURE.md`

ETF/주식 개발 시 AI API를 올바르게 활용해야 합니다:

1. **AIManager 초기화**: 직접 초기화하지 않고 `main.py`에서 전달받음
   ```python
   # main.py 패턴 (라인 1598-1614)
   if openai_api_key:
       openai_model = settings.get('openai_model', 'gpt-3.5-turbo')
       openai_base_url = settings.get('openai_base_url')  # 오픈소스 전환용
       self.ai_manager = AIManager(openai_api_key, openai_model, base_url=openai_base_url)
   ```

2. **가드 체크 필수**: `if self.ai_manager and self.ai_manager.enabled()` 항상 사용
   ```python
   # ETF 신호 생성 시
   if self.ai_manager and self.ai_manager.enabled():
       ai_analysis = self.ai_manager.analyze_market_conditions(...)
   else:
       # AI 비활성화 시 기본 분석만 사용
       pass
   ```

3. **에러 폴백**: AI 호출 실패 시 기본 분석으로 폴백
4. **오픈소스 전환 준비**: `base_url` 설정 지원으로 향후 전환 가능

### 대시보드 UI 일관성 유지
**현재 상태**: 블록체인 서비스와 동일한 패턴으로 이미 구현됨
- ✅ `create_service_sub_tabs('stock')` 구현 완료 (라인 4081-4129)
- ✅ `create_broker_*` 메서드들 구현 완료 (라인 4353-4648, placeholder)
- ✅ 좌/우 2단 레이아웃 구조 유지
- ✅ 동일한 색상/폰트/위젯 구조 사용

**참고**: `docs/STOCK_ETF_UI_VERIFICATION_20260118.md`에서 UI 구조 검증 결과 확인
