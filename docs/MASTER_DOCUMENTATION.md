# NoahAI 마스터 문서 (운영 참조 인덱스)

> **최신 동기화 기준: 2026-06-22 · v3.8.9.22**
>
> 본 파일은 **정본 문서 인덱스**입니다.
> 실제 내용은 아래 링크한 정본 문서를 직접 참조하세요.
> 2025~2026 이전 이력은 하단 레거시 섹션을 참고하세요.
> 2026-06-22 갱신: 배포 버전 단일 소스 `config/app_version.py` 기준 `v3.8.9.22`로 동기화

---

## 📌 정본 문서 인덱스 (현행 기준)

| 카테고리 | 정본 파일 | 역할 |
|----------|-----------|------|
| 제품 버전 / 변경 이력 | `docs/CHANGELOG.md` | 버전별 변경 내역의 유일한 정본 |
| 사용자 가이드 | `docs/USER_GUIDE.md` | 기능 설명·단계별 사용법 (외부 공개 가능) |
| 인앱 매뉴얼 | `ui/widgets/user_manual_widget.py` | 대시보드 내 사용설명서 위젯 |
| 아키텍처 / 책임 경계 | `docs/ARCHITECTURE.md` | 판단·기록·검증·환류 파이프라인 구조 |
| 개발 계획 / 로드맵 | `docs/UPDATE_PLAN.md` | 기술 확장 계획 (개발팀용) |
| 테스트 현황 | `docs/TEST_STATUS.md` | 최신 pytest 결과 + 신규 테스트 그룹 |
| API 참조 | `docs/API_REFERENCE.md` | REST·WebSocket 엔드포인트 |
| 증권/ETF 상태 | `docs/STOCK_ETF_IMPLEMENTATION_STATUS_20260423.md` | 증권사·어댑터 현황 |
| KPI 트랙션 | `docs/KPI_VC_TIPS_GUIDE_20260428.md` | KPI 집계·VC 공유 가이드 |
| 법무 패키지 | `docs/LEGAL_PACKAGE_20260428_INDEX.md` | 책임 경계·개인정보·투자자문 검토 |
| 사업/특허 최종 정합 점검 | `docs/FINAL_BUSINESS_PATENT_READINESS_20260622.md` | 코드 근거 기반 사실성 판정/확인 체크리스트 |
| ChatGPT 업로드 패키지 | `docs/CHATGPT_PROJECT_KNOWLEDGE_PACK_20260622.md` | ChatGPT Pro 프로젝트 업로드 우선순위/작업 순서 |
| ChatGPT 작성 브리프 | `docs/CHATGPT_PATENT_BUSINESS_AUTHORING_BRIEF_20260622.md` | 특허/사업 제안서 작성용 팩트 고정 입력본 |
| 증권 라이브 체크리스트 | `docs/STOCK_LIVE_READINESS_CHECKLIST_20260428.md` | 실거래 전환 점검 |
| 코인 선정 가이드 | `docs/COIN_SELECTION_GUIDE.md` | 암호화폐 종목 선정 알고리즘 |
| 생활금융 가이드 | `docs/LIFE_FINANCE_GUIDE.md` | Phase F 생활금융 구현 현황 |
| 세무 계산 모듈 | `trading/tax_calculation_service.py` | 연말정산·금투세·ISA/IRP 절세 비교 ✅ NEW |
| 이상 탐지 모듈 | `trading/fraud_detection_service.py` | 보이스피싱·이상거래·약탈적 대출 탐지 ✅ NEW |
| 세무 테스트 | `tests/test_tax_calculation_service.py` | 53 passed ✅ NEW |
| 이상탐지 테스트 | `tests/test_fraud_detection_service.py` | 32 passed ✅ NEW |
| 로깅 가이드 | `docs/LOGGING_SYSTEM_GUIDE.md` | 로그 시스템 구조 |
| TP/SL 가이드라인 | `docs/TP_SL_GUIDELINES.md` | TP/SL 정책·설정 |
| AlphaArena | `docs/ALPHA_ARENA_DEVELOPMENT.md` | AlphaArena 모드 설계 |
| 문서 관리 정책 | `docs/DOCUMENTATION_POLICY.md` | 문서 작성·중복 방지 규칙 |

---

## 📋 중복/레거시 문서 현황

아래 문서들은 특정 시점의 작업 기록 또는 중간 분석 산출물입니다.
현재 기능 상태 판단은 **위 정본 인덱스의 링크 문서**를 우선하세요.

### 아카이브된 분석 문서 (참고 전용)
- `docs/STOCK_ETF_CURRENT_STATUS_20260118.md` → 2026-01 시점 이력 (정본: TEST_STATUS.md)
- `docs/STOCK_ETF_DEVELOPMENT_GUIDE_20260118.md` → 2026-01 개발 가이드 (정본: STOCK_ETF_ADDITION_GUIDE.md)
- `docs/DEVELOPMENT_STATUS_COMPREHENSIVE_20260427.md` → 2026-04-27 종합 현황 (정본: TEST_STATUS.md + CHANGELOG.md)
- `docs/WORK_COMPLETION_2026-04-24.md` → 2026-04-24 완료 기록 (정본: CHANGELOG.md)
- `docs/IMPLEMENTATION_ROADMAP_2026-04-24.md` → 2026-04-24 로드맵 (정본: UPDATE_PLAN.md)
- `docs/DEVELOPMENT_VALIDATION_2026-04-24.md` → 2026-04-24 검증 기록 (정본: TEST_STATUS.md)
- `docs/SECTION_PROGRESS_FEEDBACK_20260428.md` → 2026-04-28 진행 피드백 (정본: CHANGELOG.md)
- `docs/STOCK_DEVELOPMENT_COMPLETION_20260424.md` → 2026-04-24 증권 완료 기록 (정본: CHANGELOG.md)
- `docs/BLOCKCHAIN_INTEGRATION_ANALYSIS_20260428.md` → 블록체인 분석 (정본: ARCHITECTURE.md)
- `docs/EXCHANGE_ADDITION_ACTION_PLAN_20260428.md` → 거래소 추가 계획 (정본: UPDATE_PLAN.md)
- `docs/AI_REPORT_TRADE_HISTORY_ANALYSIS_20260118.md` → 2026-01 분석 리포트

### AlphaArena 복수 문서 → 정본 링크
- `docs/ALPHA_ARENA_DEVELOPMENT.md` ← **정본**
- `docs/ALPHA_ARENA_DIFFERENCES.md`, `ALPHA_ARENA_FINAL_REVIEW.md`, `ALPHA_ARENA_MODE.md`,
  `ALPHA_ARENA_PROMPT_ANALYSIS.md`, `ALPHA_ARENA_REAL_TRADING_ANALYSIS.md`,
  `ALPHA_ARENA_TRADING_FLOW.md`, `ALPHA_ARENA_TRADING_VERIFICATION.md` ← 보조 참고

### TP/SL 복수 문서 → 정본 링크
- `docs/TP_SL_GUIDELINES.md` ← **정본**
- `docs/TP_SL_DOCUMENTATION_INDEX.md` ← 세부 인덱스
- `docs/TP_SL_FIX_V3.8.9.11_20260125.md`, `docs/TP_SL_GALA_JASMY_ROOT_CAUSE_ANALYSIS_20260125.md` ← 이력

### UI/테마 복수 문서 → 정본 링크
- `docs/UI_DESIGN_GUIDE.md` ← **정본**
- `docs/WIDGET_CONSOLIDATION_REPORT.md`, `docs/WIDGET_COLORS_FIX_PLAN.md`,
  `docs/WIDGET_USAGE_ANALYSIS.md`, `docs/WIDGETS_HARDCODED_COLORS_ANALYSIS.md` ← 이력

---

## 📜 레거시 이력 (2025-10-24 작업 기록)

> 이하 내용은 2025-10-24 시점 버그 수정 기록입니다.
> 현재 코드 상태와 다를 수 있으므로 **참고 전용**으로만 사용하세요.

## 코인 정보 대시보드 수정 (2025-10-24)

### 🚨 **사용자 보고 문제**
- 목차가 두 개로 중복 표시됨
- 리스크 점수가 전부 0으로 표시됨
- 로그 분석과 점수들이 다름

### 🔍 **문제 분석 과정**
1. **코드 전체 검색**: `coin_evaluation` 테이블 사용처 확인
2. **데이터베이스 구조 확인**: 실제 테이블 구조 vs 코드의 구조 불일치 발견
3. **점수 계산 로직 확인**: `evaluator.py`와 `analyzer.py`의 `risk_score` 계산 방식 다름
4. **하드코딩된 값 확인**: 여러 파일에서 하드코딩된 점수들 발견
5. **접근 방식 확인**: `main.py`에서 딕셔너리를 객체로 접근하려는 문제 발견

### 📝 **수정 내용 상세**

#### **1. `ui/dashboard_modern.py` 수정**
- **라인 3728-3743**: 목차 중복 제거
  - **변경 전**: AI 평가 데이터가 있을 때와 없을 때 모두 헤더 생성
  - **변경 후**: AI 평가 데이터가 있을 때만 테이블 헤더 생성
- **라인 3894-3901**: SELECT 쿼리 수정
  - **변경 전**: 새로운 컬럼 구조로 조회 시도
  - **변경 후**: 기존 컬럼 구조에 맞게 조회

#### **2. `trading/evaluator.py` 수정**
- **라인 1822-1834**: 리스크 점수 계산 로직 추가
  ```python
  # 7. 리스크 점수 계산 - 변동성과 거래량 종합
  risk_score = 70  # 기본값
  try:
      # 변동성과 거래량을 종합하여 리스크 평가
      volatility_risk = 100 - volatility_score  # 변동성이 높으면 리스크 높음
      volume_risk = 100 - volume_score  # 거래량이 불안정하면 리스크 높음
      
      # 리스크 점수 계산 (낮을수록 좋음)
      risk_score = max(20, min(100, (volatility_risk + volume_risk) / 2))
  ```
- **라인 1866**: `coin_scores`에 `risk_score` 필드 추가
  ```python
  'risk_score': risk_score  # 🔥 리스크 점수 추가
  ```
- **라인 1912-1928**: 데이터베이스 테이블 구조 수정
  - **변경 전**: 새로운 컬럼 구조로 테이블 생성 시도
  - **변경 후**: 기존 구조 유지 (호환성 보장)
- **라인 1940-1957**: INSERT 쿼리 수정
  - **변경 전**: 새로운 컬럼 구조로 삽입 시도
  - **변경 후**: 기존 컬럼 구조에 맞게 삽입

#### **3. `trading/recorder.py` 수정**
- **라인 247-262**: 데이터베이스 테이블 구조 통일
  - **변경 전**: 새로운 컬럼 구조로 테이블 생성 시도
  - **변경 후**: 기존 구조 유지 (호환성 보장)

#### **4. `trading/unified_trader.py` 수정**
- **라인 380-404**: 하드코딩된 `overall_score` 값들 제거
  - **변경 전**: `{'symbol': 'BTCUSDT', 'overall_score': 0.8, 'is_major': True}`
  - **변경 후**: `{'symbol': 'BTCUSDT', 'is_major': True}`

#### **5. `trading/analyzer.py` 수정**
- **라인 1227-1258**: `risk_score` 계산을 `evaluator.py`와 동일한 방식으로 통일
  - **변경 전**: 자체적인 리스크 점수 계산 로직
  - **변경 후**: `evaluator.py`와 동일한 변동성+거래량 종합 방식

#### **6. `main.py` 수정**
- **라인 2763-2777**: `analysis_result` 딕셔너리 접근 방식을 `getattr`에서 `get`으로 수정
  - **변경 전**: `getattr(analysis_result, 'overall_score', 'N/A')`
  - **변경 후**: `analysis_result.get('overall_score', 'N/A')`
- **라인 2707-2721**: `_save_analysis_to_database` 메서드도 동일하게 수정

#### **7. `test_trader_cycle.py` 수정**
- **라인 55-57**: 테스트용 하드코딩된 점수들 제거
  - **변경 전**: `{'symbol': 'BTCUSDT', 'overall_score': 85.0, 'is_major': True}`
  - **변경 후**: `{'symbol': 'BTCUSDT', 'is_major': True}`

### 🔧 **리스크 점수 계산 방식 (통일)**
- **변동성 리스크**: `100 - volatility_score` (변동성이 높으면 리스크 높음)
- **거래량 리스크**: `100 - volume_score` (거래량이 불안정하면 리스크 높음)
- **최종 리스크 점수**: `(volatility_risk + volume_risk) / 2` (범위: 20-100)

### 🗄️ **데이터베이스 구조 (기존 호환성 유지)**
```sql
CREATE TABLE coin_evaluation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    technical_score REAL,
    volatility_score REAL,
    volume_score REAL,
    trend_score REAL,
    risk_score REAL,
    overall_score REAL,
    rank INTEGER,
    selection_reason TEXT,
    risk_level TEXT,
    timestamp DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```
**⚠️ 중요**: 기존 데이터베이스 호환성을 위해 테이블 구조를 변경하지 않고 기존 구조를 유지합니다.

### 📊 **영향받는 파일들**
- **코인 점수 사용**: `ui/dashboard_modern.py`, `trading/trader.py`, `trading/unified_trader.py`, `main.py`, `trading/analyzer.py`, `trading/market_sentiment_analyzer.py`, `test_trader_cycle.py`
- **데이터베이스 사용**: `trading/evaluator.py`, `trading/recorder.py`, `ui/dashboard_modern.py`
- **분석 결과 사용**: `main.py` (딕셔너리 접근 방식으로 수정)

### 🚨 **위험했던 수정 시도 (차단됨)**
사용자가 제안한 다음 수정은 **매우 위험**하여 차단됨:
```sql
-- 🚨 위험한 수정 (차단됨)
total_score REAL,           ← overall_score와 다름!
volume_spike REAL,          ← 존재하지 않는 컬럼!
change_15m REAL,            ← 존재하지 않는 컬럼!
change_1h REAL,             ← 존재하지 않는 컬럼!
rsi_15m REAL,              ← 존재하지 않는 컬럼!
rsi_1h REAL,               ← 존재하지 않는 컬럼!
trend_strength REAL,        ← 존재하지 않는 컬럼!
trade_frequency REAL,       ← 존재하지 않는 컬럼!
orderbook_depth REAL,       ← 존재하지 않는 컬럼!
timestamp TEXT,             ← DATETIME에서 TEXT로 변경!
is_major BOOLEAN DEFAULT 0, ← 존재하지 않는 컬럼!
```
**위험성**: 기존 데이터 완전 손실, 애플리케이션 크래시, 데이터베이스 무결성 파괴

### ✅ **검증 완료 사항**
1. **데이터베이스 구조 호환성**: 기존 테이블 구조 유지
2. **모든 사용처 확인**: 5개 파일에서 사용하는 모든 부분 수정 완료
3. **데이터 매핑 정확성**: 올바른 컬럼 매핑 확인
4. **기존 데이터 보호**: 기존 데이터 손실 위험 없음
5. **린터 오류 없음**: 모든 수정 파일에서 문법 오류 없음

## 동적 설정 시스템 업데이트 (2025-10-21 v3.8.8.8)

### 하드코딩된 값들을 설정 파일로 이동하여 동적 조절 가능하도록 최적화

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

## 거래 안정성 업데이트 요약 (2025-10)

### TP/SL 생성 규약 통일
- 모든 TP/SL 생성은 `trading/trader.py`의 `_tp_sl_order_params` 헬퍼를 경유합니다.
- **원웨이 모드**: `closePosition=True`, `workingType`만 포함( `positionSide` 제외 )
- **헤지 모드**: `closePosition=True`, `positionSide`, `workingType` 포함
- 이 규약으로 원웨이/헤지 모드 불일치(-1106 등) 오류를 예방합니다.

### 주문 정리 정책(선별 취소)
- 기본 원칙: TP/SL 외 주문만 선별 취소합니다.
- 필터: `type` not in (`TAKE_PROFIT`, `TAKE_PROFIT_MARKET`, `STOP`, `STOP_MARKET`)
- 전량 취소는 폴백으로만 사용합니다.

### 가격 규칙: tickSize 스냅 + price_precision 포맷
- 심볼 정보(`get_symbol_info_direct`)에서 `tick_size`, `price_precision`을 읽어 가격을 스냅 후 포맷합니다.
- 스냅 규칙:
  - LONG: TP 상향 스냅, SL 하향 스냅
  - SHORT: TP 하향 스냅, SL 상향 스냅

### 포지션 조회 리트라이
- 체결 직후 레이스(0 응답) 완화를 위해 100~300ms 백오프, 최대 3회 재시도합니다.
- 구현: `trading/trader.py::_get_position_info_with_retry`

### workingType 설정화
- 설정 키: `tp_sl_working_type` (기본 `MARK_PRICE`, 선택 `CONTRACT_PRICE`)
- 모든 TP/SL 생성 경로에서 설정값을 사용합니다.

### 로그/WS
- `_ensure_ws_subscriptions(symbol)`로 핵심 지점에서 WS 구독 보장 호출을 수행합니다.

# NoahAI 3.8 - 통합 문서

> 참고: 2025-10-30 기준, 기존 테마/레이아웃 관련 산출물은 폐기되었으며 새로운 단일 UI 가이드로 대체되었습니다.
> • 새로운 기준 문서: [UI 디자인 가이드](./UI_DESIGN_GUIDE.md)
> • 변경 기록: [UI 디자인 변경 기록](./UI_DESIGN_CHANGELOG.md)
> • 폐기 사유: CustomTkinter 내부 monkey patch 및 복수의 설계 문서가 혼선을 유발. 고정 스킨 + 단일 가이드 체계로 정리.

## 📋 개요

NoahAI 3.8은 AI 금융 의사결정 인프라로, 다중 거래소 지원과 통합 판단·기록·검증 구조를 제공합니다. 다만 **바이낸스 전용 경로와 CCXT 기반 다중거래소 경로는 구조가 분리되어 있으며, AI 판단 철학은 공유하지만 실행 세부 기능과 안정성은 거래소별로 검증 수준이 다를 수 있습니다.**

**현재 버전**: v3.8.8.9 (역사 참조)  
**마지막 업데이트**: 2026-05-29 (정합성 안내 갱신)  
**상태**: 역사 문서(참고용). 최신 운영 기준은 `RELEASE_NOTES.md`, `docs/TRADING_FLOW.md`, `docs/USER_GUIDE.md`, `USER_GUIDE_AI_EXECUTION.md`를 우선 참조

## 🚨 중요: 테마 시스템 안전성 강화 완료 (2025-10-21 업데이트)

### 테마 시스템 안전성 강화
- **폰트 폴백 시스템**: 테마 파일이 비어있거나 키가 누락되어도 안전하게 동작
- **기본 폰트 구성**: 누락 방지용 기본 폰트 구성으로 안정성 보장
- **강화된 예외 처리**: 폰트 객체 생성 실패 시에도 최소한의 폰트라도 반환
- **사용자 경험 개선**: 대시보드 로그와 글자들이 더 나은 가독성으로 개선

## 🚨 중요: 바이낸스 자체 API 전환 완료 (2025-10-20 업데이트)

### 바이낸스 아키텍처 최적화
- **바이낸스**: `trader.py` + `api/binance_client.py` (python-binance) - **완전 독립 시스템**
- **CCXT 거래소**: `unified_trader.py` + CCXT 어댑터 - 통합 시스템
- **제거된 중복**: `binance_extended_api.py`, `legacy_binance_adapter.py` 삭제
- **통합된 API**: 모든 바이낸스 고급 API가 `api/binance_client.py`에 통합

### 올바른 거래 실행 흐름
```
바이낸스: main.py.trading_loop() → trader.execute_trades() → api/binance_client.py
CCXT 거래소: unified_trader.start_trading() → CCXT 어댑터 → 각 거래소 API
```

자세한 내용은 [EXCHANGE_SEPARATION_GUIDELINES.md](./EXCHANGE_SEPARATION_GUIDELINES.md) 참조

## 🎯 핵심 특징

### **완전 자동화 시스템**
- **AI 기반 거래**: 시장 분석부터 거래 실행까지 모든 과정 자동 처리
- **실시간 최적화**: 거래 결과를 실시간으로 학습하여 파라미터 자동 조정
- **다중 거래소 지원**: 바이낸스, 바이비트, OKX, 비트겟, 업비트, 빗썸 지원
- **통합 거래 시스템**: 하나의 인터페이스로 모든 거래소 제어
- **AI 어시스턴트**: 실시간 거래 상황 분석 및 맞춤형 조언 제공

### **거래소별 특화 기능**
- **바이낸스**: python-binance (독립 시스템, 고급 주문 지원)
- **새 거래소들**: CCXT 통합 (바이비트, OKX, 비트겟)
- **한국 거래소**: CCXT 통합 (업비트, 빗썸)

#### ✅ 활성화 로직 정비(2025-09 반영)
- **사용자 경험 목표**: API 키는 사전에 등록해두고, 설정 UI의 `enabled_exchanges` 체크 상태만으로 실사용 거래소를 결정합니다.
- **적용 내용**
  - `trading/api_signal_manager.py` — `_collect_signals()` 루프와 헬퍼가 활성 목록을 우선 확인하며, 비활성 거래소는 완전히 건너뜁니다.
  - `trading/exchange_manager.py` — 클라이언트 생성·잔고·가격 조회·일괄 조회가 `enabled_exchanges` 기반 가드를 공통 적용합니다.
  - `trading/unified_trader.py` — 초기화/코인 선택/설정 갱신 시 활성 거래소만 관리하고, 비활성 거래소 관련 캐시와 통계를 정리합니다.
  - `trading/unified_trading_manager.py` — CCXT 초기화/재연결/잔고·포지션 조회 경로가 동일한 필터링 규칙을 사용합니다.
- **회귀 방지**: `test_multi_exchange_runtime.py`를 비롯한 통합 테스트에서 비활성 거래소 호출이 없는지 점검하고, UI 체크 토글 시 로그·대시보드 반응을 수동 확인했습니다.
- **문서/가이드 업데이트**: `docs/EXCHANGE_SETUP.md`와 사용자 가이드에 “키 보존 + 체크 해제” 정책을 명시하고, 향후 릴리스 노트에 반영합니다.

#### 🖥️ 대시보드 하이라이트 (2025-09)
- 전역 제어 버튼: `▶️ 모두 시작 / ⏹️ 모두 정지` 버튼이 상단 우측에 위치하며 활성 거래소 전체를 일괄 제어합니다.
- Quick Actions 바: `📚 사용자 매뉴얼`만 제공(디버그용 “탭 순서 확인” 버튼 제거).
- 거래 현황 패널: 활성 포지션, 총 거래 수, 누적 손익, 승률, 자동 거래 상태를 실시간 요약합니다(`_refresh_trading_summary`).
- 시장 트렌드 탭: `📈 시장 트렌드` 탭이 대표 코인 수익률, 섹터 흐름, 시장 심리, 포트폴리오 요약을 제공하며 차후 온체인/펀딩 지표를 연동할 예정입니다.
- 실시간 로그: 좌측 메인 로그는 전체 거래 흐름을, 거래소 탭의 로그 위젯은 거래소별 필터된 로그를 표시합니다.

#### 🖥️ 대시보드 하이라이트 (2025-09)
- 전역 제어 버튼: `▶️ 모두 시작 / ⏹️ 모두 정지` 버튼이 상단 우측에 위치하며 활성 거래소 전체를 일괄 제어합니다.
- Quick Actions 바: `📚 사용자 매뉴얼`만 제공(탭 순서 확인 제거).
- 거래 현황 패널: 활성 포지션 수, 총 거래 수, 누적 손익, 자동 거래 상태를 실시간 요약합니다(`_refresh_trading_summary`).
- 실시간 로그: 좌측 메인 로그는 전체 거래 흐름을, 거래소 탭의 로그 위젯은 거래소별 필터된 로그를 표시합니다.

## 🏗️ 시스템 아키텍처

### **전체 구조**
```
noahai_client/
├── main.py                           # 메인 애플리케이션
├── path_utils.py                     # 경로 관리 유틸리티 (핵심)
├── ui/                               # 사용자 인터페이스
│   ├── dashboard_modern.py           # 모던 대시보드 (CustomTkinter)
│   ├── login_modern.py               # 모던 로그인 (CustomTkinter)
│   ├── settings_modern.py            # 모던 설정 (CustomTkinter)
│   └── widgets/
│       ├── ai_assistant_widget_modern.py  # AI 어시스턴트 (CustomTkinter)
│       ├── ai_report_widget_real.py       # AI 리포트 (CustomTkinter)
│       └── ai_learning_widget_fixed.py    # AI 학습 (CustomTkinter)
├── trading/                          # 거래 로직
│   ├── trader.py                     # 메인 거래 엔진 (바이낸스 전용)
│   ├── unified_trader.py             # 통합 거래 시스템 (다중 거래소)
│   ├── exchange_manager.py           # 거래소 관리자
│   ├── unified_trading_manager.py    # 통합 거래 매니저
│   ├── life_finance_products.py      # 생활금융 상품 비교 엔진 (대출/보험/예적금)
│   ├── life_finance_assistant.py     # 생활금융 AI 어시스턴트 (자연어 인텐트 라우팅)
│   ├── tax_calculation_service.py    # 세무 계산 서비스 (연말정산·금투세·ISA/IRP) ✅ NEW
│   ├── fraud_detection_service.py    # 금융 이상 탐지 서비스 (보이스피싱·이상거래) ✅ NEW
│   ├── exchanges/                    # 거래소 모듈
│   │   ├── interfaces/               # 거래소 인터페이스
│   │   │   ├── exchange_interface.py
│   │   │   ├── futures_exchange.py
│   │   │   └── spot_exchange.py
│   │   ├── adapters/                 # 거래소 어댑터
│   │   │   ├── binance_futures_adapter.py
│   │   │   ├── bybit_futures_adapter.py
│   │   │   ├── okx_futures_adapter.py
│   │   │   ├── bitget_futures_adapter.py
│   │   │   ├── upbit_spot_adapter.py
│   │   │   └── bithumb_spot_adapter.py
│   │   └── exchange_factory.py       # 거래소 팩토리
│   └── ai/                           # AI 모듈
├── api/                              # API 연동
│   └── binance_client.py             # 바이낸스 클라이언트 (python-binance)
├── config/                           # 설정 파일
│   ├── settings.json                 # 메인 설정
│   ├── settings_template.json        # 설정 템플릿
│   └── theme_config.json             # 테마 설정
├── theme_system/                     # 테마 시스템 (v3.8.8.9 강화)
│   ├── theme_manager.py              # 테마 관리자 (폰트 폴백 시스템)
│   ├── windows_font_system.py        # Windows 폰트 시스템
│   ├── color_palettes.py             # 색상 팔레트
│   └── ui_components.py              # UI 컴포넌트
└── data/                             # 데이터 저장소 (사용자별)
    ├── trading.db                    # 거래 데이터베이스
    └── logs/                         # 로그 파일
```

### **핵심 컴포넌트**

#### **1. 경로 관리 시스템 (path_utils.py)**
```python
# 개발 환경 vs 빌드 환경 자동 감지
def get_app_base_dir():
    if getattr(sys, 'frozen', False):
        # PyInstaller 배포 환경
        return sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
    else:
        # 개발 환경
        return os.path.dirname(os.path.abspath(__file__))

# 사용자별 데이터 분리
def get_app_data_dir():
    if _current_user_account:
        return os.path.join(base_dir, _current_user_account)
    else:
        return base_dir
```

#### **2. 테마 시스템 (v3.8.8.9 강화)**
```python
# 안전한 폰트 폴백 시스템
class ThemeManager:
    DEFAULT_FONT_CONFIG = {
        "fonts": {"primary": "맑은 고딕", "monospace": "Consolas"},
        "sizes": {"h1": 20, "h2": 18, "h3": 16, "h4": 14, "body": 12, "caption": 11, "small": 10, "code": 12},
        "weights": {"normal": "normal", "medium": "normal", "semibold": "bold", "bold": "bold"}
    }
    
    def get_current_fonts(self):
        # 안전한 정규화 로직으로 누락된 키를 기본값으로 보완
        # 폰트 객체 생성 실패 시에도 최소한의 폰트라도 반환
```

#### **3. 거래소 시스템**
- **바이낸스**: python-binance (독립 유지)
- **새 거래소들**: CCXT (통합)
- **통합 인터페이스**: UnifiedTradingManager

## 🔌 거래소 지원 현황

### **지원 거래소**

| 거래소 | API 라이브러리 | 거래 유형 | 구현 상태 | 비고 |
|--------|----------------|-----------|-----------|------|
| 바이낸스 | python-binance | 선물 | ✅ 완료 | 기존 방식 유지 |
| 바이비트 | CCXT | 선물 | ✅ 완료 | 신규 추가 |
| OKX | CCXT | 선물 | ✅ 완료 | 신규 추가 |
| 비트겟 | CCXT | 선물 | ✅ 완료 | 신규 추가 |
| 업비트 | CCXT | 현물 | ✅ 완료 | 기존 구현 |
| 빗썸 | CCXT | 현물 | ✅ 완료 | 기존 구현 |

### **거래소별 특성**

#### **바이낸스 (독립 시스템)**
- **API**: python-binance
- **특징**: 고급 주문 지원 (OCO, Trailing Stop)
- **WebSocket**: 전용 WebSocket
- **장점**: 안정성, 고급 기능
- **거래 시스템**: 기존 Trader 클래스 + LegacyBinanceAdapter
- **⚠️ 중요**: 바이낸스는 `Trader` 클래스 사용, 대시보드에서 `main_app.trader.active_positions` 참조 필요

#### **새 거래소들 (CCXT 통합)**
- **API**: CCXT
- **특징**: 통합된 인터페이스
- **WebSocket**: CCXT WebSocket
- **장점**: 일관성, 확장성
- **거래 시스템**: UnifiedTrader 클래스 (기존 Trader와 동일한 기능)
- **⚠️ 중요**: CCXT 거래소들은 `UnifiedTrader` 사용, 대시보드에서 `unified_trader.active_positions` 참조

### **통합 거래 시스템 (UnifiedTrader)**

#### **핵심 기능**
- **코인 선택**: 바이낸스와 동일한 방식으로 미리 선택된 코인 사용 ✅
- **AI 분석**: 기존 Analyzer와 완전 연동하여 거래 신호 생성 ✅
- **거래 실행**: AI 기반 고급 거래 실행 (바이낸스와 동일) ✅
- **포지션 관리**: 실시간 포지션 모니터링 및 TP/SL 자동 처리 ✅
- **리스크 관리**: 완전한 리스크 관리 시스템 ✅
- **통계 관리**: 거래소별 거래 통계 추적 및 성과 분석 ✅
- **AI 학습**: 거래소별 AI 학습 데이터 생성 및 저장 ✅
- **구조 통일**: 바이낸스와 완전히 동일한 거래 패턴 ✅

#### **거래 사이클**
1. **코인 선택**: main.py에서 `evaluator.select_trading_coins()` 호출 → UnifiedTrader에 전달
2. **AI 분석**: `analyzer.generate_trading_signal()` 호출 (거래소별)
3. **거래 실행**: 리스크 관리 → 신뢰도 체크 → 포지션 수 체크 → 거래 실행
4. **포지션 모니터링**: 실시간 가격 조회 → PnL 계산 → TP/SL 체크 → 포지션 청산
5. **AI 학습**: 분석 결과를 거래소별 학습 데이터로 저장

#### **기존 바이낸스 거래와의 비교**
- **코어 로직**: 판단 파이프라인은 높은 정합(evaluator, analyzer, risk_manager 연동) ✅
- **거래 과정**: 핵심 흐름은 유사하나 거래소 API/체결 정책 차이 존재 ✅
  - **바이낸스**: main.py에서 코인 선택 → trader.execute_trading_cycle()에서 선택된 코인 사용
  - **CCXT**: main.py에서 코인 선택 → execute_trading_cycle_unified()에서 선택된 코인 사용
- **AI 구동**: 구조는 유사(신호/패턴/청산 분석)하나 저장/복구 완결성은 거래소별 차이 존재 ✅
  - **바이낸스**: 15-35회 (거래 신호 + 패턴 분석 + 익절/손절 분석)
  - **CCXT**: 15-35회 (거래 신호 + 패턴 분석 + 익절/손절 분석)
- **학습 데이터**: 거래소별로 분리되어 저장 ✅
- **차이점**: 실행/복구/보호주문 품질은 거래소별 실거래 검증 상태에 따라 다름 ✅

### **🚨 대시보드 포지션 표시 시스템**

#### **중요한 아키텍처 차이점**
- **바이낸스**: `Trader` 클래스 사용 → 포지션은 `main_app.trader.active_positions`에 저장
- **CCXT 거래소**: `UnifiedTrader` 클래스 사용 → 포지션은 `unified_trader.active_positions`에 저장

#### **대시보드 포지션 표시 로직**
```python
# ui/dashboard_modern.py - 포지션 표시 로직
if exchange == 'binance':
    # 바이낸스: Trader 클래스에서 포지션 조회
    positions = getattr(self.main_app.trader, 'active_positions', {})
else:
    # CCXT 거래소: UnifiedTrader에서 포지션 조회
    positions = getattr(self.unified_trader, 'active_positions', {}).get(exchange, {})
```

#### **거래 현황 통계 통합**
- **활성 포지션 수**: 바이낸스 + CCXT 거래소 포지션 수 합산
- **총 거래 수**: CCXT 거래소 통계 (더 정확한 데이터)
- **누적 손익**: 모든 거래소 손익 합산
- **승률**: CCXT 거래소 기준 (더 많은 거래 데이터)

#### **⚠️ 개발 시 주의사항**
1. **새 거래소 추가 시**: CCXT 기반이면 `UnifiedTrader` 사용, 바이낸스 전용이면 `Trader` 사용
2. **포지션 표시 수정 시**: 거래소 타입에 따라 올바른 객체 참조 필요
3. **통계 수집 시**: 바이낸스와 CCXT 거래소 데이터를 분리하여 처리

#### **✅ 해결된 문제들**
1. **코인 선택 방식 통일**: 바이낸스와 동일하게 미리 선택된 코인 사용
2. **selected_coins 전달 완료**: main.py의 selected_coins가 UnifiedTrader에 자동 전달
3. **성능 최적화**: 매번 코인 선택하지 않고 미리 선택된 코인 재사용
4. **일관성 목표**: 바이낸스와 핵심 판단 흐름은 최대한 맞추되, 거래소별 API 차이로 세부 실행/복구는 별도 검증 필요

#### **🔍 실제 코드 비교 분석**

##### **1. 거래 사이클 비교**
| 기능 | 바이낸스 (trader.py) | UnifiedTrader | 현재 상태 |
|------|---------------------|---------------|-----------|
| **코인 선택** | `self.selected_coins` 사용 | `self.selected_coins[exchange]` 사용 | 높은 정합 |
| **AI 분석** | `analyzer.generate_trading_signal()` | `analyzer.generate_trading_signal()` | 높은 정합 |
| **거래 실행** | `execute_trades()` | `_execute_signal_trade()` | 구조 유사, 거래소별 API 차이 존재 |
| **포지션 모니터링** | `monitor_positions()` | `_monitor_exchange_positions()` | 구조 유사, 복구/보호주문 차이 존재 |
| **AI 학습** | `ExchangeLearningManager` 저장 | `ExchangeLearningManager` 저장 | 정합하나 거래소별 정책은 부분 미완 |
| **XAI 저장** | 로그 중심, 청산 분석 저장 일원화 미완 | 청산 분석 DB 저장 연결됨 | 부분 정합 |

##### **2. 핵심 메서드 비교**
| 메서드 | 바이낸스 | UnifiedTrader | 차이점 |
|--------|----------|---------------|--------|
| **거래 사이클** | `execute_trading_cycle()` | `execute_trading_cycle_unified(exchange)` | 거래소 파라미터 추가 |
| **거래 실행** | `execute_trades(candidates, params)` | `_execute_signal_trade(exchange, symbol, analysis)` | 거래소 파라미터 추가 |
| **포지션 모니터링** | `monitor_positions()` | `_monitor_exchange_positions(exchange)` | 거래소 파라미터 추가 |
| **PnL 계산** | `calculate_pnl(position)` | `_calculate_pnl_unified(position, price)` | 동일한 로직 |
| **청산 판단** | `should_close_position(position)` | `_should_close_position_unified(exchange, position, price, pnl)` | 동일한 로직 |

##### **3. AI 구동 횟수 비교**
| 단계 | 바이낸스 | UnifiedTrader | 현재 상태 |
|------|----------|---------------|-----------|
| **거래 신호 생성** | 수행 | 수행 | 유사 |
| **패턴 유사성 분석** | 수행 | 수행 | 유사 |
| **익절 분석** | 경로 차이 존재 | 수행 및 DB 저장 연결 | 부분 정합 |
| **손절 분석** | 경로 차이 존재 | 수행 및 DB 저장 연결 | 부분 정합 |
| **총 AI 구동** | 높음 | 높음 | 절대 횟수보다 저장/복구 완결성 검증 필요 |

##### **4. 데이터 구조 비교**
| 데이터 | 바이낸스 | UnifiedTrader | 차이점 |
|--------|----------|---------------|--------|
| **활성 포지션** | `self.active_positions: Dict[str, Position]` | `self.active_positions: Dict[str, Dict[str, Position]]` | 거래소별 분리 |
| **거래 통계** | `self.trade_stats: Dict` | `self.trade_stats: Dict[str, Dict]` | 거래소별 분리 |
| **학습 데이터** | `ai_learning_data.json` | `ai_learning_data_{exchange}.json` | 거래소별 분리 |
| **설정** | `self.settings` | `self.settings` | 동일 |

##### **5. 성능 및 안정성 비교**
| 항목 | 바이낸스 | UnifiedTrader | 평가 |
|------|----------|---------------|------|
| **메모리 사용량** | 기준 | +20% (거래소별 데이터) | 양호 |
| **CPU 사용량** | 기준 | +10% (거래소별 처리) | 양호 |
| **응답 속도** | 기준 | 대체로 유사 | 양호 |
| **안정성** | 가장 성숙 | 거래소별 추가 실거래 검증 필요 | 주의 |
| **확장성** | 제한적 | 우수 | 우수 |

#### **2026-04-22 기준 정정 메모**
- `UnifiedTrader`는 바이낸스와 동일 철학의 AI 판단 흐름을 공유하지만, 거래소별 API/포지션 모드/보험 TP/SL/복구 로직 차이로 인해 완전히 동일한 기능 품질을 보장하는 상태는 아님
- Bybit/OKX/Bitget은 어댑터 구현과 보험 TP/SL 경로가 존재하지만, 거래소별 실거래 검증과 복구/XAI 저장 완결성 점검이 계속 필요함
- Upbit/Bithumb은 현물 구조이므로 Binance futures와 1:1 동일 동작을 기대하면 안 되며, 동일해야 하는 것은 판단 원칙·학습·설명 정책임

#### **개발 우선순위 (순차적 구현)**
1. **AI 기반 거래 실행 구현** (1단계) ✅ **완료**
   - `_execute_signal_trade_unified()` 메서드 추가 ✅
   - AI 기반 진입 전 분석 통합 ✅
   - 동적 신뢰도 임계값 계산 통합 ✅
   - AI 강화 파라미터 적용 통합 ✅
   - 포지션 크기 계산 통합 ✅
   - TP/SL 포함 포지션 기록 ✅

2. **포지션 모니터링 구현** (2단계) ✅ **완료**
   - `_monitor_exchange_positions()` 메서드 완성 ✅
   - TP/SL 체크 로직 구현 ✅
   - 포지션 청산 로직 구현 ✅
   - PnL 계산 로직 구현 ✅
   - 동적 임계값 계산 구현 ✅
   - AI 기반 익절/손절 분석 구현 ✅
   - 거래소별 거래 통계 추적 구현 ✅

3. **AI 분석 구현** (3단계) ✅ **완료**
   - 익절/손절 분석 통합 ✅
   - 패턴 유사성 분석 통합 ✅
   - AI 기반 포지션 크기 계산 ✅
   - 거래소별 포지션 크기 팩터 ✅
   - 리스크 기반 포지션 크기 조정 ✅
   - 거래소별 최대 포지션 크기 제한 ✅

4. **통계 관리 구현** (4단계) ✅ **완료**
   - 거래소별 거래 통계 추적 ✅
   - 성과 분석 및 리포팅 ✅
   - 거래소별 통계 조회 ✅
   - 전체 통계 조회 ✅
   - 성과 리포트 생성 ✅
   - AI 기반 권장사항 생성 ✅

5. **구조적 차이 수정** (5단계) ✅ **완료**
   - 바이낸스와 동일한 코인 선택 방식 적용 ✅
   - main.py의 selected_coins를 UnifiedTrader에 전달 ✅
   - execute_trading_cycle_unified에서 미리 선택된 코인 사용 ✅
   - 성능 및 일관성 문제 해결 ✅
   - set_selected_coins() 메서드 추가 ✅
   - update_selected_coins() 메서드 추가 ✅
   - 코인 선택 후 자동 업데이트 구현 ✅

## 🧭 계단식 탭 구조 - 다중 서비스/거래소 동시 거래 시스템

### 📌 개요
- **목표**: 계단식 탭 구조로 서비스별(블록체인/주식/부동산) → 하위 탭(거래소별/증권사별/지역별) 독립 제어 및 실시간 상태 표시
- **핵심 원칙**: 백엔드(`UnifiedTrader`, `UnifiedTradingManager`)는 이미 다중 거래소 동시 거래를 지원 → UI에서 계단식 탭 구조로 확장하여 활용
- **확장성**: 현재 블록체인 서비스부터 시작하여 주식, 부동산 등 추가 서비스로 확장 가능

### 🏗️ 계단식 탭 구조 설계

#### **1단계: 서비스 탭 (상단)**
```
🔗 블록체인 | 📈 주식/증권 | 🏠 부동산 | 💼 기타투자 | 🤖 AI애널리스트
```

#### **2단계: 하위 탭 (서비스별)**
- **블록체인 서비스**: 거래소별 탭
  ```
  Bybit | OKX | Bitget | Binance | Upbit | Bithumb
  ```
- **주식/증권 서비스**: 증권사별 탭 (미래 확장)
  ```
  키움증권 | 대신증권 | NH투자증권 | 한국투자증권
  ```
- **부동산 서비스**: 지역별 탭 (미래 확장)
  ```
  서울 | 경기 | 부산 | 대구 | 인천
  ```

#### **3단계: 각 하위 탭 내용**
```
[시작/정지 버튼] [잔고 표시] [포지션 테이블] [거래 통계] [실시간 로그]
```

### ✅ 구현 가능성 요약
- `trading/unified_trader.py`는 거래소별로 포지션, 통계, 모니터링 스레드, 선택 코인, 거래 사이클 상태를 분리 관리함
- `trading/unified_trading_manager.py`는 각 거래소 연결/잔고/포지션 조회를 통합 제공함
- `ui/dashboard_modern.py`는 이미 서비스 탭 구조(`create_service_tabs`)와 거래소별 탭 관리(`exchange_tabs`) 기반이 준비됨

### 🖥️ UI 대시보드 변경 사항(실제 구현 지침)

#### **1. 서비스 탭 구조 확장**
```python
# 현재 구조 (291-355번째 줄) 확장
def create_service_tabs(self, parent):
    # 기존 서비스 탭 유지
    self.blockchain_btn    # 🔗 블록체인
    self.stock_btn         # 📈 주식/증권  
    self.real_estate_btn   # 🏠 부동산
    self.other_investment_btn  # 💼 기타투자
    self.ai_analyst_btn    # 🤖 AI애널리스트
    
    # 서비스별 하위 탭 관리
    self.service_sub_tabs = {
        'blockchain': {},  # 거래소별 탭
        'stock': {},       # 증권사별 탭
        'real_estate': {}  # 지역별 탭
    }
```

#### **2. 하위 탭 동적 생성**
```python
def create_service_sub_tabs(self, service):
    """서비스별 하위 탭 생성"""
    if service == "blockchain":
        # 설정에서 활성화된 거래소만 탭 생성
        for exchange in self.enabled_exchanges:
            self.create_exchange_tab(exchange)
    elif service == "stock":
        # 설정에서 활성화된 증권사만 탭 생성
        for broker in self.enabled_brokers:
            self.create_broker_tab(broker)
```

#### **3. 거래소별 탭 내용 구성**
```python
def create_exchange_tab(self, exchange):
    """거래소별 탭 생성"""
    tab = self.tab_widget.add(f"🏦 {exchange.upper()}")
    
    # 탭 내용 구성
    self.create_exchange_control_section(tab, exchange)  # 시작/정지 버튼
    self.create_exchange_balance_section(tab, exchange)  # 잔고 표시
    self.create_exchange_positions_section(tab, exchange)  # 포지션 테이블
    self.create_exchange_stats_section(tab, exchange)    # 거래 통계
    self.create_exchange_logs_section(tab, exchange)     # 실시간 로그
```

#### **4. 서비스 전환 시 하위 탭 동적 교체**
```python
def switch_service(self, service):
    """서비스 전환 시 하위 탭 교체"""
    self.current_service = service
    
    # 기존 하위 탭 제거
    self.clear_service_sub_tabs()
    
    # 새 하위 탭 생성
    self.create_service_sub_tabs(service)
    
    # 서비스별 데이터 로드
    self.load_service_data(service)
```

### 🧩 화면 비율별 최적화

#### **16:9 모니터 (1920x1080)**
```
권장 창 크기: 1600x1000
├── 상단 서비스 탭: 100px (🔗 블록체인 | 📈 주식 | 🏠 부동산 | ...)
├── 하위 탭: 50px (Bybit | OKX | Bitget | ...)
├── 메인 콘텐츠: 750px (시작/정지, 잔고, 포지션, 통계, 로그)
└── 하단 상태바: 100px
```

#### **6:4 모니터 (1440x960)**
```
권장 창 크기: 1400x900 (현재 설정)
├── 상단 서비스 탭: 80px
├── 하위 탭: 40px
├── 메인 콘텐츠: 700px
└── 하단 상태바: 80px
```

### 🏗️ 개발 체크리스트(순서별 구현)

#### **1단계: 설정 UI 개선**
- [x] `settings_modern.py`의 거래소 선택을 라디오 → 체크박스로 변경
- [x] `settings.json`에 `enabled_exchanges: ["bybit", "okx", "bitget"]` 추가 (스키마 반영)
- [x] `settings_template.json`과 `settings.py`에 동시 반영

#### **2단계: 서비스 탭 구조 확장**
- [x] `dashboard_modern.py`의 `create_service_tabs()` 함수에 하위 탭 관리 추가
- [x] `switch_service()` 함수에 하위 탭 동적 교체 로직 추가
- [x] 서비스별 하위 탭 레퍼런스 구조 `self.service_sub_tabs` 추가

#### **3단계: 거래소별 탭 구현 (블록체인 서비스)**
- [x] `create_service_sub_tabs()`에서 거래소별 탭 생성 및 내부 섹션 구성(컨트롤/잔고/포지션/통계/로그)
- [x] 거래소별 시작/정지 버튼 (`_start_trading_monitoring`, `_stop_exchange_trading`) 연결
- [x] 거래소별 잔고/포지션/통계/로그 섹션 기본 표시 (초기 1회 갱신)

#### **4단계: 실시간 업데이트 시스템**
- [x] `_update_exchange_display()` 호출 흐름 유지 + 거래소별 섹션(잔고/포지션/통계) 주기 갱신 연결
- [x] 거래소별 모니터링 스레드 루프에서 섹션 갱신 수행
- [x] 오류 발생 시 콘솔 경고로 우선 처리(배지는 후속 단계에서 추가 예정)

#### **5단계: 미래 확장 준비 (주식/부동산)**
- [x] 증권사별 탭 구조 설계
- [x] 지역별 탭 구조 설계
- [x] 서비스별 독립 데이터 관리 시스템

### 🧪 실제 동작 시나리오

#### **블록체인 서비스 (현재 구현)**
1. 사용자 설정에서 Bybit/OKX/Bitget 활성화 → 저장
2. 대시보드 진입 시 "🔗 블록체인" 서비스 선택
3. 하위 탭에 Bybit/OKX/Bitget 탭 동적 생성
4. Bybit 탭에서 [▶️ 시작] 클릭 → Bybit만 거래 시작
5. OKX 탭에서도 [▶️ 시작] → OKX 동시 거래 시작
6. 각 탭 독립적으로 잔고/포지션/통계/로그 표시

#### **주식 서비스 (미래 확장)**
1. "📈 주식/증권" 서비스 선택
2. 하위 탭에 키움/대신/NH투자 탭 동적 생성
3. 각 증권사별 독립 제어 및 데이터 표시

**구현 구조:**
```python
def create_stock_sub_tabs(self):
    """주식 서비스 하위 탭 생성"""
    enabled_brokers = self.settings.get('enabled_brokers', ['kiwoom'])
    for broker in enabled_brokers:
        tab = ctk.CTkFrame(self.content_area)
        self.service_sub_tabs['stock'][broker] = tab
        self.create_broker_tab(tab, broker)

def create_broker_tab(self, parent, broker: str):
    """증권사별 탭 구성"""
    # 컨트롤 섹션: 시작/정지, 계좌 선택
    # 잔고 섹션: 현금/주식 잔고
    # 포지션 섹션: 보유종목 리스트
    # 통계 섹션: 수익률, 거래횟수
    # 로그 섹션: 주식 거래 로그
```

#### **부동산 서비스 (미래 확장)**
1. "🏠 부동산" 서비스 선택
2. 하위 탭에 서울/경기/부산 탭 동적 생성
3. 각 지역별 독립 제어 및 데이터 표시

**구현 구조:**
```python
def create_real_estate_sub_tabs(self):
    """부동산 서비스 하위 탭 생성"""
    enabled_regions = self.settings.get('enabled_regions', ['seoul'])
    for region in enabled_regions:
        tab = ctk.CTkFrame(self.content_area)
        self.service_sub_tabs['real_estate'][region] = tab
        self.create_region_tab(tab, region)

def create_region_tab(self, parent, region: str):
    """지역별 탭 구성"""
    # 컨트롤 섹션: 매물 검색, 거래 시작/정지
    # 매물 섹션: 지역별 매물 리스트
    # 포지션 섹션: 보유 부동산
    # 통계 섹션: 수익률, 거래횟수
    # 로그 섹션: 부동산 거래 로그
```

### ⚠️ 성능/안정성 주의사항
- 거래소 6개 동시 실행 시 CPU/네트워크 사용량 증가(거래소당 CPU +2.5%, 메모리 +5MB)
- 서비스 전환 시 기존 하위 탭 완전 정리 후 새 탭 생성 (메모리 누수 방지)
- 잦은 UI 업데이트는 이벤트(거래/포지션 변화) 기반 + 주기 업데이트 혼합으로 부담 최소화
- 6개 거래소 동시 연결 시 네트워크 대역폭 고려 필요

### 🚨 성능 문제 해결 방안
- **API 키 검증**: 설정되지 않은 거래소는 연결 시도하지 않음
- **심볼 검증**: Invalid symbol 오류 방지를 위한 사전 검증
- **재시도 제한**: API 연결 실패 시 무한 재시도 방지
- **초기화 최적화**: 필요한 거래소만 초기화하여 대시보드 로딩 시간 단축

### 🔧 설정 UI 문제 해결 방안
- **거래소 선택 로드**: `load_current_settings`에서 `enabled_exchanges` 제대로 로드
- **실시간 반영**: 설정 변경 시 대시보드 즉시 업데이트
- **서비스 탭 동기화**: 거래소 선택 변경 시 하위 탭 자동 재생성
- **콜백 연결**: 설정 창과 대시보드 간 양방향 통신 구현

### 🛡️ API 호출 안정성 강화 방안
- **심볼 검증 시스템**: `SymbolValidator` 클래스로 거래소별 심볼 포맷 검증
- **안전 심볼 매핑**: 거래소별 기본 안전 심볼 사용 (BTCUSDT, KRW-BTC 등)
- **어댑터 표준화**: 모든 어댑터에 `get_account_info()` 래퍼 추가
- **호출 통일**: `get_trade_history(symbol=안전심볼, limit=…)` 강제 적용
- **재시도 제한**: API 실패 시 백오프 적용, 무한 재시도 방지

### 📚 관련 파일
- `trading/unified_trader.py` — 거래소별 상태/스레드/포지션/통계 관리
- `trading/unified_trading_manager.py` — 연결/잔고/포지션 통합 인터페이스
- `ui/dashboard_modern.py` — 서비스 탭, 하위 탭, 표시 업데이트 훅 위치
- `trading/symbol_validator.py` — 심볼 검증 및 안전 심볼 매핑 시스템
- `trading/exchanges/adapters/` — 거래소별 어댑터 (get_account_info 표준화)
- `ui/settings_modern.py` — 거래소 다중 선택 설정
- `config/settings_template.json` — `enabled_exchanges` 기본값 정의
- `config/settings.py` — 템플릿 병합/저장/로드 로직 (`enabled_exchanges` 보존)
- `path_utils.py` — 사용자별 경로 관리 (계정별 폴더 구조)

### 🔧 경로 시스템 일괄성
- **사용자별 폴더 구조**: `data/{사용자ID}/config/settings.json`
- **다중 계정 지원**: 각 사용자별 독립적인 설정 파일 관리
- **개발/배포 환경**: `path_utils.py`에서 환경별 경로 자동 처리
- **설정 보존**: `enabled_exchanges` 사용자 선택사항 템플릿 덮어쓰기 방지

## 📌 구현 진행상황
- 1단계(설정 UI 다중 선택, 스키마 반영): 완료
  - 체크박스 UI 도입, `enabled_exchanges` 저장/복원, 템플릿/로더 규칙 반영
- 2단계(서비스 탭 하위 탭 관리): 완료
  - `dashboard_modern.py`에 서비스별 하위 탭 동적 생성 구조 추가 완료
- 3단계(거래소별 탭 구현): 완료
  - 블록체인 서비스 하위 탭에서 거래소별 독립 제어 및 섹션 구성 완료
- 4단계(실시간 업데이트 시스템): 완료
  - 거래소별 모니터링 루프와 섹션 갱신 연결 완료
- 5단계(미래 확장 준비): 완료
  - 주식/부동산 서비스 구조 설계 및 문서화 완료
- 6단계(경로 시스템 일괄성): 완료
  - 사용자별 폴더 구조 확인, 모든 거래소 설정 테스트 완료
  - Binance, Bybit, OKX, Bitget, Bithumb, Upbit 6개 거래소 동시 활성화 테스트 성공

## 🤖 AI 어시스턴트 기능

### **핵심 기능**
- **실시간 거래 상황 분석**: 현재 잔고, 포지션, 시장 데이터를 실시간으로 수집하여 분석
- **맞춤형 조언 제공**: 사용자의 거래 상황에 맞는 구체적인 조언과 권장사항 제시
- **환경설정 자동 조절**: AI가 분석한 결과를 바탕으로 거래 설정을 자동으로 조정
- **시장 데이터 통합**: 주요 코인들의 가격, 변동률, 거래량을 실시간으로 분석
- **코인 분석 실행**: 선택된 거래 코인들에 대한 실시간 기술적 분석 수행

### **수집하는 정보**
1. **거래소 정보**: 현재 선택된 거래소, 연결 상태
2. **잔고 정보**: 실시간 잔고, 총 USDT 가치
3. **거래 설정**: 레버리지, TP/SL, RSI, 변동성 임계값, AI 청산 설정
4. **거래 통계**: 총 거래 횟수, 승률, 수익률, 거래당 평균 수익
5. **활성 포지션**: 현재 포지션 현황, PnL, 총 포지션 가치
6. **시장 데이터**: BTC, ETH, ADA, SOL, DOT 등 주요 코인의 실시간 가격 및 변동률
7. **선택된 거래 코인**: 현재 거래 대상 코인 목록 및 실시간 분석 결과
8. **AI 학습 데이터**: 거래소별 학습된 패턴 수 및 최근 학습 현황
9. **시스템 상태**: CPU, 메모리 사용률 등 시스템 리소스 현황

### **AI 분석 과정**
1. **데이터 수집**: 위의 모든 정보를 실시간으로 수집
2. **시장 상황 분석**: 전체적인 암호화폐 시장 동향 파악
3. **거래 상황 평가**: 현재 설정과 포지션의 적절성 검토
4. **구체적 조언 제공**: 사용자 요청에 대한 맞춤형 답변
5. **권장 설정 제안**: 필요시 구체적인 설정 변경 수치 제안

### **사용 방법**
1. **AI 어시스턴트 탭**: 대시보드에서 "AI 어시스턴트" 탭 클릭
2. **자연어 대화**: "AI야, 지금 시장 상황 어때?" 같은 자연어로 질문
3. **빠른 질문 버튼**: 미리 정의된 질문 버튼으로 빠른 분석 요청
4. **설정 적용**: AI가 제안한 설정을 "✅ 적용" 버튼으로 즉시 적용
5. **설정 거부**: 제안을 원하지 않으면 "❌ 거부" 버튼으로 거부

### **지원하는 질문 유형**
- **시장 분석**: "지금 시장 상황 어때?", "BTC 전망은?"
- **거래 조정**: "더 공격적으로 거래하고 싶어", "안전하게 해줘"
- **설정 변경**: "레버리지를 2배로 올려줘", "TP/SL을 조정해주세요"
- **성과 분석**: "최근 거래 성과는?", "어떻게 개선할 수 있어?"
- **문제 해결**: "왜 거래가 안 되고 있어?", "리스크 상황을 점검해줘"

## 🚀 사용 방법

### **1. 설치 및 설정**

#### **1.1 시스템 설치**
```bash
# 프로젝트 클론
git clone [repository-url]
cd noahai_client

# 의존성 설치
pip install -r requirements.txt

# 개발 실행
python main.py
```

#### **1.2 API 키 설정**
```json
{
  "selected_exchange": "binance",
  "binance_api_key": "your_binance_api_key",
  "binance_secret_key": "your_binance_secret_key",
  "bybit_api_key": "your_bybit_api_key",
  "bybit_secret_key": "your_bybit_secret_key",
  "okx_api_key": "your_okx_api_key",
  "okx_secret_key": "your_okx_secret_key",
  "okx_passphrase": "your_okx_passphrase",
  "bitget_api_key": "your_bitget_api_key",
  "bitget_secret_key": "your_bitget_secret_key",
  "upbit_api_key": "your_upbit_api_key",
  "upbit_secret_key": "your_upbit_secret_key",
  "bithumb_api_key": "your_bithumb_api_key",
  "bithumb_secret_key": "your_bithumb_secret_key"
}
```

### **2. 거래 시작**

#### **2.1 바이낸스 거래 (기존 시스템)**
- **자동거래**: 기존 Trader 클래스 사용
- **고급 주문**: OCO, Trailing Stop 지원
- **WebSocket**: 실시간 데이터 스트리밍

#### **2.2 다중 거래소 거래 (UnifiedTrader)**
- **거래소별 탭**: 대시보드에서 거래소별 탭 선택
- **거래 시작**: "▶️ 거래 시작" 버튼으로 자동거래 시작
- **실시간 모니터링**: 거래 상태 및 포지션 실시간 표시
- **통합 관리**: 하나의 인터페이스에서 모든 거래소 관리

#### **2.3 대시보드 사용**
1. **로그인**: 사용자 계정으로 로그인
2. **거래소 선택**: 원하는 거래소 탭 클릭
3. **거래 시작**: "▶️ 거래 시작" 버튼 클릭
4. **모니터링**: 실시간 거래 상태 확인

#### **2.4 프로그래밍 방식**
```python
# 통합 거래 시스템 사용
# UnifiedTrader를 통한 다중 거래소 거래
unified_trader = UnifiedTrader(
    settings=settings,
    exchange_manager=exchange_manager,
    unified_manager=unified_manager,
    analyzer=analyzer,
    optimizer=optimizer,
    recorder=recorder,
    ai_manager=ai_manager,
    risk_manager=risk_manager,
    logger=logger,
    dashboard=dashboard
)

# evaluator 설정 (코인 선택용)
unified_trader.set_evaluator(evaluator)

# 거래소별 거래 시작
unified_trader.start_trading('bybit')
unified_trader.start_trading('okx')

# 거래 사이클 실행 (기존 Trader와 동일한 로직)
unified_trader.execute_trading_cycle_unified('bybit')

# 활성 포지션 조회
positions = unified_trader.get_active_positions('bybit')

# 거래 통계 조회
stats = unified_trader.get_trade_stats('bybit')

# AI 학습 데이터 확인
learning_data = unified_trader.ai_manager.get_learning_data('bybit')

# 거래소별 상태 확인
status = unified_trader.get_trading_status()
```

### **3. 거래 시스템 작동 원리**

#### **3.1 거래 사이클**
```
1. 코인 선택 (select_trading_coins_unified)
   ↓
2. AI 분석 (analyze_coins_unified)
   ↓
3. 거래 실행 (execute_trading_cycle_unified)
   ↓
4. 포지션 모니터링 (실시간)
```

#### **3.2 코인 선택 시스템**
- **시장 상황 분석**: bull/bear/neutral 판단
- **거래소별 코인 수 결정**: 시장 상황에 따른 조정
- **AI 기반 선별**: 기존 evaluator 활용

#### **3.3 AI 분석 시스템**
- **기존 AI Manager 활용**: `ai_manager.analyze_market_conditions()`
- **거래소별 조정**: 신뢰도 및 신호 조정
- **현물 거래소 제한**: SHORT 거래 제한

#### **3.4 포지션 관리**
- **실시간 모니터링**: 10초마다 포지션 체크
- **TP/SL 관리**: 자동 수익/손실 한도 관리
- **거래 통계**: 실시간 거래 성과 추적

##### 포지션 크기 산정 로직(요약)
`final_size = base_size × confidence_factor × market_factor × exchange_factor × position_size_factor × risk_factor`
- base_size: 기본 수량(전략 기준)
- confidence_factor: 신호 신뢰도(0.3~1.0)
- market_factor: 시장 변동성 적합도(HIGH/LOW에 따라 가감)
- exchange_factor: 거래소별 보정 계수(binance=1.0, bybit=0.9 등)
- position_size_factor: AI 강화 파라미터에서 유도(신뢰도·패턴 기반)
- risk_factor: 연속 손실/일일 손익/시장 변동성 기반 리스크 보정

## ⚙️ 설정 옵션

### **거래 설정**
```json
{
  "default_leverage": 10,
  "default_margin_type": "ISOLATED",
  "default_tp": 0.0018,
  "default_sl": 0.002,
  "enabled_exchanges": ["binance"],
  "max_positions": 5,
"min_trade_amount": 5,
"auto_trade_interval": 10,
  "min_trade_confidence": 0.6,
  "exchange_position_factors": {
    "binance": 1.0,
    "bybit": 0.9,
    "okx": 0.8,
    "bitget": 0.85,
    "upbit": 0.7,
    "bithumb": 0.7
  }
}
```

### **거래소별 설정**
```json
{
  "market_regime_coins": {
    "bear": {"min": 10, "max": 10},
    "neutral": {"min": 15, "max": 15},
    "bull": {"min": 20, "max": 20}
  },
  "trading_strategies": {
    "scalping": {"leverage": 5, "tp": 0.001, "sl": 0.0015},
    "swing": {"leverage": 10, "tp": 0.003, "sl": 0.002}
  }
}
```

### **설정 변경 사항 (다중 거래소 지원)**
- `enabled_exchanges: string[]` 추가됨 — 다중 선택된 거래소 목록. 예: `["bybit", "okx", "bitget"]`
- `selected_exchange`는 하위 호환을 위해 유지되며, `enabled_exchanges`가 비어있을 때 폴백으로 사용됨
- 설정 저장/로드는 `config/settings.py`에서 템플릿 병합 규칙을 통해 일관성 보장
- `exchange_signal_thresholds` 추가 — 거래소별 신호 임계값 덮어쓰기. 예:
```json
{
  "signal_thresholds": {"rsi_oversold": 30, "rsi_overbought": 70},
  "exchange_signal_thresholds": {
    "bybit": {"rsi_oversold": 28, "rsi_overbought": 72},
    "okx": {"momentum_threshold": 0.0006}
  }
}
```
Analyzer는 `generate_trading_signal(..., exchange_name)` 호출 시 해당 거래소 임계값을 우선 적용합니다.

### **거래소별 추천 임계값 프리셋**
아래 값들은 시작점으로 권장되는 예시입니다. 시장 상황/개인 선호에 따라 조정하세요.
```json
{
  "exchange_signal_thresholds": {
    "binance": { "rsi_oversold": 30, "rsi_overbought": 70, "momentum_threshold": 0.0004 },
    "bybit":   { "rsi_oversold": 28, "rsi_overbought": 72, "trend_momentum_threshold": 0.0018 },
    "okx":     { "rsi_oversold": 30, "rsi_overbought": 70, "momentum_threshold": 0.0006 },
    "bitget":  { "rsi_oversold": 29, "rsi_overbought": 71 },
    "upbit":   { "rsi_oversold": 32, "rsi_overbought": 68, "momentum_threshold": 0.0008 },
    "bithumb": { "rsi_oversold": 32, "rsi_overbought": 68, "momentum_threshold": 0.0008 }
  }
}
```

### **시장 국면별 보정 가이드(권장)**
시장 변동성/추세 상태에 따라 임계값을 소폭 조정하는 것을 권장합니다.
- 저변동성(low): rsi_oversold -2, rsi_overbought +2, momentum_threshold -10% (신호 더 민감)
- 고변동성(high): rsi_oversold +2, rsi_overbought -2, momentum_threshold +10% (보수적)
설정 예시:
```json
{
  "signal_thresholds": {"rsi_oversold": 30, "rsi_overbought": 70, "momentum_threshold": 0.0004},
  "exchange_signal_thresholds": {
    "binance": {"rsi_oversold": 28, "rsi_overbought": 72},
    "okx": {"momentum_threshold": 0.0006}
  }
}
```

#### 자동 적용 옵션
- 설정으로 시장 국면(Low/High)을 자동 감지해 임계값을 보정할 수 있습니다.
- 키: `dynamic_thresholds_enabled` (기본 true)
- 프로파일: `dynamic_thresholds_profile.low/high`
  - `rsi_oversold_delta`, `rsi_overbought_delta` (정수, 포인트)
  - `momentum_threshold_scale` (배율)
동작: Analyzer는 변동성이 동적 기준보다 낮으면 Low, 기준의 설정 배율(`dynamic_thresholds_high_multiplier`)을 초과하면 High로 간주하여 보정치를 적용합니다.
추가로 히스테리시스 옵션을 통해 판정의 출렁임을 줄일 수 있습니다.
- `dynamic_thresholds_hysteresis_enabled`: true/false (기본 true)
- `dynamic_thresholds_hysteresis`: `{ high_enter_mult, high_exit_mult, low_enter_mult, low_exit_mult }`
  - 예: high_enter=1.5, high_exit=1.3 → High 유지 후 완화 기준 1.3 배에서 Normal/Low 복귀
UI: 설정 창 > AI 시스템 상태 탭에서 자동 보정 활성화 및 HIGH 배율을 입력할 수 있습니다. 또한 `auto/manual` 모드를 선택하고 수동일 경우 국면(LOW/NORMAL/HIGH)을 직접 지정할 수 있습니다.

### **프리셋 표 — 거래소/시장 국면별 권장값**
아래 표는 시작점을 제시하는 권장 프리셋입니다(실거래 성과에 따라 조정 권장).

| 거래소 | 국면 | rsi_oversold | rsi_overbought | momentum_threshold | 비고 |
|---|---|---:|---:|---:|---|
| Binance | Low | 28 | 72 | 0.00036 | 민감도↑ (기회 포착) |
| Binance | Normal | 30 | 70 | 0.00040 | 기본값 |
| Binance | High | 32 | 68 | 0.00044 | 보수적 진입 |
| Bybit | Low | 27 | 73 | 0.00038 | 변동성 대비 민감 |
| Bybit | Normal | 28 | 72 | 0.00042 | 기본 권장 |
| Bybit | High | 30 | 70 | 0.00046 | 보수적 |
| OKX | Low | 30 | 70 | 0.00054 | 기본보다 +10% |
| OKX | Normal | 30 | 70 | 0.00060 | 기본 권장 |
| OKX | High | 32 | 68 | 0.00066 | 보수적 |
| Bitget | Low | 29 | 71 | 0.00040 | 기본 유사 |
| Bitget | Normal | 29 | 71 | 0.00042 | 기본 권장 |
| Bitget | High | 31 | 69 | 0.00046 | 보수적 |
| Upbit (Spot) | Low | 32 | 68 | 0.00072 | 현물·저유동성 고려 |
| Upbit (Spot) | Normal | 32 | 68 | 0.00080 | 기본 권장 |
| Upbit (Spot) | High | 34 | 66 | 0.00088 | 보수적 |
| Bithumb (Spot) | Low | 32 | 68 | 0.00072 | 현물·저유동성 고려 |
| Bithumb (Spot) | Normal | 32 | 68 | 0.00080 | 기본 권장 |
| Bithumb (Spot) | High | 34 | 66 | 0.00088 | 보수적 |

적용 방법: `signal_thresholds`에 기본값을 두고, `exchange_signal_thresholds`에 거래소별/국면 반영 값을 덮어씌웁니다. 국면은 내부 시장 분석(변동성 레벨) 또는 운영 정책에 맞춰 수동 적용하세요.

### **포지션 크기 보정(거래소별)**
- `exchange_position_factors`로 거래소 특성에 맞게 포지션 크기를 보정할 수 있습니다. 기본값은 다음과 같습니다.
```json
{
  "exchange_position_factors": {
    "binance": 1.0,
    "bybit": 0.9,
    "okx": 0.8,
    "bitget": 0.85,
    "upbit": 0.7,
    "bithumb": 0.7
  }
}
```

### **포지션 크기 디버그 로깅**
`position_sizing_debug: true`로 설정하면 포지션 크기 산정 및 리스크 팩터 계산의 세부 내역을 로그로 확인할 수 있습니다.
- 주요 키워드: "🔎 PositionSizing Debug", "🔎 RiskFactor Debug"
- 로그 파일: Documents/NoahAI/logs/trading.log

### **사이징-성과 매핑 로그**
포지션 진입 시점의 사이징 세부값과 청산 시점의 PnL을 연결해 출력합니다.
- 키워드: "📈 SizingOutcome Mapping"
- 포함 내용: signal, position_size, leverage, entry_price, pnl_percent, sizing_detail(각 요소값)
 - 옵션으로 CSV 파일에 저장할 수 있습니다(`position_sizing_persist: true`).
   - 저장 위치: `…/Documents/NoahAI/analytics/sizing_outcomes.csv`
   - 컬럼: timestamp, exchange, symbol, signal, entry_price, exit_price, pnl_percent, position_size, leverage,
           confidence, tp_percent, sl_percent, base_size, confidence_factor, market_factor, exchange_factor,
           position_size_factor, risk_factor, pre_clamp, min_size, max_size, final_size

### **애널리틱스 요약 유틸리티**
`analytics/reporting.py`를 사용해 `sizing_outcomes.csv`의 요약 통계를 확인할 수 있습니다.
```bash
python -m noahai_client.analytics.reporting --path "~/Documents/NoahAI/analytics/sizing_outcomes.csv" --limit 500 --days 7
```
출력: 전체/거래소별 총 거래 수, 승률, 평균/중앙 PnL, 평균 포지션 크기
옵션: `--limit N`으로 최근 N건만, `--days D`로 최근 D일만 요약 가능

### **애널리틱스 자동 새로고침 간격**
- 대시보드의 애널리틱스 요약 자동 새로고침 주기는 `analytics_refresh_interval_minutes`로 설정합니다(기본 30분, 최소 5분 / 최대 180분).

### **선물 주문 레버리지/마진 타입 자동화**
- UnifiedTrader가 선물 거래소 주문 실행 전에 레버리지(`set_leverage`)와 마진 타입(`set_margin_type`)을 자동 설정합니다.
- 마진 타입 기본값은 `default_margin_type`(기본 `ISOLATED`)입니다.

## 🔧 개발 가이드

### **개발 환경**
- **언어**: Python 3.8+
- **GUI**: CustomTkinter (모던 UI), PyQt5 (레거시)
- **거래소 API**: python-binance (바이낸스), CCXT (다른 거래소)
- **AI**: OpenAI GPT-4 API
- **로깅**: Loguru
- **데이터 처리**: NumPy, Pandas

### **의존성 패키지**
```bash
# 핵심 패키지
python-binance==1.0.19    # 바이낸스 API
ccxt>=4.0.0              # 통합 거래소 API
openai>=1.35.0           # AI API
loguru==0.7.2            # 로깅
numpy==1.24.3            # 수치 계산
pandas==2.0.3            # 데이터 처리

# GUI 및 웹소켓
customtkinter            # 모던 UI
PyQt5==5.15.9           # 레거시 UI
websockets==11.0.3       # 실시간 데이터
requests==2.31.0         # HTTP 요청
```

### **개발 환경 설정**
1. **Python 3.8+ 설치**
2. **가상환경 생성 및 활성화**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # Linux/Mac
   ```
3. **의존성 패키지 설치**
   ```bash
   pip install -r requirements.txt
   ```
4. **API 키 설정** (settings.json)

### **코드 구조**
```
noahai_client/
├── main.py                    # 애플리케이션 진입점
├── path_utils.py              # 경로 관리 (개발/빌드 환경)
├── trading/                   # 거래 로직
│   ├── trader.py              # 바이낸스 전용 거래 엔진
│   ├── unified_trader.py      # 다중 거래소 통합 거래 엔진
│   ├── analyzer.py            # 기술적 분석
│   ├── evaluator.py           # 코인 선택
│   ├── risk_manager.py        # 리스크 관리
│   ├── ai/                    # AI 모듈
│   └── exchanges/             # 거래소 모듈
├── ui/                        # 사용자 인터페이스
│   ├── dashboard_modern.py    # 모던 대시보드
│   ├── login_modern.py        # 모던 로그인
│   └── settings_modern.py     # 모던 설정
├── config/                    # 설정 파일
│   ├── settings.json          # 메인 설정
│   ├── settings_template.json # 설정 템플릿
│   └── theme_config.json      # 테마 설정
└── data/                      # 데이터 저장소
    ├── logs/                  # 로그 파일
    ├── nwsoft/               # 사용자별 데이터
    └── reports/              # 거래 리포트
```

### **1. 코드 일관성**
- 모든 파일 경로는 `path_utils.py` 사용
- 거래소별 차이는 인터페이스로 추상화
- 에러 처리는 일관된 패턴 사용

### **2. 설정 관리**
- 새 설정 항목은 `settings_template.json`에 먼저 추가
- `settings.py`에서 템플릿과 병합 처리
- 사용자별 설정은 계정별 폴더에 저장

### **3. 로깅**
- 모든 로그는 `path_utils.py`의 경로 사용
- 로그 레벨은 적절히 설정
- 디버깅 정보는 개발 환경에서만 출력

## 📦 빌드 및 배포

### **빌드 환경**
- **빌드 도구**: PyInstaller 5.13+
- **Python 버전**: 3.8+
- **OS 지원**: Windows 10/11
- **아키텍처**: x64

### **빌드 과정**
1. **의존성 설치**
   ```bash
   pip install -r requirements_windows.txt
   pip install pyinstaller==5.13
   ```

2. **빌드 실행**
   ```bash
   # 안전한 빌드 (권장)
   python build_safe.py
   
   # 또는 직접 빌드
   pyinstaller --onefile --windowed --icon=icon.ico main.py
   ```

3. **빌드 결과**
   ```
   dist/
   ├── AITrading.exe          # 메인 실행 파일 (약 150MB)
   └── build/                 # 빌드 임시 파일
   ```

### **배포 파일 구조**
```
AITrading.exe                 # 메인 실행 파일
├── data/                     # 데이터 폴더 (자동 생성)
│   ├── nwsoft/              # 사용자별 데이터
│   │   ├── config/          # 계정별 설정
│   │   │   ├── settings.json
│   │   │   └── theme_config.json
│   │   ├── logs/            # 거래 로그
│   │   │   └── trading.log
│   │   ├── reports/         # 거래 리포트
│   │   └── trading.db       # 거래 데이터베이스
│   └── logs/                # 시스템 로그
└── config/                  # 기본 설정 (템플릿)
    ├── settings_template.json
    └── theme_config.json
```

### **사용자 데이터 관리**
- **사용자별 폴더**: `data/nwsoft/` (자동 생성)
- **계정별 설정 분리**: 각 계정마다 독립적인 설정
- **로그 파일 자동 생성**: 거래 활동 자동 기록
- **데이터 백업**: 설정 및 거래 데이터 자동 백업

### **빌드 최적화**
- **단일 파일**: 모든 의존성을 하나의 exe 파일에 포함
- **윈도우 모드**: 콘솔 창 없이 실행
- **아이콘**: 커스텀 아이콘 적용
- **압축**: UPX를 사용한 파일 크기 최적화

### **배포 체크리스트**
- [ ] API 키 설정 완료
- [ ] 거래소 연결 테스트
- [ ] UI 정상 작동 확인
- [ ] 로그 파일 생성 확인
- [ ] 데이터 폴더 권한 확인

## 🛡️ 보안 및 관리

### **1. API 키 관리**
- API 키는 `settings.json`에 암호화 저장
- 사용자별 계정으로 데이터 분리
- 중복 실행 방지 시스템

### **2. 계정 관리**
- 사용자별 폴더 자동 생성
- 계정별 설정 분리
- 로그인 시 계정 전환

## 🔍 문제 해결

### **1. 경로 문제**
- `path_utils.py`의 경로 함수 사용 확인
- 개발/빌드 환경 구분 확인
- 사용자 계정 설정 확인

### **2. 설정 문제**
- `settings_template.json`과 `settings.json` 동기화
- 사용자별 설정 폴더 확인
- API 키 입력 확인

### **3. 거래소 연결 문제**
- API 키 유효성 확인
- 네트워크 연결 확인
- 거래소별 API 제한 확인

## 📊 성능 및 최적화

### **1. API 제한 처리**
- 거래소별 API 제한 자동 관리
- 요청 간격 자동 조정
- 에러 시 재시도 로직

### **2. 메모리 관리**
- 사용자별 데이터 분리
- 로그 파일 자동 정리
- 캐시 최적화

### **3. 실시간 모니터링**
- 10초마다 거래 사이클 실행
- 포지션 실시간 모니터링
- 대시보드 자동 업데이트(실시간 로그 탭은 좌측 로그 중심 · 우측 Quick Actions/거래 현황으로 단순화, 불필요한 플레이스홀더 제거)

## 🚀 향후 계획

### **1. 추가 거래소 지원**
- 코인원, 코빗 등 한국 거래소
- 해외 주요 거래소 확장

### **2. 고급 기능**
- 포트폴리오 관리
- 리스크 관리 강화
- 백테스팅 시스템

### **3. UI/UX 개선**
- 모바일 지원
- 웹 대시보드
- 실시간 알림

## 📞 지원

### **1. 문제 해결**
- 로그 파일 확인
- 설정 파일 검증
- API 키 유효성 확인

### **2. 업데이트**
- 정기적인 기능 업데이트
- 보안 패치
- 성능 최적화

---

**NoahAI 3.7.5** - AI 금융 의사결정 인프라 (암호화폐 중심)
### **리스크 튜닝(성과 기반)**
- 최근 승률이 낮으면 포지션 크기를 자동 다운시프트, 높으면 업시프트합니다.
- 설정 키(기본값):
  - `risk_winrate_window`: 최근 N건(기본 10)
  - `risk_downshift_threshold`: % 미만 시 다운(기본 40)
  - `risk_upshift_threshold`: % 초과 시 업(기본 60)
  - `risk_shift_factor_down`: 다운시프트 배율(기본 0.85)
  - `risk_shift_factor_up`: 업시프트 배율(기본 1.10)
- 거래소별 최소/최대 포지션 크기는 `exchange_risk_overrides.{exchange}.min_position_size / max_position_size`로 제어합니다.
