# 주식/ETF 서비스 개발 가이드 (2026-01-18)

> [정합성 안내 - 2026-04-23]
> 이 문서는 초기 단계 개발 가이드(이력)입니다. 현재 완료/미완 상태와 우선순위는
> `docs/STOCK_ETF_CURRENT_STATUS_20260118.md`의 "최신 기준" 섹션과
> `docs/CHANGELOG.md` 최상단을 정본으로 우선 적용하세요.

## 📋 목표

"📈 주식/증권" 버튼을 클릭했을 때, 블록체인 서비스와 동일한 방식으로 하위 탭들이 표시되도록 구현합니다.

### 현재 구조 (블록체인)
```
🔗 블록체인 클릭
├─ 기본 탭들 (항상 유지)
│  ├─ 📊 실시간 거래 로그
│  ├─ 🪙 코인 정보
│  ├─ 📈 거래 통계
│  ├─ 📈 시장 트렌드
│  ├─ 📚 AI 학습
│  ├─ 📊 AI 리포트
│  ├─ 💬 AI 어시스턴트
│  └─ 👥 커뮤니티
└─ 거래소별 탭 (동적 생성)
   ├─ 🏦 BINANCE
   ├─ 🏦 UPBIT
   └─ 🏦 OKX
```

### 목표 구조 (주식/증권)
```
📈 주식/증권 클릭
├─ 기본 탭들 (항상 유지 - 블록체인과 동일)
│  ├─ 📊 실시간 거래 로그 (주식 거래 로그 필터링)
│  ├─ 🪙 종목 정보 (코인 정보 → 종목 정보)
│  ├─ 📈 거래 통계 (주식 거래 통계 필터링)
│  ├─ 📈 시장 트렌드 (주식 시장 트렌드)
│  ├─ 📚 AI 학습 (주식 학습 데이터)
│  ├─ 📊 AI 리포트 (주식 리포트)
│  ├─ 💬 AI 어시스턴트
│  └─ 👥 커뮤니티
└─ 증권사별 탭 (동적 생성)
   ├─ 🏦 키움증권 (주식/ETF 포함)
   ├─ 🏦 이베스트증권
   └─ 🏦 NH투자증권
```

## 🎯 개발 단계

### 1단계: 설정 구조 추가

#### 1.1 `settings.json` 구조 확장
**파일**: `config/settings_template.json`, `config/settings.py`

**추가할 설정:**
```json
{
  "enabled_stock_brokers": ["kiwoom"],
  "stock_broker_configs": {
    "kiwoom": {
      "enabled": true,
      "api_type": "openapi",  // 또는 "dart"
      "account_no": "",
      "password": "",
      "asset_types": ["stock", "etf"],  // 지원 자산 종류
      "cert_password": "",  // 공인인증서 비밀번호 (필요시)
      "id": ""  // 계정 ID (필요시)
    }
  }
}
```

**작업:**
- [ ] `config/settings_template.json`에 `enabled_stock_brokers`, `stock_broker_configs` 추가
- [ ] `config/settings.py`에 설정 로드/저장 로직 추가

---

### 2단계: UI - `show_stock_content()` 구현

#### 2.1 메서드 구현
**파일**: `ui/dashboard_modern.py`

**위치**: `update_service_content()` 메서드 근처 (라인 3292-3312)

**구현 내용:**
```python
def show_stock_content(self):
    """주식/증권 서비스 콘텐츠 표시"""
    try:
        self.logger.info("주식/증권 서비스 콘텐츠 표시")
        # 기본 탭들은 이미 생성되어 있으므로, 필터링만 적용
        # 증권사별 탭은 create_service_sub_tabs()에서 생성됨
    except Exception as e:
        self.logger.error(f"주식/증권 콘텐츠 표시 오류: {e}")
```

**작업:**
- [ ] `show_stock_content()` 메서드 추가 (라인 3300 근처)
- [ ] 기본 동작 구현 (블록체인과 유사하지만 로그만)

---

### 3단계: UI - `create_service_sub_tabs()` 확장

#### 3.1 `stock` 서비스 케이스 추가
**파일**: `ui/dashboard_modern.py`

**위치**: `create_service_sub_tabs()` 메서드 (라인 3719)

**현재 코드:**
```python
def create_service_sub_tabs(self, service_name: str):
    if service_name == 'blockchain':
        # 블록체인 거래소 탭 생성
        ...
```

**추가할 코드:**
```python
def create_service_sub_tabs(self, service_name: str):
    if service_name == 'blockchain':
        # 기존 블록체인 로직
        ...
    elif service_name == 'stock':
        # 설정에서 활성화된 증권사만 탭 생성
        enabled_brokers = self.settings.get('enabled_stock_brokers', ['kiwoom'])
        for broker in enabled_brokers:
            tab_label = f"🏦 {broker.upper()}"
            try:
                tab = self._get_or_add_tab(tab_label)
                self._clear_tab_children(tab)
                self.service_sub_tabs['stock'][tab_label] = tab
                
                # 레이아웃 컨테이너
                container = ctk.CTkFrame(tab, fg_color="#0b1120")
                container.pack(fill="both", expand=True, padx=10, pady=10)
                
                # 좌/우 2단 레이아웃
                root_split = ctk.CTkFrame(container, fg_color="#0b1120")
                root_split.pack(fill="both", expand=True)
                
                left_pane = ctk.CTkFrame(root_split, width=420, fg_color="#0b1120")
                left_pane.pack(side="left", fill="y", padx=(0, 10))
                
                # 1) 제어 섹션
                control_frame = self._create_card_frame(left_pane)
                control_frame.pack(fill="x", pady=(0, 10))
                self.create_broker_control_section(control_frame, broker)
                
                # 2) 잔고 섹션
                balance_frame = self._create_card_frame(left_pane)
                balance_frame.pack(fill="x", pady=(0, 10))
                self.create_broker_balance_section(balance_frame, broker)
                
                # 3) 포지션 섹션 (주식/ETF)
                positions_frame = self._create_card_frame(left_pane)
                positions_frame.pack(fill="both", expand=True, pady=(0, 10))
                self.create_broker_positions_section(positions_frame, broker)
                
                # 4) 거래 통계 섹션
                stats_frame = self._create_card_frame(left_pane)
                stats_frame.pack(fill="x")
                self.create_broker_stats_section(stats_frame, broker)
                
                # 오른쪽: 실시간 로그
                right_pane = ctk.CTkFrame(root_split, fg_color="#0b1120")
                right_pane.pack(side="left", fill="both", expand=True)
                self.create_broker_logs_section(right_pane, broker)
                
            except Exception as e:
                self.logger.error(f"증권사 탭 생성 실패: {broker} - {e}")
```

**작업:**
- [ ] `create_service_sub_tabs()`에 `elif service_name == 'stock':` 케이스 추가
- [ ] 블록체인 구조를 참고하여 증권사별 탭 생성 로직 작성

---

### 4단계: UI - 증권사별 섹션 메서드 구현

#### 4.1 제어 섹션
**파일**: `ui/dashboard_modern.py`

**메서드**: `create_broker_control_section(parent, broker: str)`

**구현 내용:**
- 시작/정지 버튼
- 증권사 연결 상태 표시
- 자산 종류 필터 (주식/ETF 체크박스)
- 계좌 선택 (여러 계좌 지원 시)

**참고**: `create_exchange_control_section()` 구조 참고

**작업:**
- [ ] `create_broker_control_section()` 메서드 추가
- [ ] 시작/정지 버튼 구현
- [ ] 자산 종류 필터 (주식/ETF) 추가

#### 4.2 잔고 섹션
**파일**: `ui/dashboard_modern.py`

**메서드**: `create_broker_balance_section(parent, broker: str)`

**구현 내용:**
- 현금 잔고 표시
- 주식 평가액 표시
- ETF 평가액 표시
- 총 자산 표시

**참고**: `create_exchange_balance_section()` 구조 참고

**작업:**
- [ ] `create_broker_balance_section()` 메서드 추가
- [ ] 잔고 표시 로직 구현

#### 4.3 포지션 섹션
**파일**: `ui/dashboard_modern.py`

**메서드**: `create_broker_positions_section(parent, broker: str)`

**구현 내용:**
- 보유 종목 리스트 (주식/ETF 구분 표시)
- 종목명, 수량, 평균 단가, 현재가, 평가 손익
- 자산 종류 필터 적용

**참고**: `create_exchange_positions_section()` 구조 참고

**작업:**
- [ ] `create_broker_positions_section()` 메서드 추가
- [ ] 포지션 표시 로직 구현
- [ ] 주식/ETF 구분 표시

#### 4.4 거래 통계 섹션
**파일**: `ui/dashboard_modern.py`

**메서드**: `create_broker_stats_section(parent, broker: str)`

**구현 내용:**
- 총 거래 횟수
- 승률
- 총 수익률
- 평균 수익률

**참고**: `create_exchange_stats_section()` 구조 참고

**작업:**
- [ ] `create_broker_stats_section()` 메서드 추가
- [ ] 통계 표시 로직 구현

#### 4.5 로그 섹션
**파일**: `ui/dashboard_modern.py`

**메서드**: `create_broker_logs_section(parent, broker: str)`

**구현 내용:**
- 증권사별 실시간 거래 로그
- 필터링 (자산 종류, 심볼 등)

**참고**: `create_exchange_logs_section()` 구조 참고

**작업:**
- [ ] `create_broker_logs_section()` 메서드 추가
- [ ] 로그 표시 로직 구현

---

### 5단계: 기본 탭 필터링 로직

#### 5.1 실시간 거래 로그 탭 필터링
**파일**: `ui/dashboard_modern.py` 또는 로그 위젯 파일

**작업:**
- [ ] 현재 서비스가 'stock'일 때 자동으로 주식/ETF 로그만 필터링
- [ ] `current_service` 변수 활용

#### 5.2 종목 정보 탭
**파일**: 코인 정보 위젯 또는 새로 생성

**작업:**
- [ ] "🪙 코인 정보" 탭의 내용을 주식/ETF 정보로 변경
- [ ] 또는 별도 위젯 생성

#### 5.3 거래 통계/시장 트렌드/AI 학습/AI 리포트
**파일**: 각각의 위젯 파일

**작업:**
- [ ] 현재 서비스가 'stock'일 때 자동으로 주식/ETF 데이터만 표시
- [ ] 필터링 로직 추가

---

### 6단계: 증권사 어댑터 구조 준비 (향후 확장)

#### 6.1 어댑터 인터페이스
**파일**: `trading/exchanges/base_exchange.py` 확장 또는 새 파일

**작업:**
- [ ] 주식/ETF 거래를 위한 인터페이스 정의 (선택사항, 향후 확장용)
- [ ] 키움증권 OpenAPI 연동을 위한 기본 구조

#### 6.2 어댑터 생성 (선택사항)
**파일**: `trading/exchanges/adapters/kiwoom_adapter.py` (향후 생성)

**작업:**
- [ ] 키움증권 OpenAPI 연동 어댑터 (향후 구현)
- [ ] 현재는 UI 구조만 준비

---

## 📝 구현 체크리스트

### 필수 작업
- [ ] **1단계**: 설정 구조 추가 (`settings.json`, `settings.py`)
- [ ] **2단계**: `show_stock_content()` 메서드 구현
- [ ] **3단계**: `create_service_sub_tabs()`에 `stock` 케이스 추가
- [ ] **4.1**: `create_broker_control_section()` 구현
- [ ] **4.2**: `create_broker_balance_section()` 구현
- [ ] **4.3**: `create_broker_positions_section()` 구현
- [ ] **4.4**: `create_broker_stats_section()` 구현
- [ ] **4.5**: `create_broker_logs_section()` 구현

### 선택 작업 (향후 확장)
- [ ] **5단계**: 기본 탭 필터링 로직 (현재는 기본 탭 내용 유지 가능)
- [ ] **6단계**: 실제 증권사 API 연동 (키움증권 어댑터 등)

---

## 🔍 참고 코드 위치

### 블록체인 구현 참고
1. **서비스 전환**: `switch_service()` - 라인 3243
2. **콘텐츠 업데이트**: `update_service_content()` - 라인 3292
3. **하위 탭 생성**: `create_service_sub_tabs()` - 라인 3719
4. **거래소 제어**: `create_exchange_control_section()` - 검색 필요
5. **거래소 잔고**: `create_exchange_balance_section()` - 라인 3679
6. **거래소 포지션**: `create_exchange_positions_section()` - 라인 3780
7. **거래소 통계**: `create_exchange_stats_section()` - 검색 필요
8. **거래소 로그**: `create_exchange_logs_section()` - 검색 필요

### 주요 메서드 패턴
- `_get_or_add_tab(tab_label)`: 탭 가져오기 또는 생성
- `_clear_tab_children(tab)`: 탭 내용 초기화
- `_create_card_frame(parent)`: 카드 스타일 프레임 생성
- `service_sub_tabs['stock'][tab_label] = tab`: 탭 레퍼런스 저장

---

## 🎨 UI 구성 예시

### 증권사별 탭 구조 (키움증권 예시)
```
┌─────────────────────────────────────────────────┐
│ 🏦 키움증권                                      │
├─────────────────────────────────────────────────┤
│ [좌측]                    │ [우측: 실시간 로그] │
│                          │                    │
│ ┌─ 제어 ─────────────┐   │                    │
│ │ [▶️ 시작] [⏹️ 정지] │   │                    │
│ │ 자산 종류: ☑️ 주식   │   │   로그 내용...    │
│ │           ☑️ ETF    │   │                    │
│ └────────────────────┘   │                    │
│                          │                    │
│ ┌─ 잔고 ─────────────┐   │                    │
│ │ 현금: 10,000,000원 │   │                    │
│ │ 주식: 5,000,000원  │   │                    │
│ │ ETF: 3,000,000원   │   │                    │
│ └────────────────────┘   │                    │
│                          │                    │
│ ┌─ 포지션 ───────────┐   │                    │
│ │ 삼성전자 (주식)     │   │                    │
│ │ TIGER 200 (ETF)   │   │                    │
│ └────────────────────┘   │                    │
│                          │                    │
│ ┌─ 통계 ─────────────┐   │                    │
│ │ 거래: 10회          │   │                    │
│ │ 승률: 70%          │   │                    │
│ └────────────────────┘   │                    │
└─────────────────────────────────────────────────┘
```

---

## ⚠️ 주의사항

1. **기본 탭 보호**: `_destroy_previous_service_tabs()` 메서드에서 기본 탭은 제거하지 않도록 확인
2. **탭 중복 방지**: `_get_or_add_tab()` 사용하여 탭 중복 생성 방지
3. **레퍼런스 관리**: `self.service_sub_tabs['stock'][tab_label]`에 탭 저장
4. **에러 처리**: 각 섹션 생성 시 try-except로 에러 처리
5. **블록체인 참고**: 거래소 탭 구조를 최대한 참고하여 일관성 유지

---

## 🚀 다음 단계 (향후)

1. **키움증권 OpenAPI 연동**: 실제 거래 실행을 위한 어댑터 구현
2. **주식/ETF 선택 로직**: AI가 주식/ETF를 선택하는 로직 구현
3. **실시간 모니터링**: 포지션 모니터링 및 자동 청산 로직
4. **백테스팅**: 주식/ETF 거래 백테스팅 기능
5. **리포트**: 주식/ETF 전용 리포트 생성

---

## 📅 개발 일정 (예상)

- **1-2단계**: 1일 (설정, 기본 구조)
- **3단계**: 2일 (하위 탭 생성)
- **4단계**: 3일 (각 섹션 구현)
- **5단계**: 1일 (필터링, 선택)
- **테스트**: 1일

**총 예상 기간**: 7-8일

---

## 📚 관련 문서

### 개발 가이드
- `docs/MASTER_DOCUMENTATION.md`: 전체 아키텍처
- `docs/ARCHITECTURE.md`: 거래소 시스템 구조
- `docs/EXCHANGE_SETUP.md`: 거래소 설정 가이드
- `docs/STOCK_ETF_ADDITION_GUIDE.md`: 증권/ETF 기술적 추가 가이드
- `docs/STOCK_ETF_CURRENT_STATUS_20260118.md`: 현재 개발 현황 및 다음 단계
- `docs/STOCK_ETF_UI_VERIFICATION_20260118.md`: UI 구조 검증 보고서
- `docs/AI_API_ARCHITECTURE.md`: **AI API 구조 및 오픈소스 전환 가이드** (필수 참고)

### 코드 참고
- `ui/dashboard_modern.py`: 대시보드 UI 구현
  - 라인 4081-4129: `create_service_sub_tabs('stock')` 구현 (이미 완료)
  - 라인 4353-4648: `create_broker_*` 메서드들 (이미 구현됨)
  - 라인 4651-4670: `show_stock_content()` 구현 (이미 완료)
- `trading/exchanges/interfaces/stock_exchange.py`: StockExchange 인터페이스 (이미 생성됨)
- `trading/exchanges/adapters/kiwoom_stock_adapter.py`: 키움증권 어댑터 (이미 생성됨)
- `trading/ai/ai_manager.py`: AI 분석 API 구조 참고
- `trading/ai/openai_client.py`: OpenAI 클라이언트 구조 참고 (오픈소스 전환 고려)

## ⚠️ 중요: AI API 구조 활용 및 오픈소스 전환 고려

### AI API 활용 가이드
**참고 문서**: `docs/AI_API_ARCHITECTURE.md`

**핵심 원칙**:
1. **AIManager 초기화**: 직접 초기화하지 않고 `main.py`에서 전달받음
2. **가드 체크 필수**: `if self.ai_manager and self.ai_manager.enabled()` 항상 사용
3. **에러 폴백**: AI 호출 실패 시 기본 분석으로 폴백
4. **오픈소스 전환 준비**: `base_url` 설정 지원으로 향후 전환 가능

**ETF 개발 시 AI 활용 예시**:
```python
# ETF 신호 생성 시
if self.ai_manager and self.ai_manager.enabled():
    ai_analysis = self.ai_manager.analyze_market_conditions(
        symbol=symbol,
        market_data=[...],
        indicators={...}
    )
    # AI 분석 결과 반영
else:
    # AI 비활성화 시 기본 분석만 사용
    pass
```

### 대시보드 UI 일관성 유지
**현재 상태**: 블록체인 서비스와 동일한 패턴으로 이미 구현됨
- ✅ `create_service_sub_tabs('stock')` 구현 완료
- ✅ `create_broker_*` 메서드들 구현 완료 (placeholder)
- ✅ 좌/우 2단 레이아웃 구조 유지
- ✅ 동일한 색상/폰트/위젯 구조 사용

**다음 단계**: 실제 데이터 로드 및 API 연동

---

## 🔄 다음 단계 (Phase 2: 데이터 입력 강화)

### 2026-04-23 설계 결정: 통합 방식 채택

**주요 결정**: 주식과 ETF를 단일 "stock" 서비스로 통합 관리

**근거**:
- 거래 방식, 데이터 구조, API가 동일
- 구현 기간 3-4일 (분리 방식은 2-3주)
- 산업 표준 (Bloomberg, 네이버 증권 등)

**세부 내용**: `docs/STOCK_ETF_ARCHITECTURE_DECISION_20260423.md` 참고

### Phase 2-1: AI 컨텍스트에 ETF 조건부 입력 추가

**목표**: AI가 주식과 ETF를 구분하여 분석

**파일**: `trading/ai_report_manager.py`

**작업**:
- [ ] `_get_current_trading_context()` 메서드 수정
- [ ] 포지션 루프에서 `is_etf(symbol)` 체크
- [ ] ETF 시에만 추적오차, 괴리율, 거래대금 입력
- [ ] AI 프롬프트에 "주식/ETF 구분" 명시

**구현 예시**:
```python
def _get_current_trading_context(self) -> str:
    context = ""
    for pos in self.current_positions:
        context += f"\n## {pos['name']} ({pos['code']})"
        if pos.get('is_etf', False):
            context += f"\n[ETF] 추적오차: {pos.get('tracking_error', 0):.3f}%"
        else:
            context += f"\n[주식] 기업 분석 중심"
    return context
```

**기간**: 1일

### Phase 2-2: ETF 판별 로직 강화

**파일**: `trading/exchanges/adapters/kiwoom_stock_adapter.py`

**작업**:
- [ ] `is_etf(code)` 메서드 구현 (패턴 매칭)
- [ ] 키움증권 ETF 코드 범위 정의
- [ ] 테스트 케이스 작성

**코드 범위** (한국거래소):
- 69500-69599: KODEX, KINDEX 등
- 102000-102999: 기타 ETF
- 111000-111999: 테마 ETF
- 122000-122999: 해외 ETF

**기간**: 0.5일

### Phase 2-3: 다중 증권사 팩토리 확장 (2주 후)

**목표**: 키움 외 신한, 미래에셋 등 추가

**파일**: `trading/exchanges/exchange_factory.py`

**작업**:
- [ ] 팩토리에 신한증권, 미래에셋 어댑터 등록
- [ ] 각 증권사별 어댑터 기본 구조 (placeholder)
- [ ] 설정 UI에 체크박스 추가

**구조**:
```python
def create_stock_exchange(provider: str) -> StockExchange:
    if provider == "kiwoom":
        return KiwoomStockAdapter()
    elif provider == "shinhan":
        return ShinhanStockAdapter()
    elif provider == "mirae":
        return MiraeAssetAdapter()
```

**기간**: 3-5일 (증권사별 1일)

### Phase 2-4: 실데이터 연동 (1개월 후)

**목표**: Kiwoom OpenAPI+ 실제 연동

**파일**: `trading/exchanges/adapters/kiwoom_stock_adapter.py`

**작업**:
- [ ] Kiwoom API 라이브러리 통합
- [ ] `get_stock_list()` 실제 구현
- [ ] `get_etf_list()` 실제 구현
- [ ] 포지션/잔고 자동 로드
- [ ] 거래 통계 계산

**기간**: 2-3주

---

## 📊 전체 로드맵

| Phase | 내용 | 기간 | 상태 |
|-------|------|------|------|
| Phase 1 | UI 골격, 설정, 컨텍스트 | 완료 ✅ | 완료 |
| **Phase 2-1** | **AI 컨텍스트 ETF 지표** | **1일** | 🔄 |
| **Phase 2-2** | **ETF 판별 로직** | **0.5일** | 🔄 |
| Phase 2-3 | 다중 증권사 확장 | 3-5일 | ⏳ (2주 후) |
| Phase 2-4 | Kiwoom 실데이터 연동 | 2-3주 | ⏳ (1개월 후) |
| Phase 3 | 고급 기능 (ETF 전용 탭 등) | 가변 | ⏳ (선택) |
