# 대시보드 사용자 메뉴얼 UI 구현 가이드 (이력 보관)

**작성일:** 2026년 4월 27일  
**목적:** 개발팀이 대시보드에 사용자 메뉴얼을 통합하기 위한 기술 명세서  
**상태:** 🚧 구현 대기 (데이터는 준비 완료)

---

## 📋 개요

### 목표
- ✅ 사용자가 MD 파일을 읽지 않아도 대시보드에서 직접 도움말 확인
- ✅ AI 어시스턴트와 통합된 실시간 상담
- ✅ 서비스별(암호화폐/주식/ETF/AI) 컨텍스트 기반 가이드

### 설계 원칙
```
사용자 경험 최우선:
  - 명확하고 간단한 UI
  - 한국어 기반 설명
  - 모바일 친화적 (향후)
```

---

## 🎨 UI 구조

### 현재 대시보드 구조
```
┌─────────────────────────────────────────────┐
│ Dashboard Modern (dashboard_modern.py)      │
├─────────────────────────────────────────────┤
│  🪙 암호화폐 │ 📈 주식 │ ... │ 🤖 AI 어시스턴트 │
├─────────────────────────────────────────────┤
│                                             │
│  (각 서비스별 탭 내용)                      │
│                                             │
├─────────────────────────────────────────────┤
│ 하단: 서비스 버튼 (암호화폐/주식/ETF/통합)  │
└─────────────────────────────────────────────┘
```

### 제안: 메뉴얼 탭 추가

#### 옵션 1: 각 서비스 내에 "❓ 도움말" 탭 추가 (권장)

```
🪙 암호화폐 탭 하부:
├─ 📊 코인 선택
├─ 🔔 활성 포지션
├─ 📈 거래 통계
└─ ❓ 도움말 ← NEW

정규/주식 탭 하부:
├─ 🔍 종목 검색
├─ 🛡️ 증권 주문
├─ 📈 포지션
└─ ❓ 도움말 ← NEW
```

**장점:**
- 각 서비스에서 곧바로 도움말 확인
- 컨텍스트 유지
- UI 구조 단순

#### 옵션 2: 메인 대시보드에 "도움말" 패널 추가

```
상단 우측에 "❓" 버튼 추가
  → 클릭 시 패널 열림
  → 선택된 서비스별 메뉴얼 표시
```

**장점:**
- 언제든 접근 가능
- 모든 서비스에 통일된 위치

---

## 💻 구현 명세

### 1️⃣ UI 컴포넌트 (Python/CustomTkinter)

```python
# ui/widgets/user_manual_widget.py (새로 생성)

class UserManualWidget:
    """사용자 메뉴얼을 표시하는 위젯"""
    
    def __init__(self, parent, service_name):
        """
        Args:
            parent: 부모 프레임
            service_name: 'crypto', 'stock', 'etf', 'ai_assistant'
        """
        self.service_name = service_name
        self.manual_data = self.load_manual_data(service_name)
        self.create_widgets()
    
    def create_widgets(self):
        """메뉴얼 UI 구성"""
        # 탭바 생성: 개요 | 빠른 시작 | FAQ | 용어
        tabs = [
            ("📘 개요", self.show_overview),
            ("⚡ 빠른 시작", self.show_quick_start),
            ("❓ FAQ", self.show_faq),
            ("📚 용어", self.show_glossary),
        ]
        
        self.tabview = CTkTabview(self.parent)
        for tab_name, callback in tabs:
            self.tabview.add(tab_name)
        
        # AI에 물어보기 버튼
        ask_ai_btn = CTkButton(
            self.parent, 
            text="🤖 AI에 물어보기",
            command=self.open_ai_chat
        )
    
    def load_manual_data(self, service_name):
        """user_manual_data.json 에서 데이터 로드"""
        import json
        with open('data/nwsoft/user_manual_data.json', 'r', encoding='utf-8') as f:
            all_data = json.load(f)
        return all_data.get(service_name, {})
    
    def show_overview(self):
        """개요 탭 표시"""
        label = CTkLabel(
            self.tabview.tab("📘 개요"),
            text=self.manual_data['overview'],
            wraplength=600,
            justify="left"
        )
        label.pack(pady=10, padx=10)
    
    def show_quick_start(self):
        """빠른 시작 탭 표시"""
        frame = self.tabview.tab("⚡ 빠른 시작")
        steps = self.manual_data.get('quick_start', {})
        
        for step, description in steps.items():
            label = CTkLabel(frame, text=description, wraplength=600)
            label.pack(pady=5, padx=10, anchor="w")
    
    def show_faq(self):
        """FAQ 탭 표시"""
        frame = self.tabview.tab("❓ FAQ")
        faqs = self.manual_data.get('faq', [])
        
        for item in faqs:
            q_label = CTkLabel(frame, text=f"Q: {item['q']}", text_color="#4CAF50")
            q_label.pack(pady=5, padx=10, anchor="w")
            
            a_label = CTkLabel(frame, text=f"A: {item['a']}", wraplength=600, justify="left")
            a_label.pack(pady=5, padx=20, anchor="w")
            
            sep = CTkLabel(frame, text="─" * 70, text_color="gray")
            sep.pack(pady=3)
    
    def show_glossary(self):
        """용어 탭 표시"""
        frame = self.tabview.tab("📚 용어")
        glossary = self.manual_data.get('glossary', {})
        
        for term, definition in glossary.items():
            term_label = CTkLabel(frame, text=term, text_color="#2196F3", font=("Arial", 12, "bold"))
            term_label.pack(pady=3, padx=10, anchor="w")
            
            def_label = CTkLabel(frame, text=definition, wraplength=600, justify="left")
            def_label.pack(pady=2, padx=30, anchor="w")
    
    def open_ai_chat(self):
        """AI 어시스턴트 채팅 열기"""
        # AI 어시스턴트 탭으로 포커스 이동
        self.parent.root.open_ai_assistant()
```

### 2️⃣ 대시보드 통합 (dashboard_modern.py)

```python
# ui/dashboard_modern.py 수정사항

class DashboardModern:
    
    def show_blockchain_content(self):
        """기존 암호화폐 탭"""
        # 기존 코드 유지
        self.crypto_frame = CTkFrame(self.main_panel)
        
        # 서브탭 추가
        self.crypto_tabview = CTkTabview(self.crypto_frame)
        self.crypto_tabview.add("📊 코인 선택")
        self.crypto_tabview.add("🔔 활성 포지션")
        self.crypto_tabview.add("📈 거래 통계")
        self.crypto_tabview.add("❓ 도움말")  # ← NEW
        
        # 도움말 탭에 메뉴얼 위젯 추가
        from ui.widgets.user_manual_widget import UserManualWidget
        manual_frame = self.crypto_tabview.tab("❓ 도움말")
        self.crypto_manual = UserManualWidget(manual_frame, 'crypto')
    
    def show_stock_content(self):
        """주식 탭"""
        # 기존 코드 유지
        # ...
        
        # 도움말 탭 추가
        stock_manual_frame = self.stock_tabview.tab("❓ 도움말")
        self.stock_manual = UserManualWidget(stock_manual_frame, 'stock')
    
    def open_ai_assistant(self):
        """AI 어시스턴트 탭으로 포커스"""
        # 기존 AI 어시스턴트 탭으로 이동
        self.main_tabview.set("🤖 AI 어시스턴트")
```

### 3️⃣ 데이터 파일 (이미 생성 완료)

```
data/nwsoft/user_manual_data.json
  ├─ crypto: { overview, quick_start, faq, glossary }
  ├─ stock: { overview, quick_start, faq, glossary }
  ├─ etf: { overview, quick_start, faq, glossary }
  ├─ ai_assistant: { overview, quick_start, faq, glossary }
  └─ common: { glossary, tips }
```

---

## 📦 파일 체크리스트

### 이미 준비된 파일
- ✅ `data/nwsoft/user_manual_data.json` - 모든 메뉴얼 데이터
- ✅ `docs/DOCUMENTATION_MAINTENANCE_POLICY.md` - 정책 문서
- ✅ `docs/USER_GUIDE.md` - 개발팀용 문서 (업데이트됨)
- ✅ `docs/TRADING_FLOW.md` - 기술 명세서 (업데이트됨)

### 구현 필요 파일
- 🚧 `ui/widgets/user_manual_widget.py` - 메뉴얼 위젯 (새로 생성)
- 🚧 `ui/dashboard_modern.py` - 대시보드 수정 (도움말 탭 추가)

---

## 🔄 구현 단계

### Phase 1: 기본 메뉴얼 위젯 (2시간)
```python
1. UserManualWidget 클래스 구현
   - create_widgets()
   - load_manual_data()
   - show_overview/quick_start/faq/glossary()

2. 간단한 UI 테스트
   - 데이터 로드 확인
   - 탭 전환 확인
```

### Phase 2: 대시보드 통합 (3시간)
```python
1. 암호화폐 탭에 도움말 추가
2. 주식 탭에 도움말 추가
3. ETF 탭에 도움말 추가 (필요시)

4. 테스트
   - 각 탭별 도움말 표시 확인
   - 데이터 로드 확인
   - AI 어시스턴트 연동 확인
```

### Phase 3: AI 어시스턴트 연동 (1시간)
```python
1. "🤖 AI에 물어보기" 버튼 동작
   - 현재 서비스와 관련된 질문 자동 생성
   - AI 어시스턴트 탭으로 포커스

2. 예시:
   암호화폐 도움말 → "BTC는 언제 사야 하나?"
   주식 도움말 → "삼성전자는 지금 사도 될까?"
```

---

## 🧪 테스트 케이스

### 기본 기능 테스트
```
✅ 메뉴얼 위젯 로드
   - JSON 파일 읽기
   - 데이터 파싱
   
✅ 탭 전환
   - 개요 탭 표시
   - 빠른 시작 탭 표시
   - FAQ 탭 표시
   - 용어 탭 표시
   
✅ AI 어시스턴트 연동
   - "AI에 물어보기" 버튼 클릭
   - AI 어시스턴트 탭으로 이동
```

### 통합 테스트
```
✅ 각 서비스별 도움말
   - 암호화폐 도움말
   - 주식 도움말
   - ETF 도움말
   - AI 어시스턴트 도움말
   
✅ 사용자 흐름
   1. 사용자가 거래소 선택
   2. 첫 거래 실패 또는 의문
   3. "❓ 도움말" 탭 클릭
   4. 관련 FAQ 확인 또는 "AI에 물어보기" 클릭
```

---

## 🎯 예상 효과

### 사용자 관점
- ✅ 자주 묻는 질문 즉시 해결
- ✅ 24/7 AI 상담 가능
- ✅ MD 파일을 읽을 필요 없음

### 개발팀 관점
- ✅ 문서 관리 간편화 (중복 제거)
- ✅ JSON 기반 데이터로 쉬운 업데이트
- ✅ 사용자 피드백 반영 용이

### 비즈니스 관점
- ✅ 사용자 경험 향상
- ✅ 고객 이탈률 감소
- ✅ 지원 비용 절감

---

## 💡 향후 확장 (Phase 4+)

### 동영상 튜토리얼 추가
```python
# 각 빠른 시작 스텝 옆에 "▶️ 영상" 버튼
"Step 1: 거래소 연결 [▶️ 영상 (1분)]"
  → YouTube 또는 내부 서버 링크
```

### 음성 안내 (향후)
```python
# TTS (Text-to-Speech) 통합
"🔊 이 문서를 읽어줄까요?" 버튼
```

### 다국어 지원 (향후)
```python
# EN, 중국어, 일본어 등
language_selector = ["한국어", "English", "中文", "日本語"]
```

### 반응형 디자인 (향후)
```python
# 모바일/태블릿 친화적 UI
# 텍스트 크기 조절
# 다크 모드 지원
```

---

## 📝 참고사항

### JSON 데이터 유지보수
```
user_manual_data.json 수정 시:
1. 각 서비스별 섹션 구조 유지
2. 용어는 한국어 + 영어 병기 (optional)
3. 예시는 최신 상태로 유지
4. 분기별 업데이트 권장
```

### UI 일관성
```
모든 도움말 탭은 동일한 UI 구조 유지:
  - 개요: 단락 형식
  - 빠른 시작: 번호 리스트
  - FAQ: Q&A 형식
  - 용어: 용어 정의 형식
```

---

## ✅ 최종 체크리스트

- [ ] `user_manual_widget.py` 구현
- [ ] `dashboard_modern.py` 수정 (도움말 탭 추가)
- [ ] 기본 기능 테스트 (데이터 로드, 탭 전환)
- [ ] 통합 테스트 (사용자 흐름)
- [ ] AI 어시스턴트 연동 확인
- [ ] 사용자 피드백 수집
- [ ] 문서 업데이트 (CHANGELOG)

---

**🔍 구현 시작 시 이 문서를 참고하세요!**  
**📧 질문이나 건의사항:** 개발팀 채널에 공유
