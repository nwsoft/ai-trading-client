# "데이터 부족" 원인 분석 (이력 보관)

## 🔍 질문: "데이터 부족"이 무엇을 의미하는가?

### 답변: **코인별 실제 거래 실행 이력 (메모리 데이터)**

---

## 📊 데이터 종류 명확화

### ❌ 이것이 아닙니다:

1. **AI 학습 데이터** (ai_learning_data.json 등)
   - 몇천개~몇만개의 학습 데이터와는 **무관**합니다.
   - AI 학습 데이터는 패턴 인식용이며, 거래 실행 여부 판단과는 별개입니다.

2. **데이터베이스의 전체 거래 이력** (trade_log 테이블)
   - 데이터베이스에 저장된 과거 거래 기록과도 **무관**합니다.
   - 이 데이터는 분석에 사용되지 않습니다.

### ✅ 이것입니다:

**`RiskManager.coin_trade_history` - 코인별 실제 거래 실행 이력 (메모리 데이터)**

---

## 🔍 코드 분석

### 1. 데이터 소스 위치

**파일**: `trading/risk_manager.py` Line 56

```python
class RiskManager:
    def __init__(self, binance_client, database_manager):
        # ...
        self.coin_trade_history = {}  # 코인별 거래 이력 (메모리)
```

**특징:**
- **메모리 변수**: 프로그램 실행 중에만 존재
- **코인별 관리**: `{coin: [trade1, trade2, ...]}` 형태
- **프로그램 재시작 시 초기화**: 영구 저장되지 않음

---

### 2. 데이터 업데이트 시점

**파일**: `trading/risk_manager.py` Line 75-99

```python
def update_coin_trade_history(self, symbol: str, trade_result: str, ...):
    """코인별 거래 이력 업데이트"""
    coin = symbol.replace('USDT', '')
    
    if coin not in self.coin_trade_history:
        self.coin_trade_history[coin] = []  # 초기화
    
    # 거래 이력 추가
    trade_info = TradeResult(...)
    self.coin_trade_history[coin].append(asdict(trade_info))
```

**업데이트 시점:**
- **실제 거래가 실행되어 종료될 때만** 업데이트됩니다.
- 거래 신호가 발생해도 실행되지 않으면 업데이트되지 않습니다.

---

### 3. 데이터 부족 판단 기준

**파일**: `trading/trader.py` Line 3087-3136

```python
def _analyze_recent_trading_patterns(self, coin: str) -> Dict:
    """확장된 거래 패턴 분석 (최근 50회, 시장 상황별 분석)"""
    if self.risk_manager and coin in self.risk_manager.coin_trade_history:
        # 최근 50회 거래 분석
        recent_trades = self.risk_manager.coin_trade_history[coin][-50:]
        
        total = len(recent_trades)
        
        return {
            'recent_trades': total,
            # ...
            'data_insufficient': bool(total < 20),  # 최소 20회 필요
        }
    else:
        # 거래 이력이 없는 경우
        return {
            'recent_trades': 0,
            'data_insufficient': True,  # 데이터 부족
        }
```

**판단 기준:**
- **코인별**로 판단합니다 (토탈이 아님)
- 해당 코인의 **최근 50회 거래** 중 **20회 미만**이면 `data_insufficient = True`
- 해당 코인에 **거래 이력이 없으면** `data_insufficient = True`

---

### 4. 데이터 부족 시 영향

**파일**: `trading/trader.py` Line 3022-3028

```python
if not pattern_analysis.get('data_insufficient', False):
    # 데이터 충분: 전체 조건 검증
    proceed = (
        pattern_analysis['loss_rate'] < dynamic_thresholds['max_loss_rate'] and
        pattern_analysis['recent_trades'] >= dynamic_thresholds['min_trades_history'] and
        market_conditions['volatility_suitable'] and
        ai_validation['confidence'] >= dynamic_confidence_threshold
    )
else:
    # 데이터 부족: 더 보수적인 임계값 적용 (신뢰도 요구사항 강화)
    conservative_threshold = max(dynamic_confidence_threshold, 0.75)  # 최소 0.75 이상
    proceed = (
        market_conditions['volatility_suitable'] and
        ai_validation['confidence'] >= conservative_threshold
    )
```

**영향:**
- `user_signal_threshold = 68`이면 `dynamic_confidence_threshold = 0.68`
- 하지만 데이터 부족 시 **최소 0.75 (75%)를 강제**합니다.
- AI 검증 기본 신뢰도는 0.7 (70%)인데, 0.75를 요구하므로 **0.7 < 0.75로 거래가 차단**됩니다.

---

## 🎯 핵심 정리

### 데이터 종류

| 데이터 종류 | 위치 | 용도 | 거래 실행 판단에 사용? |
|-----------|------|------|---------------------|
| **AI 학습 데이터** | `data/nwsoft/ai_learning_data_*.json` | 패턴 학습 | ❌ 사용 안 함 |
| **데이터베이스 거래 이력** | `trading.db` (trade_log 테이블) | 과거 기록 저장 | ❌ 사용 안 함 |
| **코인별 거래 실행 이력** | `RiskManager.coin_trade_history` (메모리) | 거래 실행 여부 판단 | ✅ **사용함** |

### 데이터 부족 판단 기준

1. **코인별**로 판단 (토탈이 아님)
2. **해당 코인의 최근 50회 거래** 중 **20회 미만**이면 부족
3. **해당 코인에 거래 이력이 없으면** 부족

### 문제점

- **새로운 코인**: 거래 이력이 없어서 `data_insufficient = True`
- **거래 이력이 적은 코인**: 20회 미만이면 `data_insufficient = True`
- **프로그램 재시작**: 메모리 데이터이므로 초기화되어 모든 코인이 `data_insufficient = True`

---

## 📝 결론

**"데이터 부족"은 해당 코인에 대한 실제 거래 실행 이력이 부족하다는 의미입니다.**

- 학습 데이터나 데이터베이스 데이터와는 **무관**합니다.
- **코인별**로 판단하며, **토탈이 아닙니다**.
- 프로그램이 재시작되면 모든 코인이 데이터 부족 상태가 됩니다.
- 실제 거래가 실행되어 종료될 때마다 업데이트됩니다.

**따라서 거래가 실행되지 않으면 데이터가 쌓이지 않고, 데이터가 없으면 거래가 실행되지 않는 "닭과 달걀" 문제가 발생할 수 있습니다.**

---

## 📅 작성일

2025-01-27
