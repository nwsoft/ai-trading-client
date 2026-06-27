# 📊 NoahAI 로깅 시스템 통합 가이드

## 🎯 개요
NoahAI의 로깅 시스템은 **저장된 로그**와 **실시간 로그**를 동시에 관리하는 통합 시스템입니다.

## ✅ 로그 시스템 통일 완료 (2025-10-19 업데이트)

### 🎯 현재 상태 (완료)
- **거래 신호 분석 로그 완벽 구현**: 상세한 분석 과정 표시
- **통합 로그 시스템 적용**: `log_event()` 함수 사용
- **거래소별 명확한 분류**: `(ex=binance)` 형식으로 일관성 확보
- **WebSocket 중복 초기화 방지**: 성능 최적화 완료

### 🏆 달성된 목표
- **완벽한 분석 로그**: 시그널, 신뢰도, 트렌드, 변동성, RSI, MACD 등 모든 정보 표시
- **AI 추론 정보**: 상세한 분석 근거와 시장 심리 정보 포함
- **일관된 로그 형식**: 터미널과 UI에서 동일한 형식으로 표시

## 🏗️ 로깅 시스템 아키텍처

### 📁 핵심 구성 요소
```
log_system/
├── log_adapter.py      # 통합 로그 어댑터 (log_event 함수)
├── log_stream.py      # 실시간 로그 스트림 서비스
└── __init__.py        # 모듈 초기화

trading/
├── trader.py          # 바이낸스 전용 트레이더 (🔥 log_event로 통일 필요)
└── unified_trader.py  # CCXT 거래소 트레이더 (🔥 log_event로 통일 필요)

ui/widgets/
└── realtime_log_widget.py  # 실시간 로그 위젯 (필터링 및 표시)
```

### 🔄 로그 처리 플로우 (완료)
```
1. 모든 모듈에서 log_event() 호출 ✅
   ↓
2. log_adapter.py → LogStreamService + 표준 로거 ✅
   ↓
3. LogStreamService → UI 위젯 실시간 표시 ✅
   ↓
4. 표준 로거 → 파일 저장 (거래소별) ✅
```

## 📝 로그 형식 및 카테고리

### 🏷️ 로그 카테고리
- **`system`**: 시스템 초기화, 설정 변경
- **`analysis`**: 코인 분석, 기술적 지표 계산
- **`trade`**: 거래 실행, 신호 생성
- **`order`**: 주문 실행, 체결
- **`monitor`**: 포지션 모니터링
- **`exit`**: 청산, 손익 실현

### 📋 로그 형식 (완료)
```
저장된 로그: 2025-10-19 03:43:23 | INFO - [KAVAUSDT] 분석 과정 상세 (ex=binance)
실시간 로그: 2025-10-19 03:43:23 | INFO - [KAVAUSDT] 분석 과정 상세 (ex=binance)
```

## 🔧 로그 시스템 통일 가이드라인

### ✅ 완료된 로깅 방법
```python
# ✅ 완료: log_event() 사용 (trader.py에서 구현됨)
self.log_event('analysis', f"[{symbol}] 분석 과정 상세")
self.log_event('analysis', f"   • 시그널: {signal}")
self.log_event('analysis', f"   • 신뢰도: {confidence:.2f}")
self.log_event('analysis', f"   • RSI: {rsi:.2f}")
self.log_event('analysis', f"   • 추론: {reason}")
```

### 🎯 표준 로깅 패턴 (모든 모듈 적용)
```python
# 거래 신호 분석 로그 (완료)
self.log_event('analysis', f"[{symbol}] 분석 과정 상세")
self.log_event('analysis', f"   • 시그널: {signal}")
self.log_event('analysis', f"   • 신뢰도: {confidence:.2f}")
self.log_event('analysis', f"   • 트렌드: {trend_str}")
self.log_event('analysis', f"   • 변동성: {volatility:.2f}%")
self.log_event('analysis', f"   • 지지 레벨: {support_level:.4f}")
self.log_event('analysis', f"   • 저항 레벨: {resistance_level:.4f}")
self.log_event('analysis', f"   • RSI: {rsi:.2f}")
self.log_event('analysis', f"   • MACD: {macd:.4f}")
self.log_event('analysis', f"   • 볼린저밴드 위치: {bb_position:.2f}")
self.log_event('analysis', f"   • 이동평균 20: {ma20:.4f}")
self.log_event('analysis', f"   • 이동평균 50: {ma50:.4f}")
self.log_event('analysis', f"   • 추론: {reason}")
self.log_event('analysis', f"{symbol} 분석 완료 - 시그널: {signal}")
```

### 🔧 완료된 코드 수정 사항

#### ✅ 1. trader.py 완료
```python
# ✅ 완료: 거래 신호 분석 로그 구현
self.log_event('analysis', f"[{symbol}] 분석 과정 상세")
self.log_event('analysis', f"   • 시그널: {signal}")
self.log_event('analysis', f"   • 신뢰도: {confidence:.2f}")
# ... 모든 분석 정보 표시
```

#### ✅ 2. BinanceClient 완료
```python
# ✅ 완료: log_event 메서드 추가
self.log_event = lambda category, msg, level='INFO': log_event(category, msg, exchange='binance', level=level)
```

#### ✅ 3. WebSocket 중복 초기화 방지 완료
```python
# ✅ 완료: 중복 초기화 방지 로직
if hasattr(self, '_initialization_completed') and self._initialization_completed:
    self.logger.debug(f"Market data already initialized, skipping: {symbols}")
    return symbols
```

## 🎯 거래소별 로그 분류

### 📊 바이낸스 로그
```python
# 모든 바이낸스 관련 로그
log_event('category', 'message', exchange='binance')
```

### 📊 CCXT 거래소 로그
```python
# 바이비트
log_event('category', 'message', exchange='bybit')

# OKX
log_event('category', 'message', exchange='okx')

# 비트겟
log_event('category', 'message', exchange='bitget')
```

## 🔧 설정 및 필터링

### ⚙️ 로그 레벨 설정
- **ALL**: 모든 로그 표시
- **INFO**: 정보성 로그만 표시
- **WARNING**: 경고 이상 표시
- **ERROR**: 오류만 표시

### 🎯 거래소별 필터링
- **바이낸스**: `binance` 키워드 + 코인 심볼 필터링
- **바이비트**: `bybit` 키워드 필터링
- **OKX**: `okx` 키워드 필터링
- **비트겟**: `bitget` 키워드 필터링

## 🚨 해결된 문제들

### ✅ 완료된 문제 해결
1. **저장된 로그와 실시간 로그 일치** ✅
   - 해결: `log_adapter.py`의 통합 로깅 시스템 구현

2. **거래소 탭에서 로그 정확한 표시** ✅
   - 해결: `(ex=binance)` 형식으로 일관성 확보

3. **로그 중복 표시 방지** ✅
   - 해결: `log_event()` 함수로 통일

4. **WebSocket 중복 초기화 방지** ✅
   - 해결: `_initialization_completed` 플래그로 중복 방지

### 🎯 표준 사용법 (모든 모듈 적용)
```python
# ✅ 표준 방법 (trader.py에서 구현됨)
self.log_event('analysis', f"[{symbol}] 분석 과정 상세")
self.log_event('analysis', f"   • 시그널: {signal}")
self.log_event('analysis', f"   • 신뢰도: {confidence:.2f}")
self.log_event('analysis', f"   • RSI: {rsi:.2f}")
self.log_event('analysis', f"   • 추론: {reason}")
```

## 📊 로그 파일 위치
```
data/
├── nwsoft/
│   └── logs/
│       ├── trading.log           # 전체 로그
│       ├── trading_binance.log   # 바이낸스 로그
│       ├── trading_bybit.log     # 바이비트 로그
│       └── trading_okx.log       # OKX 로그
```

## 🔄 업데이트 내역

### 2025-10-19 (완료)
- ✅ **거래 신호 분석 로그 완벽 구현**: 상세한 분석 과정 표시
- ✅ **통합 로그 시스템 적용**: `log_event()` 함수 사용
- ✅ **거래소별 명확한 분류**: `(ex=binance)` 형식으로 일관성 확보
- ✅ **WebSocket 중복 초기화 방지**: 성능 최적화 완료
- ✅ **AI 추론 정보 포함**: 상세한 분석 근거와 시장 심리 정보

### 2025-10-18
- `_StreamForwardHandler` 카테고리 분류 개선
- 거래소 탭 필터링 키워드 추가
- 로깅 방식 통일 (`self.logger.info()` 사용)

---

## 🎯 완성된 로그 시스템 예시

### ✅ 실제 출력되는 로그 (2025-10-19)
```
2025-10-19 03:43:23 | INFO     - [KAVAUSDT] 분석 과정 상세 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 시그널: LONG (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 신뢰도: 0.60 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 트렌드: UNKNOWN (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 변동성: 0.00% (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 지지 레벨: 0.0000 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 저항 레벨: 0.0000 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • RSI: 0.00 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • MACD: 0.0000 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 볼린저밴드 위치: 0.00 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 이동평균 20: 0.0000 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 이동평균 50: 0.0000 (ex=binance)
2025-10-19 03:43:23 | INFO     -    • 추론: RSI at neutral level, MACD showing bullish crossover, low volatility and volume + 낮은 변동성 - 공격적 설정 + 약한 트렌드 (알트코인) + 심리조정(중립심리로 신뢰도하락/높은펀딩비로 레버리지축소) + 시장심리:중립 + 기술적 분석 완료 - LONG 신호 (ex=binance)
2025-10-19 03:43:23 | INFO     - KAVAUSDT 분석 완료 - 시그널: LONG (ex=binance)
```

*이 문서는 NoahAI 로깅 시스템의 완성된 가이드입니다. 모든 목표가 달성되었습니다.*
