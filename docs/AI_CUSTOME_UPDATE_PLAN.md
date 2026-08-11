# AI 커스텀 핵심 고도화 계획

기준 제품: NoahAI Client v3.9.0.8 AI Custom Update Fix 1 소스  
기준일: 2026-08-10  
문서 상태: P0~P3 클라이언트 소스 구현과 외부 운영 게이트를 분리한 제품·개발 정본  
배포 경계: Windows 재빌드·실계정 장시간 E2E 전 (`pending_windows_rebuild`)
릴리스 결정: P0~P3 클라이언트 고도화와 사용자 매뉴얼·AI 어시스턴트 지식을 `v3.9.0.8 AI Custom Update Fix 1` 범위로 관리한다. 새 Windows EXE·SHA-256·설치 검증 전에는 배포 완료로 표시하지 않는다.

> 파일명 `AI_CUSTOME_UPDATE_PLAN.md`는 기존 경로 호환을 위해 유지한다. 제품명과 본문 표기는 `AI 커스텀`, 영문 식별자는 `AI_CUSTOM`으로 통일한다.

## 1. 결론

AI 커스텀 고도화 방향은 타당하다. 다만 시장에서 강한 무기가 되는 대상은 단순한 `자연어 전략 생성기`나 `노코드 자동매매`가 아니다. 이 기능들은 이미 여러 경쟁 제품이 제공하고 있어 빠르게 범용화되고 있다.

NoahAI가 집중할 제품 명제는 다음과 같다.

> **사용자가 가진 투자 지식을 출처 근거가 남는 안전한 전략으로 변환하고, 변환 차이·미지원 조건·시장국면·계좌 위험·주문 결과까지 한 버전으로 검증·운영하는 AI 전략 컴파일·운영체제**

핵심 개발 축은 다음 세 가지다.

1. **Noah Strategy IR** — 서로 다른 전략 원본을 하나의 제한된 중간표현으로 변환한다.
2. **근거 기반 컴파일러** — 원문과 실행 규칙을 연결하고 모호함과 미지원 조건을 조용히 제거하지 않는다.
3. **Progressive Strategy UI** — 한 전략을 요약, 핵심값, 전체 그래프의 세 깊이에서 같은 버전으로 다룬다.

이 세 축은 기존의 검증 연구소, 국면 오케스트레이터, 실행 OS, 전략 여권과 결합할 때만 사업적 차별점이 된다.

## 2. 왜 이 방향이 필요한가

### 2.1 해결할 사용자 문제

- 투자 전략을 모르거나 코드를 작성하지 못하는 사용자는 빈 프롬프트나 빈 편집기에서 시작하기 어렵다.
- 숙련자는 이미 Pine, 문서, 영상, 개인 메모로 전략을 가지고 있지만 다른 실행 환경으로 옮길 때 의미가 달라질 수 있다.
- 자연어 생성 결과는 그럴듯해 보여도 누락 조건, 캔들 시점, 수수료, 주문 상태가 다르면 원 전략과 다른 결과를 낸다.
- 백테스트 통과가 PAPER 또는 LIVE의 안전성과 같지 않다.
- 백테스트는 미래 수익 예측이나 홍보 수단이 아니라, 규칙이 의도대로 작동하는지와 손실 구조가 최소 기준을 통과하는지 확인하는 1차 필터다.
- 전략 변경과 실행 결과가 같은 버전·근거·계좌 사건으로 연결되지 않으면 사후 검증이 어렵다.

### 2.2 제품 원칙

- 초보자를 `프롬프트를 잘 쓰는 사용자`로 정의하지 않는다.
- 초보자용 제품과 고급 사용자용 제품을 서로 다른 엔진으로 만들지 않는다.
- AI는 전략을 마법처럼 발명하는 역할보다 비정형 지식을 명시적인 실행 규칙으로 번역하는 역할을 우선한다.
- 현재 지원하는 표현 범위만 변환하고, 모호하거나 미지원인 부분은 질문 또는 차단 상태로 남긴다.
- 전략 저장, 사용자 승인, 자동검증, 최종 적용, PAPER, LIVE를 각각 다른 상태로 유지한다.
- 전략값과 계좌 안전을 분리한다. 위험 충돌 시 전략의 손절값을 몰래 바꾸지 않고 수량을 축소하거나 주문을 차단한다.
- `모든 전략`, `모든 Pine`, `수익 전략 자동 생성`, `즉시 실거래`를 약속하지 않는다.

### 2.3 익숙함을 지키는 상위 호환 원칙

오랫동안 TradingView와 기존 자동매매 도구를 사용한 사람의 습관은 제거할 마찰이 아니라 시장 진입을 위한 호환 계약이다. 사용자 의견을 그대로 투표 결과처럼 구현하지는 않지만, 반복적으로 검증된 익숙한 표현과 흐름은 다음 기준으로 적극 수용한다.

- LONG/SHORT, 진입·청산, TP/SL, 시간봉, 지표, PnL, MDD, 승률, Profit Factor, 월별·연별 표처럼 시장에서 통용되는 용어와 읽는 순서를 유지한다.
- Pine·TradingView 전략을 가져온 사용자가 기존 전략의 의미와 NoahAI 변환 결과를 같은 화면에서 비교할 수 있게 한다.
- 익숙한 기능을 숨기거나 철학을 이유로 제거하지 않고, 기본 기능으로 제공한 뒤 NoahAI의 근거·검증·운영 계층을 그 위에 더한다.
- 새로운 개념을 강요해야 할 때는 기존 개념과의 대응 관계, 필요한 이유, 달라지는 실행 결과를 XAI로 설명한다.
- 초보자는 단순한 기본 화면에서 시작하고 기존 숙련자는 고급 기능을 즉시 열 수 있지만, 두 사용자 모두 같은 전략 IR과 안전 계약을 사용한다.

목표 구조는 다음과 같다.

```text
시장 표준의 익숙한 제작·성과 확인 경험
+ NoahAI 원본 근거·모호함/미지원 차단
+ 국면·위험·주문·체결 검증
+ PAPER 전진검증·버전 감사·AI 설명
= 익숙하지만 더 검증 가능하고 운영 가능한 AI 커스텀
```

`상위 호환`은 내부 제품 목표다. 외부에는 기능 목록만으로 우위를 단정하지 않고, 변환 일치율·첫 전략 완성 시간·재생 차이·PAPER 유지율·실체결 괴리·차단 정확도와 사용자 이동 성공률로 입증된 범위만 표현한다.

## 3. 2026년 시장 검증

### 3.1 확인된 경쟁 기준

| 제품 | 공식 자료에서 확인한 강점 | NoahAI가 단순 복제하면 약한 이유 |
|---|---|---|
| TradingView | Pine 전략, 백테스트·포워드 테스트, Strategy Tester, 실시간 알림과 웹훅 생태계 | 차트·스크립트·커뮤니티 규모로 정면 경쟁하기 어렵다. Pine 입력은 교체 대상이 아니라 가져올 원본이다. |
| TrendSpider | 노코드 전략 테스트, 사용자 정의 지표, ML 모델 학습, 차트·스캔·알림·봇 연결 | `AI가 전략을 만든다`와 `코딩 없이 자동화한다`는 메시지만으로 차별화할 수 없다. |
| Capitalise.ai | 자유 텍스트로 전략 작성, 백테스트·모의운용, 반복 전략 | 자연어→자동화는 이미 독립 제품 범주다. |
| QuantConnect | AI가 아이디어를 코드로 만들고 컴파일·백테스트하며, 연구→백테스트→PAPER 파이프라인과 라이브 조정을 제공 | AI 에이전트와 정량 연구 파이프라인 자체도 경쟁 우위가 아니다. |

시장 검증 기준일은 2026-08-09이며 외부 공개 전 다시 확인한다. 공식 근거는 [TradingView Strategies](https://www.tradingview.com/pine-script-docs/concepts/strategies/), [TradingView Alerts](https://www.tradingview.com/pine-script-docs/concepts/alerts/), [TrendSpider ML Quant Lab](https://trendspider.com/product/machine-learning-quant-trading-strategy-lab/), [Capitalise.ai Features](https://capitalise.ai/features/), [QuantConnect Backtest Assistant](https://www.quantconnect.com/docs/v2/ai-assistance/predefined-assistants/backtest-assistant), [QuantConnect Reconciliation](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation)이다.

### 3.2 사업 판단

| 판단 | 결론 |
|---|---|
| 자연어 전략 생성만으로 강력한 무기인가 | **아니다.** 시장에서 이미 제공되는 기본 기대치다. |
| 멀티모달 입력 수가 많으면 방어력이 생기는가 | **부분적이다.** 입력 수보다 변환 근거·정확도·지원 경계가 중요하다. |
| 범용 전략 IR은 타당한가 | **타당하다.** 전략별 기능을 계속 하드코딩하는 비용을 줄이고 UI·검증·실행·공유의 공통 계약이 된다. |
| `Universal`을 대외 약속으로 사용해도 되는가 | **아니다.** 데이터와 실행 구조가 다른 전략군까지 모두 지원한다는 오해를 만든다. 내부 목표로만 두고 외부에는 지원 프로필을 명시한다. |
| Progressive UI가 필요한가 | **그렇다.** 초보·숙련자를 분리하지 않고 같은 전략의 이해와 편집 깊이만 확장할 수 있다. |
| 현재 가장 강한 후보 무기인가 | **조건부로 그렇다.** 변환 신뢰성, PAPER 유지율, 실체결 조정, 실패 폐쇄 증거를 제품 KPI로 입증해야 한다. |

### 3.3 백테스트의 제품 포지션

사용자 피드백을 반영해 백테스트를 제거하지 않는다. 총 PnL, 총 수익률, MDD, 승률, Profit Factor와 월별·연별 수익률 표를 제공하되 다음 순서를 강제한다.

```text
과거 재생 최소 통과조건
→ 미사용 구간·워크포워드
→ 비용·파라미터 민감도·몬테카를로·과최적화 경고
→ PAPER 전진검증
→ 사용자 검토와 최종 적용
```

과거 전체를 알고 맞춘 수익률은 미래 성과 근거가 아니다. 따라서 백테스트만으로 자동 승격하지 않으며, 성과표에는 `과거 결과이며 미래를 보장하지 않음`, 사용 데이터 기간, 비용 가정과 PAPER 상태를 함께 표시한다. 음수 총 PnL, 과도한 MDD, 표본 부족은 최소 통과 실패 사유로 명시한다.

### 3.4 NoahAI의 차별화 쐐기

경쟁 메시지를 `AI가 전략을 만들어 준다`가 아니라 다음 순서로 고정한다.

```text
Bring your strategy
→ See exactly what NoahAI understood
→ Resolve ambiguity and unsupported rules
→ Validate by regime, cost, and execution reality
→ Approve one immutable version
→ Operate under account and order guardrails
→ Reconcile decisions, orders, fills, and outcomes
```

한국어 대외 표현:

> **당신의 전략을 가져오세요. NoahAI가 무엇을 어떻게 이해했는지 확인하고, 검증된 한 버전만 안전 경계 안에서 운영하세요.**

방어 가능한 자산은 프롬프트가 아니라 다음의 누적 데이터와 계약이다.

- 원문 조각과 규칙 노드의 연결 데이터
- 모호함 질문과 사용자 확정 이력
- 지원·미지원 변환 회귀 코퍼스
- 같은 전략 버전의 백테스트·PAPER·LIVE 차이
- 국면별 HOLD·차단·주문·체결·복구 기록
- 거래소·증권사별 주문 능력과 실패 패턴
- 전략 여권, 권리, 호환성, 검증 증거

## 4. 목표 아키텍처: Noah Strategy IR

`Universal Trading Strategy IR`은 장기 내부 방향이다. 제품 계약 명칭은 과장 범위를 줄인 `Noah Strategy IR`로 사용한다.

```text
자연어·Pine·PDF·이미지·영상·TradingView·기본 전략·직접 편집
                              ↓
                    Source Evidence Graph
                              ↓
                 Parser / AI Interpretation
                              ↓
             Noah Strategy IR + Capability Profile
                              ↓
        Validate / Clarify / Unsupported / Compare Diff
                              ↓
       Replay / PAPER / Regime / Risk / Execution Guard
                              ↓
             Decision / Order / Fill / Outcome Ledger
```

### 4.1 공통 Primitive

| 계층 | 최소 구성요소 |
|---|---|
| Data | OHLCV, 시간, 심볼·시장, 지표 입력, 비용·유동성 |
| Signal | Trend, Momentum, Mean Reversion, Breakout, Volatility, Volume, Price Action |
| Operator | `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `crosses_above`, `crosses_below`, `AND`, `OR` |
| Action | Enter Long, Enter Short, Hold, Exit, Partial Exit |
| Risk | Risk Budget, Position Size, Leverage Cap, SL, TP, Trailing, Break-even |
| State | Position, Previous Value, Cooldown, Re-entry Count, Partial-fill State |
| Scope | Asset, Exchange/Broker, Symbol Universe, Timeframe, Regime Scope |
| Evidence | Source Span, Confidence, Clarification, Unsupported Reason, User Decision |

현재 선언형 엔진의 실제 지원 범위와 목표 범위를 섞지 않는다.

| 구분 | 현재 v3.9.0.7 소스 | 후속 IR 목표 |
|---|---|---|
| 사용자 지정 지표 | SMA, EMA, RSI, ATR, 거래량 평균 + 제한형 산술 수식·의존성 검사 | 전체 Pine/Python 호환과 별도 데이터 지표 |
| 고정 필드 | 가격·OHLCV, MACD, 볼린저, ADX, ATR, 시간 등 허용 필드 | 공통 데이터 노드로 정규화 |
| 조건 결합 | 최상위 `all`·`any`와 깊이/노드 제한 중첩 `and/or` Expression Graph | 드래그형 캔버스와 더 넓은 노드 라이브러리 |
| 상태·청산 | 부분익절, 추적손절, 손익분기, 재진입·피라미딩 계획 | 명시적 상태머신과 기관별 capability |
| 외부 전략 | 제한된 Pine·자료 추출, HMAC 서명·시간창·nonce·delivery 중복방지 webhook 게이트 | 서버 수신 endpoint·영속 중복 저장소·운영 E2E |
| 특수 전략군 | 일반 기술적 규칙 중심 | 오더북·차익거래·옵션·뉴스·온체인은 별도 확장 프로필 |

### 4.2 Capability Profile

모든 전략을 한 번에 지원하려 하지 않는다. 전략마다 필요한 능력을 선언하고 현재 런타임과 비교한다.

```yaml
required_capabilities:
  data: [ohlcv]
  indicators: [ema, rsi, volume_sma]
  state: [previous_value, cooldown]
  orders: [market, stop_loss, partial_exit]
  venues: [crypto_spot, crypto_perpetual]
```

결과는 다음 세 상태만 허용한다.

- `supported`: 현재 데이터·계산·주문 계약으로 의미를 보존할 수 있음
- `needs_clarification`: 사용자 정의가 없으면 의미가 확정되지 않음
- `unsupported`: 현재 엔진이 의미를 보존할 수 없어 저장·승인·실행 차단

## 5. Progressive Strategy UI

초보 모드와 고급 모드를 별도 제품으로 만들지 않고 한 전략 버전의 노출 깊이를 조절한다.

### Level 1 — 이해하고 시험하기

- 원본 가져오기 또는 2~3개 교육형 후보 선택
- 전략 한 줄 요약, 권장·금지 국면, 상대적 위험, HOLD 조건 표시
- `테스트하기`, `근거 보기`, `모호한 조건 확인` 제공
- 전문 용어와 전체 JSON/DSL은 기본 숨김

예시:

```text
볼린저밴드 + RSI 평균회귀
횡보장의 과매도 반등을 관찰합니다.
권장: 횡보·저변동 / 금지: 강한 하락·유동성 부족
현재 상태: 사용자 확인 2건 필요
```

### Level 2 — 핵심값만 바꾸기

- 진입 임계값, 시간봉, 손절·익절, 위험예산, 대상 국면을 카드로 편집
- 변경 즉시 의미와 거래 빈도·위험의 예상 방향을 설명
- `변경 전후 테스트`와 원문 대비 차이 표시
- 자연어 단일 조건 수정도 같은 diff를 생성

### Level 3 — 전체 그래프 편집

- 중첩 AND/OR, 다중 시간봉, 상태, 부분청산, 재진입, 유니버스 정책 편집
- 노드별 원문 근거, 입력 데이터, 계산값, 지원 상태 표시
- 임의 Python/Pine 실행 없이 허용 노드만 저장
- 저장은 새 버전을 만들 뿐 승인·적용·실행하지 않음

세 화면은 같은 `strategy_id`, `version_id`, IR, 검증 결과를 사용한다. Level 간 이동으로 다른 전략이 생성되거나 의미가 조용히 바뀌면 안 된다.

설정의 `초보자 / 일반 / 고급 / 실험실`은 별도 엔진이 아니라 초기 노출 프로필이다. 과거 재생, 월·연도 표, Expression Graph, 사용자 지표 언어, 전략 패키지, 팀 권한 메타데이터, 품질 리포트, 서명 webhook, B2B 감사 번들을 개별적으로 다시 켜거나 끌 수 있다. 기반 기능을 끄면 종속 기능도 실패 폐쇄되며, 유료 마켓은 어떤 프로필에서도 열리지 않는다.

## 6. 개발 우선순위

### P0 — 수직 슬라이스 정본화

- [x] Noah Strategy IR v1 스키마와 현재 엔진 기반 capability registry 구현
- [x] 현재 `DeclarativeStrategyEngine` 조건·고급 주문 계획을 canonical rules로 무손실 왕복하고 SHA-256 무결성 검사
- [x] 원문 evidence excerpt → IR node ID/path → canonical 실행 조건 연결. 문자 단위 source span offset은 P1 코퍼스 작업에서 보강
- [x] `supported / needs_clarification / unsupported`를 저장·승인·검증·활성화 게이트에 연결하고 변조 IR fail-closed 차단
- [x] 대표 RSI 전략의 자연어 가져오기→Level 1/2/3→버전 diff→선언형 재생→PAPER 상태 기록 소스 수직 슬라이스 구현
- [x] 기존 `confirm / independent`, 국면, 위험, 주문 상태 계약과 활성 풀 최대 10개 정책 보존
- [ ] 실제 Windows 화면에서 Level 전환·저장·재시작 복원·PAPER 사용자 E2E 및 피드백 기록

### P1 — 사용자 가치 검증

- [x] Level 1 요약·근거 연결 수·누락·지원 상태 단일 화면
- [x] Level 2 핵심 파라미터/조건 투영과 기존 위험·국면 카드, 버전 변경점 연결
- [x] Level 3 전체 IR·capability·노드 근거 보기와 안전 DSL 편집기 연결
- [ ] Pine·자연어·PDF 대표 코퍼스의 의미 동등성 테스트
- [x] TradingView/참조 재생과 NoahAI 재생의 캔들·체결시점·가격·비용 차이 리포트 생성 계약
- [ ] 실제 TradingView 대표 전략 결과를 사용한 비교 코퍼스 채움
- [ ] 첫 전략 입력→초안→PAPER 전환 퍼널 계측

> 2026-08-09 현재 완료 표시는 이 작업 폴더의 소스와 자동 회귀 기준이다. Windows EXE, 실제 거래소 계정, 장시간 PAPER/LIVE 운용 완료를 뜻하지 않는다. 사용 절차와 피드백 양식은 `AI_CUSTOM_FEATURE_TEST_AND_FEEDBACK_GUIDE_20260809.md`를 따른다.

### P2 — 표현력 확장

- [x] 깊이·노드 수 제한과 fail-closed 검증을 갖춘 중첩 불리언 Expression Graph
- [x] 임의 import·속성 접근·파일/네트워크 호출을 차단하는 제한형 사용자 지표 수식과 함수·변수 의존성 그래프
- [x] 명시적 상태머신: 쿨다운, 재진입, 단계 청산, 피라미딩
- [x] HMAC 서명·시간창·nonce·delivery ID 재전송/중복 방지 webhook 게이트. 서버 endpoint와 영속 nonce 저장소 E2E는 외부 게이트
- [x] Noah Strategy IR 데이터·지표·상태·주문·venue capability profile과 초보자/일반/고급/실험실 기능 프로필

### P3 — 운영 자산과 사업화

- [x] `.noahstrategy` exporter/importer, SHA-256 변조 검사, 선택형 로컬 서명, 전략 여권 연결과 비활성 검토 가져오기
- [x] 로컬 패키지의 private/team/unlisted 권한 메타데이터와 업데이트 수동 승인 계약
- [ ] 회원 초대·철회·오브젝트 저장소·다운로드를 포함한 실제 서버 팀 공유 E2E
- [x] 과거/PAPER/LIVE/변환 동등성을 분리하는 품질 리포트
- [x] B2B 전략 감사 번들 계약. 인증 배포 API와 기관 연동은 서버 외부 게이트
- [ ] 결제·정산·분쟁·법무 게이트 완료 후에만 유료 마켓 검토

> P1~P3의 `[x]`는 이 작업 폴더의 클라이언트 소스와 자동 회귀 완료를 뜻한다. Windows 설치본, TradingView 실제 코퍼스, 서버 팀 공유, webhook 운영 endpoint, 기관 API, 결제·법무는 각각 별도 검증이 끝나기 전 제공 완료로 말하지 않는다.

## 7. 완료 기준과 KPI

### 7.1 제품 완료 기준

- 같은 전략이 Level 1·2·3에서 동일한 IR·버전·검증 결과를 표시한다.
- 원문 근거 없는 실행 노드는 생성되지 않는다.
- 모호하거나 미지원인 조건이 저장·승인 과정에서 누락되지 않는다.
- Pine/원본과 NoahAI 재생 차이가 캔들·가격·비용·주문 모델별로 설명된다.
- 전략 변경은 새 버전이며 기존 활성 버전을 자동 교체하지 않는다.
- LEARNING/PAPER에서 실제 주문 API 호출이 없고 LIVE는 기존 권한·가드레일을 통과한다.
- 전략·국면·계좌 판단부터 주문·체결·결과까지 하나의 상관 ID로 추적한다.

### 7.2 사업 KPI

| 단계 | 대표 KPI |
|---|---|
| 가져오기 | 자료 입력 성공률, 지원 가능한 규칙 비율, 원문→노드 근거 연결률 |
| 이해 | 확인 질문 완료율, 미지원 이유 이해율, 첫 유효 전략까지 걸린 시간 |
| 편집 | Level 2 사용률, 변경 전후 비교율, 버전 되돌리기 성공률 |
| 검증 | 재생 완료율, PAPER 전환율, 7일·30일 PAPER 유지율 |
| 운영 | HOLD·차단 이유 표시율, 주문·체결 조정률, 재시작 복구 성공률 |
| 사업 | 체험→라이선스 전환, 지원 비용, 팀/B2B 파일럿 유지율 |

승률, 수익률, LLM 호출 수, 생성 전략 수를 단독 대표 KPI로 사용하지 않는다.

### 7.3 Go / No-Go 게이트

다음 조건을 충족하면 AI 커스텀을 NoahAI의 최우선 고객 획득 무기로 확대한다.

- 대표 원본 코퍼스의 실행 의미 보존율과 미지원 차단율이 사전 기준을 충족함
- 신규 사용자의 첫 PAPER 전략 도달 시간이 기존 흐름보다 유의하게 감소함
- 30일 PAPER 유지율과 설명 이해도가 개선됨
- Windows·실계정에서 주문·체결·재시작 조정 증거가 확보됨
- 고객 문의가 `AI가 알아서 수익을 보장한다`가 아니라 전략 이해·검증 가치로 수렴함

기준을 충족하지 못하면 표현력 확대보다 변환 신뢰성과 단일 화면 UX를 먼저 개선한다.

## 8. 공개 문구

### 권장

- `내 전략을 가져와 NoahAI가 이해한 규칙과 근거를 확인합니다.`
- `지원되는 규칙만 안전한 전략으로 변환하고 모호함과 미지원 조건을 먼저 보여 줍니다.`
- `시장국면·비용·계좌·주문 조건을 검증하고 사용자가 승인한 버전만 운용합니다.`
- `백테스트, PAPER, LIVE와 실제 체결 결과를 구분합니다.`

### 금지

- `세상의 모든 전략을 자동 변환`
- `TradingView 완전 대체 또는 상위호환`
- `AI가 수익 전략을 자동 생성`
- `검증 통과 전략은 수익 보장`
- `Pine/PDF/영상만 넣으면 즉시 실거래`

## 9. 연결 정본

- 제품 계층·단계 상태: `docs/AI_CUSTOM_STRATEGY_OS_PRODUCT_ROADMAP.md`
- 현재 구현·실행 계약: `docs/AI_CUSTOM_STRATEGY_ARCHITECTURE.md`
- 대외 설명·사업 구조: `docs/NOAHAI_EXTERNAL_POSITIONING_AND_BUSINESS_PLAN_20260804.md`
- 대화형 프리셋·입문 UX: `docs/AI_CUSTOM_CONVERSATIONAL_PRESETS_PLAN_v3.9.0.3.md`
- 전략 공유·여권: `docs/AI_CUSTOM_STRATEGY_SHARING_AND_PASSPORT.md`
- 전체 개발·검증 상태: `docs/UPDATE_PLAN.md`
- 사용자 안전 순서: `ui/ai_custom_guidance.py`의 `AI_CUSTOM_SAFE_STEPS`

이 문서는 AI 커스텀의 다음 고도화 의사결정 정본이다. 실제 제공 범위는 설치 버전, `AI_CUSTOM_STRATEGY_ARCHITECTURE.md`, 업데이트 내역과 실환경 검증 증거를 함께 확인한다.
