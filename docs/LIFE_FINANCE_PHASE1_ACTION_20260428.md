# 🚀 생활금융 Phase 1 즉시 실행 계획 (2026-04-28)

**상태**: 지금 당장 시작 가능  
**기간**: 1~2주 (현재 개발 속도 기준)  
**담당자**: 개발팀  
**목표**: AI 어시스턴트 개인화 상담 기능 완성

---

## 📋 현재 상태

✅ **완료됨**:
- 생활금융 Phase 3 UI 프로토타입 (대출/보험/예적금 조건 입력 + 시각 테이블)
- 금융상품 비교 알고리즘 (더미 데이터로 점수 계산)
- LifeFinanceAssistant 의도 분류 (AI 대화 라우팅)
- 테스트 통과 (170/170 ✅)

❌ **미구현** (Phase 1 목표):
- 사용자 신용도 입력 필드
- 개인화 점수 계산 로직
- AI 상담 강화 (자연어 응답)

---

## 🎯 Phase 1 액션 (3단계, 1~2주)

### **Step 1: 신용도/위험도 입력 UI 추가** (~3일)

**파일**: `ui/widgets/life_finance_widget.py`

```python
# _setup_products_tab() 상단에 추가

def _add_credit_profile_section(self):
    """신용도/위험도 선택 패널"""
    profile_frame = ctk.CTkFrame(self.products_frame, fg_color="#1e293b", corner_radius=8)
    profile_frame.pack(fill="x", padx=10, pady=10)
    
    # 신용도 선택
    ctk.CTkLabel(profile_frame, text="당신의 신용도", text_color="#94a3b8").pack(side="left", padx=10)
    self.credit_score = ctk.CTkComboBox(
        profile_frame, 
        values=["좋음 (750~900)", "보통 (650~750)", "낮음 (~650)"],
        state="readonly",
        width=150
    )
    self.credit_score.pack(side="left", padx=5)
    self.credit_score.set("보통 (650~750)")
    
    # 위험도 선택
    ctk.CTkLabel(profile_frame, text="위험도", text_color="#94a3b8").pack(side="left", padx=10)
    self.risk_level = ctk.CTkComboBox(
        profile_frame,
        values=["회피형", "보수형", "공격형"],
        state="readonly",
        width=120
    )
    self.risk_level.pack(side="left", padx=5)
    self.risk_level.set("보수형")
```

**테스트**: 
```bash
cd tests/
python -m pytest test_life_finance_widget.py::test_credit_input -v
```

---

### **Step 2: 개인화 점수 계산 로직** (~3일)

**파일**: `trading/life_finance_products.py`

```python
# FinanceProductAdvisor 클래스에 메서드 추가

def apply_credit_adjustment(self, products_list, credit_score):
    """신용도에 따른 점수 조정
    
    Args:
        products_list: [{'name': '...', 'score': ...}, ...]
        credit_score: "좋음" | "보통" | "낮음"
    """
    adjustment = {
        "좋음": {"loan": -0.5, "insurance": 0.1, "savings": 0.3},      # 대출 유리
        "보통": {"loan": 0, "insurance": 0, "savings": 0},             # 표준
        "낮음": {"loan": 0.5, "insurance": -0.2, "savings": -0.1}     # 대출 불리
    }
    
    adj = adjustment.get(credit_score, {})
    for product in products_list:
        ptype = product.get('type', 'savings')
        product['adjusted_score'] = product['score'] + adj.get(ptype, 0)
    
    return sorted(products_list, key=lambda x: x['adjusted_score'])
```

**테스트**:
```bash
python -m pytest tests/test_life_finance_products.py::test_credit_adjustment -v
```

---

### **Step 3: AI 상담 강화** (~4일)

**파일**: `trading/life_finance_assistant.py`

```python
# LifeFinanceAssistant.generate_recommendation() 메서드 확장

def generate_recommendation(self, user_message, credit_score=None, risk_level=None):
    """사용자 신용도/위험도를 고려한 맞춤 조언"""
    
    # 의도 분류
    intent = self._classify_intent(user_message)
    
    if intent == "loan_recommendation":
        loans = self.advisor.compare_loans(
            amount=self._extract_amount(user_message),
            term_months=self._extract_term(user_message)
        )
        
        # 신용도 적용
        if credit_score:
            loans['best'] = self._apply_credit_label(loans['best'], credit_score)
            loans['best']['rate_adjusted'] = self._calculate_adjusted_rate(
                loans['best']['rate'], credit_score
            )
        
        return self._format_loan_response(loans, credit_score)
    
    # ... insurance, savings도 동일 구조
```

**사용자 대화 흐름 예시**:
```
사용자: "신용도가 좋으면 금리가 얼마나 낮아져?"
AI: "당신의 신용도(좋음)를 기반으로, 
    KB국민 주택담보는 기본 4.05% → 우대금리 3.75% (0.3% 인하) 예상됩니다.
    신한은행 신용대출은 5.5% → 5.0% (0.5% 인하) 가능합니다.
    
    💡 추천: 현재 금액/기간으로 비교해드릴까요?"

사용자: "그럼 5000만원, 30년 대출로"
AI: [대출 비교 테이블 표시]
    KB국민이 가장 유리합니다 (총 이자: OOO만원)
    신한은행이 2순위입니다 (총 이자: OOO만원)
    
    ⚠️ 현재는 시뮬레이션입니다. 
       실제 신청은 각 금융사 웹사이트에서 직접 진행하세요.
```

**통합 테스트**:
```bash
python -m pytest tests/test_life_finance_assistant.py -v
```

---

## 🔄 통합 검증 (1일)

```bash
# 전체 UI 흐름 테스트
python -m pytest tests/test_life_finance_widget.py -v

# 비즈니스 로직 테스트
python -m pytest tests/test_life_finance_assistant.py -v
python -m pytest tests/test_life_finance_products.py -v

# 회귀 테스트 (AI 애널리스트 등 다른 기능)
python -m pytest tests/ -v --tb=short | tail -20
```

---

## 📝 사용자 메뉴얼 업데이트 (1일)

**파일**: `ui/widgets/user_manual_widget.py`

```markdown
### 🧪 생활금융 (프로토타입/데모)

**v3.8.9.15 추가 기능**:
- 🆕 신용도/위험도 기반 개인화 상담
  당신의 신용도(좋음/보통/낮음)를 선택하면,
  AI가 맞춤형 금리/상품을 제안해드립니다.
  
- 💬 AI와 자연어로 대화
  "5000만원 30년 대출로" → 즉시 비교표 표시
  
- ⚠️ 주의사항
  • 현재는 더미 데이터 기반 시뮬레이션입니다
  • 실제 금율/상품은 금융사 웹사이트 확인 필수
  • 실제 신청은 각 금융사에서 직접 진행하세요
```

---

## ✅ 완료 기준

```
Phase 1 완료 체크리스트:

□ 신용도/위험도 입력 UI 동작 (UI 클릭 → 값 저장)
□ 개인화 점수 계산 로직 동작 (신용도별 점수 조정 확인)
□ AI 상담 강화 (사용자 메시지 → 개인화 응답 생성)
□ 통합 테스트 통과 (170+ tests passed)
□ 메뉴얼 업데이트 (사용자가 프로토타입 인식)
□ CHANGELOG.md 업데이트 (v3.8.9.15.1 기록)
```

---

## 🚀 지금 당장 시작 (다음 단계)

**1단계** (오늘):
```bash
# 신용도/위험도 UI 스켈레톤 작성
# tests/test_life_finance_widget.py 추가
```

**2단계** (내일):
```bash
# 개인화 점수 계산 로직 구현
# 테스트 통과 확인
```

**3단계** (모레~3일):
```bash
# AI 상담 강화 (generate_recommendation 확장)
# 통합 테스트 + 메뉴얼 업데이트
```

**4단계** (4일):
```bash
# 최종 검증 + CHANGELOG 업데이트
# 메인 브랜치에 머지
```

---

## 📚 참고 문서

- [DEVELOPMENT_STATUS_COMPREHENSIVE_20260427.md](DEVELOPMENT_STATUS_COMPREHENSIVE_20260427.md) — 전체 개발 현황
- [LIFE_FINANCE_PRODUCT_COMPARISON_ANALYSIS_20260429.md](LIFE_FINANCE_PRODUCT_COMPARISON_ANALYSIS_20260429.md) — 전략 분석
- [LIFE_FINANCE_ROADMAP_20260428.md](LIFE_FINANCE_ROADMAP_20260428.md) — Phase 0~4 장기 로드맵

---

**문서 버전**: v3.8.9.15  
**작성일**: 2026-04-28  
**상태**: 즉시 실행 가능 🟢
