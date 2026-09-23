# 개발자 가이드 (회귀 방지 규칙)

## Coinone 공통 실행 조건 적용 — 2026-09-24

2026-09-24 최종 정책 정정 (v3.9.1.46 소스 후보): Coinone 전용 E2E 승인 차단을 제거했습니다. 등록부의 LIVE 허용과 주문 어댑터를 공통 실행 조건에 맞추며, 옛 coinone_live_e2e_verified 값은 사용하지 않습니다. API 인증·명시적 LIVE 시작·회원/주문 범위·위험/최소주문/소유권 조건은 유지합니다. 실제 계좌 검증은 테스터가 진행하며 자동시험 통과를 실계좌 검증 완료로 표시하지 않습니다. 업데이트가 자동 거래를 시작하지 않습니다.

아래 이전 점검의 Coinone LIVE 미지원·승인 전 차단은 변경 전 이력입니다. 위 정책을 현재 기준으로 사용합니다.

## 제품 상태 문서화 계약 (2026-09-18)

- NoahAI Client는 검증 완료 후 무료·유료 서비스 중으로 표기한다.
- Strategy Studio는 현재 제공 중, Strategy Hub는 무료 공개 테스트 중으로 구분한다.
- 유료 Marketplace·결제·제작자 정산은 구현·운영 게이트가 닫히기 전 현재 서비스처럼 표시하지 않는다.
- 코인·증권·ETF 제공 사실과 개별 기관의 PAPER/LIVE 준비도를 분리한다. 제품 전체를 `검증 중`으로 되돌리지 않고 기관 capability를 구체적으로 표시한다.
- 생활금융은 현재 단계적 서비스다. 현금흐름·목표·보안 경고·세금 계산·금융상품 비교의 실제 화면/계산 제공과, 외부 금융기관 가입·심사·실행을 분리한다.
- 릴리즈 시 README, MASTER, UPDATE_PLAN, CHANGELOG, 공개 웹, 구조화 데이터, `llms.txt`를 함께 점검한다.

> 기준: 2026-09-11 · v3.9.1.27 Strategy Assistant 연속성·AI 비용·모델 라우팅 공개판  
> 금융 인텔리전스의 메뉴·데이터·상태 모델은 `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`, 검증은 `FINANCIAL_INTELLIGENCE_TEST_CHECKLIST_20260723.md`를 따릅니다. 빌드 절차는 이 문서에 복제하지 않고 `BUILD_GUIDE.md`만 사용합니다.

본 문서는 개발 단계에서의 회귀를 막고, Pylance/런타임 안정성을 유지하기 위한 규칙 모음입니다. PR 전 체크리스트로 활용하세요.

Strategy Studio에서 외부 화면으로 질문을 연결할 때는 `ai_custom` 문맥과 복귀 대상을 함께 설정하고, 원문·File 객체·분석 상태를 가진 컴포넌트를 언마운트하지 않는다. Provider 공백 응답은 성공으로 캐시하지 않으며 로컬 정본 fallback을 유지한다. 기본 NoahAI 사용 경로를 실행 규칙 없는 커스텀 전략 생성으로 연결해서는 안 된다.

외부 AI 보조 호출과 결정형 전략 컴파일은 서로 다른 실패 경계다. `interactive_ai_budget_exceeded`는 텍스트·Pine 로컬 컴파일을 중단시키지 않고 외부 설명만 생략한다. AI 답변을 Strategy Studio로 전달할 때는 편집 가능한 미적용 초안으로 두고, 사용자 확정·재분석·저장·승인·PAPER·LIVE 단계를 합치지 않는다. 설명 수준은 프롬프트와 캐시 키에 포함한다.

사용자 요청형 AI 비용은 성공 응답의 실제 토큰과 기준일 가격표가 함께 있을 때만 계산한다. 토큰·가격·모델 귀속이 없으면 0으로 보정하지 말고 `비용 미산출`로 남긴다. 캐시 응답을 새 Provider 호출로 중복 집계하지 않으며 이 원장을 자동매매 전체 비용이나 Provider 청구서로 이름 붙이지 않는다.

Provider가 이미지 전송 형식을 지원하더라도 선택 모델 capability가 비전 입력을 지원하는지 별도로 검사한다. DeepSeek 일반 Flash/Pro는 텍스트·JSON 경로, Vision 실험 모델은 명시적 이미지 경로로 분리한다. 모델 이름은 공식 API ID와 실제 계정 조회 결과만 허용하고 마케팅 명칭을 추측해 정적 등록하지 않는다. 역할별 모델 변경은 사용자 저장 뒤 적용하며 비용만으로 전략 의미나 실행 규칙을 자동 변경하지 않는다.

Strategy Studio의 화면 예시 문구와 deterministic source compiler는 같은 입력 계약을 사용해야 한다. 위험예산·증거금/종목 비중은 명시적 `%`와 의미 라벨이 함께 있을 때만 구조화하고, 분석 결과를 UI 위험 상태에 동기화한 뒤 최종 저장한다. 자동 보완은 화면에서 사용자가 이미 확정한 운용값에만 허용하며 진입·청산·방향·지표·임계값을 AI가 만들어 넣어서는 안 된다.

## 신규 거래소·증권사 개발 규칙

1. `venue_capabilities.py`를 기관 의미의 유일한 Python 정본으로 사용한다. 통계·런타임 모듈에 새 기관 set을 복사하지 않는다.
2. `web_ui_feature_inventory.json`과 `webui/src/venueSources.ts`를 함께 갱신하고 화면은 공통 목록을 import한다. `test_canonical_venue_registry_drives_runtime_statistics_and_ui_inventory` 통과 전에는 메뉴를 공개하지 않는다.
3. `validate_venue_onboarding_profile()`에 주문 단위, contract size, 포지션 모드, 보호주문, 주문/체결/포지션 대조, client order ID, 비용, 시간 동기화, 호출 제한과 native escape hatch를 선언한다.
4. LIVE/PAPER/LEARNING을 별도 권한·원장으로 구현하고 현재 포지션과 기간 청산 통계를 혼합하지 않는다. 통화 불명·조회 실패·가격 없음은 0으로 보정하지 않는다.
5. 기관별 표시 기준은 `account + service + source`만 바꾸는 비파괴 상태다. 위험·학습·전략 PAPER 원장에 전달하지 않는다.
6. 시작하지 않은 조회용 어댑터도 안전 종료 대상이다. 정상 종료, 강제 종료, 재시작, 토큰/COM 대기, 진행 중 HTTP 요청을 기관별로 시험한다.
7. 실제 사용자 폴더를 fixture로 열거나 자동 선택하지 않는다. 합성 fixture와 명시적인 QA 계정만 사용한다.
8. 소스 테스트 뒤 대상 OS 패키지, PAPER soak, 승인된 소액 LIVE 원장을 외부 기관 기록과 대조해야 지원 완료다.

## UI 플랫폼 전환 개발 규칙

현재 구현 위치는 `web_platform/`, `webui/`, `config/web_ui_feature_inventory.json`이다. Stage 0 읽기 전용 계약은 종료됐고, 현재 command endpoint는 엄격 DTO·명시 intent·멱등 ID·계정 경계·감사·fail-closed를 모두 만족해야 한다. 새 명령은 화면이 어댑터를 직접 호출하지 않고 Application Services를 거쳐야 한다.

1. **엔진 우선 분리**: 새 화면보다 application service와 DTO/event 계약을 먼저 만든다. UI 모듈에서 Trader, 거래소 SDK, DB connection을 새로 직접 참조하지 않는다.
2. **하나의 원본**: 기존 CTk와 새 Web UI는 같은 설정·전략·포지션·명령 서비스를 사용한다. 호환을 위해 저장소나 손익 계산을 복제하지 않는다.
3. **조회/명령 분리**: query DTO는 부작용이 없어야 한다. command는 멱등성 키, 기대 상태 버전, 권한, 감사 결과를 가진다.
4. **이벤트 계약**: 모든 WebSocket event는 `schema_version`, `sequence`, `event_id`, `occurred_at`, `source`, `account_scope`를 포함한다. gap이 생기면 snapshot을 재조회한다.
5. **GUI thread 격리**: CustomTkinter, Web renderer, PyQt5/QAxWidget의 GUI 객체는 각 소유 스레드/프로세스 밖에서 접근하지 않는다. thread에서 위젯 메서드를 직접 호출하지 않는다.
6. **Qt binding 혼합 금지**: 현재 Windows 키움 worker가 PyQt5/QAxWidget을 사용하므로 주 프로세스에 PySide6/PyQt6를 추가하지 않는다. 필요하면 별도 프로세스와 제한 IPC를 사용한다.
7. **브라우저 비밀정보 금지**: API Secret·passphrase·복호화 값은 renderer payload, localStorage, console, crash report에 포함하지 않는다.
8. **기능 플래그와 롤백**: route별 `legacy/new`, `read/write`, `paper/live` 권한을 분리한다. 새 화면 오류가 엔진 중지나 열린 포지션 청산으로 연결되지 않게 한다.
9. **레거시 변경 제한**: 전환 기간의 CustomTkinter 신규 기능은 안전/법규/필수 운영에 한정한다. 일반 제품 기능은 service 계약과 새 UI를 먼저 구현한다.
10. **완료 정의**: 단위 테스트만으로 UI 이전 완료를 선언하지 않는다. parity, 패키지 설치, 반복 전환, updater, crash/recovery, PAPER soak와 실제 대상 OS 결과를 함께 기록한다.

Fix Patch 5 필수 자동 게이트:

```bash
.venv/bin/python scripts/active_source_audit.py
.venv/bin/python verify_build_includes.py
.venv/bin/python scripts/doc_consistency_check.py
.venv/bin/python -m pytest -q
```

- API 조회 실패를 정상 `0건`으로 변환하지 않습니다. 성공 빈 상태, 캐시, 실패 상태를 계약으로 분리합니다.
- 최소 주문·수량·가격 규격 검증 예외은 fail-closed합니다. 검증 전 수량으로 주문을 계속하지 않습니다.
- 미사용 소스는 즉시 완전 삭제하지 않고 `SOURCE_QUARANTINE_MANIFEST_20260801.md`의 해시·사유·복원 규칙을 따릅니다.

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
- [ ] 새 문서를 만들기 전에 기존 `ARCHITECTURE.md`, `TRADING_FLOW.md`, `EXCHANGE_SEPARATION_GUIDELINES.md`에 통합
- [ ] `UPDATE_PLAN.md`에 개발 계획 반영
- [ ] 기관 등록부·Web inventory·자격증명·런타임·통계·PAPER·Strategy Studio·안전 종료 동시 갱신
- [ ] mock, 대상 OS, PAPER, 승인된 소액 LIVE와 배포 문서 게이트 분리 기록

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
- 데이터 보안: 현재 로컬 자격증명 정책을 문서와 일치시키고, 향후 암호화 저장을 도입할 때는 모든 연결 키·마이그레이션·롤백을 함께 설계
- 정확성 검증: 세금 계산 결과는 전문가 검토 필요
