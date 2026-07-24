# AI 리포트 상세 거래 내역 분석 (2026-01-18) (이력 보관)

## 📋 문제점

사용자가 AI 리포트 탭에서 "전체 새로고침"으로 상세 거래 내역을 확인했을 때:
1. **진입되지 않은 거래들도 나타남** (0.00 USDT 거래)
2. **같은 시간에 여러 거래가 나타남** (예: CHZUSDT가 15:13에 3개, 14:41에 2개)
3. **어떤 기준으로 어떤 거래들이 나오는지 불명확**

## 🔍 코드 분석 결과

### 1. 거래 로그 저장 조건

**`_log_trade_entry()` 호출 시점:**
```python
# trading/trader.py 라인 3003-3009
self.active_positions[symbol] = position  # 포지션 생성
self._log_trade_entry(...)  # 포지션 생성 직후 로그 저장
```

**결론:**
- `_log_trade_entry()`는 **포지션이 생성된 직후**에만 호출됨
- 포지션이 생성되었다는 것은 **실제로 주문이 성공**했다는 의미
- 따라서 **진입 실패한 거래는 로그가 저장되지 않음**

### 2. 0.00 USDT 거래가 나타나는 이유

**거래 로그 저장 시:**
```python
# trading/trader.py 라인 946-964
trade_log = TradeLog(
    pnl=None,  # 진입 시에는 None (청산 시에만 설정)
    pnl_percent=None,
    exit_price=None,  # 진입 시에는 None (미청산 상태)
    ...
)
```

**AI 리포트 표시:**
```python
# ui/widgets/ai_report_widget.py 라인 851-857
for i, trade in enumerate(today_data[:20]):
    pnl = trade['pnl']  # None일 수 있음
    pnl_percent = trade['pnl_percent']  # None일 수 있음
    detail_text += f"... {pnl:8.2f} USDT ({pnl_percent:6.2f}%)\n"
```

**결론:**
- `pnl=None`인 경우 (아직 청산되지 않은 포지션) → 표시 시 `0.00`으로 나타남
- `pnl=0.00`은 **"아직 청산되지 않은 미청산 포지션"**을 의미
- 진입 실패가 아니라 **진입 성공 후 아직 청산 안 된 상태**

### 3. 같은 시간에 여러 거래가 나타나는 이유

**시간 저장 방식:**
```python
# trading/trader.py 라인 955
entry_time=datetime.now(),  # 초 단위까지 저장
```

**AI 리포트 표시:**
```python
# ui/widgets/ai_report_widget.py 라인 852
entry_time = trade['entry_time'][:16]  # 초 단위 제거, 분 단위까지만 표시
```

**결론:**
- `entry_time`은 초 단위까지 저장되지만, 표시 시 **분 단위까지만** 표시됨
- 빠르게 연속으로 시도한 경우 (예: 15:13:00, 15:13:05, 15:13:10) → 모두 "15:13"으로 표시
- 같은 시간에 여러 방향 시도 (LONG, SHORT) → 모두 같은 시간으로 표시

### 4. 거래 데이터 조회 조건

**`_get_trading_data()` 조회 로직:**
```python
# ui/widgets/ai_report_widget.py 라인 787-796
base_sql = """
    SELECT * FROM trade_log 
    WHERE date(entry_time) >= date('now', '-{} days')
""".format(days)
base_sql += " ORDER BY entry_time DESC"
```

**결론:**
- `trade_log` 테이블의 **모든 레코드**를 조회
- `pnl`이 NULL이거나 0인 경우, `exit_price`가 NULL인 경우 (미청산) 모두 포함
- **필터링 없이 모든 거래 로그 표시**

## ✅ 실제 의미

### "상세 거래 내역"에 포함되는 거래들:

1. **진입 성공한 거래** (포지션 생성됨)
   - `pnl=None` 또는 `pnl=0.00`: 아직 청산되지 않은 미청산 포지션
   - `pnl>0`: 수익 거래 (청산 완료)
   - `pnl<0`: 손실 거래 (청산 완료)

2. **진입 실패한 거래는 포함되지 않음**
   - 포지션이 생성되지 않았으므로 로그가 저장되지 않음

### 같은 시간에 여러 거래가 나타나는 경우:

1. **빠른 연속 시도**: 초 단위 차이 (예: 15:13:00, 15:13:05)
2. **다른 방향 시도**: 같은 시간에 LONG과 SHORT 시도
3. **재시도 로직**: 실패 후 즉시 재시도

## 📊 사용자 예시 분석

사용자가 보여준 거래 내역:
```
3. 2026-01-18 15:16 | CHZUSDT  | SHORT |     0.17 USDT (  0.86%)  ✅ 청산 완료
4. 2026-01-18 15:13 | CHZUSDT  | LONG  |     0.00 USDT (  0.00%)  ⚠️ 미청산 포지션
5. 2026-01-18 15:13 | CHZUSDT  | LONG  |     0.00 USDT (  0.00%)  ⚠️ 미청산 포지션 (중복?)
6. 2026-01-18 15:13 | CHZUSDT  | LONG  |     0.00 USDT (  0.00%)  ⚠️ 미청산 포지션 (중복?)
```

**가능한 시나리오:**
1. 15:13에 CHZUSDT LONG을 여러 번 시도 (재시도 로직)
2. 각 시도마다 포지션이 생성되어 로그가 저장됨
3. 하지만 실제로는 하나의 포지션만 존재할 수 있음

## 🔧 개선 방안

### 1. 미청산 포지션 구분 표시

```python
# 현재
detail_text += f"... | {pnl:8.2f} USDT ({pnl_percent:6.2f}%)\n"

# 개선안
if trade['exit_price'] is None:
    pnl_text = "진입 중"
else:
    pnl_text = f"{pnl:8.2f} USDT ({pnl_percent:6.2f}%)"
```

### 2. 초 단위까지 표시 (중복 구분)

```python
# 현재
entry_time = trade['entry_time'][:16]  # 분 단위

# 개선안
entry_time = trade['entry_time'][:19]  # 초 단위까지 표시
```

### 3. 필터링 옵션 추가

```python
# 청산 완료된 거래만 표시
filtered_data = [t for t in today_data if t['exit_price'] is not None]

# 또는 미청산 포지션만 표시
filtered_data = [t for t in today_data if t['exit_price'] is None]
```

## 💡 결론

1. **진입 실패한 거래는 포함되지 않음** (포지션이 생성되지 않았으므로 로그 없음)
2. **0.00 USDT 거래는 미청산 포지션** (아직 청산되지 않은 상태)
3. **같은 시간에 여러 거래는 빠른 연속 시도** (초 단위 차이, 분 단위로 표시됨)
4. **"상세 거래 내역"은 진입 성공한 모든 거래** (미청산 포함)를 시간순으로 표시

**표시되는 거래들의 기준:**
- ✅ 진입 성공한 거래 (포지션 생성됨)
- ✅ 미청산 포지션 포함 (`pnl=None` 또는 `pnl=0.00`)
- ✅ 청산 완료된 거래 포함 (`pnl` 계산됨)
- ❌ 진입 실패한 거래 제외 (로그 없음)
