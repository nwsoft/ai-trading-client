# 코인 선택 테스트 구현 완료 (이력 보관)

## 📋 작업 요약

API 키 없이도 **코인 선택 로직을 테스트**할 수 있는 완전한 테스트 스크립트를 구현했습니다.

---

## ✨ 제공되는 도구

### 1. 간단 버전 (기본 권장)
**파일**: `scripts/test_coin_selection_full.py`  
**실행**: `python scripts/test_coin_selection_full.py`

**특징**:
- ✅ API 키 불필요
- ✅ 거래소 연결 불필요  
- ✅ 빠른 실행 (< 1초)
- ✅ 100% 안정적
- ✅ 사전 정의된 코인 풀에서 선택

**거래소 지원**: Binance, Bitget, Bybit, OKX, Upbit, Bithumb

### 2. 고급 버전 (Evaluator 포함)
**파일**: `scripts/test_coin_selection_full.py --evaluator`  
**실행**: `python scripts/test_coin_selection_full.py --evaluator`

**특징**:
- ✅ 실제 Evaluator 모듈 사용
- ✅ 시장 분석 기반 선택
- ✅ 실제 거래 로직과 동일
- ✅ 고도화된 선택 기준 적용
- ⚠️ 약간 더 복잡한 초기화

---

## 🚀 빠른 시작

### 기본 사용법

```bash
# Binance 코인 선택 테스트
python scripts/test_coin_selection_full.py

# Bitget 테스트
python scripts/test_coin_selection_full.py --exchange bitget

# 커스텀 수량 (주요 10개, 알트 20개)
python scripts/test_coin_selection_full.py --major 10 --alt 20
```

### 고급 사용법

```bash
# 실제 Evaluator로 테스트
python scripts/test_coin_selection_full.py --evaluator

# OKX 거래소 + Evaluator + 커스텀 수량
python scripts/test_coin_selection_full.py --evaluator --exchange okx --major 5 --alt 15
```

---

## 📊 테스트 결과 확인

### 콘솔 출력 예시

```
================================================================================
📊 코인 선택 로직 테스트 (간단 버전)
================================================================================
🏦 거래소: BINANCE
🎯 주요 코인: 5개, 알트 코인: 15개

🟡 주요 코인 (5개):
   1. BTCUSDT
   2. ETHUSDT
   3. BNBUSDT
   4. XRPUSDT
   5. ADAUSDT

🔵 알트 코인 (15개):
   1. SOLUSDT
   2. AVAXUSDT
   ... (생략)

💾 결과 저장: data/test_coin_selection_simple.json
```

### JSON 결과 파일

**간단 버전**: `data/test_coin_selection_simple.json`
```json
{
  "exchange": "binance",
  "num_major": 5,
  "num_alt": 15,
  "major_coins": ["BTCUSDT", "ETHUSDT", "BNBUSDT", ...],
  "alt_coins": ["SOLUSDT", "AVAXUSDT", ...],
  "total_coins": 20
}
```

**Evaluator 버전**: `data/test_coin_selection_full.json`
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

## 🔗 실제 거래 연결

### Paper Trading으로 시뮬레이션

1. **코인 선택 테스트** ✅
   ```bash
   python scripts/test_coin_selection_full.py
   ```

2. **Paper Trading 활성화**
   ```json
   // data/settings.json
   {
     "paper_trading": true,
     "selected_coins": [결과에서 선택한 코인들]
   }
   ```

3. **대시보드 실행** (실제 자금 없이 테스트)
   ```bash
   python main.py
   ```

4. **거래 결과 확인**
   - 대시보드 실시간 통계
   - 로그: `data/nwsoft/logs/trading_{exchange}.log`
   - DB: `data/nwsoft/trading.db`

---

## 📁 파일 구조

```
noahai_client/
├── scripts/
│   ├── test_coin_selection_full.py      ← 메인 테스트 스크립트
│   └── test_coin_selection.py           ← 이전 버전 (참고용)
├── data/
│   ├── settings.json                    ← 사용자 설정
│   ├── test_coin_selection_simple.json  ← 테스트 결과 (간단 버전)
│   ├── test_coin_selection_full.json    ← 테스트 결과 (Evaluator 버전)
│   └── nwsoft/
│       ├── logs/
│       │   ├── trading_binance.log
│       │   ├── trading_bitget.log
│       │   └── trading_{exchange}.log
│       └── trading.db                   ← 거래 데이터베이스
├── docs/
│   └── COIN_SELECTION_TEST.md           ← 상세 가이드
├── trading/
│   ├── evaluator.py                     ← 코인 선택 로직
│   ├── analyzer.py                      ← 시장 분석
│   └── recorder.py                      ← 거래 기록
└── config/
    └── settings.py                      ← 설정 스키마
```

---

## 🎯 사용 시나리오

### 시나리오 1: 빠른 테스트 (추천)
```bash
# 30초 이내 완료
python scripts/test_coin_selection_full.py --exchange binance
# → data/test_coin_selection_simple.json 확인
```

### 시나리오 2: 거래소별 비교
```bash
# 각 거래소의 코인 풀 비교
python scripts/test_coin_selection_full.py --exchange binance
python scripts/test_coin_selection_full.py --exchange bitget
python scripts/test_coin_selection_full.py --exchange bybit

# → 결과를 비교하여 최적 거래소 선택
```

### 시나리오 3: 상세 분석 (Evaluator 포함)
```bash
# 실제 거래 전 Evaluator 로직 검증
python scripts/test_coin_selection_full.py --evaluator --exchange binance

# → 상세 분석 결과로 실제 거래 결정
```

### 시나리오 4: Paper Trading 완전 테스트
```bash
# 1단계: 코인 선택
python scripts/test_coin_selection_full.py --exchange binance

# 2단계: 설정에서 Paper Trading 활성화
# data/settings.json 에서 "paper_trading": true

# 3단계: 대시보드 실행
python main.py

# 4단계: 로그 및 DB에서 결과 확인
tail -f data/nwsoft/logs/trading_binance.log
```

---

## ✅ 완성된 기능 목록

- ✅ 간단한 코인 선택 테스트 (API 키 불필요)
- ✅ 실제 Evaluator 모듈 통합 테스트
- ✅ 4개 거래소 지원 (Binance, Bitget, Bybit, OKX)
- ✅ 커스텀 수량 선택 가능
- ✅ JSON 형식 결과 저장
- ✅ 상세 콘솔 출력
- ✅ 에러 처리 및 폴백
- ✅ 전체 사용 설명서 제공

---

## 📚 관련 문서

- [📘 전체 가이드](./COIN_SELECTION_TEST.md)
- [🎯 거래 시작 가이드](./ACCOUNT_MANAGEMENT.md)
- [🔧 설정 가이드](../config/settings_template.json)
- [📊 AI 거래 전략](./AI_API_ARCHITECTURE.md)

---

## 🆘 문제 해결

| 문제 | 해결책 |
|------|--------|
| "Evaluator 초기화 실패" | 간단 버전 사용: `python scripts/test_coin_selection_full.py` |
| "코인 선택 0개" | 지원 거래소 확인: binance, bitget, bybit, okx |
| "JSON 파일 없음" | `mkdir -p data` 실행 |
| "Import 오류" | `.venv` 활성화: `source .venv/bin/activate` |

---

## 🎓 다음 단계

1. ✅ **코인 선택 테스트** (현재)
2. 📊 **Paper Trading 시뮬레이션** (다음)
3. 🚀 **실제 거래 활성화** (최종)

```bash
# Paper Trading 활성화 예시
python scripts/test_coin_selection_full.py  # 코인 선택
# → data/settings.json에서 "paper_trading": true
python main.py  # 거래 시뮬레이션
```

---

## 📞 지원

문제 발생 시:
1. 콘솔 출력 메시지 확인
2. `docs/COIN_SELECTION_TEST.md` 참고
3. 로그 파일 확인: `data/nwsoft/logs/`
4. JSON 결과 파일 검증: `data/test_coin_selection_*.json`
