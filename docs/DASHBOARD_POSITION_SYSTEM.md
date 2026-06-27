# 대시보드 포지션 표시 시스템 가이드

## 🚨 중요: 바이낸스와 CCXT 거래소의 아키텍처 차이

### 문제 상황
- **바이낸스**: `Trader` 클래스 사용 → 포지션은 `main_app.trader.active_positions`에 저장
- **CCXT 거래소**: `UnifiedTrader` 클래스 사용 → 포지션은 `unified_trader.active_positions`에 저장
- **대시보드**: 기존에는 `UnifiedTrader`만 참조하여 바이낸스 포지션이 표시되지 않음

### 해결 방법

#### 1. 포지션 표시 로직 수정
```python
# ui/dashboard_modern.py - create_exchange_positions_section()
def refresh_once():
    positions = {}
    
    # 바이낸스는 Trader 클래스에서 포지션 조회
    if exchange == 'binance':
        if hasattr(self, 'main_app') and hasattr(self.main_app, 'trader') and self.main_app.trader:
            positions = getattr(self.main_app.trader, 'active_positions', {})
    else:
        # CCXT 거래소들은 UnifiedTrader에서 조회
        if hasattr(self, 'unified_trader') and self.unified_trader:
            positions = getattr(self.unified_trader, 'active_positions', {}).get(exchange, {})
```

#### 2. 거래 현황 통계 통합
```python
# ui/dashboard_modern.py - _refresh_trading_summary()
# 바이낸스 통계 (Trader 클래스)
if hasattr(self, 'main_app') and hasattr(self.main_app, 'trader') and self.main_app.trader:
    binance_positions = getattr(self.main_app.trader, 'active_positions', {})
    active_positions += len(binance_positions)

# CCXT 거래소 통계 (UnifiedTrader 클래스)
unified_trader = getattr(self, 'unified_trader', None)
if unified_trader:
    stats = unified_trader.get_all_statistics()
    # CCXT 거래소 통계 추가
```

#### 3. 시장 트렌드 위젯 수정
```python
# ui/widgets/market_trend_widget.py - _update_portfolio_section()
# 바이낸스 통계 (Trader 클래스)
if self.dashboard_ref and hasattr(self.dashboard_ref, 'main_app'):
    main_app = getattr(self.dashboard_ref, 'main_app', None)
    if main_app and hasattr(main_app, 'trader') and main_app.trader:
        binance_positions = getattr(main_app.trader, 'active_positions', {})
        active_positions += len(binance_positions)

# CCXT 거래소 통계 (UnifiedTrader 클래스)
unified_trader = getattr(self.dashboard_ref, 'unified_trader', None)
if unified_trader:
    # CCXT 거래소 통계 추가
```

## 📋 개발 시 체크리스트

### 새 거래소 추가 시
- [ ] 거래소가 CCXT 기반인지 확인
- [ ] CCXT 기반이면 `UnifiedTrader` 사용
- [ ] 바이낸스 전용이면 `Trader` 사용
- [ ] 대시보드 포지션 표시 로직에 올바른 분기 추가

### 포지션 표시 수정 시
- [ ] 거래소 타입 확인 (바이낸스 vs CCXT)
- [ ] 올바른 객체 참조 사용
  - 바이낸스: `main_app.trader.active_positions`
  - CCXT: `unified_trader.active_positions[exchange]`
- [ ] 통계 수집 시 두 시스템 모두 고려

### 통계 수집 시
- [ ] 바이낸스와 CCXT 거래소 데이터 분리 처리
- [ ] 포지션 수는 두 시스템 합산
- [ ] 거래 수와 손익은 각각의 시스템에서 조회
- [ ] 승률은 더 많은 거래 데이터를 가진 시스템 기준

## 🔍 디버깅 가이드

### 포지션이 표시되지 않는 경우
1. **바이낸스 포지션 미표시**:
   - `main_app.trader` 객체 존재 확인
   - `main_app.trader.active_positions` 내용 확인
   - 거래 실행 로그에서 포지션 기록 확인

2. **CCXT 거래소 포지션 미표시**:
   - `unified_trader` 객체 존재 확인
   - `unified_trader.active_positions[exchange]` 내용 확인
   - 거래소별 활성화 상태 확인

### 통계가 정확하지 않은 경우
1. **활성 포지션 수 부정확**:
   - 바이낸스와 CCXT 거래소 포지션 수 모두 합산되는지 확인
   - 각 시스템의 `active_positions` 길이 확인

2. **거래 수나 손익 부정확**:
   - CCXT 거래소 통계가 올바르게 조회되는지 확인
   - 바이낸스 통계는 별도 시스템에서 관리되는지 확인

## 📚 관련 파일

- `ui/dashboard_modern.py`: 메인 대시보드 포지션 표시
- `ui/widgets/market_trend_widget.py`: 시장 트렌드 위젯 통계
- `trading/trader.py`: 바이낸스 거래 시스템
- `trading/unified_trader.py`: CCXT 거래소 통합 시스템
- `main.py`: 거래 시스템 초기화 및 관리

## ⚠️ 주의사항

1. **객체 참조 안전성**: `hasattr()` 체크 후 접근
2. **거래소 타입 확인**: `exchange == 'binance'` 분기 필수
3. **통계 통합**: 두 시스템의 데이터를 올바르게 합산
4. **성능 고려**: 불필요한 API 호출 최소화

이 가이드를 따라하면 바이낸스와 CCXT 거래소의 포지션이 모두 정상적으로 표시됩니다.
