# 바이낸스 거래 보수적 설정 분석 보고서

## 📋 개요

바이낸스 거래에서 거래가 거의 발생하지 않는 원인을 분석한 보고서입니다. 현재 설정값과 코드 로직을 기반으로 보수적 거래의 주요 원인을 파악했습니다.

---

## 🔍 주요 원인 분석

### 1. **AI 신호 임계값 (user_signal_threshold) - 가장 큰 원인**

**현재 설정값:**
- `data/nwsoft/config/settings.json`: **80점**
- `config/settings_template.json`: **85점** (기본값)
- `config/settings.py`: **85점** (기본값)

**영향:**
- `analyzer.py`의 `_should_generate_signal_despite_low_volatility()` 메서드에서 신호 점수가 **80점 이상**이어야만 거래 신호가 생성됩니다.
- 신호 점수 계산 방식:
  - 극단적 RSI (≤20 또는 ≥80): +40점
  - 강한 RSI 신호 (≤30 또는 ≥70): +25점
  - 강한 MACD 신호: +20점
  - 볼린저 밴드 극단 위치: +25점
  - 강한 모멘텀: +15점
  - 시장 상황 고려: +10~20점
  - 연속 HOLD 5회 이상: +15점
  - AI 학습 기반 권장: +20점

**문제점:**
- 80점 기준은 매우 높아서 대부분의 신호가 차단됩니다.
- 여러 조건을 동시에 만족해야만 거래 신호가 생성됩니다.

**코드 위치:**
```2273:2285:trading/analyzer.py
            # 최종 판단 (사용자 설정 기준 이상이면 신호 생성)
            should_signal = signal_score >= self.user_signal_threshold

            if should_signal:
                self.logger.info(f"🤖 AI 신호 생성 승인: {signal_score}점 (기준: {self.user_signal_threshold}점)")
                self.logger.info(f"   - 이유: {', '.join(reasons)}")
                self.logger.info(f"   - 변동성: {current_vol:.4%} (기준: {threshold_vol:.4f}%)")

                # 연속 HOLD 카운터 리셋
                if not hasattr(self, '_consecutive_holds'):
                    self._consecutive_holds = {}
                self._consecutive_holds[symbol] = 0
            else:
                self.logger.info(f"🤖 AI 신호 생성 거부: {signal_score}점 (필요: {self.user_signal_threshold}점)")
```

---

### 2. **AI 신뢰도 임계값 (동적 임계값)**

**현재 설정값:**
- `user_signal_threshold` (80) → 신뢰도 0.80 (80%)로 변환
- 데이터 부족 시: **최소 0.75 (75%)** 이상 요구

**영향:**
- `trader.py`의 `_calculate_dynamic_confidence_threshold()` 메서드에서 `user_signal_threshold`를 100으로 나눈 값(0.80)을 기본 임계값으로 사용합니다.
- 데이터 부족 시 더 보수적으로 **0.75 이상**을 요구합니다.

**코드 위치:**
```3251:3297:trading/trader.py
    def _calculate_dynamic_confidence_threshold(self, symbol: str, signal_data: Dict) -> float:
        """AI 기반 동적 신뢰도 임계값 계산"""
        try:
            # 1) 분석기 임계값을 신뢰도 기준에 반영 (50~90 → 0.50~0.90)
            analyzer_th = 0
            try:
                if hasattr(self, 'analyzer') and self.analyzer:
                    analyzer_th = int(self.analyzer.get_user_signal_threshold())
            except Exception:
                analyzer_th = 0

            # 기본 맵핑: 50 → 0.50, 60 → 0.60, 70 → 0.70, 80 → 0.80, 90 → 0.90
            # user_signal_threshold를 그대로 신뢰도로 사용 (50~90 → 0.50~0.90)
            base_threshold = analyzer_th / 100.0 if analyzer_th > 0 else 0.65

            # 2) 시장 상황에 따른 소폭 가감 (곱이 아닌 가/감산으로 과도한 완화 방지)
            try:
                if hasattr(self, 'analyzer') and self.analyzer:
                    market_data = self.analyzer._analyze_current_market_conditions()
                    market_level = (market_data or {}).get('level', 'NORMAL')
                    if market_level == 'HIGH':
                        base_threshold += 0.02  # 고변동성 → 더 보수적
                    elif market_level == 'LOW':
                        base_threshold -= 0.02  # 저변동성 → 약간 완화
            except Exception:
                pass

            # 3) 연속 성과 기반 미세 조정(±0.03 이내)
            try:
                if hasattr(self, 'risk_manager') and self.risk_manager:
                    coin = symbol.replace('USDT', '')
                    consecutive_wins = int(self.risk_manager.coin_consecutive_wins.get(coin, 0))
                    consecutive_losses = int(self.risk_manager.coin_consecutive_losses.get(coin, 0))
                    if consecutive_wins >= 2:
                        base_threshold -= 0.03
                    elif consecutive_wins == 1:
                        base_threshold -= 0.015
                    elif consecutive_losses >= 2:
                        base_threshold += 0.03
                    elif consecutive_losses == 1:
                        base_threshold += 0.015
            except Exception:
                pass

            # 4) 안전 가드레일
            base_threshold = max(0.30, min(base_threshold, 0.95))
            return base_threshold

        except Exception as e:
```

**데이터 부족 시 보수적 처리:**
```3023:3028:trading/trader.py
            else:
                # 데이터 부족: 더 보수적인 임계값 적용 (신뢰도 요구사항 강화)
                conservative_threshold = max(dynamic_confidence_threshold, 0.75)  # 최소 0.75 이상
                proceed = (
                    market_conditions['volatility_suitable'] and
                    ai_validation['confidence'] >= conservative_threshold
                )
```

---

### 3. **AI 거래 선호도 (risk_tolerance)**

**현재 설정값:**
```json
"ai_trading_preferences": {
  "risk_tolerance": "CONSERVATIVE",
  "balance_utilization_limit": 0.15,
  "max_position_size_factor": 5.0,
  "min_position_size_factor": 0.5,
  "risk_levels": {
    "conservative": {
      "balance_utilization": 0.10,  // 잔고의 10%만 사용
      "max_position_factor": 2.0,   // 최대 포지션 크기 배수 2.0
      "description": "보수적 접근 - 안전 우선"
    }
  }
}
```

**영향:**
- 잔고의 **10%만** 사용 가능
- 최대 포지션 크기가 **2.0배**로 제한

---

### 4. **거래소별 리스크 오버라이드 (exchange_risk_overrides)**

**현재 설정값:**
```json
"exchange_risk_overrides": {
  "binance": {
    "max_positions": 3,
    "max_position_size": 0.01,  // 포지션 크기 1%로 제한
    "min_position_size": 0.001,
    "max_leverage": 20
  }
}
```

**영향:**
- 바이낸스의 최대 포지션 크기가 **0.01 (1%)**로 매우 작게 설정됨
- 최대 포지션 수: **3개**

---

### 5. **최소 거래 금액 (min_trade_amount)**

**현재 설정값:**
- `min_trade_amount`: **5.0 USDT** (일반)
- `symbol_min_notional_overrides.ETHUSDT`: **20.0 USDT** (ETHUSDT 특별 설정)

**영향:**
- `trader.py`의 `should_execute_trade()` 메서드에서 최소 거래 금액을 확인합니다.
- API의 `min_notional`과 설정값 중 **더 큰 값**을 사용합니다.

**코드 위치:**
```1600:1607:trading/trader.py
                    # 🔥 바이낸스 API의 min_notional과 설정값 중 더 큰 값 사용 (안전성)
                    api_min_notional = None
                    if isinstance(filters, dict):
                        api_min_notional = filters.get('min_notional', filters.get('minNotional'))
                    if api_min_notional is None:
                        api_min_notional = 0.0
                    config_min_notional = float(self.settings.get('min_trade_amount', 5.0))
                    min_notional = max(float(api_min_notional), config_min_notional)
```

---

### 6. **진입 전 분석 (Pre-entry Analysis)**

**현재 로직:**
- 패턴 분석, 시장 조건, AI 검증을 모두 통과해야만 거래 실행
- 데이터 부족 시 더 보수적인 임계값 적용

**코드 위치:**
```3014:3028:trading/trader.py
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

---

## 📊 설정값 요약

| 설정 항목 | 현재 값 | 영향도 | 설명 |
|---------|--------|--------|------|
| `user_signal_threshold` | **80점** | ⭐⭐⭐⭐⭐ | AI 신호 생성 임계값 (30~90 범위) |
| `risk_tolerance` | **CONSERVATIVE** | ⭐⭐⭐⭐ | 리스크 허용 수준 |
| `balance_utilization` | **0.10 (10%)** | ⭐⭐⭐ | 잔고 사용 비율 |
| `max_position_size` (binance) | **0.01 (1%)** | ⭐⭐⭐ | 최대 포지션 크기 |
| `max_position_factor` | **2.0** | ⭐⭐ | 최대 포지션 배수 |
| `min_trade_amount` | **5.0 USDT** | ⭐⭐ | 최소 거래 금액 |
| `max_positions` | **3개** | ⭐⭐ | 최대 동시 포지션 수 |
| 동적 신뢰도 임계값 | **0.80 (80%)** | ⭐⭐⭐⭐⭐ | AI 신뢰도 기준 (user_signal_threshold 기반) |
| 데이터 부족 시 임계값 | **0.75 (75%)** | ⭐⭐⭐⭐ | 데이터 부족 시 최소 신뢰도 |

---

## 🔧 권장 조정 방안

### 1. **user_signal_threshold 낮추기 (가장 효과적)**

**현재:** 80점 → **권장:** 60~70점

**효과:**
- 거래 신호 생성 빈도가 크게 증가합니다.
- 60점: 보통 수준의 신호도 허용
- 70점: 중간 수준의 신호 허용

**설정 위치:**
- `data/nwsoft/config/settings.json`의 `analyzer_settings.user_signal_threshold`
- `config/settings_template.json`의 `analyzer_settings.user_signal_threshold`

---

### 2. **risk_tolerance 조정**

**현재:** CONSERVATIVE → **권장:** MODERATE

**효과:**
- 잔고 사용 비율: 10% → 25%
- 최대 포지션 배수: 2.0 → 5.0

**설정 위치:**
- `data/nwsoft/config/settings.json`의 `ai_trading_preferences.risk_tolerance`

---

### 3. **max_position_size 증가**

**현재:** 0.01 (1%) → **권장:** 0.02~0.03 (2~3%)

**효과:**
- 포지션 크기 제한 완화

**설정 위치:**
- `data/nwsoft/config/settings.json`의 `exchange_risk_overrides.binance.max_position_size`

---

### 4. **balance_utilization_limit 증가**

**현재:** 0.15 (15%) → **권장:** 0.25~0.30 (25~30%)

**효과:**
- 전체 잔고 사용 비율 증가

**설정 위치:**
- `data/nwsoft/config/settings.json`의 `ai_trading_preferences.balance_utilization_limit`

---

## 📝 코드 참조 위치

### 주요 파일

1. **`trading/analyzer.py`**
   - Line 152: `user_signal_threshold` 초기화
   - Line 217-237: `set_user_signal_threshold()`, `get_user_signal_threshold()`
   - Line 2273: 신호 생성 판단 로직 (`signal_score >= self.user_signal_threshold`)

2. **`trading/trader.py`**
   - Line 1542-1744: `should_execute_trade()` - 거래 실행 조건 검증
   - Line 3000-3083: `_pre_entry_analysis()` - 진입 전 분석
   - Line 3251-3297: `_calculate_dynamic_confidence_threshold()` - 동적 신뢰도 임계값 계산

3. **`config/settings_template.json`**
   - Line 302-324: `analyzer_settings` 섹션
   - Line 368-392: `ai_trading_preferences` 섹션
   - Line 435-470: `exchange_risk_overrides` 섹션

4. **`data/nwsoft/config/settings.json`**
   - Line 221-244: `analyzer_settings` 섹션 (실제 사용 설정)
   - Line 287-311: `ai_trading_preferences` 섹션
   - Line 400-435: `exchange_risk_overrides` 섹션

---

## 🎯 결론

바이낸스 거래가 보수적으로 거의 발생하지 않는 **주요 원인**은 다음과 같습니다:

1. **`user_signal_threshold`가 80점으로 매우 높게 설정됨** (가장 큰 원인)
2. **동적 신뢰도 임계값이 0.80 (80%)로 높음**
3. **`risk_tolerance`가 CONSERVATIVE로 설정됨**
4. **`max_position_size`가 0.01 (1%)로 매우 작음**
5. **`balance_utilization`이 0.10 (10%)로 제한됨**

**가장 효과적인 조정:**
- `user_signal_threshold`를 **60~70점**으로 낮추기
- `risk_tolerance`를 **MODERATE**로 변경
- `max_position_size`를 **0.02~0.03 (2~3%)**로 증가

이러한 조정을 통해 거래 빈도가 크게 증가할 것으로 예상됩니다.

---

## 📅 작성일

2025-01-27

---

## 🔄 설정 변경 이력 및 되돌리기 가이드

### 원본 설정값 (보수적 모드)

**변경 전 원본 값 (2025-01-27 기준):**

| 설정 항목 | 원본 값 | 파일 위치 |
|---------|--------|----------|
| `analyzer_settings.user_signal_threshold` | **80** | `data/nwsoft/config/settings.json` (Line 222) |
| `analyzer_settings.user_signal_threshold` | **85** | `config/settings_template.json` (Line 303) |
| `analyzer_settings.user_signal_threshold` | **85** | `config/settings.py` (Line 558) |
| `ai_trading_preferences.risk_tolerance` | **CONSERVATIVE** | `data/nwsoft/config/settings.json` (Line 288) |
| `ai_trading_preferences.risk_tolerance` | **CONSERVATIVE** | `config/settings_template.json` (Line 369) |
| `ai_trading_preferences.risk_tolerance` | **CONSERVATIVE** | `config/settings.py` (Line 626) |
| `ai_trading_preferences.balance_utilization_limit` | **0.15** | `data/nwsoft/config/settings.json` (Line 289) |
| `ai_trading_preferences.balance_utilization_limit` | **0.15** | `config/settings_template.json` (Line 370) |
| `ai_trading_preferences.balance_utilization_limit` | **0.15** | `config/settings.py` (Line 627) |
| `ai_trading_preferences.risk_levels.conservative.balance_utilization` | **0.10** | `data/nwsoft/config/settings.json` (Line 294) |
| `ai_trading_preferences.risk_levels.conservative.balance_utilization` | **0.10** | `config/settings_template.json` (Line 375) |
| `ai_trading_preferences.risk_levels.conservative.balance_utilization` | **0.10** | `config/settings.py` (Line 632) |
| `exchange_risk_overrides.binance.max_position_size` | **0.01** | `data/nwsoft/config/settings.json` (Line 403) |
| `exchange_risk_overrides.binance.max_position_size` | **0.01** | `config/settings_template.json` (Line 438) |
| `exchange_risk_overrides.binance.max_position_size` | **0.01** | `config/settings.py` (Line 650) |

---

### 테스트용 설정값 (2025-01-27 변경)

**거래 테스트를 위해 완화된 값:**

| 설정 항목 | 테스트 값 | 변경 내용 | 목적 |
|---------|---------|----------|------|
| `analyzer_settings.user_signal_threshold` | **68** | 80 → 68 (-12점) | 실제 시그널이 발생하고 분석이 잘된 거래 허용 |
| `ai_trading_preferences.risk_tolerance` | **MODERATE** | CONSERVATIVE → MODERATE | 중간 수준의 리스크 허용 |
| `ai_trading_preferences.balance_utilization_limit` | **0.20** | 0.15 → 0.20 (+0.05) | 잔고 사용 비율 약간 증가 |
| `ai_trading_preferences.risk_levels.conservative.balance_utilization` | **0.12** | 0.10 → 0.12 (+0.02) | 보수적 모드에서도 약간 완화 |
| `exchange_risk_overrides.binance.max_position_size` | **0.02** | 0.01 → 0.02 (2배) | 포지션 크기 제한 완화 |

**조정 원칙:**
- 무분별한 거래 방지: `user_signal_threshold`를 68점으로 설정하여 실제 분석이 잘된 거래만 허용
- 적절한 리스크 관리: MODERATE 모드로 전환하되 과도하지 않게 조정
- 점진적 완화: 각 값들을 크게 변경하지 않고 적절히 완화

---

### 되돌리기 가이드

**원본 보수적 설정으로 되돌리려면 다음 값들을 복원하세요:**

#### 1. `data/nwsoft/config/settings.json` 수정

```json
{
  "analyzer_settings": {
    "user_signal_threshold": 80  // 68 → 80
  },
  "ai_trading_preferences": {
    "risk_tolerance": "CONSERVATIVE",  // "MODERATE" → "CONSERVATIVE"
    "balance_utilization_limit": 0.15,  // 0.20 → 0.15
    "risk_levels": {
      "conservative": {
        "balance_utilization": 0.10  // 0.12 → 0.10
      }
    }
  },
  "exchange_risk_overrides": {
    "binance": {
      "max_position_size": 0.01  // 0.02 → 0.01
    }
  }
}
```

#### 2. `config/settings_template.json` 수정

```json
{
  "analyzer_settings": {
    "user_signal_threshold": 85  // 68 → 85
  },
  "ai_trading_preferences": {
    "risk_tolerance": "CONSERVATIVE",  // "MODERATE" → "CONSERVATIVE"
    "balance_utilization_limit": 0.15,  // 0.20 → 0.15
    "risk_levels": {
      "conservative": {
        "balance_utilization": 0.10  // 0.12 → 0.10
      }
    }
  },
  "exchange_risk_overrides": {
    "binance": {
      "max_position_size": 0.01  // 0.02 → 0.01
    }
  }
}
```

#### 3. `config/settings.py` 수정

```python
'analyzer_settings': {
    'user_signal_threshold': 85,  # 68 → 85
    # ...
},
'ai_trading_preferences': {
    'risk_tolerance': 'CONSERVATIVE',  # 'MODERATE' → 'CONSERVATIVE'
    'balance_utilization_limit': 0.15,  # 0.20 → 0.15
    'risk_levels': {
        'conservative': {
            'balance_utilization': 0.10,  # 0.12 → 0.10
            # ...
        }
    }
},
# ...
'exchange_risk_overrides': {
    'binance': {
        'max_position_size': 0.01,  # 0.02 → 0.01
        # ...
    }
}
```

**주의사항:**
- 설정 변경 후 애플리케이션 재시작 필요
- 빌드 시 `settings_template.json`과 `settings.py`의 값이 새 사용자에게 적용됨
- 기존 사용자는 `data/nwsoft/config/settings.json`의 값이 우선 적용됨

---

### 변경 사항 요약

**변경일:** 2025-01-27  
**목적:** 거래 테스트를 위한 적절한 완화 (무분별한 거래 방지)  
**변경 파일:**
1. `data/nwsoft/config/settings.json`
2. `config/settings_template.json`
3. `config/settings.py`

**변경 내용:**
- AI 신호 임계값: 80 → 68 (실제 분석이 잘된 거래 허용)
- 리스크 허용 수준: CONSERVATIVE → MODERATE
- 잔고 사용 비율: 0.15 → 0.20
- 포지션 크기: 0.01 → 0.02

