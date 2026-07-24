# NoahAI 공식 기술백서 (Technical Whitepaper v1.5)
## Financial AI Decision Infrastructure Hub

> 문서 동기화 기준 (2026-07-24)
> - 현재 배포 기준 버전: v3.9.0.1 (2026-07-24)
> - 안정화 기준선: v3.8.9.28 (코인 우선 1단계, 학습/로그/fallback 정합)
> - 최신 변경 상세: CHANGELOG.md
> - 최신 운영 패치: 다중 자산 금융 인텔리전스 + 출처·기준시각·재현 기록 + 분석/주문 분리(2026-07-24)

### 2026-07-24 v3.9.0.1 금융 인텔리전스

- 주식·ETF·코인·지수·환율·원자재의 공통 시장 데이터 계약과 섹터·자산 분류를 사용한다.
- 이벤트·뉴스·내러티브·재무·가치평가·스크리너·기술지표·성과·백테스트·산업·거시·기관 분석을 공통 서비스 계층으로 제공한다.
- 모든 외부 데이터와 계산 결과에 출처·기준시각·지연·품질·계산 버전을 남긴다.
- 분석 결과는 직접 주문 신호가 아니며 기존 가드레일을 자동 변경하거나 우회하지 않는다.

### 2026-07-19 정합성 보정 메모

- 본 문서의 구조/철학 설명은 유지하되, 기능 상태 판정은 `docs/UPDATE_PLAN.md`의 2026-07-19 상태 매트릭스를 우선 적용한다.
- 현재 제공: AI 커스텀 전략 모드(텍스트/Pine/PDF/OCR/영상/YouTube/TradingView), 공통 가드레일, AlphaArena 검증 흐름.
- 제한 제공: 다중 거래소 아비트리지(비용/유동성/체결성 게이트 기반).
- 업데이트 예정: 전략 공유/랭킹, 뉴스/유튜브 신뢰도 판별 카드 고도화.

## 📖 서문 (Introduction)

### 정체성 정의 (최상위)
**NoahAI**는 **AI 자산 의사결정 인프라(AI Asset Decision Infrastructure)**이다.  
NoahAI는 판단·분석·설명·기록·검증·환류만 수행한다.  
실제 거래 집행, 법적 행위, 자금 이동의 책임은 항상 사용자 또는 외부 시스템(거래소·증권사·금융기관 API)에 있다.

NoahAI는 금융상품 판매자, 운용자, 중개자가 아니다.  
투자 판단에 대한 법적 책임은 사용자에게 있으며, NoahAI는 설명 가능한 AI(XAI) 기반 판단 보조 인프라이다.

### 프로젝트 개요
NoahAI는 **노아에이아이랩스(Noah AI Labs)**가 개발·운영하는 **실시간 AI 학습형 자산 의사결정 인프라**이다.  
(핵심 판단 구조의 기술적 기원은 DAL의 **AI 디지털케어로그**이다.)  
2024년 11월부터 암호화폐 영역에서 실환경 24/7 운영 중이며, ETF/주식도 상시 운영 가능한 구조로 확장되어 실제 사용자/테스터 환경에서 사용되고 있다. 기본 정책은 신규 사용자 보호를 위해 실주문 차단이며, 사용자 설정에서 실주문 허용 시 실제 주문 경로로 동작한다.  
거래 실행은 외부 API 및 사용자 계정을 통해 이루어진다.

**현재 운영·기능 요약**:
- **다중 거래소 연동**: 바이낸스, 바이비트, OKX, 비트겟, 업비트, 빗썸(판단·기록 파이프라인 연동)
- **Alpha Arena**: LLM 기반 판단 실험/벤치마크 환경(연구·검증 모드, 일반 서비스와 분리)
- **Paper Trading 모드**: 실제 집행 없이 전략·판단 검증
- **Chart Screenshot Analyzer**: OCR 기반 차트 이미지 분석 및 판단 보조
- **Classic View**: AI 기능 중심 인터페이스
- **커뮤니티 기능**: QnA 게시판, 고객센터, 단체 채팅 (플레이스홀더)

### 개발 의의 및 문제 해결 (Why NoahAI Was Created)

NoahAI는 **판단 부담을 구조적으로 분산**시키기 위해 설계되었다.

#### 1. 정보 격차 해소 (Information Gap Reduction)
- **문제**: 일반 투자자들의 시장 분석 정보·지식 접근 한계
- **역할**: 전문가 수준의 분석·요약·설명 제공(판단 보조). 실행은 사용자·외부 시스템 책임

#### 2. 스트레스 및 심리적 부담 해소 (Stress & Psychological Burden Reduction)
- **문제**: 24시간 시장 모니터링 부담, 감정적 판단으로 인한 손실
- **역할**: 데이터 기반 판단·설명·기록 제공, 검증·재현 가능한 구조

#### 3. 시니어 친화 및 사용 편의성 (Senior-Friendly & Ease of Use)
- **문제**: 복잡한 금융 플랫폼·기술 설정의 접근성
- **역할**: 직관적 인터페이스·대화형 AI로 설명·조회 중심 지원(실행 지시 아님)

#### 4. 사고 방지 및 리스크 관리 (Mistake Prevention & Risk Management)
- **문제**: 실수·감정적 판단으로 인한 손실
- **역할**: 리스크 가드·검증·가드레일 적용, 모든 판단 과정 로그 기록(재현·감사 가능)

#### 5. 판단 능력의 확장 (AI-Powered Decision Support)
- **문제**: 인간의 인지·시간 한계
- **역할**: 24/7 분석·판단·설명·기록 인프라 제공. 실행은 사용자·외부 시스템 책임

### 시장 문제 정의 (참고)
기존 규칙 기반/비학습형 시스템의 한계:
- **규칙 기반**: 미리 정해진 조건만 따르는 정적 구조
- **비학습형**: 시장 변화에 적응하지 못함
- **투명성 부족**: 결정 과정의 블랙박스화

NoahAI는 **학습·기록·검증·설명 가능 구조**로 위 한계를 완화하는 인프라를 지향한다.

### 비전 선언
> **"판단·설명·기록·검증·환류만 담당하는 AI 자산 의사결정 인프라"**

NoahAI는 자동매매·자산 운용 주체가 아니다.  
**사용자와 외부 시스템이 실행을 담당하는 가운데, 판단 환경을 구조화하고 설명·기록·검증을 제공**하는 인프라이다.

**핵심 가치**:
- **정보 격차 해소**: 전문가 수준의 분석·설명을 누구나 접근 가능하게
- **판단 부담 분산**: 24/7 분석·기록으로 검증·재현 가능한 판단 보조
- **시니어 친화**: 음성·대화로 설명·조회 중심 지원
- **사고 방지**: 리스크 가드·가드레일·로그로 검증 가능 구조
- **설명 가능성(XAI)**: 모든 판단은 로그로 남고, 사후 검증 가능

### 운영 전환 기준선 부록 (2026-04-30)

NoahAI의 실제 운영 전환은 다음의 게이트 체계를 따른다.

1. prekey 게이트
- 목적: 키 없이 완료 가능한 개발/검증/문서 정합성을 먼저 닫는다.
- 명령: `python scripts/release_gate.py --profile prekey`

2. key-day 원샷
- 목적: 사용자 키/권한 입력 후 실브로커 동작 가능 여부를 단일 절차로 판정한다.
- 명령: `python scripts/stock_keyday_one_shot.py`

3. release 게이트
- 목적: 배포 직전 엄격 검증으로 운영 위험을 차단한다.
- 명령: `python scripts/release_gate.py --profile release`

이 체계는 "수익 보장"이 아니라 "실행 가능성과 책임 경계의 명확화"를 위한 구조다.
수익률 개선·전략 최적화는 별도의 후속 고도화 트랙으로 관리한다.

---

## 👨‍💻 창안자 및 기술 기원

**AI 디지털케어로그**는 DAL(드림에이아이랩) 창업자 **정해성(Jung Haesung)** 박사에 의해 고안되었고, 의료·돌봄 영역에서 기록·분석·환류 구조로 검증되었다.  
동일한 구조적 원리를 금융 의사결정 문제에 맞게 재설계·구현한 제품이 **NoahAI**이며, **개발·운영·서비스 주체는 노아에이아이랩스(Noah AI Labs)**이다.

- **디지털케어로그 발명·기술 기원**: 정해성 (Dr. Haesung Jung), DAL(드림에이아이랩) Founder & Chief Architect  
- **NoahAI 제품 운영 주체**: 노아에이아이랩스(Noah AI Labs)  
- **기술 기원**: AI 디지털케어로그(의료·돌봄) → AI 자산 의사결정 인프라(학습·기록·판단·설명·검증)  
- **기술 철학**: "AI는 인간의 판단을 보완하고, 감정을 초월한 합리적 결정을 지원한다. 실행은 사용자·외부 시스템이 담당한다."

---

## 🧠 기술 요약 (Technology Overview)

### 기술 기원: DAL의 AI 디지털케어로그
DAL(드림에이아이랩)은 독자 개발한 **AI 디지털케어로그 기술**을 기반으로 의료·교육·돌봄 등 영역의 AI 전문 역량을 보유한다.  
**NoahAI**는 그 **기록·분석·환류 구조를 금융 의사결정 문제에 맞게 재설계·구현**한 제품이며, **운영·고도화는 Noah AI Labs**가 담당한다.

#### 핵심 기술 연관성 (기술 기원)
```
의료·돌봄 AI 디지털케어로그 → 금융 의사결정 인프라
├── 시계열 데이터 분석 엔진
├── 패턴 인식 및 예측 모델
├── 실시간 학습·환류 시스템
└── 멀티모달 데이터 처리
```

### 기술 전이 경로 (기술 기원)

의료·돌봄 영역의 '기록-분석-학습-환류' 구조를 금융 의사결정 문제에 맞게 재설계하여 적용했다.  
NoahAI는 '시장기록-분석-학습-환류' 파이프라인으로, **판단·설명·기록·검증**만 담당하며 실행은 외부 시스템이 수행한다.

| AI 디지털케어로그 (의료·돌봄) | NoahAI (금융 의사결정 인프라) |
|------------------|----------------------|
| 생체신호 데이터 분석 | 실시간 시장 데이터 분석 |
| 환자 행동 패턴 예측 | 시장·자산 패턴 예측 |
| 치료 피드백 루프 | 판단·결과 환류 루프 |
| 맞춤형 치료 계획 | 개인화된 판단·설명 지원 |
| 기록·설명·검증 구조 | 기록·설명·검증 구조 (실행은 외부) |

### 멀티모달 AI 시스템
NoahAI는 다음과 같은 다양한 데이터를 통합 분석한다(판단 보조용):
- **차트 이미지**: 기술적 분석을 위한 시각적 패턴
  - **Chart Screenshot Analyzer**: 사용자 업로드 차트 이미지 OCR 분석 및 LLM 기반 **판단 제안** 생성(실행 지시 아님)
- **수치 데이터**: 가격, 거래량, 변동성 등 정량적 지표
- **심리 데이터**: 시장 공포/탐욕 지수, 펀딩비 등 정성적 지표

### 기존 시스템과의 구조적 차이

| 구분 | 기존 규칙 기반 시스템 | NoahAI |
|------|------------------|--------|
| **기술 범주** | 단순 조건 실행 프로그램 | AI 자산 의사결정 인프라 |
| **학습 방식** | 규칙 기반 (정적) | AI 학습형 (동적·적응형) |
| **판단 기준** | 미리 정해진 조건 | 실시간 데이터·패턴·심리 분석 |
| **적응성** | 없음 | 지속적 학습 및 환류 |
| **투명성** | 블랙박스 | 모든 판단 과정 로깅 및 설명 가능(XAI) |
| **리스크** | 수동 개입 | Risk Guard·가드레일·검증 |
| **실행** | 프로그램이 실행 | **외부 거래소·증권사 API가 실행** |

---

### 기술적 위치 (2026.02 기준)

- **실시간 AI 학습형 자산 의사결정 인프라**: 판단·설명·기록·검증·환류만 담당  
- **기술 기원**: 의료·돌봄 영역의 기록·분석·환류 구조를 금융 의사결정에 재설계 적용  
- **AI 디지털케어로그 기술 파이프라인(DAL)**: 의료-교육-돌봄 등을 하나의 **판단·기록·설명** 구조로 연결; NoahAI는 금융 의사결정 인프라로의 구현 사례  
- **정체성**: 단순 자동화가 아닌 **AI 자산 의사결정 인프라**. 실행은 항상 외부 시스템이 담당한다.

---

## 🏗️ 시스템 아키텍처 (System Architecture)

### Decision Pipeline ≠ Execution Engine
NoahAI는 **판단 파이프라인(Decision Pipeline)**을 담당하며, **실행 엔진(Execution Engine)**이 아니다.  
실제 주문·체결·자금 이동은 항상 외부 거래소·증권사·금융기관 API가 수행한다.  
Evaluator / Analyzer / Risk Guard / Recorder / Explainer는 모두 **판단·설명·기록·검증** 역할이며, 실행은 외부 시스템이 담당한다.

### 전체 시스템 구성도 (참고)
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   UI Dashboard  │◄──►│   Main Core     │◄──►│  판단→외부 API  │
│  (Modern UI)    │    │  (Controller)   │    │ (집행은 외부)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  AI Manager     │◄──►│   Evaluator     │◄──►│    Recorder     │
│ (판단·설명·환류) │    │ (자산 선정)     │    │ (기록·검증)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 핵심 모듈 역할

#### 1. **analyzer.py** - 시장 분석 및 AI 신호 생성
- **기술적 지표 계산**: RSI, MACD, 볼린저 밴드, 이동평균(SMA/EMA), ATR, 거래량 분석
- **시장 상황 분석**: 변동성, 트렌드 강도, 모멘텀, 시장 심리 지수
- **신호 생성**: `generate_signal()` - 기본 기술적 신호 + AI 강화 신호 통합
- **AI 강화 신호**: `_generate_ai_enhanced_signal()` - AI 학습 데이터 반영 신호 생성
- **동적 임계값**: `calculate_dynamic_volatility_threshold()` - 시장 국면별 변동성 임계값 자동 조정
- **신뢰도 계산**: 기술적 지표 + AI 학습 데이터 + 시장 심리 통합 신뢰도 (0.0 ~ 1.0)

#### 2. **evaluator.py** - 코인 선정 알고리즘
- **5가지 차원 점수 계산**: 변동성(35%) + 추세(25%) + 거래량(20%) + 거래빈도(10%) + 호가창깊이(5%) + RSI(5%)
- **AI 기반 평가**: `_evaluate_coins_with_ai()` - AI 학습 데이터를 활용한 코인 평가
- **메이저/알트 비율 동적 조정**: 시장 상황(상승장/하락장/횡보장)에 따른 자동 비율 조정
- **시장 상황별 선택 전략**: LOW/NORMAL/HIGH 변동성에 따른 코인 선택 기준 자동 조정
- **하이브리드 접근법**: 캐싱 + 백업 + 하드코딩으로 안정성과 성능 동시 확보
- **성능 최적화**: 초기 로딩 4분 → 즉시 (99% 개선), API 의존성 100% → 30% (70% 감소)

#### 3. **unified_trader.py** - 판단→집행 브리지 (CCXT)
- **다중 거래소 연동**: CCXT 기반 거래소 API 브리지. 판단은 NoahAI, 집행은 외부 API
- **포지션·주문 모니터링**: 거래소별 주기적 조회(5-15초)로 상태 반영
- **TP/SL·포지션 크기**: 판단 결과를 외부 API 호출로 전달. 실제 주문·체결은 거래소 API가 수행
- **Paper Trading**: 실제 집행 없이 전략·판단 검증 가능

#### 4. **ai_manager.py** - AI 학습 및 패턴 강화
- **시장 분석**: `analyze_market_conditions()` - 시장 상황 분석 및 동적 설정 제안
- **청산 분석**: `analyze_exit_conditions()` - 청산 시점 최적화 분석
- **패턴 유사성 검증**: `analyze_pattern_similarity()` - 진입 전 패턴 검증 (k-NN 기반)
- **손절 분석**: `analyze_loss_trade()` - 손절 거래 원인 분석 및 개선점 도출
- **익절 분석**: `analyze_profit_trade()` - 익절 거래 성공 요인 분석
- **일일 리포트**: `generate_daily_report()` - 일일/주간/월간 거래 리포트 생성
- **문제 진단**: `diagnose_trading_issues()` - 거래 부재 문제 진단 및 해결책 제시
- **대화형 AI**: `chat_completion()` - 자연어 대화를 통한 AI 어시스턴트 기능

#### 5. **recorder.py** - 데이터베이스 및 학습 데이터 관리
- 거래 기록 영구 저장
- AI 학습 데이터 관리
- 통계 및 성과 분석

#### 6. **alpha_arena_trader.py** - Alpha Arena (v3.8.8.6+) — 연구·검증 모드
- **LLM 기반 판단 실험/벤치마크**: 현재 실행 경로는 DeepSeek 3.1 기준이며, Qwen 3 Max 관련 설정 항목은 준비 상태다. **LLM이 거래를 수행하는 것이 아니라, LLM 판단 실험 환경**이다.
- **벤치마크 검증**: nof1.ai Alpha Arena 벤치마크 검증 알고리즘 적용
- **일반 서비스와 분리**: 기존 판단·기록 파이프라인과 별도 구조. 연구·검증 목적
- **Binance Futures 연동**: 바이낸스 선물 API와의 집행 브리지(집행은 외부 API)
- **고정 코인**: BTC, ETH, SOL, XRP, DOGE, BNB 6개 코인만 판단·실험 대상
- **가드레일**: 레버리지·리스크 캡·TP/SL 필수 등. 실행은 사용자 계정·외부 API 책임

#### 7. **chart_screenshot_analyzer.py** - 차트 이미지 분석 (v3.8+)
- **OCR 기반 차트 분석**: PaddleOCR을 활용한 차트 이미지 텍스트 추출
- **특징 파싱**: 심볼, 타임프레임, 이동평균, 가격 정보 자동 인식
- **LLM 분석**: 추출된 특징을 기반으로 LLM이 **판단 제안** 생성(실행 지시 아님)
- **로컬 처리**: 서버 업로드 없이 로컬에서 완전 처리

---

## 🌐 Financial AI Infrastructure Map (Hub View)

### 허브(Hub)의 정의
NoahAI는 **금융기관을 대체하는 시스템이 아니라**, **판단·설명·기록·검증을 표준화하여 연결하는 중립 계층(Infrastructure Hub)**이다.  
실행·계약·자금 이동은 항상 외부 거래소·증권사·금융기관·사용자가 담당한다.

### 3계층 구조 (근거 기반)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Decision Layer                                │
│  (판단·설명·기록·검증·환류)                                      │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │Analyzer  │  │Evaluator │  │AIManager │  │Recorder  │      │
│  │(분석)    │  │(선정)    │  │(학습·환류)│  │(기록·검증)│      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
│                                                                   │
│  근거: trading/analyzer.py, trading/evaluator.py,              │
│        trading/ai/ai_manager.py, trading/recorder.py            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Execution Bridge Layer                             │
│  (집행 브리지: 외부 API와의 연결 계층)                          │
│                                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │Binance API   │  │CCXT Adapters │  │Stock Broker  │         │
│  │(바이낸스)     │  │(다중 거래소)  │  │Adapter       │         │
│  │              │  │              │  │(증권사)      │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                   │
│  근거: api/binance_client.py, trading/unified_trader.py,        │
│        trading/exchanges/adapters/kiwoom_stock_adapter.py       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│            Audit & Replay Layer                                  │
│  (감사·재현: 로그·DB·XAI)                                        │
│                                                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │Logs      │  │Database  │  │XAI       │  │Replay    │      │
│  │(로그)    │  │(DB)      │  │(설명)    │  │(재현)    │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
│                                                                   │
│  근거: log_system/*, trading/recorder.py,                       │
│        문서의 XAI 정책 및 로그 예시                              │
└─────────────────────────────────────────────────────────────────┘
```

### 역할 분리 표 (NoahAI vs External Institutions vs User)

| 역할 | NoahAI (Decision Hub) | 외부 기관 (Execution) | 사용자 (Owner) |
|------|----------------------|---------------------|---------------|
| **판단·분석** | ✅ 담당 (Analyzer, Evaluator, AIManager) | ❌ | ❌ |
| **설명·기록** | ✅ 담당 (Recorder, XAI, Logs) | ❌ | ❌ |
| **검증·재현** | ✅ 담당 (DB, Replay) | ❌ | ❌ |
| **주문·체결** | ❌ | ✅ 거래소·증권사 API | ❌ |
| **자금 이동** | ❌ | ✅ 금융기관·은행 | ✅ 최종 책임 |
| **계약·법적** | ❌ | ✅ 금융기관·증권사 | ✅ 최종 책임 |
| **상품 판매** | ❌ | ✅ 금융기관·증권사 | ❌ |

**근거**: `trading/unified_trader.py` (CCXT 브리지), `api/binance_client.py` (Binance API), `trading/exchanges/adapters/kiwoom_stock_adapter.py` (증권사 브리지)

### 자산군 확장 경로 (동일 파이프라인)

```
암호화폐 (Already Implemented)
  ├─ Decision Layer: analyzer.py, evaluator.py, ai_manager.py
  ├─ Execution Bridge: binance_client.py, unified_trader.py (CCXT)
  └─ Audit & Replay: recorder.py, log_system/*

ETF/주식 (In Progress)
  ├─ Decision Layer: 동일 모듈 재사용 (근거: StockExchange 인터페이스)
  ├─ Execution Bridge: kiwoom_stock_adapter.py (근거: trading/exchanges/adapters/)
  └─ Audit & Replay: 동일 스키마 확장 (근거: recorder.py 구조)

해외주식/선물/부동산/일반금융 (Extensible)
  ├─ Decision Layer: 동일 모듈 재사용 가능
  ├─ Execution Bridge: 새로운 어댑터 추가 (조건: 외부 API 연동)
  └─ Audit & Replay: 동일 스키마 확장 가능
```

**근거**: `trading/exchanges/interfaces/stock_exchange.py` (인터페이스), `trading/exchanges/adapters/` (어댑터 패턴), `trading/recorder.py` (통합 스키마)

---

## 🤖 AI 판단·환류 엔진 (AI Decision & Feedback Engine)

### 실시간 학습 메커니즘
NoahAI의 AI 엔진은 **판단·설명·기록·검증·환류**만 수행하며, 실행은 외부 시스템이 담당한다. 작동 방식:

#### 1. **강화학습 구조**
```python
# 학습 데이터 구조 예시
{
    "signal_history": [
        {
            "timestamp": "2025-10-20T03:25:00Z",
            "symbol": "BTCUSDT",
            "signal": "LONG",
            "confidence": 0.85,
            "market_conditions": {...},
            "result": "profit",
            "profit_rate": 0.032
        }
    ],
    "pattern_analysis": {...},
    "dynamic_thresholds": {...}
}
```

#### 2. **패턴 유사성 분석**
- 과거 거래 패턴과 현재 시장 상황 비교
- 유사한 패턴에서의 성과 분석
- 진입 전 패턴 검증을 통한 리스크 관리

#### 3. **동적 임계값 조정**
- 시장 변동성에 따른 신뢰도 임계값 자동 조정
- 거래 이력 기반 성과 개선
- 실시간 전략 최적화

### AI 호출 최적화 설계
- **현재 호출 경계**: AI가 활성화되면 최종 신호 확정 전 심볼별 시장 분석 호출이 발생하므로 거래 수와 모델 호출 수는 같지 않다.
- **현재 제공**: 빈번 호출·표준 분석·정밀 진단 역할별 모델 배치
- **미완료 비용 게이트**: 심볼별 쿨다운, 상태 중복 제거, 거래소별 예산, 다심볼 배치, 캐시 적중률 계측
- **검증 원칙**: 비용 절감과 성능 향상은 Usage·Fee 차감 순손익·MDD를 함께 측정한 뒤 판정하며 자동 향상을 전제하지 않는다.

---

## 🔄 판단 파이프라인 (Decision Pipeline)

**Decision Pipeline ≠ Execution Engine.**  
판단·설명·기록·검증·환류는 NoahAI가 담당하며, 주문·체결·자금 이동은 항상 외부 거래소·증권사 API가 수행한다.

### 전체 판단·기록 프로세스 (실행은 외부)
```
시작 → 시장 분석 → 자산 선정 → 신호 생성 → (판단 결과) → 외부 API 집행 → 모니터링 → 결과 기록 → 학습·환류 → DB 저장
  ↑                                                                                                        ↓
  └─────────────────────── 실시간 피드백 루프 (판단·기록·검증) ──────────────────────────────────────────┘
```

### 상세 프로세스

#### 1. **시장 분석 단계**
- 실시간 가격, 거래량, 변동성 수집
- 기술적 지표 계산 (RSI, MACD, 볼린저 밴드, 이동평균)
- 시장 심리 분석 (공포/탐욕 지수)

#### 2. **AI 신호 생성**
- 기본 기술적 신호 생성
- AI 학습 데이터 반영
- 패턴 유사성 검증
- 최종 신호 결정 (LONG/SHORT/HOLD)

#### 3. **판단 결과 → 외부 집행**
- 리스크 가드·검증
- AI 진입 전 분석(판단)
- 포지션 크기·TP/SL 판단 결과 산출
- **주문·체결·TP/SL 설정은 외부 거래소·증권사 API가 수행**

#### 4. **실시간 모니터링**
- **바이낸스**: 10초마다 포지션 상태 체크
- **CCXT 거래소**: 거래소별 최적화된 주기 (5-15초)
- PnL 실시간 계산
- AI 기반 익절/손절 분석
- 청산 조건 확인

#### 5. **청산 후 처리**
- 거래 결과 데이터베이스 저장
- AI 학습 데이터 업데이트
- 패턴 분석 및 개선점 도출
- 다음 거래를 위한 전략 조정

#### 6. **Paper Trading 모드 (시뮬레이션)**
- 실제 거래 없이 전략 검증
- API 키 없이도 기능 검증 가능
- 안전한 테스트 환경 제공
- 모든 분석 및 신호 생성 로직은 실제와 동일하게 작동

#### 7. **Alpha Arena** (v3.8.8.6+) — 연구·검증 모드
- LLM 기반 판단 실험/벤치마크 환경. **일반 서비스와 분리된 구조**
- 현재 실행 경로는 DeepSeek 3.1 기준이며, Qwen 3 Max 관련 설정 항목은 준비 상태
- nof1.ai Alpha Arena 벤치마크 검증 전략 적용
- 기존 판단·기록 파이프라인과 별도. 연구·검증 목적
- Binance Futures 연동, 고정 6개 코인. 집행은 외부 API

#### 8. **Chart Screenshot Analyzer** (차트 이미지 분석)
- OCR 기반 차트 분석 (PaddleOCR)
- 심볼, 타임프레임, 이동평균 자동 인식
- LLM 기반 **판단 제안** 생성(실행 지시 아님)
- 로컬 처리 (서버 업로드 없음)

### 거래소별 구조 차이

#### **바이낸스 전용 경로**
```
main.py → trader.py → api/binance_client.py → 바이낸스 API
```

#### **CCXT 거래소 전용 경로**
```
main.py → unified_trader.py → CCXT 어댑터 → 각 거래소 API
```

---

## 📊 AI 학습 데이터 및 통계 시스템

### 강화학습 구조와 보상 설계

#### 학습 데이터 구조
```json
{
    "ai_learning_data": {
        "signal_history": [...],
        "pattern_analysis": {
            "similarity_threshold": 0.7,
            "pattern_types": ["bullish", "bearish", "sideways"]
        },
        "performance_metrics": {
            "win_rate": 0.68,
            "avg_profit_rate": 0.023,
            "avg_loss_rate": -0.015
        },
        "dynamic_thresholds": {
            "confidence_threshold": 0.4,
            "volatility_threshold": 0.05
        }
    }
}
```

#### 보상 설계
- **수익 거래**: 양의 보상 (수익률에 비례)
- **손실 거래**: 음의 보상 (손실률에 비례)
- **리스크 관리**: 손절 성공 시 부분 보상
- **학습 진전**: 패턴 인식 정확도 향상 시 추가 보상

### 거래 통계 영구 저장 시스템
- **SQLite 데이터베이스**: 모든 거래 기록 영구 저장
- **실시간 동기화**: 메모리와 DB 간 실시간 동기화
- **포지션 복구**: 앱 재시작 시 실제 거래소에서 포지션 자동 복구
- **통계 정확성**: DB 기반 정확한 통계 계산

---

## ⚡ 성능 및 기술 성과

### WebSocket 최적화 성과
- **이전**: 코인 선택 시 46초 지연
- **현재**: 즉시 시작 (99% 성능 향상)
- **기술**: API 기반 분석으로 WebSocket 의존성 제거

### 판단·기록 파이프라인 성능 지표
- **판단 주기**: 5-10초 단위 분석·판단·기록
- **응답 속도**: 실시간 시장 변화 대응
- **안정성**: 99% 이상 인프라 가동률
- **메모리 효율**: 최적화된 캐싱 시스템

### AI 학습·환류 (참고)
- **학습 데이터**: 판단·결과·패턴 수집으로 환류 구조 유지
- **지속적 개선**: 매 판단·결과마다 로그·환류 반영
- **적응성**: 시장 변화에 따른 임계값·정책 보정(실행은 외부)

---

## 🎯 기술적 난이도와 차별점

### 다른 규칙 기반 시스템과의 차이

#### 1. **실시간 학습 구조 부재**
- 기존 시스템: 정적 규칙 기반
- NoahAI: 동적 AI 학습 시스템

#### 2. **강화학습/패턴 유사성 엔진 미보유**
- 기존 시스템: 단순 조건문
- NoahAI: 고급 AI 패턴 분석 엔진

#### 3. **고난이도 구현 요소**
- 거래소 API 통합 및 동기화
- 실시간 포지션 모니터링
- 슬리피지 분석 및 최적화
- 다중 거래소 리스크 관리

### 기술 기원 (의료·돌봄 → 금융 의사결정)

#### 1. **의료·돌봄 영역의 기록·분석·환류 구조**
- 의료·돌봄에서 사용되던 기록·분석·환류 구조를 금융 의사결정 문제에 맞게 재설계 적용
- 시계열·패턴 인식·예측 모델의 기술 전이(우월성 주장 없음)

#### 2. **멀티모달 데이터 파이프라인**
- 의료 이미지 + 수치 데이터 → 차트 + 시장 데이터
- 실시간 데이터 처리·판단 보조

#### 3. **학습·환류 프레임워크**
- 의료·돌봄 영역의 학습·환류 구조를 금융 판단 인프라에 적용
- 실행은 외부 시스템, NoahAI는 판단·기록·검증만 담당

---

## 🛡️ 안정성과 보안 설계

### API 키 보안
- **로컬 암호화 저장**: API 키는 로컬에만 저장
- **외부 전송 금지**: 절대 외부 서버로 전송하지 않음
- **권한 최소화**: "읽기" + "거래" 권한만 부여

### 거래소 오류 대응
- **Binance vs CCXT Fallback**: 거래소별 독립 시스템
- **네트워크 오류 복구**: 자동 재연결 및 상태 복원
- **포지션 복원 로직**: 앱 재시작 시 포지션 자동 복구

### 로깅 및 모니터링
- **통합 로깅 시스템**: 모든 거래 과정 실시간 기록
- **카테고리별 분류**: [analysis], [trade], [order], [monitor], [exit]
- **오류 추적**: 상세한 오류 로그 및 디버깅 정보

---

## 🔍 XAI (설명 가능한 AI) 철학과 정책

### 투명성 원칙
NoahAI는 **XAI(Explainable AI)** 철학을 핵심으로 하여 모든 **판단·결정 과정**을 투명하게 공개한다.

#### 1. **완전한 로그 공개**
```
사용자가 볼 수 있는 모든 로그:
• [analysis] - 시장 분석, AI 분석 과정
• [trade] - 거래 신호, 진입/청산 결정
• [order] - 판단 결과→외부 API 주문·TP/SL (집행은 외부)
• [monitor] - 포지션 모니터링 상태
• [exit] - 포지션 청산, 손익 결과
```

#### 2. **AI 결정 과정 투명화**
- **신호 생성 근거**: RSI, MACD, 볼린저 밴드 등 모든 지표 값 공개
- **패턴 분석 결과**: 유사한 과거 패턴과 성과 비교
- **동적 임계값**: 시장 상황에 따른 임계값 조정 과정
- **학습 데이터**: 거래 이력과 성과 분석 결과

#### 3. **실시간 대화를 통한 검증**
- **AI 어시스턴트**: "왜 그렇게 판단했어?" 질문에 대한 상세 설명
- **자연어 대화**: 복잡한 설정을 일상 언어로 설명
- **즉시 확인**: 모든 거래 결정의 근거를 실시간으로 확인 가능

#### 4. **검증 가능한 구조**
- **로컬 저장**: AI 호출 로그/학습 데이터는 로컬 우선 저장하며, 운영 학습 파일은 최신 N개 슬라이딩 정책으로 관리됩니다. 장기 검증은 DB(`trade_log`) 및 보존 경로(아카이브/배치)와 함께 사용합니다.
- **외부 검증**: 사용자가 직접 로그를 확인하여 AI 작동 검증 가능
- **조작 불가**: 미리 저장된 데이터가 아닌 실시간 AI 분석 결과

### XAI 구현 사례
```python
# 실제 로그 예시
2025-10-20 03:25:00 | INFO - [analysis] 시장 분석 시작 (ex=binance)
2025-10-20 03:25:01 | INFO - [trade] ADAUSDT 분석 시작 (ex=binance)
2025-10-20 03:25:02 | INFO - [analysis] ADAUSDT RSI: 61.50 (ex=binance)
2025-10-20 03:25:03 | INFO - [trade] ADAUSDT 시그널: SHORT (ex=binance)
2025-10-20 03:25:04 | INFO - [order] ADAUSDT 판단→주문 요청 (ex=binance, 집행=외부 API)
2025-10-20 03:25:05 | INFO - [monitor] ADAUSDT 포지션 모니터링 시작 (ex=binance)
2025-10-20 03:25:06 | INFO - [exit] ADAUSDT 익절 청산 완료 (ex=binance)
```

---

## ⚖️ 윤리·법적 위치 (Ethics & Legal Position)

NoahAI는 **금융상품 판매자, 운용자, 중개자가 아니다.**  
**투자 판단에 대한 법적 책임은 사용자에게 있다.**  
NoahAI는 **설명 가능한 AI(XAI) 기반 판단 보조 인프라**이다.

- AI의 판단은 **데이터 근거**에 의해 설명 가능해야 한다(XAI).  
- 사용자의 자산·API 키는 **절대 NoahAI 서버로 이전되지 않는다.**  
- AI는 **인간의 욕망이 아닌 합리적 판단 보조**를 제공한다. 실행은 사용자·외부 시스템 책임.  
- Noah AI Labs는 **AI 금융 윤리·투명성 표준**을 지향한다(기술 기원: AI 디지털케어로그, DAL).  

---

## 🌟 기술 철학과 확장 원리

### 핵심 철학
> **"판단·설명·기록·검증·환류만 담당하는 AI 자산 의사결정 인프라"**

NoahAI는 **인간의 감정적 판단 부담을 구조적으로 분산**시키는 인프라이다.  
실행·자금 이동·법적 행위는 항상 사용자 또는 외부 시스템이 담당한다.

---

## 📊 구현 상태 구분 (Already Implemented / In Progress / Extensible)

### ✅ Already Implemented (실구현/실운영/완료)

**근거**: 실제 코드/문서/운영 로그 기반

#### 1. 암호화폐 판단 인프라 (2024.11~ 실환경 24/7 운영)
- **Decision Layer**: `trading/analyzer.py`, `trading/evaluator.py`, `trading/ai/ai_manager.py`
- **Execution Bridge**: `api/binance_client.py`, `trading/unified_trader.py` (CCXT)
- **Audit & Replay**: `trading/recorder.py`, `log_system/*`
- **다중 거래소**: 바이낸스, 바이비트, OKX, 비트겟, 업비트, 빗썸 (판단·기록은 NoahAI, 집행은 외부 API)
- **운영 검증**: 2024년 11월부터 약 1년 이상 실환경 검증, Binance API 정책 변경 대응 완료

#### 2. Alpha Arena (v3.8.8.6+) — 연구·검증 모드
- **근거**: `trading/alpha_arena/alpha_arena_trader.py`
- LLM 기반 판단 실험/벤치마크 (DeepSeek 3.1, Qwen 3 Max)
- 일반 서비스와 분리된 독립 구조. 집행은 Binance Futures API

#### 3. Paper Trading 모드
- 실제 집행 없이 전략·판단 검증. API 키 불필요

#### 4. Chart Screenshot Analyzer (v3.8+)
- **근거**: `trading/ai/chart_screenshot_analyzer.py`
- OCR 기반 차트 분석, LLM 판단 제안 생성(실행 지시 아님)

#### 5. 로그/XAI/DB 시스템
- **근거**: `log_system/*`, `trading/recorder.py`, 문서의 XAI 정책
- 모든 판단 과정 로그 기록, 재현·감사 가능

#### 6. 생활금융 의사결정 보조 인프라 (v3.8.9.15~18) ✅
- **근거**: `trading/life_finance_products.py`, `trading/life_finance_assistant.py`, `ui/widgets/life_finance_widget.py`
- **생활금융 Phase 3 완성**:
  - 대출(20개)·보험(20개)·예적금(20개) 비교 엔진, loan_type 필터·월납입액 계산
  - AI 어시스턴트 의도 라우팅: "보험 추천" → `_handle_compare_insurance()` 정확 연결
- **Phase 1 신용도 기반 개인화 상담**:
  - 신용도/위험도 드롭다운 UI (`좋음(750~900)` / `보통` / `낮음`)
  - `apply_credit_adjustment_to_loans()`: 신용도별 ±0.5% 금리 조정
  - AI 응답에 "신용도(좋음 🟢)를 반영한 예상 금리: 3.75%" 포함
- **테스트**: `tests/test_life_finance_assistant.py` 9 passed ✅

#### 6-1. 세무 계산 서비스 (v3.8.9.18) ✅ **NEW**
- **근거**: `trading/tax_calculation_service.py`
- **2026년 세법 기준 세무 계산**:
  - `calc_year_end_tax_settlement()`: 연말정산 종합 (근로소득공제·누진세율·카드·의료비·교육비·기부금·연금저축·IRP)
  - `check_financial_income_comprehensive_tax()`: 금융소득종합과세 판정 (이자+배당 2000만원)
  - `calc_financial_investment_tax()`: 금투세 예상 세액 (국내 기본공제 500만원, 해외·ETF 250만원)
  - `compare_tax_saving_accounts()`: ISA / 연금저축 / IRP 절세 효과 비교
- **AI 어시스턴트 연동**: `TAX_SETTLEMENT` / `CHECK_FINANCIAL_INCOME_TAX` / `CALC_INVESTMENT_TAX` / `COMPARE_TAX_ACCOUNTS` 인텐트
- **책임 경계**: 계산·요약 제공, 신고·납부·제출은 외부 주체 책임
- **테스트**: `tests/test_tax_calculation_service.py` **53 passed** ✅

#### 6-2. 금융 이상 탐지 서비스 (v3.8.9.18) ✅ **NEW**
- **근거**: `trading/fraud_detection_service.py`
- **패턴 기반 금융 위협 탐지**:
  - `analyze_voice_phishing()`: 보이스피싱 12개 + 스미싱 5개 패턴, risk_level: low~critical
  - `detect_abnormal_transactions()`: z-score 이상·심야이체·쪼개기·신규계좌·현금인출
  - `check_predatory_loan()`: 법정최고금리 20% 초과·선납수수료·원금보장 사기
- **AI 어시스턴트 연동**: `ANALYZE_FRAUD_MESSAGE` / `DETECT_ABNORMAL_TX` / `CHECK_PREDATORY_LOAN` 인텐트
- **책임 경계**: 패턴 탐지·경고 제공, 법적 조치·신고는 사용자 책임
- **테스트**: `tests/test_fraud_detection_service.py` **32 passed** ✅

#### 7. 주식 분석 서비스 및 가드레일 (v3.8.9.16) ✅ **NEW**
- **근거**: `trading/stock_analysis_service.py`, `trading/stock_order_guardrails.py`
- **StockAnalysisService**: 주식·ETF 분석 서비스 (판단 계층)
  - `score_stock()`: 모멘텀·수익률·거래량 기반 점수 (0~100)
  - `score_etf()`: NAV 괴리율·추적오차·거래대금 기반 ETF 전용 점수
  - `ETFMetrics`: NAV 괴리율·추적오차·위험 등급 평가 컨테이너
  - `evaluate_trade_signal(is_etf=True)`: ETF etf_risk 기반 BUY/SELL/HOLD 분기
  - `run_auto_trade_cycle()`: 주식·ETF 자동매매 1회 사이클 (Mock/Live 분기)
  - 실행 제어 원칙: 자동매매 실행 자체는 START/STOP(AUTO) 상태로 제어하며, 설정 키(`stock_auto_trading.auto_start`, legacy `enabled`)는 탭 진입 시 자동 예약 시작 옵션으로만 사용
- **v3.8.9.16 3가지 고도화 원칙 (철학 정합)**
  - 주식/ETF 유니버스 선정기: 후보군 자동 선별 + 점수 근거 XAI 저장
  - AI 명령 실행기: 자연어 의도를 정책으로 변환하고 기존 자동 루프에 반영
  - 설정 UI 보강: 초보자/디지털약자도 자동 정책 상태를 쉽게 이해·통제
  - 해석 기준: 위 3가지는 수동화가 아니라 자동 의사결정 품질·투명성·접근성 강화
  - 코인과의 관계: 코인 경로는 일부가 내장 파이프라인으로 동작하며, 주식/ETF는 시장구조 차이로 명시 레이어를 강화
- **StockOrderGuardrails**: 14개 테스트 통과 ✅
  - `evaluate_stock_order_guardrails()`: 장중·금액·수량·모드·최소수량·단위 복합 검증
  - `is_krx_market_open()`: 한국 정규장 시간 판정
  - 브로커별 최소수량/단위 정책 적용 (Kiwoom/Shinhan/MiraeAsset)

---

### 🔄 In Progress (진행 중: 내부 테스트/안정화/Phase)

**근거**: 코드 구조 존재, UI/인터페이스 완료, 내부 테스트 단계

#### 1. ETF/주식 판단 인프라 운영 고도화 (상시 운영 + 안전정책형)
- **근거**: `trading/exchanges/interfaces/stock_exchange.py`, `trading/exchanges/adapters/kiwoom_stock_adapter.py`, `trading/stock_analysis_service.py`
- **상태**: StockAnalysisService 완성, ETF/주식 신호 분기 완성, 증권사 어댑터 경로 완성. 상시 운영 가능하며, 실주문은 `enable_stock_live_order`/`allow_live_order` 정책으로 제어된다.
- **완성된 부분**: ETF/주식 분석·신호·가드레일·AI 컨텍스트 생성 ✅
- **운영 중 항목**: 실제 사용자/테스터가 상시 사용 중이며(내부 운영 기준 약 30명), 정책형 실주문 제어 하에서 운영 데이터를 축적한다.
- **고도화 항목**: 브로커별 운영 파라미터 튜닝, OS/브로커 편차 대응, 실주문 정책·가드레일 세분화
- **실행**: 외부 증권사 API (집행 브리지만 NoahAI)

#### 2. 오픈소스 LLM 전환 고도화
- **근거**: `trading/ai/openai_client.py` (`base_url` 지원)
- **상태**: 코드 구조상 전환 준비 완료. 다양한 LLM API 통합 가능
- **다음 단계**: DeepSeek/Qwen 등 오픈소스 LLM 통합 테스트

---

### 🔮 Extensible by Current Architecture (현재 구조로 가능한 확장 경로)

**조건부/가능성**: 현재 아키텍처가 지원하나, 구현·검증·외부 연동 필요

#### 1. 해외주식/선물 판단 인프라
- **조건**: 외부 증권사/거래소 API 연동 필요
- **근거**: 동일한 `StockExchange` 인터페이스 패턴, `unified_trader.py` 어댑터 구조 재사용 가능
- **경계**: 실행은 외부 API, NoahAI는 판단·기록만

#### 2. 부동산 데이터 기반 판단 실험
- **조건**: 부동산 시세 API 연동, 데이터 수집 파이프라인 구축 필요
- **근거**: `analyzer.py`, `evaluator.py` 패턴 재사용 가능, `recorder.py` 스키마 확장 가능
- **경계**: 매매·자금 이동은 외부·사용자 책임, 포트폴리오 자동 운용 아님

#### 3. 일반 금융 (예금/적금/채권 등)
- **조건**: 금융상품 정보 API 연동 필요
- **근거**: 동일한 판단·설명·기록 파이프라인 적용 가능
- **경계**: 가입·이체·계약은 외부 기관·사용자 책임

#### 4. 기관 연계 (Enterprise)
- **조건**: 기관별 API/인터페이스 연동 필요
- **근거**: Execution Bridge Layer 구조로 다양한 외부 시스템 연결 가능
- **경계**: 실행·계약·법적 책임은 기관·외부 시스템

#### 5. 음성/대화형 인터페이스 확장
- **현재 상태**: 베타 운영 (TTS 즉시 사용 가능, STT는 옵션 의존성 설치 시 사용)
- **근거**: `ui/widgets/ai_voice_module.py`, `ui/widgets/ai_assistant_widget.py`
- **운영 조건**: STT는 `SpeechRecognition` + `PyAudio` 설치 환경에서만 마이크 인식 가능
- **경계**: 설명·조회 중심, 실행 지시 아님

---

## 🎯 확장 원리 (원리-검증-확장-경계)

### (원리) Decision Pipeline + Adapter + Audit/Replay
- **Decision Layer**: Analyzer / Evaluator / AIManager / Risk Guard / Recorder / Explainer
- **Execution Bridge**: Binance API, CCXT, Stock Broker Adapter (예: Kiwoom)
- **Audit & Replay**: Logs / DB / Replay / XAI

**근거**: `trading/analyzer.py`, `trading/evaluator.py`, `trading/ai/ai_manager.py`, `trading/recorder.py`, `api/binance_client.py`, `trading/unified_trader.py`, `trading/exchanges/adapters/kiwoom_stock_adapter.py`

### (검증) 암호화폐에서 24/7 운영 + 로그/XAI + 멀티 거래소
- 2024년 11월부터 실환경 24/7 운영
- 모든 판단 과정 로그 기록·재현 가능
- 6개 거래소 동시 연동 검증
- Binance API 정책 변경 등 외부 환경 변화 즉시 대응

**근거**: 릴리스 히스토리, 운영 로그, `log_system/*`, `trading/recorder.py`

### (확장) 동일 구조로 ETF/주식/해외주식/선물/부동산/일반금융까지 '판단 인프라' 확장 가능
- 자산 타입만 교체, 동일한 Decision Pipeline 재사용
- 새로운 Execution Bridge (어댑터) 추가로 외부 시스템 연결
- Audit & Replay 스키마 확장

**근거**: `trading/exchanges/interfaces/stock_exchange.py` (인터페이스 패턴), `trading/exchanges/adapters/` (어댑터 구조)

### (경계) 실행/계약/자금 이동 책임은 항상 사용자/외부기관
- 주문·체결·자금 이동: 외부 거래소·증권사·금융기관 API
- 계약·법적 책임: 사용자 또는 외부 기관
- NoahAI는 판단·설명·기록·검증만 담당

**근거**: `trading/unified_trader.py` (브리지 역할), `api/binance_client.py` (외부 API 호출), 역할 분리 표 (Financial AI Infrastructure Map 섹션)

---

## 🏢 산업 연계 (Enterprise 관점)

### 역할 분리: NoahAI vs External Institutions

| 기능 영역 | NoahAI (Decision Hub) | 외부 기관 (Execution) | 사용자 (Owner) |
|----------|----------------------|---------------------|---------------|
| **판단·분석** | ✅ 담당 | ❌ | ❌ |
| **설명·기록** | ✅ 담당 | ❌ | ❌ |
| **검증·재현** | ✅ 담당 | ❌ | ❌ |
| **주문·체결** | ❌ | ✅ 거래소·증권사 API | ❌ |
| **자금 이동** | ❌ | ✅ 금융기관·은행 | ✅ 최종 책임 |
| **계약·법적** | ❌ | ✅ 금융기관·증권사 | ✅ 최종 책임 |
| **상품 판매** | ❌ | ✅ 금융기관·증권사 | ❌ |

**연계 가능성**: Execution Bridge Layer 구조로 다양한 외부 시스템(거래소/증권사/은행/자산운용/핀테크/플랫폼)과 연결 가능.  
**조건**: 외부 API 연동, 계약·법적 책임 명확화 필요.  
**경계**: 실행·계약·법적 책임은 항상 외부 기관·사용자.

---

## 🌍 인류사회적 의의 및 개발 목적

NoahAI는 단순히 재테크를 자동화한 시스템이 아니라,  
**인공지능이 인간의 판단 능력을 확장하는 새로운 문명적 도약의 시작**을 상징합니다.  

### 핵심 개발 목적

#### 1. 정보 격차 해소를 통한 경제적 기회 균등
- 전문가 수준의 시장 분석을 누구나 접근 가능하게 제공
- 복잡한 금융 정보를 AI가 요약하여 이해하기 쉽게 전달
- 다양한 거래소와 자산에 대한 정보 접근성 차이 해소

#### 2. 스트레스 해소 및 삶의 질 향상
- 24시간 시장 모니터링·판단 부담을 인프라가 분산. 실행은 사용자·외부 시스템.
- 감정적 판단으로 인한 스트레스 완화: 데이터 기반 판단·설명·기록 제공

#### 3. 시니어 친화를 통한 디지털 격차 해소
- 복잡한 기술적 지식 없이도 전문가 수준의 **판단·설명** 접근 가능
- 음성·대화로 설명·조회 중심 지원. 실행 지시 아님.

#### 4. 사고 방지를 통한 자산 보호
- 리스크 가드·가드레일·검증. 모든 판단 과정 로그·재현 가능.
- 실행·자금 이동은 사용자·외부 시스템 책임.

#### 5. 판단 능력의 확장
- 24/7 분석·판단·기록 인프라. 실행은 외부.
- 수백 개 지표 동시 분석·설명. 감정·편향 없는 데이터 기반 판단 보조.

### 사회적 가치

- 인간의 감정·편향을 넘어선 **판단 보조**·설명 가능 구조  
- 의료·돌봄에서 시작된 기록·분석·환류 구조가 금융 의사결정에 재설계 적용  
- NoahAI는 **자산 운용·자동 투자 주체가 아님**. 판단·설명·기록·검증 인프라.  
- Noah AI Labs의 목표: "AI로 인간의 판단 부담을 분산시키는 구조 창조" (디지털케어로그 철학과 연속)

---

## 🧾 기술검증 및 공개 정책

본 백서는 실제 구현된 코드 기반(NoahAI v3.8.9.21)을 토대로 작성되었다.  
모든 알고리즘은 **판단·기록·검증** 관점에서 실환경 로그 및 데이터베이스 기록을 통해 검증되었다.

**테스트 커버리지 (2026-05-07 기준)**: `python -m pytest tests/ -q` → **864 passed, 6 skipped** ✅

**근거 출처**: 본 문서는 `docs/*` 및 `trading/*` 코드 구조를 근거로 작성되며, 외부 공개 시 민감정보는 제거한다.

- **공개 범위**: 아키텍처, 데이터 흐름, 학습·환류 구조, 학습데이터 스키마, 로그 시스템  
- **비공개 범위**: OpenAI API 키, 거래소 API 키, 개인 데이터, 설정 파일 세부사항, 인증 토큰  
- **검증 방식**: 실환경 판단·기록 로그 검증 + 데이터베이스 기록 분석 + 외부 API 연동 결과 반영
- **근거 파일**: `trading/analyzer.py`, `trading/evaluator.py`, `trading/ai/ai_manager.py`, `trading/recorder.py`, `api/binance_client.py`, `trading/unified_trader.py`, `trading/exchanges/interfaces/stock_exchange.py`, `trading/exchanges/adapters/kiwoom_stock_adapter.py`, `log_system/*`

추가 사용자 적용 정책 (v3.8.9.21):
- OpenAI 설정/AI 어시스턴트 설정관리에서 원클릭 모델 프리셋(절약형/균형형/정밀형) 제공
- 프리셋 선택 시 예상 비용 레벨(낮음/중간/높음) 표시로 사용자 이해도 향상
- 고위험 변경 요청 시 설명 가능한 경고/최종확인 게이트를 거쳐 오적용을 최소화

다음 기획(설계 방향):
- 초기 환경설정 단계에서 AI가 질문-응답으로 사용자 성향을 파악해 맞춤형 설정 제안
- 이유 설명(XAI) + 단계적 변경 권고 + 7일/최소표본 검증 후 재조정 루프 고정

---

## 🔬 상세 기술 명세 (Detailed Technical Specifications)

### 1. AI 강화학습 엔진 상세 구조

#### 1.1 실시간 학습 루프 (Reinforcement Learning Loop)

NoahAI의 강화학습 시스템은 다음과 같은 5단계 피드백 루프로 구성됩니다:

```
1. 판단 (Decision Making)
   ↓
2. 결과 (Outcome Recording)
   ↓
3. 로그 (Complete Logging)
   ↓
4. 복기 (Pattern Analysis)
   ↓
5. 정책 보정 (Policy Adjustment)
   ↑
   └─────────────────────── (다음 거래로 반복)
```

**구현 위치**: `trading/ai/ai_manager.py`, `trading/exchange_learning_manager.py`

#### 1.2 보상 함수 설계 (Reward Function Design)

**수익 거래 보상**:
```
R_profit = α × profit_rate × confidence_score × (1 - risk_penalty)
```
- `α`: 보상 스케일링 계수 (기본값: 1.0)
- `profit_rate`: 실제 수익률 (0.0 ~ 1.0)
- `confidence_score`: AI 신뢰도 (0.0 ~ 1.0)
- `risk_penalty`: 리스크 페널티 (0.0 ~ 0.5)

**손실 거래 보상**:
```
R_loss = -β × |loss_rate| × (1 + consecutive_loss_penalty)
```
- `β`: 손실 스케일링 계수 (기본값: 1.2)
- `loss_rate`: 실제 손실률 (음수)
- `consecutive_loss_penalty`: 연속 손실 페널티 (0.0 ~ 0.3)

**리스크 관리 보상**:
```
R_risk_management = γ × (early_exit_bonus - late_exit_penalty)
```
- `γ`: 리스크 관리 보상 계수 (기본값: 0.5)
- `early_exit_bonus`: 조기 손절 보너스 (0.0 ~ 0.2)
- `late_exit_penalty`: 늦은 손절 페널티 (0.0 ~ 0.3)

**구현 위치**: `trading/ai/ai_manager.py` - `analyze_loss_trade()`, `analyze_profit_trade()`

#### 1.3 패턴 유사성 분석 알고리즘 (Pattern Similarity Analysis)

**유사도 계산**:
```
similarity_score = w₁×RSI_sim + w₂×volatility_sim + w₃×trend_sim + w₄×volume_sim
```
- `w₁, w₂, w₃, w₄`: 가중치 (합 = 1.0)
- 각 `sim` 값은 코사인 유사도 또는 유클리드 거리 기반

**패턴 매칭 프로세스**:
1. 현재 시장 상태 벡터화: `[RSI, MACD, volatility, trend_strength, volume_ratio]`
2. 과거 패턴 데이터베이스에서 k-NN 검색 (k=5)
3. 유사도 임계값 이상 패턴만 선택 (threshold = 0.7)
4. 선택된 패턴의 성과 분석 (승률, 평균 수익률)
5. 패턴 기반 진입/회피 결정

**구현 위치**: `trading/ai/ai_manager.py` - `analyze_pattern_similarity()`

#### 1.4 동적 임계값 조정 알고리즘 (Dynamic Threshold Adjustment)

**시장 국면별 임계값 조정**:
```
adjusted_threshold = base_threshold × regime_multiplier × performance_factor
```

**국면 감지**:
- **LOW 변동성**: `volatility < dynamic_vol_threshold × 0.8`
- **NORMAL 변동성**: `dynamic_vol_threshold × 0.8 ≤ volatility ≤ dynamic_vol_threshold × 1.5`
- **HIGH 변동성**: `volatility > dynamic_vol_threshold × 1.5`

**성과 기반 조정**:
```
performance_factor = 1.0 + (win_rate - 0.5) × 0.2 - (consecutive_losses × 0.05)
```

**구현 위치**: `trading/analyzer.py` - `_determine_basic_signal()`, `calculate_dynamic_volatility_threshold()`

### 2. 시장 분석 엔진 상세 구조

#### 2.1 기술적 지표 계산 (Technical Indicators)

**RSI (Relative Strength Index)**:
```
RSI = 100 - (100 / (1 + RS))
RS = Average Gain / Average Loss (14-period)
```

**MACD (Moving Average Convergence Divergence)**:
```
MACD = EMA(12) - EMA(26)
Signal = EMA(9) of MACD
Histogram = MACD - Signal
```

**볼린저 밴드 (Bollinger Bands)**:
```
Middle Band = SMA(20)
Upper Band = Middle + (2 × Standard Deviation)
Lower Band = Middle - (2 × Standard Deviation)
BB Position = (Price - Lower) / (Upper - Lower)
```

**구현 위치**: `trading/analyzer.py` - `calculate_indicators()`

#### 2.2 신호 생성 알고리즘 (Signal Generation Algorithm)

**기본 신호 결정 로직**:
```python
if RSI ≤ extreme_oversold_threshold:
    signal = "LONG"
elif RSI ≥ extreme_overbought_threshold:
    signal = "SHORT"
elif RSI ≤ oversold_threshold and momentum > -trend_momentum_threshold:
    signal = "LONG"
elif RSI ≥ overbought_threshold and momentum < trend_momentum_threshold:
    signal = "SHORT"
elif oversold_threshold < RSI < overbought_threshold:
    if momentum > momentum_threshold:
        signal = "LONG"
    elif momentum < -momentum_threshold:
        signal = "SHORT"
    else:
        signal = "HOLD"
```

**AI 강화 신호 생성**:
```python
if ai_confidence > 0.7:
    final_signal = ai_signal  # AI 신호 우선
elif ai_confidence > 0.5 and ai_signal == technical_signal:
    final_signal = ai_signal  # AI와 기술적 지표 일치 시 강화
    confidence = min(1.0, confidence × 1.2)
else:
    final_signal = technical_signal  # 기술적 지표 우선
```

**구현 위치**: `trading/analyzer.py` - `_determine_basic_signal()`, `_generate_ai_enhanced_signal()`

#### 2.3 코인 선택 알고리즘 (Coin Selection Algorithm)

**5가지 차원 점수 계산**:
```
total_score = (
    volatility_score × 0.35 +    # 변동성 (35%)
    trend_score × 0.25 +           # 추세 강도 (25%)
    volume_score × 0.20 +          # 거래량 (20%)
    trade_freq_score × 0.10 +      # 거래 빈도 (10%)
    depth_score × 0.05 +            # 호가창 깊이 (5%)
    rsi_score × 0.05               # RSI (5%)
)
```

**점수 정규화**:
```
total_score = max(36, min(58, total_score))  # 36-58 범위로 조정
```

**구현 위치**: `trading/evaluator.py` - `_evaluate_coins_with_ai()`

### 3. TP/SL 최적화 시스템 (v3.8.9.11)

#### 3.1 가격 정밀도 자동 조정 (Price Precision Auto-Adjustment)

**문제**: GALA, JASMY 등 저가 알트코인에서 TP 주문 실패 (`-2021: Order would immediately trigger`)

**근본 원인**:
1. `trader.py`: 키 이름 불일치 (`price_precision` vs `pricePrecision`)로 `price_prec`가 항상 2로 고정
2. `binance_client.py`: TP 방향 검증 누락 (SHORT 포지션에서 TP > 현재가인 경우 감지 못함)

**해결 방법**:
```python
# 키 이름 호환성 처리
price_prec = exchange_info.get('pricePrecision') or exchange_info.get('price_precision', 2)

# 저가 코인 자동 감지 및 정밀도 강제 조정
if current_price < 0.02:  # 저가 코인 감지
    price_prec = max(price_prec, 3)  # 최소 3자리 정밀도 보장
    if current_price < 0.001:
        price_prec = max(price_prec, 4)  # 매우 저가 코인은 4자리

# TP 방향 검증
if side == "LONG" and tp_price <= current_price:
    raise ValueError(f"LONG 포지션 TP 가격({tp_price})은 현재가({current_price})보다 높아야 합니다")
elif side == "SHORT" and tp_price >= current_price:
    raise ValueError(f"SHORT 포지션 TP 가격({tp_price})은 현재가({current_price})보다 낮아야 합니다")
```

**구현 위치**: `trading/trader.py`, `api/binance_client.py`

**효과**: 모든 저가 알트코인에서 정확한 TP/SL 가격 계산 및 주문 성공

### 4. AI API 아키텍처 및 오픈소스 전환

#### 4.1 현재 AI API 구조

**계층 구조**:
```
AIManager (trading/ai/ai_manager.py)
  ├─ OpenAIClient (trading/ai/openai_client.py)
  │   ├─ OpenAI SDK 래퍼
  │   ├─ base_url 지원 (오픈소스 LLM 전환)
  │   └─ model 설정 가능
  └─ 주요 기능:
      ├─ analyze_market_conditions() - 시장 분석
      ├─ analyze_exit_conditions() - 청산 분석
      ├─ analyze_pattern_similarity() - 패턴 유사성 검증
      ├─ analyze_loss_trade() - 손절 거래 분석
      ├─ analyze_profit_trade() - 익절 거래 분석
      └─ chat_completion() - 대화형 AI
```

#### 4.2 오픈소스 LLM 전환 지원

**현재 구조의 장점**: `OpenAIClient`는 이미 `base_url`을 지원하므로, **코드 변경 없이** 다른 LLM API로 전환 가능

**전환 예시**:
```python
# DeepSeek API 사용
self.ai_manager = AIManager(
    api_key="sk-...",
    model="deepseek-chat",
    base_url="https://api.deepseek.com"
)

# OpenRouter 사용 (다양한 모델 선택)
self.ai_manager = AIManager(
    api_key="sk-or-...",
    model="qwen/qwen-2.5-72b-instruct",
    base_url="https://openrouter.ai/api/v1"
)

# 로컬 LLM 서버 사용
self.ai_manager = AIManager(
    api_key="not-needed",
    model="local-model",
    base_url="http://localhost:8000/v1"
)
```

**구현 위치**: `trading/ai/openai_client.py` - `__init__()` 메서드

**참고 문서**: `docs/AI_API_ARCHITECTURE.md`

### 5. Alpha Arena 모드 상세 구조 (v3.8.8.6+)

#### 5.1 LLM 기반 판단 실험/벤치마크 환경

**아키텍처** (연구·검증 모드, 일반 서비스와 분리):
```
Alpha Arena Trader (독립 모듈)
  ├─ LLM 엔진 선택 (DeepSeek 3.1 / Qwen 3 Max)
  ├─ 시장 데이터 수집 (6개 코인: BTC, ETH, SOL, XRP, DOGE, BNB)
  ├─ Alpha Arena 형식 프롬프트 생성
  ├─ LLM 응답 파싱 (MODEL_CHAT + TRADING_DECISIONS)
  └─ 판단 결과→외부 API 브리지 (집행은 Binance API)
```

**프로세스**:
1. **시장 데이터 수집**: 6개 코인 시세/지표 + 계좌 정보 + 현재 포지션
2. **LLM 프롬프트 생성**: Alpha Arena 벤치마크 형식 프롬프트
3. **LLM 응답**:
   - `MODEL_CHAT`: 사람이 읽는 설명 (화면 표시용)
   - `TRADING_DECISIONS`: 실행 가능한 JSON (외부 API로 전달)
4. **집행** (외부 시스템):
   - `TRADING_DECISIONS` 파싱 및 검증
   - 가드레일 적용 (레버리지, 리스크 캡, 쿨다운 등)
   - **Binance Futures API가 실제 주문·체결 수행**

**가드레일 시스템**:
- **레버리지 범위**: 10-20x 자동 클램핑
- **TP/SL 필수**: 진입 시 반드시 TP/SL 지정 필요 (없으면 실행 안 함)
- **쿨다운**: 동일 코인 재진입 최소 30초 간격
- **리스크 캡**: 틱당 최대 리스크 제한 (기본 1500 USDT)
- **최대 동시 포지션**: 6개 코인 (심볼당 1개)

**초기 자금 기준 선택** (v3.8.8.8+):
- 만불 ($10,000): Alpha Arena 벤치마크와 동일 (기본값)
- 천불 ($1,000): 소액 거래 테스트용
- 백불 ($100): 최소 자금으로 시작
- 선택한 기준에 따라 LLM의 거래 판단이 달라짐

**구현 위치**: `trading/alpha_arena/alpha_arena_trader.py`

**참고 문서**: `docs/ALPHA_ARENA_DEVELOPMENT.md`, `docs/USER_GUIDE.md` (AlphaArena 섹션)

### 6. Chart Screenshot Analyzer 상세 구조

#### 6.1 OCR 기반 차트 분석 시스템

**아키텍처**:
```
Chart Screenshot Analyzer
  ├─ 이미지 업로드 (로컬 파일)
  ├─ OCR 텍스트 추출 (PaddleOCR)
  ├─ 특징 파싱 (심볼, 타임프레임, MA/EMA, 가격)
  ├─ LLM 분석 호출 (OpenAIClient)
  └─ 거래 제안 생성 (진입/청산/목표가)
```

**처리 프로세스**:
1. **이미지 업로드**: 사용자가 거래소 캔들 차트 스크린샷 업로드
2. **OCR 추출**: PaddleOCR로 차트의 텍스트 정보 추출
3. **특징 파싱**:
   - 심볼 인식: BTCUSDT, BTC/USDT, KRW-BTC 등
   - 타임프레임 인식: 1D, 4H, 1H, 15M, 5M, 1W 등
   - 이동평균 인식: MA20, EMA50 등
   - 가격 정보 추출
4. **LLM 분석**: 추출된 특징을 기반으로 LLM이 거래 제안 생성
5. **결과 표시**: 진입/청산/목표가 등 구체적인 거래 계획 제시

**반환 스키마**:
```json
{
  "action": "ENTER_LONG" | "ENTER_SHORT" | "WAIT",
  "horizon": "scalp" | "intraday" | "short_swing" | "swing" | "position",
  "stance": "LONG" | "SHORT" | "NEUTRAL",
  "confidence": 0.0-1.0,
  "confidence_basis": "string(KO)",
  "scenarios": [
    {
      "title": "string(KO)",
      "prob": 0.0-1.0,
      "narrative": "string(KO)"
    }
  ],
  "plan": {
    "entry": number,
    "entry_zone": [number, number],
    "stop": number,
    "tp": [number, number],
    "notes": "string(KO)"
  }
}
```

**구현 위치**: `trading/ai/chart_screenshot_analyzer.py`

**참고 문서**: `docs/TRADING_FLOW.md` (Chart Screenshot Analyzer 섹션)

### 7. ETF/주식 확장 아키텍처 (v3.8.9.11+)

#### 7.1 현재 구현된 확장 기반

**구현된 확장 인프라** (In Progress):
- ✅ 설정 구조 추가 (`enabled_stock_brokers`, `stock_broker_configs`)
- ✅ 설정 UI 확장 (키움증권 API 입력 필드)
- ✅ 대시보드 서비스 전환 로직 (`show_stock_content()`)
- ✅ 증권사별 탭 생성 (`create_service_sub_tabs('stock')`)
- ✅ `StockExchange` 인터페이스 생성 (`trading/exchanges/interfaces/stock_exchange.py`)
- ✅ `KiwoomStockAdapter` 기본 구조 생성 (`trading/exchanges/adapters/kiwoom_stock_adapter.py`)

**확장 시 활용 가능한 기존 구조**:
- 기존 `evaluator.py` 패턴을 활용한 ETF 종목 **판단·선정** 로직 구현 가능
- 기존 `analyzer.py` 패턴을 활용한 ETF 시장 **분석·판단** 로직 구현 가능
- **집행은 외부 증권사 API**. `unified_trader.py`/어댑터는 "집행 브리지"로만 사용
- 기존 `recorder.py` 구조를 활용한 **판단·결과 기록** 스키마 확장 가능

#### 7.2 기술적 설계 원칙

**공통 인터페이스 활용**:
- `StockExchange` 인터페이스는 `ExchangeInterface`를 확장
- 암호화폐 거래소와 동일한 패턴으로 구현
- AI 분석 엔진 재사용 (`AIManager`는 자산 타입 무관하게 사용 가능)

**UI 일관성**:
- 블록체인 서비스와 완전히 동일한 2단 레이아웃 구조
- 좌측: 제어/잔고/포지션/통계
- 우측: 실시간 로그

**참고 문서**: 
- `docs/STOCK_ETF_DEVELOPMENT_GUIDE_20260118.md`
- `docs/STOCK_ETF_CURRENT_STATUS_20260118.md`
- `docs/AI_API_ARCHITECTURE.md`

---

## 📋 부록 (Appendix)

### 주요 파일 구조 (보안 고려)
```
noahai_client/
├── main.py                 # 메인 애플리케이션 진입점
├── ui/                     # 사용자 인터페이스
│   ├── dashboard_modern.py  # 메인 대시보드
│   ├── login_modern.py      # 로그인 화면
│   └── settings_modern.py   # 설정 화면
├── trading/               # 거래 로직
│   ├── trader.py          # 바이낸스 거래 엔진
│   ├── unified_trader.py  # CCXT 거래 엔진
│   ├── evaluator.py       # 코인 선택 엔진
│   ├── analyzer.py        # 시장 분석 엔진
│   ├── ai/                # AI 모듈
│   │   ├── ai_manager.py  # AI 관리 모듈
│   │   ├── auto_optimizer.py # 자동 최적화
│   │   └── openai_client.py # AI 클라이언트
│   └── recorder.py        # 거래 기록 관리
├── api/                   # API 연동
│   ├── backend_api.py     # 백엔드 서버 연동
│   └── binance_client.py  # 바이낸스 API 클라이언트
├── log_system/            # 로깅 시스템
│   ├── log_adapter.py     # 통합 로그 어댑터
│   └── log_stream.py      # 실시간 로그 스트림
├── config/                # 설정 파일 (보안)
│   ├── settings.py        # 설정 관리
│   └── [보안 파일들]       # API 키 및 인증 정보
└── data/                  # 데이터 저장소 (보안)
    ├── trading.db         # 거래 데이터베이스
    └── logs/              # 로그 파일
```

**보안 고려사항:**
- `config/` 및 `data/` 디렉토리는 실제 파일명을 공개하지 않음
- API 키, 토큰, 개인 데이터는 별도 보안 영역에 저장
- 사용자별 데이터는 계정별로 분리되어 관리

### AI 데이터 스키마
```json
{
    "ai_learning_data": {
        "signal_history": [
            {
                "timestamp": "2025-10-20T03:25:00Z",
                "symbol": "BTCUSDT",
                "signal": "LONG",
                "confidence": 0.85,
                "market_conditions": {...},
                "result": "profit",
                "profit_rate": 0.032
            }
        ],
        "pattern_analysis": {
            "similarity_threshold": 0.7,
            "pattern_types": ["bullish", "bearish", "sideways"]
        },
        "performance_metrics": {
            "win_rate": 0.68,
            "avg_profit_rate": 0.023,
            "avg_loss_rate": -0.015
        },
        "dynamic_thresholds": {
            "confidence_threshold": 0.4,
            "volatility_threshold": 0.05
        }
    },
    "trade_log": [
        {
            "timestamp": "2025-10-20T03:25:00Z",
            "symbol": "BTCUSDT",
            "side": "LONG",
            "entry_price": 45000.0,
            "exit_price": 45150.0,
            "quantity": 0.001,
            "pnl": 0.15,
            "pnl_percent": 0.33
        }
    ],
    "analysis_log": [...],
    "ai_decisions": [...],
    "ai_optimization": [...]
}
```

### 성능 벤치마크

#### 시스템 성능 지표
- **시작 시간**: 46초 → 즉시 시작 (99% 성능 향상)
- **거래 주기**: 5-10초 초단위 트레이딩
- **응답 속도**: 실시간 시장 변화 대응
- **시스템 안정성**: 99% 이상 가동률
- **메모리 사용량**: 최적화된 캐싱으로 효율성 극대화

#### AI 학습·환류 지표 (참고)
- **학습 데이터 수집**: 판단·결과·패턴 수집으로 환류 구조 유지
- **지속적 개선**: 매 판단·결과마다 로그·환류 반영
- **적응성**: 시장 변화에 따른 임계값·정책 보정 (실행은 외부)

**⚠️ 디스클레이머**: 내부 로그 기반 참고치이며, 승률/수익률/거래건수 등 수치는 시장/설정/계정별로 변동하며 보장 불가. NoahAI는 수익 보장·자동 운용 주체가 아님.

#### 실전 환경 검증 지표 (근거 기반)
- **운영 기간**: 2024년 11월부터 약 1년 이상 실전 환경 검증 (근거: 릴리스 히스토리)
- **거래소 지원**: 6개 거래소 동시 운영 검증 (근거: `trading/unified_trader.py`, `api/binance_client.py`)
- **의사결정 지원 사례**: 실전 환경 의사결정 지원 사례를 통해 운영 안정성, 재현성, 로그 완결성 검증 (근거: `log_system/*`, `trading/recorder.py`)
- **안정성 검증**: Binance API 정책 변경 등 외부 환경 변화 즉시 대응 (근거: v3.8.9.9 릴리스)
- **재현성 검증**: 로그 완결성을 통한 모든 의사결정 과정 재현 가능 (근거: `trading/recorder.py`, XAI 정책)

### 릴리스 히스토리

#### v3.8.9.11 (2026-01-25) - TP/SL -2021 오류 근본 수정
**주요 변경사항**:
- **문제**: GALA, JASMY 등 저가 알트코인에서 TP 주문 실패 (`-2021: Order would immediately trigger`)
- **근본 원인**:
  1. `trader.py`: 키 이름 불일치 (`price_precision` vs `pricePrecision`)로 `price_prec`가 항상 2로 고정
  2. `binance_client.py`: TP 방향 검증 누락 (SHORT 포지션에서 TP > 현재가인 경우 감지 못함)
- **수정 내용**:
  - 키 이름 호환성 처리 (`pricePrecision` 또는 `price_precision` 둘 다 지원)
  - 저가 코인 자동 감지 및 정밀도 강제 조정 (0.001~0.02 범위)
  - TP 방향 검증 추가 (LONG/SHORT 포지션별 올바른 방향 확인)
- **효과**: 모든 저가 알트코인에서 정확한 TP/SL 가격 계산 및 주문 성공
- **기술적 세부사항**: 상세 기술 명세 섹션 3.1 참조

#### v3.8.9.9 (2025-12-27) - Binance Algo Order API 완전 구현
**주요 변경사항**:
- Binance Algo Order API 완전 구현 및 가격 정밀도 문제 해결
- 서명 생성 규칙 준수
- 조건부 주문(STOP_MARKET, TAKE_PROFIT_MARKET) 자동 Algo Order API 라우팅

#### v3.8.9.8 (2025-12-26) - Binance Algo Order API 마이그레이션
**주요 변경사항**:
- Binance Algo Order API 마이그레이션 (초기 구현)
- 2025-12-09 Binance 정책 변경 대응

#### v3.8.9.7 (2025-01-26) - Binance API 규칙 준수
**주요 변경사항**:
- Binance API 규칙 준수 및 백업 TP/SL 설정 개선

#### v3.8.9.15 (2026-04-28) — 생활금융 고도화 + ETF/주식 신호 분기 + 대시보드 UX 개선
**주요 변경사항**:
- **생활금융 Phase 3 완성**: 대출·보험·예적금 비교 엔진 + AI 의도 라우팅 + 실행형 UI 탭 연동
  - `trading/life_finance_products.py`: 신용도별 금리/이자 조정 (`apply_credit_adjustment_to_loans`, `apply_credit_adjustment_to_savings`)
  - `trading/life_finance_assistant.py`: 신용도·위험도 컨텍스트 기반 AI 상담 (`FinanceContext.credit_score/risk_level`)
  - `ui/widgets/life_finance_widget.py`: 개인화 프로필 UI + 자동 비교 갱신
- **ETF/주식 자동매매 신호 분기 강화**: `trading/stock_analysis_service.py`
  - `evaluate_trade_signal()`: `is_etf=True` 시 `etf_risk` 기반 분기 (alert=SELL, ok+고점수=BUY, warn=HOLD)
  - `analyze_symbol()`: ETF 결과에 `etf_risk` 필드 추가 (ETFMetrics.risk_level() 반영)
- **주식 주문 가드레일 강화**: `tests/test_stock_order_guardrails.py` 12→14개
  - `test_guardrail_rejects_max_quantity_exceeded`: max_quantity 한도 초과 차단
  - `test_guardrail_rejects_outside_market_hours`: 장외 시간(09:00~15:30 외) 주문 차단
- **대시보드 UX 4종 개선**: `ui/dashboard_modern.py`
  - 잔고 7초 주기 자동 갱신 (`create_exchange_balance_section` 주기 루프 추가)
  - 거래소 상태 배지 정확성 복원 (`_check_actual_exchange_status` 실제 상태 조회)
  - 개별 토글 ↔ 전역 상태 동기화 (`_running_exchanges` 세트 + `_update_global_status_ui`)
  - 설정 저장 시 탭 중복 재빌드 제거 (`refresh_after_settings_change` 중복 호출 1회 삭제)
- **종목 검색 고도화 2차**: 자동완성·부분일치 추천·원클릭 검색 제안 UI
- **자산 통합 확장**: 집중도(HHI) + crypto/stock 상관계수 + 동적 리밸런싱 액션
- **테스트 커버리지**: 864 passed, 6 skipped ✅ (2026-05-07 기준)

#### v3.8.9.11 (2026-01-25) — TP/SL -2021 오류 근본 수정
**주요 변경사항**:
- **문제**: GALA, JASMY 등 저가 알트코인에서 TP 주문 실패 (`-2021: Order would immediately trigger`)
- **ETF/주식 판단 인프라 확장**: UI 기본 구조 완료. 실행은 외부 증권사 API.
- **StockExchange 인터페이스**: `trading/exchanges/interfaces/stock_exchange.py` — 자산군별 판단 인터페이스
- **키움증권 어댑터**: `trading/exchanges/adapters/kiwoom_stock_adapter.py` — 증권사 API 집행 브리지
- **대시보드 확장**: 암호화폐/ETF/주식 자산군별 판단·기록 UX
- **기술적 세부사항**: 상세 기술 명세 섹션 7 참조

#### v3.8.8.3 (2025-10-20) - AI 시스템 완전 분석 및 문서화
**주요 변경사항**:
- AI 시스템 완전 분석 및 문서화
- 바이낸스 자체 API 전환 완료
- WebSocket 아키텍처 개선 (46초 지연 문제 해결)

#### v3.8.8 (2025-10-15) - 거래 통계 영구 저장 시스템
**주요 변경사항**:
- 거래 통계 영구 저장 시스템 구현
- SQLite 데이터베이스 기반 통계 관리

#### v3.8.0 (2025-10-12) - WebSocket 최적화
**주요 변경사항**:
- WebSocket 최적화 및 성능 향상
- API 기반 분석으로 WebSocket 의존성 제거

#### v3.7.8 (2025-10-12) - 다중 거래소 지원
**주요 변경사항**:
- 다중 거래소 지원 및 안정화
- CCXT 통합 시스템 구축

---

## 📞 연락처 및 지원

### 개발사·운영 주체 정보
- **NoahAI 제품 운영**: 노아에이아이랩스(Noah AI Labs)
- **기술 기원**: DAL(드림에이아이랩) — AI 디지털케어로그
- **웹사이트**: [Noah AI Labs 공식 웹사이트] / [DAL 공식 웹사이트]
- **이메일**: [연락처 이메일]
- **기술 지원**: [기술 지원 이메일]

### 기술 문의
NoahAI의 기술적 세부사항이나 파트너십에 대한 문의는 언제든지 환영합니다.

---

## 🔮 확장 가능성 및 기술적 잠재력 (Technical Scalability)

**참고**: 본 섹션은 "📊 구현 상태 구분" 섹션의 "Extensible by Current Architecture"와 중복되므로, 여기서는 **연구 방향**에 집중한다.

### 현재 아키텍처의 확장성 (근거 기반)

NoahAI의 현재 아키텍처는 모듈화된 설계로 인해 다양한 자산 타입과 서비스로의 확장이 용이하도록 설계되어 있다.  
모든 확장은 기존 파이프라인과 구조를 재사용하여 구현 가능하다.

**근거**: `trading/exchanges/interfaces/stock_exchange.py` (인터페이스 패턴), `trading/exchanges/adapters/` (어댑터 구조), `trading/recorder.py` (통합 스키마)

### 오픈소스 LLM 전환 가능성

**기술적 기반**:
- **근거**: `trading/ai/openai_client.py` (`base_url` 지원)
- 코드 변경 없이 다른 LLM API로 전환 가능하도록 설계되어 있다

**전환 시 연구 가능한 방향**:
- DeepSeek/Qwen 등 오픈소스 LLM 통합
- 로컬 LLM 서버 구축
- 금융 도메인 특화 파인튜닝

## 🎯 기술적 차별화 및 경쟁 우위

### 1. 검증된 실전 환경 실증 시스템
- **경쟁사**: 계획 단계 또는 제한적 기능의 프로토타입
- **NoahAI**: **2024년 11월부터 실전 환경에서 검증된 실증 기반 시스템**
- **실증 지표** (근거: 릴리스 히스토리, 운영 로그):
  - 2024년 11월부터 약 1년 이상 실전 환경 검증
  - 6개 거래소 동시 운영 검증 (근거: `trading/unified_trader.py`, `api/binance_client.py`)
  - 실전 환경 의사결정 지원 사례를 통해 운영 안정성, 재현성, 로그 완결성 검증 (근거: `log_system/*`, `trading/recorder.py`, 운영 기간 2024.11~)
  - Binance API 정책 변경 등 외부 환경 변화 즉시 대응 (안정성 검증, 근거: v3.8.9.9 릴리스)

### 2. 기술 기원 (의료·돌봄 → 금융 의사결정)
- **경쟁사**: 범용 LLM 기반 또는 단순 규칙 기반
- **NoahAI**: **의료·돌봄 영역의 기록·분석·환류 구조를 금융 의사결정에 재설계 적용**
- **기술 차별화** (근거: 기술 기원 섹션):
  - DAL이 보유한 AI 디지털케어로그 기술 기반 + Noah AI Labs의 금융 인프라 구현 (기술 기원·제품화)
  - 실전 환경에서 검증된 학습·환류 알고리즘 (근거: 2024.11~ 운영)
  - 동일한 판단·기록·설명 구조를 자산군에 독립적으로 확장 가능 (근거: `trading/exchanges/interfaces/stock_exchange.py`)

### 3. XAI (설명 가능한 AI) 철학
- **경쟁사**: 블랙박스 AI 또는 제한적 설명
- **NoahAI**: **완전한 투명성과 설명 가능성**
- **XAI 구현**:
  - 모든 의사결정 지원 과정 로그 공개
  - 실시간 AI 판단 근거 설명
  - 자연어 대화를 통한 검증
  - 로컬 저장으로 외부 검증 가능 (로그 완결성)

### 4. 실시간 적응형 학습·환류 시스템
- **경쟁사**: 정적 규칙 또는 제한적 학습
- **NoahAI**: **매 판단·결과마다 학습·환류 및 정책 보정**
- **학습 특징**:
  - 실시간 강화학습 엔진 (근거: `trading/ai/ai_manager.py`)
  - 시장 변화 즉시 반영 (근거: `trading/analyzer.py` 동적 임계값)
  - 개인별 맞춤 정책 생성 가능
  - 동적 임계값 보정 (실행은 외부)

### 5. 다중 자산 판단 인프라
- **경쟁사**: 단일 자산 타입 또는 제한적 통합
- **NoahAI**: **암호화폐, 주식, ETF, 부동산, 일반 금융까지 동일한 판단 파이프라인 적용 가능**
- **역할**:
  - 하나의 인터페이스로 **판단·기록·설명** 제공. 실행은 외부.
  - 잔고·통계 조회·표시 (데이터는 외부 API)
  - 자산별 **판단 근거·결과** 비교·분석
  - **판단 보조** (포트폴리오 자동 운용 아님)

## 🔬 실증 데이터 및 검증 결과

### 실전 환경 검증 데이터

#### 운영 안정성 검증
- **운영 기간**: 약 1년 이상 실전 환경 검증
- **시스템 가동률**: 99% 이상
- **외부 환경 변화 대응**: Binance API 정책 변경 등 즉시 대응 완료
- **포지션 복구 시스템**: 앱 재시작 시 실제 거래소에서 포지션 자동 복구 검증 완료

#### 재현성 검증
- **로그 완결성**: 모든 의사결정 과정 완전 기록
- **데이터베이스 기록**: 모든 거래 기록 영구 저장 및 검증 가능
- **외부 검증 가능**: 사용자가 직접 로그를 확인하여 AI 작동 검증 가능

#### 성능 검증
- **시작 시간**: 46초 → 즉시 시작 (99% 성능 향상)
- **판단 주기**: 5-10초 단위 분석·판단·기록
- **응답 속도**: 실시간 시장 변화 대응
- **메모리 효율**: 최적화된 캐싱으로 효율성 극대화

#### AI 학습·환류 검증 (참고)
- **학습 데이터 수집**: 판단·결과·패턴 수집으로 환류 구조 유지
- **지속적 개선**: 매 판단·결과마다 로그·환류 반영
- **적응성**: 시장 변화에 따른 임계값·정책 보정 (실행은 외부) 검증

**⚠️ 디스클레이머**: 내부 로그 기반 참고치이며, 승률/수익률/거래건수 등 수치는 시장/설정/계정별로 변동하며 보장 불가. NoahAI는 수익 보장·자동 운용 주체가 아님.

### 기술적 검증 결과

#### TP/SL 시스템 검증 (v3.8.9.11)
- **문제**: GALA, JASMY 등 저가 알트코인에서 TP 주문 실패
- **해결**: 가격 정밀도 자동 조정 및 TP 방향 검증 추가
- **결과**: 모든 저가 알트코인에서 정확한 TP/SL 가격 계산 및 주문 성공

#### Binance Algo Order API 검증 (v3.8.9.9)
- **문제**: Binance API 정책 변경 (2025-12-09)
- **해결**: 조건부 주문 자동 Algo Order API 라우팅 구현
- **결과**: 서명 생성 규칙 준수 및 가격 정밀도 문제 해결 완료

## 🚀 기술적 확장 가능성 및 연구 방향

### 1. 금융 특화 LLM 개발 가능성
**현재 기술적 기반**:
- `OpenAIClient`의 `base_url` 지원으로 다양한 LLM API 통합 가능
- 금융 도메인 특화 프롬프트 엔지니어링 경험 축적

**확장 시 연구 가능한 방향**:
- 금융 데이터 기반 파인튜닝
- 금융 용어 및 개념 이해 향상
- 시장 분석 정확도 개선

### 2. 멀티모달 분석 고도화 가능성
**현재 기술적 기반**:
- 차트 이미지 분석 기능 (`ChartScreenshotAnalyzer`) 구현 완료
- 수치 데이터 분석 엔진 구현 완료
- 시장 심리 데이터 통합 분석 시스템 구축

**확장 시 연구 가능한 방향**:
- Vision-Language Model 통합
- 뉴스 감정 분석 정확도 향상
- 차트 패턴 인식 정확도 개선

### 3. 강화학습 알고리즘 고도화 가능성
**현재 기술적 기반**:
- 실시간 강화학습 엔진 구현 완료
- 보상 함수 설계 및 패턴 유사성 분석 시스템 구현 완료
- 동적 임계값 조정 알고리즘 구현

**확장 시 연구 가능한 방향**:
- PPO, A3C 등 고급 강화학습 알고리즘 적용
- 멀티에이전트 강화학습 연구
- 메타러닝 기반 빠른 적응 알고리즘 개발

### 4. 리스크 관리 시스템 고도화 가능성
**현재 기술적 기반**:
- 일일 손실 한도 체크 시스템 구현
- 포지션 크기 제한 및 레버리지 관리 시스템 구현 완료
- TP/SL 최적화 시스템 구현

**확장 시 연구 가능한 방향**:
- VaR (Value at Risk) 계산 및 모니터링
- 포트폴리오 이론 기반 자산 배분 최적화
- 동적 헤징 전략 개발

### 5. 실시간 대규모 데이터 처리 확장 가능성
**현재 기술적 기반**:
- 6개 거래소 동시 운영 검증 완료
- 최적화된 캐싱 시스템 구현
- WebSocket 아키텍처 최적화 완료

**확장 시 연구 가능한 방향**:
- 분산 처리 아키텍처 설계
- 실시간 스트리밍 데이터 처리 최적화
- 고성능 캐싱 시스템 구축

---

## ⚖️ 법적/저작권 고지

---
**© 2025 노아에이아이랩스(Noah AI Labs). All Rights Reserved.**  
NoahAI 제품 문서 및 운영 관련 표기는 Noah AI Labs를 기준으로 합니다.  
**AI 디지털케어로그** 등 기술 기원에 해당하는 연구개발 성과는 **DAL(드림에이아이랩)** 및 **창안자 정해성(Jung Haesung)**의 지적재산권 범위를 포함할 수 있습니다.  
무단 복제·인용·상업적 이용을 금합니다.

*이 기술백서는 NoahAI의 기술적 성취와 혁신을 공식적으로 문서화한 것입니다. 본 문서의 내용은 실제 구현된 시스템을 기반으로 작성되었으며, 지속적으로 업데이트됩니다.*

**최종 업데이트**: 2026-06-08  
**문서 버전**: v1.5 (버전 고정 정책, 2026-06-05 기준 동기화 반영)  
**기준 시스템 버전**: v3.8.9.21 (2026-06-05)  
**정합성 기준**: Website, UPDATE_PLAN.md, ARCHITECTURE.md와 100% 일치. NoahAI = AI 자산 의사결정 인프라. 실행·법적·자금 이동은 항상 사용자·외부 시스템 책임.  
**근거 출처**: 본 문서는 `docs/*` 및 `trading/*` 코드 구조를 근거로 작성되었으며, 모든 확장 가능성은 현재 구현된 모듈·인터페이스·아키텍처를 증거로 제시한다.

> **v1.5 기준 동기화 요약(2026-06-05)**: v3.8.9.21 기준 문서 정합화 / 다중 거래소 안정화(상태·코인 오염 방지) / 거래소별 로그 태깅 정렬 / 사용자 공지(릴리즈노트·인앱 업데이트·가이드) 동기화
