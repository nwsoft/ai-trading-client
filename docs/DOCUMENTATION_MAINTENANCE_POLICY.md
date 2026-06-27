# 📚 문서 관리 정책 (Documentation Maintenance Policy)

**작성일:** 2026년 4월 27일  
**목적:** 개발팀이 참고하는 문서 관리 원칙 - 중복 방지, 유지보수성 극대화, 사용자 경험 개선

---

## 📋 핵심 원칙

### 1️⃣ **3계층 정보 제공 구조**

```
최종 사용자 (일반인)
  ↓
  ├─ 대시보드 사용자 메뉴얼 (UI 내장)
  └─ AI 어시스턴트 (실시간 상담) ✨ 권장
  
개발팀 (우리)
  ↓
  └─ 기존 문서 (통합된 기술 명세서)
```

**원칙:**
- ❌ **사용자가 MD 파일을 읽지 않습니다**
- ✅ **대시보드와 AI 어시스턴트로만 정보 제공**
- ✅ **기존 문서는 개발팀 참고용으로 유지**

### 2️⃣ **신규 변경사항 동기화 필수 규칙 (2026-05-07 적용)**

기능/테스트/운영정책이 새로 추가되면, 같은 작업 배치에서 아래 항목을 함께 갱신한다.

**필수 동기화 대상:**
- `docs/CHANGELOG.md`: 변경 요약 + 날짜 + 검증 수치
- `docs/DEVELOPMENT_STATUS_COMPREHENSIVE_20260427.md`: 운영/완성도 관점 상태 반영
- `docs/TEST_STATUS.md`: 실제 실행한 테스트 명령/결과 반영
- `ui/widgets/user_manual_widget.py` 의 `📅 업데이트` 탭: 사용자 영향 중심 안내 반영

**버전 표기 규칙:**
- 배포 승인 전에는 버전을 올리지 않는다.
- 버전 고정 상태에서 변경이 발생하면 기존 버전 항목에 날짜 기반 하위 업데이트를 누적한다.
- 현재 기준: `v3.8.9.21` (2026-06-05 동기화 기준)

**사용자 공지 규칙:**
- 사용자가 체감하는 변화(화면, 동작, 제한, 위험, 준비 상태)는 인앱 메뉴얼에 반드시 포함한다.
- 개발 내부 세부사항(내부 리팩터링, 구조 정리)은 문서에 남기되 사용자 메뉴얼에는 영향 중심으로 축약한다.

**작업 종료 체크:**
- [ ] CHANGELOG 반영
- [ ] DEVELOPMENT_STATUS 반영
- [ ] TEST_STATUS 반영
- [ ] 사용자 메뉴얼 업데이트 탭 반영
- [ ] 날짜/버전 일치 확인

### 2-1️⃣ **자동 동기화 게이트 규칙 (2026-06-13 적용)**

기능 변경이 있을 때 문서/인앱 누락을 방지하기 위해 prekey/release 게이트에서 아래 검사를 필수로 수행한다.

- 실행 스크립트: `scripts/user_visible_sync_guard.py`
- 게이트 연동: `scripts/release_gate.py`의 `SYNC_GUARD` 단계
- 실패 조건:
   - 사용자 노출 코드(`ui/`, `trading/`, `api/`, `main.py`, `config/`) 변경 감지
   - 그런데 아래 4개 파일 중 하나라도 같은 배치에서 수정되지 않음
      - `docs/CHANGELOG.md`
      - `docs/USER_GUIDE.md`
      - `USER_GUIDE_AI_EXECUTION.md`
      - `ui/widgets/user_manual_widget.py`
- 예외 조건:
   - 문서/테스트/스크립트만 수정된 배치는 PASS

운영 원칙:
- 이 검사는 "권장"이 아니라 배포 전 필수 통과 항목이다.
- git 변경 목록을 수집할 수 없는 환경에서는 `--changed-files` 또는 `SYNC_GUARD_CHANGED_FILES`를 사용한다.

### 2-2️⃣ **사용자 문구 작성 규칙 (2026-06-13 적용)**

사용자용 문서/인앱 매뉴얼에는 내부 구현 식별자를 기본적으로 노출하지 않는다.

- 지양: 함수명/설정 키/파일 경로/스크립트 경로 (`_show_goals`, `stock_auto_trading`, `docs/...`, `scripts/...` 등)
- 권장: 사용자가 화면에서 보는 버튼명/탭명/행동 순서 중심 표현
- 예시:
   - "목표 관리 버튼 오류(`_show_goals`) 수정" → "목표 관리 버튼 오류 수정"
   - "점검 정본 문서 경로" → "설정 화면의 점검 가이드 버튼으로 확인"

예외:
- 개발자 전용 문서(CHANGELOG, DEV_GUIDE, 기술 보고서)에는 필요한 범위에서 내부 식별자 사용 가능

---

## 📑 현재 핵심 문서 (개발팀용)

### 의무 문서 (반드시 최신 유지)

| 문서 | 파일 | 목적 | 담당 |
|------|------|------|------|
| **사용자 가이드** | `USER_GUIDE.md` | 서비스 개요, AI 역할, 현재 기능 상태 | 기술 리드 |
| **거래 흐름 명세** | `TRADING_FLOW.md` | TP/SL, 거래 파이프라인, 코드 경로 | 거래 개발 |
| **아키텍처** | `ARCHITECTURE.md` | 전체 시스템 구조 | 아키텍처 리드 |
| **API 레퍼런스** | `API_REFERENCE.md` | API 명세 | API 개발 |

### 참고 문서 (필요시 업데이트)

| 카테고리 | 파일 예시 | 용도 |
|---------|----------|------|
| **증권 (주식/ETF)** | `STOCK_ETF_*.md` | 증권 기능 설명 |
| **AI 시스템** | `AI_API_ARCHITECTURE.md` | AI 통합 방식 |
| **거래 최적화** | `OPTIMIZATION_GUIDE.md` | 성과 개선 |
| **빌드/배포** | `BUILD_GUIDE.md` | 프로젝트 구축 |

### 아카이브 문서 (`docs/archive/`)

| 분류 | 파일 예시 | 보관 이유 |
|------|----------|---------|
| 분석 보고서 | `BUG_FIX_REPORT_*.md` | 과거 이슈 기록 |
| 상태 리포트 | `STATUS_REPORT_*.md` | 진행 상황 추적 |
| 기술 검증 | `VERIFICATION_*.md` | 테스트 결과 |

---

## ✅ 문서 작성 가이드

### 새 문서를 만들려고 할 때

**체크리스트:**
```
❌ 기존 문서에 병합할 수 있나?
   → YES → 기존 문서에 추가 (새 섹션)
   → NO → 계속

❌ 개발팀만 필요한가?
   → YES → `docs/` 에 작성 (기술 문서)
   → NO → 다음 스텝

❌ 사용자를 위한 정보인가?
   → YES → "대시보드 메뉴얼" 또는 "AI 어시스턴트" 데이터로 작성
   → NO → 아카이브에 저장
```

### 기존 문서 수정할 때

**절차:**
1. 해당 기존 문서 열기 (USER_GUIDE, TRADING_FLOW 등)
2. 해당 섹션 찾아서 업데이트
3. 다른 관련 문서의 이전 정보 제거 (중복 제거)
4. CHANGELOG.md에 기록

**예시:**
```
❌ 나쁜 방식
- QUICK_START_GUIDE.md (새로 만듦)
- GETTING_STARTED.md (새로 만듦)
- START_HERE.md (새로 만듦)
→ 혼란, 관리 어려움

✅ 좋은 방식
- USER_GUIDE.md 에 "⚡ 5분 시작" 섹션 추가
→ 한 곳에서 관리
```

---

## 🎯 정보 제공 우선순위

### 최우선 (사용자에게)
1. **대시보드 사용자 메뉴얼** (UI 내장 도움말)
   ```python
   # ui/dashboard_modern.py 에서 구현 필요
   class UserManualPanel:
       - "도움말" 탭
       - 서비스별 컨텍스트 도움말
       - FAQ
       - "AI에 물어보기" 버튼
   ```

2. **AI 어시스턴트** (LLM 기반 실시간 상담)
   ```python
   # data/nwsoft/user_manual_data.json 필요
   {
       "user_manual": {
           "start": "5분 내 시작하기...",
           "faq": {...},
           "glossary": {...}
       }
   }
   ```

### 차순위 (개발팀이)
1. **통합된 기술 문서** (USER_GUIDE, TRADING_FLOW 등)
2. **코드 주석** (실제 구현 근거)
3. **CHANGELOG** (변경 이력)

---

## 🗑️ 문서 정리 규칙

### 정기적으로 정리 (분기별)

```python
불필요한 문서 판단 기준:

1. 작성 후 1년 이상 수정 없음
2. 코드와 일치하지 않음 (deprecated)
3. 다른 문서에 이미 포함됨 (중복)
4. "~계획", "~예정", "~진행 중" 등 미완성 표시

→ archive/ 로 이동 또는 삭제
```

### 문서 생명 주기

```
작성 (Creation)
   ↓
개발 (Development)
   ├─ 정기 업데이트 (Maintenance)
   └─ 버전 관리 (Versioning)
   ↓
아카이브 (Archive) or 삭제 (Delete)
```

**타임라인:**
- 새 기능 출시: 즉시 문서 업데이트
- 버그 수정: 문서는 수정 불필요 (코드가 진실)
- 아키텍처 변경: 반드시 문서 업데이트
- 1년 미사용: archive 이동 고려

---

## 🔄 현재 상태 (2026-04-27)

### ✅ 완료된 작업

1. **기존 2개 문서에 새로운 내용 통합**
   - `USER_GUIDE.md` ← "⚡ 5분 시작" 섹션 추가
   - `TRADING_FLOW.md` ← "거래 흐름도" 및 코드 경로 추가

2. **불필요한 새 문서 삭제**
   - ❌ `COMPREHENSIVE_TRADING_GUIDE.md` (내용 USER_GUIDE + TRADING_FLOW로 통합)
   - ❌ `QUICK_START_GUIDE.md` (내용 USER_GUIDE로 통합)
   - ❌ `DOCUMENTATION_INDEX.md` (대시보드 메뉴얼로 구현 예정)

3. **archive 폴더 생성**
   - 향후 아카이브 문서 이동 시 사용

### 🚧 진행 중

1. **대시보드 사용자 메뉴얼 UI 설계** (Phase 3)
   - 서비스별 탭 기반 도움말
   - 컨텍스트 기반 가이드
   - FAQ & "AI에 물어보기" 버튼

2. **AI 어시스턴트 학습 데이터 작성** (Phase 4)
   - `data/nwsoft/user_manual_data.json`
   - FAQ, 튜토리얼, 용어 설명

3. **기존 불필요 문서 정리** (Phase 5)
   - 132개 중 100개+ 를 archive로 이동
   - 활성 문서는 10개 이하로 유지

---

## 📊 문서 유지보수 체크리스트

### 월간
- [ ] 기존 문서와 코드 일치 여부 확인
- [ ] deprecated 문서 확인

### 분기별
- [ ] 새로 작성된 문서가 기존 문서와 중복되지 않나?
- [ ] 불필요한 문서를 archive로 이동했나?

### 연간
- [ ] 모든 문서의 "마지막 업데이트" 확인
- [ ] 대시보드 메뉴얼 and AI 어시스턴트 동기화

---

## 🎯 최종 목표 (2026년 말)

```
사용자가 얻는 정보:
✅ 대시보드 내장 메뉴얼 (한국어, 컨텍스트 기반)
✅ AI 어시스턴트 상담 (24/7 한국어, 맞춤형)

개발팀이 참고하는 문서:
✅ 핵심 문서 (5~10개만) - 최신 상태 유지
✅ 아카이브 (참고용) - 과거 기록 보관

결과:
✅ 문서 관리 간편화
✅ 사용자 경험 개선
✅ 개발 속도 향상
```

---

## 💡 참고: 대시보드 메뉴얼 구현 예시 (향후)

```python
# ui/dashboard_modern.py (진행 예정)

class UserManualPanel:
    """서비스별 컨텍스트 도움말"""
    
    def show_manual_for_service(self, service):
        """선택된 서비스에 맞는 메뉴얼 표시"""
        data = load_user_manual_data(service)
        
        tabs = [
            ("📘 개요", data['overview']),
            ("⚡ 빠른 시작", data['quick_start']),
            ("❓ FAQ", data['faq']),
            ("📚 용어", data['glossary']),
        ]
        
        # AI에 물어보기 버튼
        ask_ai_button = Button("🤖 AI에 물어보기", on_click=self.chat_with_ai)
```

```json
// data/nwsoft/user_manual_data.json (필요한 데이터)

{
  "cryptocurrency": {
    "overview": "암호화폐는 24시간 거래가 가능한 자산입니다...",
    "quick_start": {
      "step1": "거래소 선택: Bybit, OKX, Bitget, Upbit, Bithumb 중 선택",
      "step2": "API 연결: API 키와 시크릿 입력",
      "step3": "코인 선택: BTC, ETH, SOL 등 분석",
      ...
    },
    "faq": {
      "q1": "데모 모드는 뭐야?",
      "a1": "실제 돈을 쓰지 않고 연습하는 모드입니다..."
    }
  },
  "stock": {
    "overview": "주식 거래는 정규 장시간(09:00~15:30)에만 가능합니다...",
    "quick_start": {...},
    "faq": {...}
  }
}
```

---

**✉️ 질문이나 개선 사항:** 이 정책 문서에 코멘트를 남겨주세요.

**🔄 마지막 업데이트:** 2026년 4월 27일
