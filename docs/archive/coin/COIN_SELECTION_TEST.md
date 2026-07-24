# 코인 선택 로직 테스트 가이드 (이력 보관)

## 개요

API 키 없이도 **코인 선택 로직**을 테스트할 수 있는 2가지 스크립트를 제공합니다.

- **`test_coin_selection_full.py`** (기본) - 빠르고 안정적한 간단 버전
- **`test_coin_selection_full.py --evaluator`** - 실제 Evaluator 모듈을 사용한 고급 버전

---

## 실행 방법

### 1. 기본 테스트 (권장)

```bash
# Binance (기본값)
python scripts/test_coin_selection_full.py

# 다른 거래소 테스트
python scripts/test_coin_selection_full.py --exchange bitget
python scripts/test_coin_selection_full.py --exchange bybit
python scripts/test_coin_selection_full.py --exchange okx
```

### 2. 고급 테스트 (Evaluator 포함)

```bash
# 실제 Evaluator 로직으로 코인 선택
python scripts/test_coin_selection_full.py --evaluator

# 다른 거래소 + Evaluator
python scripts/test_coin_selection_full.py --evaluator --exchange bitget
```

### 3. 커스텀 수량 지정

```bash
# 주요 코인 10개, 알트 코인 20개
python scripts/test_coin_selection_full.py --major 10 --alt 20

# Evaluator 사용 + 커스텀 수량
python scripts/test_coin_selection_full.py --evaluator --major 10 --alt 20
```

---

## 출력 예시

### 간단 버전 (기본)

```
================================================================================
📊 코인 선택 로직 테스트 (간단 버전)
================================================================================
🏦 거래소: BINANCE
🎯 주요 코인: 5개, 알트 코인: 15개
--------------------------------------------------------------------------------
✅ 설정 파일 로드 완료

🎲 코인 선택 완료:
   주요 코인 수: 5
   알트 코인 수: 15
   총 코인 수: 20

🟡 주요 코인 (5개):
   1. BTCUSDT
   2. ETHUSDT
   3. BNBUSDT
   4. XRPUSDT
   5. ADAUSDT

🔵 알트 코인 (15개):
   1. SOLUSDT
   2. AVAXUSDT
   3. DOTUSDT
   4. LINKUSDT
   ... (생략)

💾 결과 저장: /Users/playone/SynologyDrive/Works/noahai_client/data/test_coin_selection_simple.json
```

### Evaluator 버전 (고급)

```
================================================================================
📊 코인 선택 로직 테스트 (Evaluator 포함)
================================================================================
🏦 거래소: BINANCE
🎯 주요 코인: 5개, 알트 코인: 15개
--------------------------------------------------------------------------------
✅ 설정 파일 로드 완료
✅ 핵심 모듈 초기화 중...
✅ Analyzer 준비 완료
✅ Recorder 준비 완료
✅ Evaluator 준비 완료

🎲 코인 선택 중...
✅ 선택 완료: 10개 코인
   1. BTCUSDT
   2. ETHUSDT
   3. BNBUSDT
   4. SOLUSDT
   5. ADAUSDT
   6. XRPUSDT
   7. DOTUSDT
   8. LINKUSDT
   9. AVAXUSDT
   10. MATICUSDT

💾 결과 저장: /Users/playone/SynologyDrive/Works/noahai_client/data/test_coin_selection_full.json
```

---

## 결과 파일

테스트 완료 후 JSON 파일에 상세 결과가 저장됩니다.

### 파일 위치

- **간단 버전**: `data/test_coin_selection_simple.json`
- **Evaluator 버전**: `data/test_coin_selection_full.json`

### JSON 포맷 (간단 버전)

```json
{
  "exchange": "binance",
  "num_major": 5,
  "num_alt": 15,
  "major_coins": ["BTCUSDT", "ETHUSDT", "BNBUSDT", ...],
  "alt_coins": ["SOLUSDT", "AVAXUSDT", "DOTUSDT", ...],
  "total_coins": 20
}
```

### JSON 포맷 (Evaluator 버전)

```json
{
  "exchange": "binance",
  "total_coins": 10,
  "coins": [
    {"symbol": "BTCUSDT"},
    {"symbol": "ETHUSDT"},
    ...
  ]
}
```

---

## 거래소별 지원 코인

각 거래소에 대해 주요 코인과 알트 코인 풀이 사전에 정의되어 있습니다.

### Binance
- **주요**: BTC, ETH, BNB, XRP, ADA
- **알트**: SOL, AVAX, DOT, LINK, UNI, ARB, OP, APT, MATIC, ...

### Bitget
- **주요**: BTC, ETH, SOL, ARB, OP
- **알트**: ETH, AVAX, FTM, DOGE, APE, SAND, GALA, ...

### Bybit
- **주요**: BTC, ETH, SOL, XRP, DOGE
- **알트**: AVAX, FTM, INJ, SUI, APE, LINK, ...

### OKX
- **주요**: BTC, ETH, LTC, ETC, XLM
- **알트**: SOL, FTM, ATOM, AVAX, LINK, ...

---

## 실제 거래 흐름과의 연결

### 테스트 → 실제 거래

1. **테스트 스크립트로 코인 선택 검증**
   ```bash
   python scripts/test_coin_selection_full.py --evaluator
   ```

2. **Paper Trading 모드 활성화** (실제 자금 없이 테스트)
   ```json
   // data/settings.json
   {
     "paper_trading": true,
     "selected_coins": ["BTCUSDT", "ETHUSDT", ...]
   }
   ```

3. **대시보드에서 거래 시뮬레이션**
   ```bash
   python main.py
   // → 로그인 → Dashboard 실행 → Paper Trading 자동 활성화
   ```

4. **거래 결과 확인**
   - 로그: `data/nwsoft/logs/trading_{exchange}.log`
   - 데이터베이스: `data/nwsoft/trading.db`
   - 대시보드: 실시간 거래 통계 표시

---

## 문제 해결

### "Evaluator 초기화 실패" 메시지

**원인**: Analyzer의 binance_client가 None인 경우  
**해결**: 간단 버전 사용 (기본값) - API 키 불필요

```bash
python scripts/test_coin_selection_full.py
```

### "코인 선택 0개"

**원인**: 거래소 풀에 코인 없음  
**해결**: 지원되는 거래소 사용 (binance/bitget/bybit/okx)

```bash
python scripts/test_coin_selection_full.py --exchange binance
```

### JSON 파일이 생성되지 않음

**원인**: `data/` 디렉토리 권한 문제  
**해결**: 디렉토리 생성 권한 확인

```bash
mkdir -p data
```

---

## 스크립트 상세 설명

### `test_coin_selection_full.py` 주요 함수

#### 1. `test_coin_selection_simple()`
- **목적**: 거래소별 사전 정의된 코인 풀에서 선택
- **장점**: 빠름, 안정적, API 키 불필요
- **사용**: 기본 테스트, 빠른 검증

#### 2. `test_coin_selection_with_evaluator()`
- **목적**: 실제 Evaluator 모듈로 시장 분석 후 선택
- **장점**: 실제 거래 로직과 동일, 고도화된 선택
- **사용**: 상세 분석, 실제 거래 전 검증

---

## 관련 파일

- **테스트 스크립트**: [`scripts/test_coin_selection_full.py`](../scripts/test_coin_selection_full.py)
- **이전 버전**: [`scripts/test_coin_selection.py`](../scripts/test_coin_selection.py) (간단 버전)
- **Evaluator**: [`trading/evaluator.py`](../trading/evaluator.py) (코인 선택 로직)
- **설정**: [`config/settings.py`](../config/settings.py) (설정 구조)
- **기본 설정**: [`data/settings.json`](../data/settings.json) (사용자 설정)

---

## 다음 단계

1. ✅ **코인 선택 테스트** ← 현재 여기
2. 📊 **Paper Trading 활성화** (`data/settings.json`에서 `"paper_trading": true`)
3. 🚀 **대시보드에서 거래 시뮬레이션** (`python main.py`)
4. 📈 **거래 결과 분석** (로그 및 DB 확인)
5. 💰 **실제 거래 활성화** (`"paper_trading": false`)

---

## 도움말

```bash
# 전체 옵션 보기
python scripts/test_coin_selection_full.py --help

# 출력 예시
usage: test_coin_selection_full.py [-h] [--exchange {binance,bitget,bybit,okx,upbit,bithumb}] [--major MAJOR] [--alt ALT] [--evaluator]

옵션:
  -h, --help            도움말 표시
  --exchange {binance,bitget,bybit,okx,upbit,bithumb}
                        거래소 선택 (기본: binance)
  --major MAJOR         주요 코인 개수 (기본: 5)
  --alt ALT             알트 코인 개수 (기본: 15)
  --evaluator           실제 Evaluator 모듈 사용
```
