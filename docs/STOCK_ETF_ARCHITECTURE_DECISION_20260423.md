# 주식/ETF 통합 설계 결정 (2026-04-23)

## 📋 결정 사항

### 설계 방식: **통합 방식 (Integrated Service)**

**주식과 ETF를 단일 "stock" 서비스로 통합 관리**

---

## 🎯 설계 결정 근거

### 1. 기술적 근거

#### 같은 점
- **거래 방식**: 매수/매도, 포지션 관리 동일
- **데이터 구조**: 코드, 현재가, 거래량, 차트 모두 동일
- **API 구조**: 증권사 API에서 주식/ETF 모두 동일 엔드포인트 사용
- **UI 컴포넌트**: 주문창, 잔고, 포지션 표시 로직 공유 가능

#### 다른 점
- **구성**: 개별 종목 vs 바구니/인덱스 추종
- **분석 지표**: 추적오차, 괴리율 (ETF만 필요)
- **매매 심리**: 기업 분석 vs 자산배분

### 2. 개발 효율성

| 방식 | 구현 기간 | 코드 중복 | 관리 복잡도 |
|------|---------|---------|-----------|
| **통합** | 3-4일 | 0% | 낮음 |
| **분리** | 2-3주 | 40% | 높음 |

### 3. 산업 표준

- **Bloomberg**: 주식/ETF 통합 포지션 관리
- **네이버 증권**: 단일 "주식" 탭에서 주식/ETF 조회
- **키움 API**: 동일 조회 함수로 주식/ETF 처리

---

## 🏗️ 설계 구조

### 현재 설계

```
📈 주식/증권 서비스 (단일)
│
├─ 기본 탭들 (서비스별 필터링)
│  ├─ 📊 실시간 거래 로그
│  ├─ 🪙 종목 정보 (주식/ETF 통합)
│  ├─ 📈 거래 통계
│  ├─ 📊 AI 리포트
│  └─ 💬 AI 어시스턴트 ("주식/ETF" 컨텍스트)
│
└─ 증권사별 탭 (동적 생성)
   ├─ 🏦 키움증권 (주식/ETF 통합)
   ├─ 🏦 신한증권 (확장 시)
   └─ 🏦 미래에셋 (확장 시)
```

### AI 어시스턴트 컨텍스트

```python
"stock" 서비스:
  - 입력창: "주식/ETF 관련 질문..."
  - 퀵 질문: "ETF vs 주식", "ETF 후보", "추적오차" 등
  - 프롬프트: 주식과 ETF 모두 포함
  - **조건부 입력**: is_etf(symbol) 체크하여 ETF 전용 지표만 추가
```

### 데이터 모델

```json
단일 테이블 (stock_positions):
{
  "code": "005930",           // 주식 코드
  "is_etf": false,            // ETF 여부
  "name": "삼성전자",
  "quantity": 10,
  "entry_price": 75000,
  "current_price": 78000,
  
  // ETF 전용 (is_etf=true일 때만 의미 있음)
  "tracking_error": 0.05,     // 추적오차 %
  "nav_premium": 0.1,         // NAV 프리미엄 %
  "base_index": "KOSPI"       // 기초지수
}
```

---

## 📈 구현 로드맵

### Phase 1: 기본 설계 완료 ✅
- [x] 설정 UI (키움증권 입력)
- [x] 서비스 전환 로직
- [x] 증권사별 탭 UI 골격
- [x] AI 어시스턴트 컨텍스트 ("stock")
- [x] 메뉴얼 (ETF vs 주식 설명)

### Phase 2: 데이터 입력 강화 (다음 단계)
- [ ] AI 컨텍스트에 **조건부 ETF 지표** 추가
  - `_get_current_trading_context()`에서 `is_etf(symbol)` 체크
  - ETF 시 추적오차, 괴리율, 거래대금 입력
- [x] ETF 판별 로직 강화 (1차)
  - 테스트셋 기준 ETF 코드(예: `114800`) 판별 보완
- [ ] 증권사 로그에 ETF/주식 구분 표시

### Phase 3: 다중 증권사 확장 (2주 후)
- [x] 신한증권 어댑터 추가
- [x] 미래에셋 어댑터 추가
- [x] 팩토리 메서드 확장 (`api_type` 분기 포함)
- [x] 설정 UI 체크박스/입력 확장
- [x] 증권사별 `api_type`/`api_version` UI 저장/로드 반영

### Phase 4: 실데이터 연동 (1개월)
- [ ] Kiwoom OpenAPI+ 실제 연동
- [ ] 포지션 자동 로드
- [ ] 잔고 실시간 업데이트
- [ ] 거래 통계 계산

### Phase 5: 고급 기능 (우선순위 검토)
- [ ] **ETF 전용 탭 분리** (필요시 리팩토링)
  - 추적오차 모니터링
  - 리밸런싱 알림
  - 기초지수 비교 분석
- [ ] ETF 포트폴리오 최적화 (MVO)
- [ ] 자산배분 시뮬레이션

---

## 🛠️ 기술 디테일

### 조건부 입력 구현 예시

**파일**: `trading/ai_report_manager.py`

```python
def _get_current_trading_context(self) -> str:
    """AI에 제공할 현재 거래 컨텍스트"""
    context = ""
    
    for pos in self.current_positions:
        context += f"\n## {pos['name']} ({pos['code']})"
        context += f"\n수량: {pos['quantity']}, 진입가: {pos['entry_price']}"
        context += f"\n현재가: {pos['current_price']}, 수익률: {pos['profit_rate']:.2f}%"
        
        # ⭐ ETF 여부 체크하여 조건부 입력
        if pos.get('is_etf', False):
            context += f"\n[ETF 정보]"
            context += f"\n기초지수: {pos.get('base_index', 'N/A')}"
            context += f"\n추적오차: {pos.get('tracking_error', 0):.3f}%"
            context += f"\nNAV 괴리: {pos.get('nav_premium', 0):.2f}%"
        
    return context
```

### ETF 판별 로직

**파일**: `trading/exchanges/adapters/kiwoom_stock_adapter.py`

```python
def is_etf(self, code: str) -> bool:
    """종목코드로 ETF 여부 판별"""
    # ETF 코드 패턴 (한국거래소)
    self.etf_code_patterns = [
        (69500, 69599),   # KODEX, KINDEX 등
        (102000, 102999), # 기타 ETF
        (111000, 111999), # 테마 ETF
        (122000, 122999), # 해외 ETF
    ]
    
    try:
        code_int = int(code)
        for start, end in self.etf_code_patterns:
            if start <= code_int <= end:
                return True
        return False
    except (ValueError, TypeError):
        return False
```

---

## 📊 향후 분리 옵션

**현재 통합 설계에서도 분리는 언제든 가능합니다:**

만약 ETF 고유 기능(리밸런싱, 리스크 모니터링 등)이 필요해지면:

1. `StockExchange` 인터페이스는 이미 `get_etf_list()` 분리 상태 ✅
2. UI 단계에서만 "stock" → "stock", "etf" 분리 필요
3. AI 컨텍스트 분리 필요
4. 하지만 **기본 데이터 로드/저장은 그대로 사용 가능**

---

## 🎓 결론

### 지금 (통합)
- ✅ 빠른 구현 (3-4일)
- ✅ 코드 간결
- ✅ 유지보수 용이
- ✅ ETF 조건부 기능도 충분히 지원

### 향후 (필요시 분리)
- 🔄 기초가 단단하면 리팩토링 쉬움
- 🔄 ETF 전용 고급 기능 필요 시에만 진행

**권장**: 통합으로 시작 → 실데이터 연동 완성 → 필요시 분리 리팩토링
