# 생활금융 확장 - 완성 가이드

## 📌 개요

생활금융 시스템이 완전히 구현되었습니다. 이제 실연동 전에 모든 기능을 테스트하고 사용할 수 있습니다.

**상태**: ✅ MVP 완성 + AI 어시스턴트 통합 + UI

---

## 🎯 주요 기능

### 1️⃣ **거래 관리** (수입/지출)

```python
# 지출 추가 (자동 분류)
manager.add_transaction(
    date=date.today(),
    amount=5000,
    type_=TransactionType.EXPENSE,
    description='카페에서 커피',
    auto_classify=True  # AI가 '식비'로 자동 분류
)

# 수입 추가
manager.add_transaction(
    date=date.today(),
    amount=3500000,
    type_=TransactionType.INCOME,
    description='월급',
)
```

**자동 분류 카테고리**:
- 🍽️ 식비 (식당, 카페, 마트 등)
- 🚌 교통비 (버스, 택시, 휘발유 등)
- 🏠 주거비 (월세, 전기, 수도 등)
- 🎬 문화생활 (영화, 공연 등)
- 👕 쇼핑 (의류, 신발 등)
- ⚕️ 건강/의료 (병원, 약국, 헬스 등)
- 📚 교육 (학원, 교재 등)
- 💳 금융 (수수료, 보험료 등)
- 📺 구독 (넷플릭스, 스포티파이 등)

### 2️⃣ **목표 관리**

```python
# 목표 생성
goal = manager.add_goal(
    name='여름 휴가',
    target_amount=2000000,
    deadline=date(2026, 7, 1),
    priority='높음',
    description='해외 여행 경비'
)

# 목표에 저축 추가
manager.add_goal_savings(goal.id, 500000)

# 진행률 자동 계산
print(f"진행률: {goal.progress_rate:.1f}%")
print(f"남은 금액: {goal.remaining_amount:,}원")
print(f"월간 목표: {goal.monthly_target:,}원")
```

**목표 추적 기능**:
- 📊 진행률 자동 계산
- 🎯 마감 기한까지 남은 기간 표시
- 💰 월간 저축 목표 자동 제시
- ✅ 완료 여부 자동 판단

### 3️⃣ **재무 분석**

```python
# 월간 리포트
report = manager.get_monthly_report(2026, 4)
print(f"수입: {report.total_income:,}원")
print(f"지출: {report.total_expense:,}원")
print(f"저축: {report.net_savings:,}원")
print(f"저축률: {report.savings_rate:.1f}%")

# 카테고리별 분석
stats = manager.get_category_stats()
# → {'식비': {'total': 50000, 'count': 5, 'avg': 10000}, ...}

# 지출 추세 (6개월)
trend = manager.get_spending_trend(months=6)
# → {'2026-01': 1500000, '2026-02': 1450000, ...}

# 종합 대시보드
summary = manager.get_dashboard_summary()
```

### 4️⃣ **재무 시뮬레이션**

```python
from trading.life_finance import FinanceSimulator

# 월간 저축 프로젝션
projections = FinanceSimulator.project_savings(
    monthly_income=3500000,
    monthly_expenses=1500000,
    months=12,
    inflation_rate=0.02
)
# → [2000000, 4000000, 6000000, ...] (월별 누적)

# 목표 달성까지 필요한 기간
months_needed = FinanceSimulator.goal_achievement_timeline(
    current_savings=500000,
    monthly_savings=500000,
    goal_amount=2000000
)
# → 3개월

# 다중 시나리오 비교
scenarios = {
    '보수적': {'monthly_income': 3500000, 'monthly_expenses': 2000000},
    '적극적': {'monthly_income': 3500000, 'monthly_expenses': 1500000},
}
comparison = FinanceSimulator.scenario_comparison(scenarios, months=12)
```

### 5️⃣ **금융상품 비교 (Phase 3)**

```python
from trading.life_finance_products import FinanceProductAdvisor

advisor = FinanceProductAdvisor()

# 대출 비교
loan_result = advisor.compare_loans(amount=100000000, term_months=24)

# 보험 비교
insurance_result = advisor.compare_insurances(budget_monthly=70000)

# 예적금 비교
savings_result = advisor.compare_savings(principal=5000000, term_months=12)
```

AI 명령 예시:
- `대출 비교해줘`
- `보험 추천해줘`
- `예금 상품 비교해줘`

UI 탭:
- `🏦 금융상품` 탭에서 대출/보험/예적금 비교 버튼 제공

### 6️⃣ **세무 계산 서비스** ✅ 구현 완료

```python
from trading.tax_calculation_service import TaxCalculationService

svc = TaxCalculationService()

# 연말정산 종합 계산
result = svc.calc_year_end_tax_settlement(
    annual_salary=50_000_000,
    credit_card=8_000_000,
    debit_cash=3_000_000,
    medical_expense=1_500_000,
    education_expense=2_400_000,
    donation_amount=500_000,
    pension_savings=6_000_000,
    irp_contribution=3_000_000,
)
print(result['final_tax'])           # 최종 납부/환급 세액
print(result['optimization_tips'])  # 절세 팁 목록

# 금융소득 종합과세 판정
check = svc.check_financial_income_comprehensive_tax(
    interest_income=1_500_000,
    dividend_income=800_000,
    annual_salary=60_000_000,
)
print(check['comprehensive_tax_required'])  # True/False

# 금투세 계산
tax = svc.calc_financial_investment_tax(
    domestic_profit=20_000_000,
    overseas_profit=10_000_000,
)
print(tax['total_tax'])

# ISA / 연금저축 / IRP 절세 비교
comparison = svc.compare_tax_saving_accounts(
    annual_salary=50_000_000,
    annual_invest=3_000_000,
)
```

AI 명령 예시:
- `연말정산 계산해줘 / 환급금 얼마야?`
- `금융소득종합과세 해당돼?`
- `금투세 얼마 내야 해?`
- `ISA랑 IRP 중 뭐가 더 유리해?`
- `절세 방법 알려줘`

> ⚠️ **책임 경계**: NoahAI는 계산·요약까지만 제공합니다.  
> 세금 신고·납부·제출은 반드시 사용자(또는 세무사)가 직접 처리해야 합니다.

---

### 7️⃣ **금융 이상 탐지** ✅ 구현 완료

```python
from trading.fraud_detection_service import FraudDetectionService, TransactionRecord
from datetime import date

svc = FraudDetectionService()

# 문자/전화 내용 분석 (보이스피싱·스미싱)
alerts = svc.analyze_voice_phishing(
    "검찰청입니다. 계좌가 범죄에 연루되었습니다. OTP를 알려주세요."
)
for alert in alerts:
    print(alert.risk_level, alert.description)

# 이상 거래 감지 (z-score 기반 + 패턴)
history = [
    TransactionRecord(amount=50000, tx_date=date.today(), ...),
    ...
]
new_tx = TransactionRecord(amount=5_000_000, tx_date=date.today(), ...)
alerts = svc.detect_abnormal_transactions(history, new_tx)

# 약탈적 대출 경고
alerts = svc.check_predatory_loan(
    rate=25.0,
    amount=10_000_000,
    upfront_fee=True,
)
print(alerts[0].risk_level)  # 'critical'

# 종합 리스크 요약
summary = svc.compute_fraud_risk_summary(alerts)
print(summary['overall_risk'], summary['recommendation'])
```

AI 명령 예시:
- `이 문자가 사기인지 확인해줘`
- `보이스피싱 확인해줘`
- `이상한 거래 탐지해줘`
- `이 대출 조건이 정상이야?`

> ⚠️ **책임 경계**: NoahAI는 패턴 탐지·경고까지만 제공합니다.  
> 법적 조치·신고는 사용자 판단에 따라 직접 처리하십시오.

---

## 🤖 AI 어시스턴트 (음성/자연어)

### 자연어 명령 예시

```python
from trading.life_finance_assistant import LifeFinanceAssistant

assistant = LifeFinanceAssistant(manager)

# 비동기 처리
import asyncio

async def main():
    # 지출 기록
    result = await assistant.process_command("오늘 카페에서 5천원 썼어")
    print(result['response'])  # ✓ 지출 5,000원을 등록했습니다...
    
    # 수입 기록
    await assistant.process_command("급여로 350만원 받았어")
    
    # 조회
    await assistant.process_command("이번 달 지출이 얼마야?")
    
    # 목표
    await assistant.process_command("여름 휴가 200만원 목표 만들어")
    
    # 조언
    await assistant.process_command("어떻게 절약할까?")

asyncio.run(main())
```

### 지원하는 의도 (Intent)

| 의도 | 예시 명령어 |
|------|-----------|
| 💸 지출 추가 | "카페에서 5천원 썼어" |
| 💰 수입 추가 | "급여로 350만원 받았어" |
| 📋 거래 조회 | "최근 지출 내역 보여줘" |
| 📊 카테고리 분석 | "카테고리별 지출 분석해줘" |
| 🎯 목표 생성 | "여름 휴가 200만원 목표" |
| 📈 목표 조회 | "지금 목표 진행 상황은?" |
| 📊 월간 리포트 | "이번 달 리포트 보여줘" |
| 📈 지출 추세 | "최근 몇 달 지출 추세는?" |
| 💡 절약 조언 | "어떻게 절약할까?" |
| 💡 저축 조언 | "저축 팁 알려줘" |
| 📱 대시보드 | "전체 현황 보여줘" |
| 🏦 대출 비교 | "대출 비교해줘" / "주택담보대출 비교" |
| 🛡️ 보험 비교 | "보험 추천해줘" |
| 💳 예적금 비교 | "예금 상품 비교해줘" |
| 🧾 연말정산 계산 | "연말정산 계산해줘" / "환급금 얼마야?" |
| 💹 금융소득 과세 확인 | "금융소득종합과세 해당돼?" |
| 📈 금투세 계산 | "금투세 얼마 내야 해?" |
| 🏦 절세 계좌 비교 | "ISA랑 IRP 뭐가 더 유리해?" |
| 🔍 사기 문자 분석 | "이 문자 사기야?" / "보이스피싱 확인해줘" |
| ⚠️ 이상 거래 탐지 | "이상한 거래 탐지해줘" |
| 🚨 약탈적 대출 확인 | "이 대출 조건 정상이야?" |

---

## 🖥️ UI 대시보드 (CustomTkinter)

### 탭 구성

#### 📊 대시보드 탭
- **월간 요약**: 수입, 지출, 저축, 저축률
- **비교**: 이전 달과의 변화
- **목표 진행**: 활성 목표 3개 표시

#### 💳 거래 탭
- 최근 거래 목록 (최근 7일, 최대 20개)
- 각 거래별 아이콘, 날짜, 카테고리, 설명, 금액
- 거래 삭제 기능

#### 🎯 목표 탭
- 활성 목표 목록
- 각 목표의 진행 바, 진행률, 남은 기간
- 저축 추가 버튼
- 목표 삭제 버튼

#### 📈 분석 탭
- 카테고리별 지출 (이번 달)
- 최근 6개월 지출 추세

#### 📉 차트 탭
- 카테고리 비중 도넛 차트
- 월별 지출 라인 차트

#### 🏦 금융상품 탭
- 대출 상품 비교
- 보험 상품 비교
- 예적금 상품 비교
- 추천/대안 상품 요약

#### 🤖 AI 어시스턴트 탭
- 자연어 명령 입력창
- 🎤 음성 입력 버튼 (향후 지원)
- 대화 이력 표시

### 빠른 버튼
- 📊 대시보드
- 💸 지출 추가
- 💰 수입 추가
- 🎯 목표 관리

---

## 📁 파일 구조

```
trading/
├── life_finance.py                    # 핵심 모듈 (매니저, 거래, 목표, 시뮬레이션)
├── life_finance_assistant.py          # AI 어시스턴트 (자연어 처리)
└── ...

ui/
├── widgets/
│   ├── life_finance_widget.py        # UI 위젯 (CustomTkinter)
│   └── ...
└── ...

data/
├── life_finance_transactions.json    # 거래 데이터
├── life_finance_goals.json           # 목표 데이터
└── life_finance_monthly_cache.json   # 월간 캐시
```

---

## 🚀 시작하기

### 1. 기본 설정

```python
from trading.life_finance import LifeFinanceManager

# 매니저 초기화 (자동으로 데이터 로드)
manager = LifeFinanceManager(data_dir="data")
```

### 2. 거래 추가

```python
from datetime import date
from trading.life_finance import TransactionType

# 지출
manager.add_transaction(
    date=date.today(),
    amount=15000,
    type_=TransactionType.EXPENSE,
    description='마트 장보기',
    auto_classify=True  # 자동 분류
)

# 수입
manager.add_transaction(
    date=date.today(),
    amount=3500000,
    type_=TransactionType.INCOME,
    description='월급',
)
```

### 3. 목표 설정

```python
from datetime import date, timedelta

goal = manager.add_goal(
    name='신차 구입',
    target_amount=30000000,
    deadline=date.today() + timedelta(days=365),
    priority='높음'
)

# 진행 상황 확인
print(f"진행률: {goal.progress_rate:.1f}%")
print(f"남은 금액: {goal.remaining_amount:,}원")
```

### 4. AI 어시스턴트 사용

```python
import asyncio
from trading.life_finance_assistant import LifeFinanceAssistant

assistant = LifeFinanceAssistant(manager)

async def chat():
    result = await assistant.process_command("오늘 식사비 30000원 썼어")
    print(result['response'])

asyncio.run(chat())
```

### 5. UI 실행

```python
import customtkinter as ctk
from ui.widgets.life_finance_widget import LifeFinanceWidget

root = ctk.CTk()
root.title("생활금융")
root.geometry("1200x800")

widget = LifeFinanceWidget(root)
widget.pack(fill="both", expand=True)

root.mainloop()
```

### 6. 외부 동기화(선택)

`config/settings.json` 또는 설정 화면에서 아래 키를 지정하면 자동 백업/동기화가 동작합니다.

```json
{
    "life_finance_sync_dir": "/Users/you/SynologyDrive/FinanceSync",
    "life_finance_backup_dir": "/Users/you/SynologyDrive/FinanceBackup"
}
```

---

## 📊 데이터 구조

### 거래 (Transaction)

```json
{
  "id": "tx_1704067200000",
  "date": "2026-04-28",
  "amount": 5000,
  "type": "지출",
  "category": "식비",
  "description": "카페에서 커피",
  "method": "카드",
  "ai_confidence": 0.67
}
```

### 목표 (FinanceGoal)

```json
{
  "id": "goal_1704067200000",
  "name": "여름 휴가",
  "target_amount": 2000000,
  "current_amount": 500000,
  "deadline": "2026-07-01",
  "category": "기타",
  "priority": "높음",
  "description": "해외 여행 경비",
  "progress_rate": 25.0,
  "remaining_amount": 1500000,
  "days_until_deadline": 64,
  "monthly_target": 234375.0
}
```

### 월간 리포트 (MonthlyReport)

```json
{
  "year": 2026,
  "month": 4,
  "date_str": "2026-04",
  "total_income": 3500000,
  "total_expense": 5000,
  "net_savings": 3495000,
  "savings_rate": 99.86,
  "category_breakdown": {
    "식비": 5000
  }
}
```

---

## 🔧 고급 기능

### 1. 지출 분류 커스터마이징

```python
from trading.life_finance import ExpenseClassifier

# 설명으로부터 카테고리 추천
category, confidence = ExpenseClassifier.classify("카페에서 아메리카노")
# ('식비', 0.67)

# 상위 후보들
suggestions = ExpenseClassifier.suggest_categories("마트에서 식료품", top_k=3)
# [('식비', 0.95), ('기타', 0.5), ...]
```

### 2. 시나리오 분석

```python
from trading.life_finance import FinanceSimulator

scenarios = {
    '보수적': {
        'monthly_income': 3500000,
        'monthly_expenses': 2000000,
    },
    '적극적': {
        'monthly_income': 3500000,
        'monthly_expenses': 1500000,
    },
}

comparison = FinanceSimulator.scenario_comparison(scenarios, months=12)
# {
#   '보수적': {
#     'final_savings': 18000000,
#     'average_monthly_savings': 1500000,
#     'max_savings': 18000000
#   },
#   ...
# }
```

### 3. 고급 쿼리

```python
# 기간별 조회
from datetime import date, timedelta

start = date.today() - timedelta(days=30)
end = date.today()

transactions = manager.get_transactions(
    start_date=start,
    end_date=end,
    type_=TransactionType.EXPENSE,
    category='식비'
)

# 우선순위별 목표 정렬
high_priority = manager.get_goals()  # 자동으로 우선순위 정렬됨

# 통계
stats = manager.get_category_stats(start_date=start, end_date=end)
monthly_trend = manager.get_monthly_stats(months=12)
spending_trend = manager.get_spending_trend(months=12)
```

---

## ✅ 테스트 완료 항목

- ✅ 거래 추가 (자동 분류 포함)
- ✅ 목표 생성 및 추적
- ✅ 월간/카테고리 통계
- ✅ 재무 시뮬레이션
- ✅ AI 자연어 처리 (기본)
- ✅ UI 대시보드
- ✅ 데이터 저장/로드
- ✅ 금융상품 비교 (대출 20개·보험 20개·예적금 20개, loan_type 필터, 월납입액)
- ✅ 세무 계산 (연말정산·금융소득종합과세·금투세·ISA/IRP 비교)
- ✅ 금융 이상 탐지 (보이스피싱·스미싱·이상거래·약탈적 대출)

---

## 🔮 향후 개선 계획

### Phase 2 (선택적)
- 🎤 음성 입력 (STT)
- 📊 고급 차트/그래프
- 📧 월간 요약 메일 발송
- 🔔 목표 달성 알림
- 💾 클라우드 동기화

### Phase 3 (완료)
- ✅ 대출 상품 비교 (20개, loan_type 필터, 월납입액)
- ✅ 보험 선택 보조 (20개, 카테고리별)
- ✅ 예금/적금 추천 (20개, ISA형 포함)
- ✅ 금융 사기 탐지 (보이스피싱·이상거래·약탈적 대출)
- ✅ 세무 계산 서비스 (연말정산·금투세·절세 비교)
- 🚧 다중 계좌 통합 (미구현)

---

## �️ 대시보드 신규 탭 (v3.8.9.19)

### 🚨 보안 경고 탭

> `other(생활금융)` 서비스 → `🚨 보안 경고` 탭에서 접근

#### 목적
- 실거래 DB(`trade_log`)를 자동 분석해 이상 거래 패턴을 탐지합니다.
- 보이스피싱·스미싱 등 금융사기 위험을 자가진단할 수 있도록 안내합니다.

#### 화면 구성
| 섹션 | 내용 |
|---|---|
| 종합 리스크 점수 | `low / medium / high / critical` 4단계 위험 등급 + 색상 배지 |
| 탐지된 이상 거래 목록 | 패턴별 경고 카드 (위험 수준별 배경색) |
| 이상 거래 유형 설명 | 급격한 금액 급등, 비정상적 반복, 야간 거래 등 |
| 보이스피싱 자가 진단 | 5가지 체크리스트 (계좌이전 요청/공공기관 사칭/링크 클릭 등) |

#### 연동 서비스
- `trading/fraud_detection_service.py`
  - `detect_abnormal_transactions(records)` — 이상 거래 패턴 감지
  - `compute_fraud_risk_summary(alerts)` — 종합 리스크 점수 산출
  - `TransactionRecord` — DB `trade_log` 레코드 변환 구조체

#### 사용 방법
1. `생활금융` 서비스로 전환
2. `🚨 보안 경고` 탭 클릭
3. 자동으로 최근 거래 분석 실행 → 결과 표시
4. 보이스피싱 체크리스트 확인

---

### 💰 세금 계산 탭

> `other(생활금융)` 서비스 → `💰 세금 계산` 탭에서 접근

#### 목적
- 연말정산·금투세·ISA·연금저축·IRP 절세 효과를 한 화면에서 비교합니다.
- 수치를 입력하면 실시간으로 납부 세액, 실효 세율, 절세 팁을 제공합니다.

#### 입력 항목
| 입력 필드 | 설명 |
|---|---|
| 연봉 (만원) | 총 급여 |
| 신용카드 사용액 | 체크카드 포함 가능 |
| 의료비 | 본인 + 부양가족 |
| 교육비 | 학원비/학교 등록금 |
| 기부금 | 법정·지정기부금 |
| 금융소득 | 이자·배당 소득 |
| 주식 양도차익 | 국내 주식 기준 |

#### 결과 섹션
| 섹션 | 내용 |
|---|---|
| A. 연말정산 | 산출세액 / 총 공제액 / 납부 세액 / 실효 세율 |
| B. 금투세 | 양도차익 입력 시 조건부 표시 (250만 원 공제 후 세액) |
| C. 절세 계좌 비교 | ISA / 연금저축 / IRP — 기대 절세액 비교 |
| D. 절세 최적화 팁 | 5가지 우선순위 팁 자동 생성 |

#### 연동 서비스
- `trading/tax_calculation_service.py`
  - `calc_year_end_tax_settlement(params)` — 연말정산 계산
  - `calc_financial_investment_tax(params)` — 금투세 계산
  - `compare_tax_saving_accounts(params)` — 절세 계좌 비교
  - `generate_tax_optimization_summary(params)` — 절세 팁 생성

#### 사용 방법
1. `생활금융` 서비스로 전환
2. `💰 세금 계산` 탭 클릭
3. 입력 필드에 수치 입력 (비어있어도 0으로 계산)
4. `[세금 계산하기]` 버튼 클릭 → 즉시 결과 표시

---

## �📞 자주 묻는 질문

**Q: 데이터는 어디에 저장되나요?**
A: `data/` 폴더의 JSON 파일에 저장됩니다. 클라우드 동기화는 향후 추가 예정입니다.

**Q: 분류가 잘못되었어요.**
A: `거래 수정` 기능으로 카테고리를 수정할 수 있습니다. AI는 더 많은 데이터를 학습하면서 정확도가 향상됩니다.

**Q: 음성 입력은 언제 지원되나요?**
A: 다음 버전에서 STT (Speech-to-Text) 기능을 추가할 예정입니다.

**Q: 복수 계좌를 관리할 수 있나요?**
A: 현재 단일 계좌 기반입니다. 향후 다중 계좌 지원이 추가될 예정입니다.

---

## 📝 라이선스 & 지원

- **상태**: 완성 (MVP)
- **테스트**: ✅ 통과
- **프로덕션**: 준비 완료
- **지원**: 실연동 전 추가 요청사항 접수 가능

---

**마지막 업데이트**: 2026-05-06
**버전**: 1.2.0 (v3.8.9.19)
**상태**: ✅ 세무·이상탐지·보안경고·세금계산 탭·카탈로그 확장 포함 완료
