# 개발자 가이드 (회귀 방지 규칙)

> 기준: 2026-07-24 · v3.9.0.1  
> 금융 인텔리전스의 메뉴·데이터·상태 모델은 `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`, 검증은 `FINANCIAL_INTELLIGENCE_TEST_CHECKLIST_20260723.md`를 따릅니다. 빌드 절차는 이 문서에 복제하지 않고 `BUILD_GUIDE.md`만 사용합니다.

본 문서는 개발 단계에서의 회귀를 막고, Pylance/런타임 안정성을 유지하기 위한 규칙 모음입니다. PR 전 체크리스트로 활용하세요.

## 1) 공통 코딩 규칙
- Optional 접근은 지역 변수로 추출해 가드 후 사용합니다.
  ```python
  client = getattr(self, 'binance_client', None)
  ws = getattr(client, 'websocket_manager', None) if client else None
  if not ws: return
  ```
- selected_coins는 항상 dict로 정규화합니다.
  ```python
  normalized = []
  for c in selected_coins:
      normalized.append({'symbol': c} if isinstance(c, str) else c)
  self.selected_coins = normalized
  ```
- coin_symbol은 try 블록 밖에서 기본값을 초기화합니다.
  ```python
  coin_symbol = 'UNKNOWN'
  try:
      coin_symbol = coin['symbol'] if isinstance(coin, dict) and 'symbol' in coin else str(coin)
  except Exception as e:
      self.logger.error(f'[{coin_symbol}] ...')
  ```
- UI 업데이트 전 위젯 생존 체크를 합니다.
  ```python
  def _widget_alive(w):
      try:
          return w and getattr(w, 'winfo_exists', lambda: 0)() == 1
      except Exception:
          return False
  ```
- WebSocket API는 통일된 명칭을 사용합니다.
  - 구독: subscribe_symbol / unsubscribe_symbol
  - 조회: get_latest_ticker / get_latest_orderbook
- **WebSocket 최적화 규칙 (2025-10-20 완료)**:
  - 코인 분석은 API 기반으로 수행 (WebSocket 구독 제거)
  - WebSocket은 실제 포지션 모니터링에만 사용
  - 거래 성공 시에만 WebSocket 구독 추가

## 2) PR 전 체크리스트
- [ ] Optional 접근부가 모두 지역 변수 + getattr 가드인지 확인
- [ ] selected_coins가 dict 정규화 후 사용되는지 확인 (루프 내 .get 안전)
- [ ] coin_symbol/태그 로그가 unbound 위험이 없는지 확인 (기본값 선할당)
- [ ] UI 텍스트/위젯 업데이트가 `_widget_alive` 체크 후 이뤄지는지 확인
- [ ] websocket_manager 직접 접근이 없는지 확인 (지역 변수로 추출)
- [ ] analyzer/analyzer 메서드명 사용 일관성 (analyze_symbol)
- [ ] **WebSocket 구독이 코인 분석용이 아닌 포지션 모니터링용인지 확인**
- [ ] RiskManager 거래 이력 저장 시 거래소 필터가 필요한 경로는 `exchange` 태그가 포함되는지 확인
- [ ] Unified 자산분류 경로에서 암호화폐 거래소(upbit/bithumb 포함)가 `asset_class=crypto`로 유지되는지 확인
- [ ] log_adapter 경로에서 선행 시간/레벨 프리픽스 문자열 재유입 시 중복 출력이 발생하지 않는지 확인
- [ ] CHANGELOG에 변경점이 기록되었는지 확인

## 3) 흔한 오류와 빠른 수정
- Optional 속성 오류 → getattr 가드 + 지역 변수
- str에 get 사용 → dict 정규화 후 get 사용

## 4) 대시보드 포지션 표시 시스템 (중요)
**⚠️ 바이낸스와 CCXT 거래소의 아키텍처 차이점**

### 거래 시스템 분리
- **바이낸스**: `Trader` 클래스 사용 → `main_app.trader.active_positions`
- **CCXT 거래소**: `UnifiedTrader` 클래스 사용 → `unified_trader.active_positions[exchange]`

### 포지션 표시 로직 (필수)
```python
# 올바른 포지션 조회 방법
if exchange == 'binance':
    # 바이낸스: Trader 클래스에서 조회
    if hasattr(self, 'main_app') and hasattr(self.main_app, 'trader') and self.main_app.trader:
        positions = getattr(self.main_app.trader, 'active_positions', {})
else:
    # CCXT 거래소: UnifiedTrader에서 조회
    if hasattr(self, 'unified_trader') and self.unified_trader:
        positions = getattr(self.unified_trader, 'active_positions', {}).get(exchange, {})
```

### 통계 통합 방법
```python
# 활성 포지션 수 합산
active_positions = 0

# 바이낸스 포지션 수
if hasattr(self, 'main_app') and hasattr(self.main_app, 'trader') and self.main_app.trader:
    binance_positions = getattr(self.main_app.trader, 'active_positions', {})
    active_positions += len(binance_positions)

# CCXT 거래소 포지션 수
if hasattr(self, 'unified_trader') and self.unified_trader:
    ccxt_positions = getattr(self.unified_trader, 'active_positions', {})
    for exchange_positions in ccxt_positions.values():
        active_positions += len(exchange_positions)
```

### 체크리스트
- [ ] 새 거래소 추가 시 바이낸스 vs CCXT 분기 처리
- [ ] 포지션 표시 시 올바른 객체 참조 사용
- [ ] 통계 수집 시 두 시스템 모두 고려
- [ ] 관련 문서: `docs/DASHBOARD_POSITION_SYSTEM.md` 참고
- unbound 변수 → try 밖 기본값 초기화
- destroyed widget → 생존 체크 + 안전 업데이트 헬퍼

## 4) 문서 업데이트 원칙
- 코드에 회귀 방지 변경을 넣을 때, docs/TYPE_GUIDE.md와 TROUBLESHOOTING.md에 해당 규칙/해결책을 반드시 추가
- 아키텍처 변화(모듈 책임/명칭 통일)는 docs/ARCHITECTURE.md에도 반영
- 사용자 영향이 있거나 주요 버그 수정이면 docs/CHANGELOG.md 업데이트

## 5) 재테크 확장 개발 가이드라인

### 모듈화 원칙
- **거래 엔진 모듈화**: 암호화폐/주식/ETF 공통 인터페이스로 확장성 확보
  - `trading/exchanges/interfaces/` 디렉토리 구조 준수
  - 새로운 자산 타입 추가 시 기존 인터페이스 확장
- **AI 분석 모듈화**: 자산별 특화 분석 엔진으로 정확도 향상
  - `trading/ai/` 디렉토리에 자산별 분석 모듈 추가
  - 공통 분석 로직은 base 클래스로 추상화
- **데이터 관리 모듈화**: 통합 데이터베이스 스키마로 일관성 유지
  - `trading/recorder.py`의 데이터베이스 스키마 확장 시 하위 호환성 유지
  - 자산별 테이블은 `asset_type` 컬럼으로 구분

### 새로운 서비스 추가 시 체크리스트
- [ ] `trading/exchanges/interfaces/`에 인터페이스 정의
- [ ] `trading/exchanges/adapters/`에 어댑터 구현
- [ ] `config/settings_template.json`에 설정 추가
- [ ] `ui/dashboard_modern.py`에 서비스 탭 추가
- [ ] `docs/`에 서비스별 문서 추가
- [ ] `UPDATE_PLAN.md`에 개발 계획 반영

### ETF 모듈 추가 시 특별 고려사항
- ETF는 증권의 한 종류이지만 별도 필터링/분류 로직 필요
- **상세 개발 가이드**: 
  - `docs/STOCK_ETF_DEVELOPMENT_GUIDE_20260118.md`: 개발 단계 가이드
  - `docs/STOCK_ETF_CURRENT_STATUS_20260118.md`: **현재 개발 현황 및 다음 단계** (필수 참고)
  - `docs/STOCK_ETF_ADDITION_GUIDE.md`: 기술적 추가 가이드
- **AI API 활용**: `docs/AI_API_ARCHITECTURE.md` 참고 필수
- 증권사 API 연동 시 키움증권 OpenAPI 구조 준수
- 암호화폐 시스템의 구조와 패턴을 최대한 재사용하여 일관성 유지
- **대시보드 UI 패턴**: 블록체인 서비스와 완전히 동일한 패턴 사용 (이미 구현됨)
  - ✅ `create_service_sub_tabs('stock')` 구현 완료
  - ✅ `create_broker_*` 메서드들 구현 완료 (placeholder)
  - ✅ 좌/우 2단 레이아웃 구조 유지
  - ✅ 동일한 색상/폰트/위젯 구조 사용
- **현재 구현 상태**:
  - ✅ UI 기본 구조 완료
  - ✅ 설정 기능 완료
  - ✅ 서비스 전환 로직 완료
  - ✅ 실제 API 어댑터 구현 완료 (신한/미래에셋 REST 완성, 키움 Mock 경로 완성 + Windows 실환경 검증 대기)

### 2026-04-23 기준 우선 개발 체크리스트
- [x] 증권사 실연동 완성: 연결/잔고/포지션/주문 실API 경로 고도화 (키움 실환경은 Windows 검증 대기)
- [x] `api_type` 선택 시 `api_version` 유효 조합 동적 제한(UI)
- [x] 저장/실행 경로에서 `api_type`-`api_version` 조합 검증 강제
- [x] ETF 전용 지표(추적오차/NAV 괴리/거래대금) 컨텍스트 조건부 주입
- [ ] 레거시 계획 문서 중복 항목 정리(정본 링크 통일)

### 공개 저장소 기준 음성(STT/TTS)
- 현재 본 리포지토리에는 **전면 STT/TTS UI·라이브러리 통합이 없을 수 있음**. 대외·문서 서술은 인앱 메뉴얼·`docs/DOCUMENTATION_POLICY.md`와 같이 **로드맵·단계 공개**로 맞출 것.
- 사용자·운영 관점의 요약과 설치 후 읽는 순서는 **`docs/AI_ASSISTANT_GUIDE.md`** §8(STT/TTS)를 함께 유지합니다.

### 음성 지원 추가 시 고려사항
- STT (Speech-to-Text): 음성 인식 라이브러리 선택 (예: Whisper, Google Speech-to-Text)
- TTS (Text-to-Speech): 음성 합성 라이브러리 선택 (예: pyttsx3, gTTS)
- 시니어 친화 UI: 큰 폰트, 명확한 색상 대비, 간단한 메뉴 구조
- 대화형 인터페이스: 자연어 처리 강화, 컨텍스트 유지

### 재무/세무 기능 개발 시 주의사항
- 세금 계산: 국세청 API 또는 공식 세율 기준 사용
- 법적 검토: 세무 자동 신고 기능은 법적 검토 필수
- 데이터 보안: 민감한 재무 정보는 암호화 저장
- 정확성 검증: 세금 계산 결과는 전문가 검토 필요
