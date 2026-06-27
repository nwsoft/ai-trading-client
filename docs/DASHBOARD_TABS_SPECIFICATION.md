# 대시보드 탭 사양서

## 작성일: 2025-10-31

## 1. 코인 정보 탭

### 데이터 소스
- `self.selected_coins` (메모리)
- Evaluator에서 코인 선정 시 설정됨

### 표시 항목 (순서대로)

| 컬럼 | 필드명 | 설명 | 색상 |
|------|--------|------|------|
| 코인 | `symbol` | 심볼 (예: BTCUSDT) | - |
| **AI종합점수** | `overall_score` | 종합 평가 점수 | **70+ 초록색, 50-69 주황색, 50미만 빨간색, 굵은 글씨** |
| 변동성점수 | `volatility_score` | 변동성 평가 | - |
| 거래량점수 | `volume_score` | 거래량 평가 | - |
| 기술점수 | `technical_score` | 기술 지표 평가 | - |
| 트렌드점수 | `trend_score` | 추세 평가 | - |
| 리스크점수 | `risk_score` | 리스크 평가 | - |

### 구현 위치
- 파일: `ui/dashboard_modern.py`
- 함수: `_update_coin_info()` (1590-1650번 줄)
- 새로고침: `_refresh_coin_info()`

---

## 2. 거래 통계 탭

### 데이터 소스
- **테이블**: `trade_log`
- **조건**: `exit_time IS NOT NULL` (청산된 거래만)
- **정렬**: 총 거래 수 기준 내림차순

### 표시 항목 (순서대로)

| 컬럼 | SQL | 설명 | 색상 |
|------|-----|------|------|
| 코인 | `symbol` | 심볼 | - |
| 총 거래 | `COUNT(*)` | 총 거래 수 | - |
| 익절 | `SUM(CASE WHEN pnl > 0 ...)` | 수익 거래 수 | - |
| 손절 | `SUM(CASE WHEN pnl < 0 ...)` | 손실 거래 수 | - |
| **승률** | `(익절 / 총거래) * 100` | 승률 (%) | **50%+ 초록색, 0-50% 빨간색** |
| **평균수익률** | `AVG(pnl_percent)` | 평균 수익률 (%) | **양수 초록색, 음수 빨간색** |
| 최대수익 | `MAX(pnl)` | 최대 수익 (USDT) | - |
| 최대손실 | `MIN(pnl)` | 최대 손실 (USDT) | - |

### 구현 위치
- 파일: `ui/dashboard_modern.py`
- 함수: `_update_trading_statistics()` (1644-1750번 줄)
- 새로고침: `_refresh_trading_stats()`

### SQL 쿼리
```sql
SELECT
    symbol,
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
    AVG(pnl_percent) as avg_profit_rate,
    MAX(pnl) as max_profit,
    MIN(pnl) as max_loss
FROM trade_log
WHERE exit_time IS NOT NULL
GROUP BY symbol
ORDER BY total_trades DESC
```

---

## 3. 거래 현황 패널 (우측 상단)

### 데이터 소스
- **테이블**: `trade_log` (exit_time IS NOT NULL)
- **메모리**: `trader.active_positions`, `unified_trader.get_active_positions()`

### 표시 항목

```
📊 거래 현황

• 활성 포지션: X건
• 총 거래 수: X건
• 누적 손익: X.XX USDT
• 승률: X.XX%
• 자동 거래 상태: 실행 중 (X/Y 거래소)
```

### 계산 로직

| 항목 | 계산 방법 |
|------|----------|
| 활성 포지션 | `len(trader.active_positions) + sum(len(p) for p in unified_trader.get_active_positions().values())` |
| 총 거래 수 | `COUNT(*) FROM trade_log WHERE exit_time IS NOT NULL` |
| 누적 손익 | `SUM(pnl) FROM trade_log WHERE exit_time IS NOT NULL` |
| 승률 | `(SUM(CASE WHEN pnl > 0 ...) / COUNT(*)) * 100` |
| 자동 거래 상태 | `len(_running_exchanges)` / `len(enabled_exchanges)` |

### 구현 위치
- 파일: `ui/dashboard_modern.py`
- 함수: `_update_trading_summary_panel()` (4489-4574번 줄)

### SQL 쿼리
```sql
SELECT 
    COUNT(*) as total_trades,
    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
    SUM(pnl) as total_pnl
FROM trade_log
WHERE exit_time IS NOT NULL
```

---

## 4. exchange_trade_stats 테이블

### 상태
- **현재**: 사용 안 함 (1건만 있고 업데이트 안 됨)
- **원래 목적**: 거래소별 누적 통계 저장
- **문제**: 업데이트 로직이 작동 안 함

### 관련 코드 (유지, 사용 안 함)
- `trading/recorder.py`: `save_exchange_trade_stats()`, `load_exchange_trade_stats()`
- `trading/trader.py`: 청산 시 호출 (3472, 3781번 줄)
- `trading/unified_trader.py`: 청산 시 호출 (2097번 줄)

### 결정
- **제거하지 않음**: 향후 사용 가능성 대비
- **현재 대시보드**: `trade_log` 직접 집계 사용

---

## 5. 수정 가이드라인

### 데이터 변경 시
1. **trade_log 테이블 컬럼 변경**
   - 대시보드 SQL 쿼리 수정
   - 거래 통계 탭: `_update_trading_statistics()`
   - 거래 현황 패널: `_update_trading_summary_panel()`

2. **selected_coins 필드 변경**
   - 코인 정보 탭: `_update_coin_info()`
   - 헤더 순서 유지

3. **색상 변경**
   - AI종합점수: 70/50 임계값
   - 승률: 50% 임계값
   - 평균수익률: 0% 임계값

### UI 변경 시
1. **헤더 변경**: 목차와 정확히 일치시킬 것
2. **컬럼 순서**: 절대 변경 금지
3. **색상 적용**: 주요 지표만 (AI종합점수, 승률, 평균수익률)
4. **정렬**: font=("", 11/12, "bold") 사용

### 테스트 방법
```python
# trade_log 데이터 확인
python -c "import sqlite3; conn = sqlite3.connect('data/nwsoft/trading.db'); 
cur = conn.cursor(); 
cur.execute('SELECT symbol, COUNT(*), SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END), AVG(pnl_percent) FROM trade_log WHERE exit_time IS NOT NULL GROUP BY symbol LIMIT 5'); 
[print(row) for row in cur.fetchall()]; 
conn.close()"
```

---

## 6. 변경 이력

### 2025-10-31
- 거래 통계 탭: `exchange_trade_stats` → `trade_log` 변경
- 거래 현황 패널: `exchange_trade_stats` → `trade_log` 변경
- 코인 정보 탭: 헤더 추가, AI종합점수 색상 적용
- 경로 문제 해결: `_current_user_account` 설정 (main.py 1987번 줄)

### 2026-05-06 (v3.8.9.19) — 서비스 전용 탭 전면 고도화

#### 자산 통합(real_estate) 서비스 탭 변경

| 탭 | 이전 구현 | 변경 후 구현 |
|---|---|---|
| `📊 자산 배분 진단` | `_ensure_service_info_tab()` — 텍스트 라인 목록 | `_build_asset_allocation_diagnosis_tab()` — 비중 바차트 + HHI 미터 + 상관계수 히트맵 + 리밸런싱 카드 |
| `⚠️ 리스크 브리핑` | `_ensure_service_info_tab()` — 텍스트 라인 목록 | `_build_risk_briefing_tab()` — 3-카드 + 시나리오 손실 테이블 + 대응 액션 |

**자산 배분 진단 탭 구성**:
- 섹션1: 자산군별 비중 바차트 (tkinter Canvas, 컬러별 막대 + 범례)
- 섹션2: HHI 집중도 미터 (0~100, 삼각 마커, 3구간 색상)
- 섹션3: 상관계수 2×2 히트맵 (암호화폐↔주식, 위험도 색상)
- 섹션4: 리밸런싱 제안 (AssetCorrelationService 결과)
- 구현 함수: `_build_asset_allocation_diagnosis_tab(tab)`, `_ensure_asset_allocation_diagnosis_tab()`

**리스크 브리핑 탭 구성**:
- 섹션1: 집중도/상관계수/누적손익 3-카드 (위험 수준별 색상)
- 섹션2: 시나리오별 손실 추정 테이블 (-5%/-10%/-20%/-30%/-50%)
- 섹션3: 경고 메시지 + 즉시 권장 액션 3개
- 구현 함수: `_build_risk_briefing_tab(tab)`, `_ensure_risk_briefing_full_tab()`

#### AI 애널리스트(ai_analyst) 서비스 탭 변경

| 탭 | 이전 구현 | 변경 후 구현 |
|---|---|---|
| `🧪 시나리오 점검` | `_ensure_service_info_tab()` — 설정값 4줄 표시 | `_build_scenario_check_tab()` — DB 백테스트 엔진 |

**시나리오 점검 탭 구성**:
- 현재 정책 표시 패널 (buy_threshold / sell_threshold / 점검주기 / 최대포지션 / 리스크가드)
- DB `trade_log` 기반 3개 시나리오 비교 테이블
  - 보수(포지션 ×0.7) / 현재 정책(×1.0) / 공격(포지션 ×1.3)
  - 계산 지표: 거래수 · 승률 · 누적손익 · 건당 평균 · 최대 드로우다운
- 이번 달 성과 요약 패널
- "💬 AI에 시나리오 심층 분석 요청" 버튼
- 구현 함수: `_build_scenario_check_tab(tab)`, `_ensure_scenario_check_tab()`

#### 생활금융(other) 서비스 탭 추가

| 탭 | 구분 | 구현 |
|---|---|---|
| `📉 현금흐름 분석` | 기존 유지 | `_ensure_service_info_tab()` |
| `🎯 생활금융 목표` | 기존 유지 | `_ensure_service_info_tab()` |
| `🚨 보안 경고` | **신규** | `_build_fraud_detection_tab()` |
| `💰 세금 계산` | **신규** | `_build_tax_calculation_tab()` |
| `📌 생활금융 사용가이드` | 기존 유지 | `_ensure_service_guide_tab()` |

**보안 경고 탭 구성**:
- DB `trade_log` → `TransactionRecord` 변환 → `detect_abnormal_transactions()` 자동 탐지
- 종합 리스크 점수 표시 (`compute_fraud_risk_summary()`)
- 탐지된 경고 목록 카드 (위험 수준별 배경색)
- 보이스피싱 자가 진단 5가지 체크리스트
- 구현 함수: `_build_fraud_detection_tab(tab)`, `_ensure_fraud_detection_full_tab()`

**세금 계산 탭 구성**:
- 입력 필드: 연봉/신용카드/의료비/교육비/기부금/금융소득/주식차익 (8개)
- [세금 계산하기] 버튼 → 실시간 계산
- 결과 섹션A: 연말정산 (산출세액/총공제/납부세액/실효세율)
- 결과 섹션B: 금투세 (수익 입력 시 조건부 표시)
- 결과 섹션C: 절세 계좌 비교 (ISA/연금저축/IRP)
- 결과 섹션D: 절세 최적화 요약 팁 5가지
- 구현 함수: `_build_tax_calculation_tab(tab)`, `_ensure_tax_calculation_full_tab()`

#### 관련 정책 파일
- `ui/service_tab_policy.py`: `other` 서비스 detail 탭 3개 → 5개
