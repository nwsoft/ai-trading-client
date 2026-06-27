# 코인 재선택 로직 수정 내역 (2026-01-18)

## 📋 수정 배경

코인 재선택 로직(`_check_and_reselect_coins_optimized`)에서 발견된 문제점들을 수정하고, 로직의 일관성과 정확성을 개선했습니다.

## 🔍 발견된 문제점

### 1. 코인이 비어있을 때 재선택 안 함
- **위치**: `trading/trader.py` 라인 1072-1074
- **문제**: 코인이 비어있을 때 `return`만 하고 재선택을 하지 않음
- **영향**: 
  - `trading_worker.py`에서 초기 코인 선택이 누락되거나 실패한 경우, 거래 사이클이 계속 실행되지만 코인이 없어 거래 불가
  - 사용자가 코인을 수동으로 초기화한 경우에도 자동 선택이 안 됨

### 2. 시간 업데이트 로직 불일치
- **위치**: `trading/trader.py` 라인 1098-1127 (이전 코드)
- **문제**: 시장 상황이 유지되고 1시간 < 경과 < 3시간일 때, 시간을 무조건 업데이트함
- **영향**:
  - 1시간 경과했지만 재선택하지 않은 경우에도 시간만 갱신
  - 다음 사이클에서 다시 1시간을 기다려야 함
  - 시장 상황이 유지될 때 재선택이 3시간까지 지연될 수 있음

## ✅ 수정 내용

### 1. 코인 비어있을 때 즉시 선택 (라인 1072-1080)

**이전 코드:**
```python
if not selected_coins:
    self.log_event('coin_selection', "선택된 코인 없음 - 코인 선택 필요")
    return
```

**수정 후:**
```python
if not selected_coins:
    self.log_event('coin_selection', "선택된 코인 없음 - 코인 선택 실행")
    # 🔥 코인이 비어있을 때는 즉시 코인 선택 실행
    if hasattr(self, 'main_app') and self.main_app and hasattr(self.main_app, 'select_trading_coins'):
        self.main_app.select_trading_coins()
        self.log_event('coin_selection', f"코인 선택 완료: {len(getattr(self.main_app, 'selected_coins', []))}개")
    else:
        self.log_event('coin_selection', "main_app 또는 select_trading_coins 없음 - 코인 선택 불가", level='WARNING')
    return
```

**효과:**
- 코인이 비어있을 때 즉시 `main_app.select_trading_coins()` 호출
- 거래 사이클이 정상 작동하도록 보장
- 로그 메시지 개선으로 사용자에게 명확히 알림

### 2. 시간 업데이트 로직 조건부 적용 (라인 1104-1145)

**이전 코드:**
```python
# 1시간 경과 체크
if time_elapsed > 3600:
    current_regime = self._analyze_market_regime_binance_fast()
    
    if current_regime != self.last_market_regime:
        # 시장 상황 변경 시 재선택 로직
        ...
    else:
        # 시장 상황 유지 시 3시간 체크
        if time_elapsed > 10800:
            ...
        else:
            self.logger.info(f"시장 상황 유지: {current_regime}")
    
    # 🔥 문제: 무조건 시간 업데이트 (재선택 안 했어도)
    self.last_market_regime = current_regime
    self.last_market_analysis_time = current_time
```

**수정 후:**
```python
# 1시간 경과 체크
if time_elapsed > 3600:
    current_regime = self._analyze_market_regime_binance_fast()
    
    # 🔥 시간 업데이트 플래그: 재선택 실행/연기 여부에 따라 결정
    should_update_time = False
    
    if current_regime != self.last_market_regime:
        # 시장 상황 변경 시 재선택 로직
        if 재선택_실행 or 재선택_연기:
            should_update_time = True
    else:
        # 시장 상황 유지 시 3시간 체크
        if time_elapsed > 10800:
            if 재선택_실행 or 재선택_연기:
                should_update_time = True
        else:
            # 🔥 1시간 < 경과 < 3시간: 시간 업데이트 안 함
            should_update_time = False
    
    # 🔥 조건부 시간 업데이트: 재선택 실행/연기한 경우에만
    if should_update_time:
        self.last_market_regime = current_regime
        self.last_market_analysis_time = current_time
```

**효과:**
- 재선택 실행/연기한 경우에만 시간 업데이트
- 시장 상황 유지 + 1시간 < 경과 < 3시간: 시간 업데이트 안 함 (다음 사이클에서 계속 1시간 체크)
- 재선택 타이밍이 적절하게 유지됨

## 📊 수정 후 로직 흐름

### 코인 재선택 조건 (정리)

1. **코인 비어있음**: 즉시 `select_trading_coins()` 호출
2. **첫 실행**: 시장 분석만 하고 시간 기록 (재선택 안 함)
3. **1시간 경과 후**:
   - 시장 상황 변경 + 포지션 < 50% → 재선택 + 시간 업데이트
   - 시장 상황 변경 + 포지션 >= 50% → 재선택 연기 + 시간 업데이트
   - 시장 상황 유지 + 3시간 경과 + 포지션 < 70% → 재선택 + 시간 업데이트
   - 시장 상황 유지 + 3시간 경과 + 포지션 >= 70% → 재선택 연기 + 시간 업데이트
   - 시장 상황 유지 + 1시간 < 경과 < 3시간 → 재선택 안 함 + 시간 업데이트 안 함

## 🔄 호출 순서

1. `execute_trading_cycle()` (라인 1419)
   → `_check_and_reselect_coins_optimized()` (라인 1064)
   → 조건에 따라 `_reselect_coins()` (라인 1132) 또는 `main_app.select_trading_coins()` (라인 1150)

## 📝 수정 위치

- **파일**: `trading/trader.py`
- **메서드**: `_check_and_reselect_coins_optimized()`
- **라인**: 1069-1145

## ⚠️ 주의사항

1. **코인 선택 중복 방지**: `trading_worker.py`에서도 초기 코인 선택을 하므로, 두 곳에서 선택하더라도 문제없음 (이미 선택되어 있으면 다시 선택하지 않음)
2. **시간 업데이트 타이밍**: 재선택 실행/연기한 경우에만 시간 업데이트하여 다음 체크 타이밍을 정확히 관리
3. **시장 상황 유지 시**: 1시간 < 경과 < 3시간일 때 시간을 업데이트하지 않아 다음 사이클에서 계속 1시간을 체크하여 적절한 타이밍에 재선택 수행

## 🧪 테스트 시나리오

1. **코인 비어있을 때**: `selected_coins = []` → 즉시 `select_trading_coins()` 호출 확인
2. **시장 상황 변경**: 1시간 경과 후 시장 상황 변경 → 재선택 확인
3. **시장 상황 유지**: 1시간 경과 후 시장 상황 유지 + 3시간 미만 → 시간 업데이트 안 함 확인
4. **3시간 경과**: 시장 상황 유지 + 3시간 경과 → 재선택 확인

## 📅 수정 일자

2026-01-18
