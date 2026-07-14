# v3.8.9.28 업데이트 순차 테스트 체크리스트

기준일: 2026-07-11
대상 버전: v3.8.9.28
목적: 이번 차(28버전) 반영 항목을 순서대로 확인하고, 각 단계 종료 시 대시보드에서 확인할 포인트를 명확히 고정한다.

실행 결과 요약(2026-07-11):

- 자동 검증 완료: STEP 1, 2, 3, 4, 7
- 수동 확인 필요: STEP 5(대시보드 상용 리모델링), STEP 6의 인앱 화면 확인
- 최종 게이트 결과: py_compile 통과, pytest 핵심 묶음 10 passed

추가 반영(2026-07-12):

- fee 1차 반영: 거래 통계 탭/거래소 통계 라벨/AI 리포트(오늘/실시간) 비용 지표 표시
- fee 2차 안전 패치: 사용자 DB 경로의 exchange_trade_stats 컬럼 자동 보강 + 1회 백필 + 합계 대조

---

## 0. 사용 방법 (중요)

- 이 문서는 "순차 진행" 기준이다. 위에서 아래로만 진행한다.
- 각 단계는 다음 3개를 모두 만족해야 완료 처리한다.
  - 코드/동작 확인
  - 대시보드 확인
  - 테스트/검증 명령 통과
- 한 단계라도 실패하면 다음 단계로 넘어가지 않는다.

완료 표기:

- `[x]` 완료
- `[ ]` 미완료

---

## 1. 패치 맵 (무엇이 반영됐는지 한눈에)

1. 코인 선택 안정화
   - 목표 코인 수 달성 후 fallback 재진입 차단
2. 학습/로그 안정화
   - exchange 태그 정합
   - API 딜레이 O(1) 롤링 윈도우
   - timezone-aware UTC 정규화
   - 중복 로그 억제 + 비차단 파일 기록
3. S등급 기능
   - S-1: 계좌 건강도 + 거래 복기
   - S-2: 포트폴리오 진단(노출/현금비율/최대편중/상태요약)
4. 대시보드 상용 리모델링
   - 1차: 반응형 분할폭
   - 2차: 운영 KPI/운영 알림 추가
   - 3차: KPI 클릭 딥링크 + 심각도 배지 + 서비스별 KPI 분기
   - 4차: 우측 패널 스크롤 + 통합 잔고 구조화 + 연결 상태
5. 문서/인앱 동기화
   - UPDATE_PLAN/CHANGELOG/인앱 업데이트 반영

---

## 2. 사전 준비

### 2.1 실행 환경

- 프로젝트 루트로 이동

```bash
cd /Users/playone/SynologyDrive/Works/noahai_client
```

- 앱 실행

```bash
python3 main.py
```

### 2.2 기본 검증 명령

```bash
python -m py_compile ai_chat_strategy.py ui/dashboard_modern.py ui/widgets/user_manual_widget.py
PYTHONPATH=. pytest -q tests/test_ai_chat_performance_review.py tests/test_evaluator_selection_flow.py tests/test_exchange_learning_manager.py tests/test_auto_update_manager.py
```

통과 기준:

- py_compile 오류 0건
- pytest 실패 0건

---

## 3. 순차 테스트 절차

## STEP 1. 코인 선택 안정화 검증

목표: 목표 개수 달성 후 불필요 fallback 재진입이 없는지 확인

체크:

- [x] `tests/test_evaluator_selection_flow.py` 실행 시 통과

```bash
PYTHONPATH=. pytest -q tests/test_evaluator_selection_flow.py
```

대시보드 확인(단계 종료 시):

- [ ] 실시간 거래 로그에서 코인 선택 결과가 한 번 확정된 뒤 즉시 재선정 루프가 반복되지 않는지 확인
- [ ] 선택 완료 후 같은 사이클에서 fallback 관련 과다 로그가 연속 발생하지 않는지 확인

통과 판정:

- 테스트 통과 + 로그상 재선정 폭주 없음

---

## STEP 2. 학습/로그 안정화 검증

목표: 거래소별 학습 정합, API 딜레이 판단 안정, 로그 폭주 억제 확인

체크:

- [x] `tests/test_exchange_learning_manager.py` 통과
- [x] `tests/test_auto_update_manager.py` 통과

```bash
PYTHONPATH=. pytest -q tests/test_exchange_learning_manager.py tests/test_auto_update_manager.py
```

대시보드 확인(단계 종료 시):

- [ ] 실시간 거래 로그에서 동일 에러/경고가 짧은 시간에 과다 반복되지 않고 요약 형태로 보이는지 확인
- [ ] UI 체감상 로그 폭주로 멈춤처럼 보이는 현상이 없는지 확인

통과 판정:

- 테스트 통과 + 운영 로그 가독성/응답성 문제 재발 없음

---

## STEP 3. S-1 계좌 건강도 + 거래 복기 검증

목표: 성과검토 응답에 건강도/복기 지표가 구조적으로 출력되는지 확인

체크:

- [x] `tests/test_ai_chat_performance_review.py` 통과

```bash
PYTHONPATH=. pytest -q tests/test_ai_chat_performance_review.py
```

대시보드 확인(단계 종료 시):

- [ ] AI 어시스턴트에 "성과", "복기", "건강도" 질의 시 응답에 아래 항목이 포함되는지 확인
  - 건강도 점수/등급
  - 승률/순손익/Profit Factor
  - Sharpe/MDD
  - 거래 복기 코멘트

통과 판정:

- 테스트 통과 + AI 어시스턴트 응답 필드 확인 완료

---

## STEP 4. S-2 포트폴리오 진단 검증

목표: 성과검토 응답에 포트폴리오 진단(노출/현금비율/편중/요약)이 포함되는지 확인

체크:

- [x] `tests/test_ai_chat_performance_review.py` 통과

```bash
PYTHONPATH=. pytest -q tests/test_ai_chat_performance_review.py
```

대시보드 확인(단계 종료 시):

- [ ] AI 어시스턴트에 "포트폴리오 진단", "편중", "현금비율" 질의 시 응답에 아래 항목이 포함되는지 확인
  - 포지션 수
  - 포지션 노출
  - 현금 비율
  - 최대 편중 심볼/비율
  - 상태 요약(분산 양호/편중 주의/편중 위험)

통과 판정:

- 테스트 통과 + AI 응답에서 포트폴리오 진단 섹션 확인

---

## STEP 5. 대시보드 상용 리모델링 1~4차 검증

목표: 운영자가 첫 화면에서 판단 가능한지(가시성/동선/접근성)

주의:

- 본 단계의 운영 KPI 카드는 관리자용 최신 운영 집계 영역입니다.
- 외부 공개 웹 KPI(코호트/정적 스냅샷)와 같은 숫자가 바로 나오지 않아도 이상이 아닙니다.
- 평균 보유시간, 응답시간, AI 추론 관련 수치는 28버전 배포 이후부터 누적되므로 초기에는 0일 수 있습니다.

체크:

- [ ] 앱 실행 후 `📊 실시간 거래 로그` 탭 진입
- [ ] 우측 패널이 운영 모니터링 센터 구조로 표시되는지 확인

대시보드 확인(단계 종료 시):

- [ ] 운영 KPI 카드(포지션/거래수/손익/승률)가 보인다
- [ ] 운영 KPI와 공개 KPI가 목적상 다른 수치 체계라는 점을 QA 시 혼동하지 않는다
- [ ] 운영 알림 카드와 심각도 배지(정상/주의/위험)가 보인다
- [ ] KPI 카드를 클릭하면 관련 탭으로 이동한다
- [ ] 서비스 전환(코인/주식) 시 KPI 라벨이 서비스별로 바뀐다
- [ ] 우측 운영 패널이 스크롤되어 하단 카드까지 접근 가능하다
- [ ] 통합 잔고 요약이 구조화 포맷(소스별/통화별 합계)으로 표시된다
- [ ] 통합 잔고 하단에 연결 상태(수신 소스/전체 소스)가 표시된다

통과 판정:

- 위 7개 항목 모두 확인

---

## STEP 6. 문서/인앱 동기화 검증

목표: 코드 반영 내용이 문서와 인앱에 동일하게 노출되는지 확인

체크:

- [ ] `docs/UPDATE_PLAN.md` 진행 상태 보드 확인
  - S-1 `[x]`
  - S-2 `[x]`
  - S-3 `[ ]`
  - S-4 `[ ]`
- [ ] `docs/CHANGELOG.md`에 S-2 구현 항목 존재 확인
- [ ] 인앱 `사용자 매뉴얼 -> 📅 업데이트`에서 v3.8.9.28 최근 항목 확인

대시보드 확인(단계 종료 시):

- [ ] 대시보드에서 사용자 매뉴얼을 열고 업데이트 탭에서 28버전 패치 항목(포트폴리오 진단/우측패널 스크롤/통합잔고 구조화/KPI 딥링크)을 확인

통과 판정:

- 문서 + 인앱 업데이트 항목 정합 확인 완료

---

## STEP 7. 최종 회귀 게이트

목표: 이번 차(28버전) 필수 묶음 무회귀 확인

실행:

```bash
python -m py_compile ai_chat_strategy.py ui/dashboard_modern.py ui/widgets/user_manual_widget.py
PYTHONPATH=. pytest -q tests/test_ai_chat_performance_review.py tests/test_evaluator_selection_flow.py tests/test_exchange_learning_manager.py tests/test_auto_update_manager.py
```

체크:

- [x] py_compile 통과
- [x] pytest 통과 (실패 0)

대시보드 확인(단계 종료 시):

- [ ] 실시간 거래 로그/운영 KPI/운영 알림/통합 잔고가 정상 렌더링
- [ ] AI 어시스턴트 성과검토 응답(S-1/S-2) 정상

통과 판정:

- 테스트 성공 + 대시보드 핵심 화면 정상

---

## STEP 8. Fee 1차/2차 검증 (2026-07-12 추가)

목표: 수수료 지표 표시와 사용자 DB 자동 패치가 동시에 정상 동작하는지 확인

체크:

- [x] `python -m py_compile trading/recorder.py ui/dashboard_modern.py ui/widgets/ai_report_widget.py ui/widgets/ai_report_widget_real.py` 통과
- [x] 핵심 회귀 테스트 통과

```bash
PYTHONPATH=. pytest -q tests/test_evaluator_selection_flow.py tests/test_exchange_learning_manager.py tests/test_auto_update_manager.py tests/test_ai_chat_performance_review.py
```

DB 확인(실사용 경로):

- [x] `data/trading.db`의 `exchange_trade_stats`에 `total_fees`, `avg_fee` 컬럼 존재
- [x] `exchange_trade_stats` 합계(`total_pnl`, `total_fees`) 조회 가능

대시보드 확인(단계 종료 시):

- [ ] `📈 거래 통계` 탭의 거래소 섹션 요약에 `누적Fee`, `평균Fee`, `Fee/PnL` 표시 확인
- [ ] 거래소별 간단 통계 라벨에 `누적Fee` 표시 확인
- [ ] `📊 AI 리포트`의 `📅 오늘`, `⚡ 실시간` 탭에 비용 영향 블록(누적 Fee/평균 Fee/영향도) 표시 확인
- [ ] 해석 문구 확인: `총 수익은 trade_log pnl 합계 기준, 수수료는 별도 비용 지표`

통과 판정:

- 자동 검증 통과 + UI 수동 확인 완료

---

## 4. 최종 완료 선언 템플릿 (운영 보고용)

아래를 복사해 완료 보고에 사용한다.

```text
[v3.8.9.28 업데이트 테스트 완료]
- STEP1 코인 선택 안정화: 완료
- STEP2 학습/로그 안정화: 완료
- STEP3 S-1 계좌 건강도/복기: 완료
- STEP4 S-2 포트폴리오 진단: 완료
- STEP5 대시보드 리모델링(1~4차): 완료
- STEP6 문서/인앱 동기화: 완료
- STEP7 최종 회귀 게이트: 완료

검증 요약:
- py_compile: 통과
- pytest 핵심 묶음: 통과
- 대시보드 확인 포인트: 이상 없음
```

---

## 5. 다음 순차 작업(미완료 항목)

현재 기준 미완료:

- S-3 AI 일일 리포트
- S-4 AI 대화형 투자비서 고도화

다음 작업 원칙:

1. S-3 구현
2. 테스트 추가
3. 대시보드/인앱 확인 포인트 문서 갱신
4. S-4로 이동
