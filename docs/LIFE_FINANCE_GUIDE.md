## 2026-10-05 — v3.9.2.5 생활금융 비교·후속 관리 (로컬 소스 후보)

현재 소스 후보: v3.9.2.5 · updater 3.9.205. 현재 공개 기반: v3.9.2.4 (사용자 배포 확인·기존 게시 보고서).
현재 소스 후보 버전: **v3.9.2.5**

공개 v3.9.2.4 이후 수정입니다. 상황별 진입, 목적 필터, 관심 보험 근거 설명, 비상금·보장·대환·사용 날짜 비교, 암호화 계획과 공통 조건, 자료 피드 갱신/복구, 상담 회신 견적, 기록 수정·가져오기를 구현합니다. [반영 범위·검증·운영 연결 인수](V3925_LIFE_FINANCE_COMPLETION.md). **3.9.2.5 설치본을 게시한 상태는 아닙니다.** 아래 날짜별 후보/미게시 문장은 당시 이력입니다.

# 생활금융 사용 가이드

## 현재 사용 흐름: v3.9.2.4 소스 후보 / 공개 기반 v3.9.2.3

1. **생활금융 → 금융상품**에서 보험·대출·예적금을 고릅니다. 상품명이나 견적 없이 시작할 수 있습니다.
2. 보험은 **없어요 / 잘 모르겠어요 / 있어요**와 걱정되는 상황을 고릅니다. 대출은 생활비·주거·대환, 저축은 목돈·월 납입·비상금처럼 목적부터 고릅니다. 금액·기간은 아는 경우에 입력합니다.
3. 질문을 직접 적으면 기본 안내가 목적을 해석합니다. 해석이 어렵다면 **내 말을 AI로 이해하기**에서 설정된 AI로 요청할 수 있습니다. API 키가 없으면 **AI 엔진/API 설정 열기**로 이동해 연결·모델을 저장합니다. 보낼 내용을 확인한 후 요청합니다. 결과의 **이 해석이 맞아요**를 눌러 상황에 적용합니다.
4. 유형 차이·비교 기준·다음 확인 질문을 읽습니다. 유효한 출처가 연결된 회사·상품 후보는 검색하고 선택할 수 있습니다. 보험은 **보험회사·상품 둘러보기**에서 목적을 몰라도 회사·종류·보장 검색으로 탐색할 수 있습니다. 관심 상품 최대 4개의 특징을 나란히 비교하고 **선택 상품으로 비교·상담 준비**로 이어갑니다. 외부 비교 사이트로 이동할 필요가 없습니다. 전체 금융사 최신 조회를 보장하지 않습니다.
5. **이 상황으로 비교·상담 준비하기**에서 선택 조건을 이어갑니다. 이미 견적이 있다면 직접 비교 입력을 펼칩니다. AI 설명은 선택 조건과 수신 모델을 미리 확인한 뒤 요청합니다.
6. 상담 연결은 지정 상담사 또는 기관 API를 연결할 수 있는 구조입니다. 실제 수신처 등록·접수 확인이 있어야 접수 완료로 볼 수 있습니다. 수동 전달 자료 저장만으로 기관 접수가 완료되지는 않습니다.

[3.9.2.4 구현·모델·검증 범위](V3924_FINANCE_DECISION_UPDATE_PLAN.md). 새 설치본 게시와 실제 계정·기관 인수는 별도입니다. 아래는 과거 판본의 기록이며 현재 화면과 다르면 위 흐름을 우선합니다.

## 보험 상품을 모를 때

**보험회사·상품 둘러보기 → 종류/회사/보장 검색 → 상품 상세 → 관심 상품 선택 → 나란히 비교 → 비교·상담 준비** 순서로 이용합니다. 개인 견적이 없어도 특징과 확인할 질문을 비교할 수 있습니다. 서로 다른 종류도 표에서 읽을 수 있으며, 상담 준비는 같은 종류끼리 진행합니다. 선택은 검색 필터를 바꿔도 유지되고 보관함을 잠그면 초기화됩니다.

초기 탐색 자료는 삼성화재·현대해상·DB손해보험·교보라이프플래닛의 **7개 상품**입니다. 2026-10-04에 확인한 공식 안내의 상품명과 짧은 특징 요약이며 전체 시장·판매 상태·가입 자격·개인 보험료를 보증하지 않습니다. 보험료나 가격 순위를 만들어 표시하지 않습니다. 확인일·재확인 기한을 표시하고 기한이 지나면 관심 상품 선택을 보류합니다. 원문 링크는 상세의 ‘자료 출처’에 있습니다.

개인 견적·약관 조건이 확보되면 기존 계산·보장 비교를 이용합니다. 관심 상품은 상담 확인 질문과 선택한 비교 공유 범위에 포함됩니다. 상담 수신처 등록과 별도 동의·전송·접수 확인 전에는 앱 밖으로 보내지 않습니다. 탐색 자료 새로고침이 보험회사 실시간 조회를 뜻하지는 않습니다.

자료 운영·갱신 및 연동 범위는 [보험 내부 탐색 자료 운영](INSURANCE_REFERENCE_DIRECTORY.md)을 참고하세요.

## 빠른 질문 분류는 왜 쓰나요?

상품을 잘 모르면 ‘운전자 보장’이나 ‘대환’처럼 어떤 안내를 선택해야 할지도 어렵습니다. 빠른 질문 분류는 내 표현을 읽고 먼저 알아볼 유형을 찾아주는 선택 기능입니다. “보험은 없고 차로 출퇴근해요”라고 적으면 ‘보험 없음 · 운전 관련 보장’을 제안하고, 내가 확인한 뒤 해당 유형의 설명과 비교 준비로 이어집니다.

모델을 반드시 선택해야 금융상품을 이용할 수 있는 것은 아닙니다. 상황 버튼으로 고를 수 있다면 기본 안내를 그대로 쓰면 됩니다. 짧은 목적 판단을 자세한 설명과 나누는 이유는 반복하는 간단한 질문의 대기 시간과 비용을 줄이기 위해서입니다. 실제 절감 폭이나 정확도 우열은 검증 전이며 모델·질문·서비스 상태에 따라 달라집니다.

| 원하는 도움 | 사용할 기능 | 외부 AI 호출 |
|---|---|---|
| 내 상황에 해당하는 버튼을 고를 수 있어요 | 상황 버튼·내 PC의 기본 안내 | 없음 |
| 내 표현을 기본 안내가 이해하지 못해요 | 내 말을 AI로 이해하기 | 미리보기 확인·동의 후 선택 모델로 요청 |
| 어떤 조건을 비교하고 왜 확인하는지 자세히 알고 싶어요 | 선택한 내용으로 AI 설명 더 보기 | 별도 미리보기 확인·동의 후 요청 |

분류 결과만으로 개인 상품 추천·최적화·비교 설명이 완성되지는 않습니다. 후속 안내에서 조건과 근거를 확인해야 합니다.

### Jev와 어떤 관계인가요?

Jev는 정해진 질문에 선택·점수 등 구조화된 판단 결과를 반환하는 모델입니다. [TypeSafe 공식 설명](https://docs.typesafe.ai/introduction). NoahAI는 그 활용 취지 중 ‘짧은 목적 분류’를 기존 지원 AI로 이용하도록 했습니다. 현재 이 기능은 Jev를 직접 호출하지 않으며 Jev 설치·별도 가입이 필요하지 않습니다. 기존 대화 모델에 정해진 선택지를 요청하고 결과를 검증하는 방식으로, Jev와 같은 속도·정확도·확률 기능을 제공한다고 검증한 것은 아닙니다.

### 모델과 기본값은 어떻게 고르나요?

설정 → AI 엔진/API에서 키가 등록된 서비스의 후보를 선택할 수 있습니다. OpenAI의 GPT-6 Luna, Gemini의 Flash-Lite, DeepSeek의 Flash, Claude의 Haiku, Kimi K2.6을 후보로 표시합니다. 이는 성능 순위나 모든 계정의 사용 가능 보장이 아닙니다. 처음 기본값은 GPT-6 Luna입니다. 다른 서비스 키만 등록했다면 그 서비스의 모델을 선택하세요. API 키가 없다면 상황 버튼으로 계속 이용할 수 있습니다.

모델을 변경했다면 설정 → AI 엔진/API에서 ‘현재 설정 저장’을 눌러 적용합니다. 매번 변경할 필요가 없고, 이 생활금융 분류에만 적용됩니다. 모델 선택·설정 저장만으로 분류 요청이나 요금 청구가 시작되지는 않습니다. 실제 실행 전에 질문·수신 모델·비용 가능성을 확인하고 동의합니다.

응답에서는 해석한 목적과 질문에서 찾은 근거를 확인합니다. 맞으면 ‘이 해석이 맞아요’를 누르고, 틀리면 상황 버튼이나 질문을 수정하세요. 응답 오류·불확실한 해석은 적용하지 않고 기본 안내를 계속 이용할 수 있습니다. 실제 상품의 금리·보험료·가입 가능 여부와 거래 승인·보호 설정은 이 분류가 결정하지 않습니다.

## 과거 판본: 2026-10-02 · 3.9.2.2 소스 후보 / 당시 공개 3.9.2.1

## 3.9.2.1에서 사용하는 순서

1. 생활금융 → 거래에서 원화 수입·지출을 등록합니다. 자기 소유 계좌 간 이동만 `내 계좌 이체`로 등록합니다. 타인에게 지급한 생활비를 내부 이체로 제외하지 마세요. 기존 기록은 자동 재분류하지 않습니다.
2. 대시보드의 `이번 달 내 돈 점검`에서 기간·마지막 기록·누락 안내·지출 비중을 확인합니다. 등록 기록의 차액은 은행 잔액이나 투자 가능액이 아닙니다.
3. `수입이 줄면 어떻게 달라질까?`에 월 수입·생활비·대출 상환·목표 적립을 직접 입력합니다. 없는 항목은 0, 중복 지출은 제외합니다. 월간 계획은 저장하거나 외부로 전송하지 않습니다.
4. `이 점검을 AI에게 질문`은 질문 초안만 엽니다. 전송은 사용자가 선택합니다. 자산통합의 같은 점검에서 생활금융으로 이동할 수 있습니다.
5. 가족 전체 자동 수집·실제 은행 이체·금융상품 가입은 제공하지 않습니다. 목표 적립과 PAPER 성과를 실계좌 자산에 더하지 않습니다.

공식 자료·설계·별도 개발 항목: [현행 업데이트 계획](V3921_PERSONAL_FINANCE_PLAN.md). 아래 예전 화면별 설명과 현행 계약이 다르면 이 절을 우선합니다. 키워드 기반 분류를 별도 외부 AI 호출로 오해하지 마세요.

내 계좌 이체는 별도 `life_finance_transfers.json` 파일로 백업·동기화됩니다. 구버전에서는 이체 목록을 표시하지 않지만 수입·지출에 잘못 합산하지 않으며, 새 버전에서 다시 조회할 수 있습니다. 수동으로 자료를 옮길 때는 이 파일도 수입·지출 및 목표 파일과 함께 보관하세요.

<a id="insurance-workspace"></a>

## 3.9.2.2 금융상품 비교 — 처음 사용하는 순서

금융상품을 열면 **전체 안내 / 대출 비교 / 보험 비교 / 예금·적금 비교**가 보입니다. 이전의 여러 상품 조건 혼합 입력·신용도 기반 샘플 순위 화면을 목적별 가이드로 교체했습니다.

1. **전체 안내:** 빌릴 돈·보장·모을 돈 중 목적을 고릅니다. 서로 다른 상품을 하나의 순위로 추천하지 않습니다.
2. **가상 예시로 연습:** 대출/예적금 탭에서 직접 누른 경우에만 가상 금리와 금액이 채워집니다. 수정해도 예시 표시는 유지됩니다. `비우고 내 조건 입력`으로 실제로 받은 조건을 별도로 입력하세요.
3. **대출:** 같은 금액·기간에서 두 연 금리와 추가 비용을 비교합니다. 원리금균등/원금균등/만기일시를 고르고 월 상환 흐름·총 이자를 확인합니다. 비용을 모르면 빈칸으로 두며 총비용도 미확인으로 남습니다.
4. **예금·적금:** 목돈 한 번과 매월 납입을 구분합니다. 유형 변경 시 금액은 지워 다시 확인합니다. 세율 미입력은 세전 이자까지만 표시합니다. 예시 세율 15.4%는 모든 상품/개인의 적용 세율을 뜻하지 않습니다.
5. **보험:** 쉬운 용어와 저장되지 않는 가상 비교 예시를 읽은 뒤 아래 암호화 `내 보험 이해·비교`로 진행합니다. 원문 등록·계약 저장은 기존 별도 절차입니다.
6. **모르면 질문:** 각 탭의 용어 설명은 즉시 읽을 수 있습니다. 자주 묻는 질문→초안 수정→`AI 도움 열기`를 누르면 같은 화면 아래에서 어시스턴트가 열립니다. 직접 전송하기 전 호출하지 않고, 보험 원문·입력 조건은 자동 첨부하지 않습니다. 일반 비교 용어는 로컬 안내로 답하며 외부 AI 사용 경계는 기존 어시스턴트 설정을 따릅니다.

입력은 내부 상품 탭 전환/AI 도움 열기·닫기 동안 유지됩니다. 상위 화면 이동·앱 종료 후 대출/예적금 입력은 보존하지 않습니다. 메모/출처/확인일은 사용자 기록이며 금융사 검증이 아닙니다. 계산값 변경 시 이전 결과를 지워 오래된 값과 섞지 않습니다.

계산 범위는 동일 금리·월 단위 정상 납입, 예적금 단리·적금 매월 초 납입입니다. 일수·복리·변동금리·연체·거치기간·중도해지/상환·우대 조건은 자동 반영하지 않습니다. 표시 반올림은 원 단위 참고이며 금융사 상환표/확정 수령액과 다를 수 있습니다. **실시간 전체 금융사 조회·실제 견적·가입/대환/보험 해지·상담 접수 기능은 아닙니다.**

## 3.9.2.2 내 보험 이해·비교 사용법 (소스 후보)

1. **생활금융 → 금융상품 → 보험 비교 → 내 보험 이해·비교**에서 보험 자료 전용 비밀번호(12자 이상)로 저장소를 만듭니다. 앱 로그인과 별개이며 서버에 보내지 않고 PC 자료를 암호화합니다. **분실 시 복구할 수 없습니다.** 개봉 후 15분 또는 직접 잠금/계정 변경 시 잠깁니다.
2. 제공 권한이 있는 PDF/PNG/JPEG를 등록합니다. 파일당 20MB·PDF 100쪽, 보관 원본 합계 20MB·5개, 한 번에 1개입니다. 폴더/ZIP/Drive·암호 PDF 해제는 미지원입니다. 불필요한 건강정보·주민번호는 등록 전 가리세요.
3. `원문 대조`에서 이미지/PDF 텍스트를 봅니다. PDF 표·배치는 원본을 따로 저장·열어서 확인하세요. `입력 초안 만들기`는 명시된 상품명·보험사·월 보험료만 찾으며 상충값은 비웁니다. 스캔 OCR·자유 약관 해석·자동 승인은 하지 않습니다.
4. `계약·보장 입력 및 확인`을 펼쳐 계약/견적·상태·통화·보험료/주기·보장/납입/갱신 날짜를 입력합니다. 미확인 금액·조건은 빈칸입니다. 보장별 지급 조건·제외·면책·감액·자기부담·정액/실손·갱신과 문서/쪽/인용을 연결합니다. 이미지 전사는 사용자 입력으로 표시합니다.
5. 초안 저장은 비교 대상이 아닙니다. 원문·단위·기간을 대조한 후 확인 체크하여 저장합니다. 사용자 확인은 보험사 검증·가입 유효성·지급 확정이 아닙니다. 유지 계약의 통화별 월 환산 소계에 미확인/기간 상충 금액을 넣지 않습니다.
6. 1개 계약 점검 또는 최대 2개 사실 비교를 합니다. 보험료 차이는 **두 번째−첫 번째 월 환산값**이며 절감 보장/동등 보장이 아닙니다. 인수·면책 재시작·환급 손실·보장 축소를 보험사에 확인하세요. 유지도 선택지입니다.
7. 질문지 미리보기에서 민감정보를 직접 지운 뒤 검토 체크 후 TXT로 저장합니다. **TXT는 비암호화**이며 자동 가림은 완전하지 않습니다. 외부 상담 접수·AI 전송은 하지 않습니다.
8. 암호화 백업과 비밀번호는 따로 보관합니다. 복원은 **동일 계정·보험 저장소가 없는 새 설치**에서만 가능하고 기존 자료를 자동 덮어쓰지 않습니다. 원문 삭제 시 연결 계약 확인 해제·관련 분석 제거, 수정 시 재비교가 필요합니다. 외부 백업/TXT 사본은 직접 삭제하세요.

생활금융 첫 화면/재무 분석과 자산통합의 `보험료 계획 확인`은 실제 지출/계좌 잔액과 별개이며 자동 가계부 기록·가입금액 자산 합산을 하지 않습니다. 보험 질문은 심층분석에서도 로컬 안내로 답합니다.

샘플 보험의 보장 점수 추천·기본 예산 7만원·예산 불일치 시 전체 추천은 제거했습니다. 미입력 예산은 직접 요청하며 근거 없는 최적 상품을 만들지 않습니다. 자료 없음=미가입/보장 0, 중복 가능성=해지 필요가 아닙니다. 전체 보험사 비교/상담사 연결은 미제공입니다. [상세 지원 범위·인수 상태](LIFE_FINANCE_PRODUCT_COMPARISON_ANALYSIS_20260429.md#v3922-insurance-plan). 아래 예전 보험 예시는 이력이며 이 절이 우선합니다.

## 📌 개요

생활금융은 NoahAI Client의 현재 서비스 영역입니다. 현금흐름·거래 기록·목표·보안 경고·세금 계산·대출/보험/예적금 비교 화면과 계산 기능을 단계적으로 제공합니다.

**상태**: ✅ Client 제공 중 · 기능별 단계적 확대

금융상품 비교는 앱 기본 데이터와 사용자 입력을 이용한 정보·시뮬레이션입니다. 실제 금리·보험료 확정, 가입·대출 실행, 보험 계약, 금융기관 심사나 전문 자문을 대신하지 않습니다. 공식 금융기관 데이터/API 연동과 전면 음성 접근성은 기능별로 별도 준비 상태를 표시합니다.

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
    auto_classify=True  # 로컬 키워드 규칙으로 '식비' 분류
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

### 6️⃣ 세무 간이 계산 및 제도 안내

금융투자소득세는 폐지되어 세액을 계산하지 않습니다. 다른 세금까지 비과세라는 뜻은 아닙니다. 근로소득공제는 소득세법 제47조 구간과 2천만원 한도를 반영했습니다. 다른 간이 계산의 전체 귀속연도·예외 사항은 검증 완료가 아니며, 신고액/환급액 확정에 사용하지 마세요.

```python
from trading import tax_calculation_service as svc

# 연말정산 종합 계산
result = svc.calc_year_end_tax_settlement(
    annual_salary=50_000_000,
    credit_card=8_000_000,
    debit_cash=3_000_000,
    medical_expense=1_500_000,
    education_expense=2_400_000,
    donation=500_000,
    pension_savings=6_000_000,
    irp_contribution=3_000_000,
)
print(result['final_tax'])  # 일부 입력으로 계산한 간이값. 최종 신고/환급액 아님

# 금융소득 종합과세 판정
check = svc.check_financial_income_comprehensive_tax(
    interest_income=1_500_000,
    dividend_income=800_000,
    annual_salary=60_000_000,
)
print(check['subject_to_comprehensive_tax'])  # 단순 금액 기준 점검

# 금투세 폐지 안내: 세액을 0으로 반환하지 않음
tax = svc.calc_financial_investment_tax(
    domestic_stock_profit=20_000_000,
    overseas_stock_profit=10_000_000,
)
print(tax['message'])  # 폐지 안내
assert tax['total_tax'] is None

# ISA / 연금저축 / IRP 절세 비교
comparison = svc.compare_tax_saving_accounts(
    annual_salary=50_000_000,
    annual_investment=3_000_000,
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
| 📈 금투세 폐지 안내 | "금투세 얼마 내야 해?" |
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
- ✅ 세무 계산 (연말정산·금융소득 간이 점검·금투세 폐지 안내·ISA/IRP 가정 비교)
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
- ✅ 세무 계산 서비스 (연말정산 간이 계산·금투세 폐지 안내·절세 가정 비교)
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
- 연말정산 간이 계산·금투세 폐지 안내·ISA/연금저축/IRP 가정 비교를 제공합니다. 확정 세액이나 상품 적합성 판정이 아닙니다.
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
| B. 투자소득 과세 안내 | 금투세 폐지로 세액 미계산. 귀속연도·상품·거주성 확인 필요 |
| C. 절세 계좌 비교 | ISA / 연금저축 / IRP — 기대 절세액 비교 |
| D. 절세 최적화 팁 | 5가지 우선순위 팁 자동 생성 |

#### 연동 서비스
- `trading/tax_calculation_service.py`
  - `calc_year_end_tax_settlement(params)` — 연말정산 계산
  - `calc_financial_investment_tax(params)` — 금투세 폐지 안내
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
