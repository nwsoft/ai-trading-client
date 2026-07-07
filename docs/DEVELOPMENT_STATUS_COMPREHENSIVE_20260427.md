# 🚀 NoahAI 개발 현황 및 배포 로드맵 (2026-04-27 종합 분석)

**문서 목적:** 현재 개발 완성도, 계획된 기능 위치, 다음 단계, 배포 요구사항을 한눈에 파악

**용어 정의(운영 기준):**
- 이 문서에서 "검증"은 "미구현"이 아니라, 상시 운영 중인 기능에 대해 안전 정책/가드레일/파라미터를 지속 점검하는 운영 품질 활동을 의미한다.
- 증권/ETF는 "상시 운영(기본 안전 디폴트 + 사용자 설정 opt-in 실주문)"으로 본다.

## 🔄 2026-04-28 최신 정정 (정본 우선)

- **[2026-07-06 최신]** 자동업데이트 경로 정책 개선: 설치 위치 우선 캐시 + LocalAppData/TEMP 폴백으로 "Documents 고정 생성" 체감 완화
- **[2026-07-06 최신]** 자동업데이트 진행률 가시성 강화: 설정 업데이트 탭에서 다운로드 시작/진행률/완료 상태 실시간 표시
- **[2026-07-06 최신]** 자동업데이트 누적 정리 반영: 오래된 auto_updater 버전/적용 스크립트 자동 정리(최신 2개 유지)

- **[2026-07-05 최신]** 비바이낸스 Unified 진입 게이트 과차단 완화 반영: no-trade 기본값/최소 이력 임계값 정합화로 cold-start 구간의 장기 HOLD 고착 가능성 축소
- **[2026-07-05 최신]** 거래소 인증 진단 UX 표준화: Bitget/Bybit/OKX 어댑터에 `last_error`/`last_auth_guidance` 추가, 설정 검증 팝업에 원인별 조치 문구 연결
- **[2026-07-05 최신]** Bitget 설정 패널 공인 IP 노출 추가: 사용자 IP 화이트리스트 점검 동선 단축
- **[2026-07-05 최신]** 거래 통계 정합 보강: `log_trade_exit()` 청산 레코드에 거래소 필드 상시 기록으로 집계 누락 위험 완화
- **[2026-07-05 최신]** 운영 진단(5m x 50, 상위 10심볼): Bitget/Upbit/Bithumb 성공, Bybit(IP 불일치), OKX(연결 실패)로 원인 계층 분리 확인

- **[2026-06-05 최신]** v3.8.9.21 후속 안정화 반영: 전역 전체시작 제거, 다중 거래소 상태/코인 분리 정합화, 거래소별 로그 태깅 정렬
- **[2026-06-05 최신]** 안정성 점검 스크립트 정책 정합화: `scripts/multi_exchange_stability_check.py` 기준 PASS

- **[2026-05-07 최신]** 대시보드 전수 버튼/탭 E2E 테스트 추가: `tests/test_dashboard_full_button_e2e.py` **44 passed**
- **[2026-05-07 최신]** 핵심 묶음 회귀 재검증: `test_dashboard_full_button_e2e + test_menu_regression + test_service_tab_policy_snapshot + test_settings_backup` → **102 passed**
- **[2026-05-07 신규]** 증권 브로커 연결 검증 도구 추가: `scripts/verify_stock_broker_connection.py` (`--all_brokers`로 kiwoom/shinhan/miraeAsset 점검)
- **[2026-05-07 감사]** 최종 마무리 질문 대응 감사 리포트 추가: `docs/FINAL_COMPLETION_AUDIT_20260507.md` (완료/부분완료/미완료 판정 + 잔여 P0/P1 체크리스트)
- **[2026-05-07 완료]** Phase 9-5 설정 자동 백업/복구 구현: `save_settings()` 저장 전 자동 백업, 최신 3개 보관(retention), 백업 목록 조회/선택 복구 API 추가
- **[2026-05-07 완료]** 설정창 하단 `🗂 백업에서 복구` 버튼 추가: 최근 백업 목록 모달 제공, 선택 복구 후 UI/대시보드 즉시 동기화
- **[2026-05-07 최신]** 백업 기능 테스트 추가: `tests/test_settings_backup.py` **3 passed**
- **[2026-05-07 최신]** 전체 회귀 테스트: **864 passed, 6 skipped**
- **[2026-05-07 완료]** Phase 9-3 UX 개선 반영: 설정창 AI 진단 패널에 `상세 보기/접기` 토글 추가, 진단 시각 표시, 부족 항목 없을 때 안내 메시지 제공
- **[2026-05-07 완료]** Phase 9-4 핵심 버그 수정: 대시보드 브로커 API 조합 검증에서 `tuple -> bool` 오판정 수정(`(False, msg)`가 `True`로 처리되던 문제 차단)
- **[2026-05-07 완료]** 대시보드↔설정창 진단 포맷 정합화: tuple 기반 전달을 dict payload로 표준화(`status/summary/issues/risk_level/readiness_lines` 포함)
- **[2026-05-07 최신]** 전체 회귀 테스트: **861 passed, 6 skipped** (AI 실행 E2E 28개 포함, 직후 Phase 9-5에서 864로 갱신)
- **[2026-05-07 신규 진행]** AI 실행 준비도 진단을 설정 화면에 표시: ModernSettingsWindow에 `ai_diagnosis_result` 파라미터 추가, 진단 결과 패널 상단 표시, 부족 항목 "수정하기" 바로가기 버튼 추가
- **[2026-05-07 신규 진행]** 대시보드 설정 창 호출 시 AI 진단 동시 실행: `_on_settings_clicked()`에서 `_build_ai_execute_plan()` 먼저 호출 후 결과를 설정 창에 전달
- **[2026-05-07 신규 진행]** 설정 저장 후 AI 진단 자동 갱신: 설정 변경 반영 후 새로운 진단 결과 생성, 대시보드 내부 상태 업데이트
- **[2026-05-03 최신]** 증권사 어댑터 로버스트니스 보강: 신한/미래에셋 REST 어댑터에 GET/POST 요청 전 `_ensure_token()` 호출 + 401 응답 시 자동 토큰 갱신 후 1회 재시도 + `health_check()` 메서드 추가
- **[2026-05-03 최신]** api_type/api_version 실행 경로 방어 검증 추가: `run_auto_trade_cycle()`에서 등록된 브로커의 잘못된 api 조합 시 즉시 차단(`execution_mode: blocked`)
- **[2026-05-03 최신]** 어댑터 로버스트니스 단위테스트 추가: `tests/test_stock_adapter_robustness.py` **23 passed** (토큰 자동갱신 9건 + health_check 7건 + api 조합 검증 6건+빈 exchange 1건)
- **[2026-05-03 최신]** 전체 테스트: **404 passed, 6 skipped** (기존 377 → 신규 27 추가)
- **[2026-05-03 최신]** v3.8.9.18 배포 준비 동기화: 전략 초기화 시 민감정보(API 키/브로커 계정/backend_url) 보존 패치 + 키움 QAxWidget 오류 원본 예외 로그 포함
- **[2026-05-07 신규 계획]** 대시보드 `모두시작`을 `AI 실행` 중심으로 재정의하는 접근성 모드 착수안 추가
- **[2026-05-07 신규 계획]** `AI 상담` 기반 OpenAPI 키 발급/설정 가이드(대화형 체크리스트 + 설정 diff 승인) 로드맵 반영
- **[2026-05-07 신규 계획]** 안전장치 원칙 확정: 실주문 허용·키 저장·브로커 변경은 명시적 2단계 확인 없이는 자동 적용 금지
- **[2026-05-07 진행]** AI 어시스턴트 음성(STT) 경로에 설정 변경 의도 사전 확인 게이트 추가(인식 텍스트 확인 후 입력 반영)
- **[2026-05-07 진행]** 대시보드 전역 실행 버튼 POC 반영: `모두 시작` → `AI 실행` 전환, 실행 전 계획 요약/확인 대화상자 추가
- **[2026-05-07 완료]** AI 실행 계획에 거래소/증권 준비도 진단 추가: 거래소 연결 상태, 증권 키 준비 여부, 브로커 `api_type/api_version` 조합 점검
- **[2026-05-07 완료]** AI 실행 확인창 위험 레벨 고도화: 실주문 허용 플래그/리스크 가드 상태 기반 `일반/주의/고위험` 경고 노출
- **[2026-05-07 완료]** 하단 AI 실행 요약 카드 + 실행 이력 모달 추가: 최근 실행 결과 재확인 및 과거 실행 로그 조회 가능
- **[2026-05-03 이전]** 배포 검증 기준 갱신: 전체 테스트 **336 passed, 6 skipped**, prekey 게이트 `TEST_STOCK` **140 passed, 6 skipped**
- **[2026-05-02 최신]** ETF 지표 어댑터 연동 단위테스트 추가: StockMockAdapter/ShinhanStockAdapter(`trcErrRt`)/MiraeAssetStockAdapter(`trc_errt`) get_etf_list 필드매핑, ETFMetrics risk_level(ok/warn/alert), score_etf() → `tests/test_etf_adapter_indicators.py` **56 passed**, 전체 **336 passed, 6 skipped**
- **[2026-05-02 최신]** Phase F 생활금융 회귀 테스트 추가: LifeFinanceQualityTracker.build_quality_report() + FinanceProductAdvisor 외부 JSON 카탈로그 로드/갱신 → `tests/test_life_finance_phase_f.py` **27 passed** (280 → 336 passed 기점)

- **[2026-05-01 최신]** 증권 AI 자동매매 정합성 보강: `run_auto_trade_cycle()`에 시장 레짐 감지/임계값 동적 조정을 연결하고 고정 임계값 의존 제거
- **[2026-05-01 최신]** 증권 피드백 학습 루프 연결: 종목별 최근 거래 성과(`trade_log`)를 분석 점수 컨텍스트에 반영
- **[2026-05-01 최신]** 증권 고도화 계층 실사용 전환: `StrategyEngine`, `ProfitabilityValidator`를 사이클 기본 정책으로 활성화
- **[2026-05-01 최신]** XAI 로그 확장: 심볼/사이클 결정 로그에 `market_regime`, `effective_buy_threshold`, `effective_sell_threshold` 포함
- **[2026-05-01 최신]** 제어 의미 정리: 증권 자동매매 실행은 START/STOP(AUTO) 상태가 기준이며, 설정의 `stock_auto_trading.auto_start`(legacy `enabled`)는 탭 진입 시 자동 예약 시작 옵션으로 분리
- **[2026-05-01 최신]** 잔여 UI 과제 명시: 설정 화면에서 `stock_auto_trading.auto_start`(legacy `enabled`), `enable_stock_live_order`를 직접 제어하는 전용 UI는 추가 필요

- 종목 검색 고도화 2차 완료: 자동완성/부분일치 추천/원클릭 검색 제안 UI 반영
- 자산 통합 확장 1차 완료: 집중도(HHI) + crypto/stock 상관계수 + 동적 리밸런싱 액션 반영
- 종목 검색 고도화 1차+2차 완료 상태로 문서 정정 (최근검색/즐겨찾기/자동완성)
- 증권 핵심 회귀: `tests/test_stock_integration.py + tests/test_stock_analysis_service.py` → **85 passed, 6 skipped**
- 생활금융 확장 Phase3 완료: 대출/보험/예적금 비교 엔진 + AI 의도 분기 + 실행형 UI 탭 연동
- 생활금융 의도 라우팅 버그 수정: "보험 추천"이 절약 조언으로 오분류되던 문제 해결 및 검증 완료
- 생활금융 설정 연동 완료: `life_finance_sync_dir`, `life_finance_backup_dir` 설정 키 반영
- D1 사전점검 자동화 추가: `scripts/stock_d1_preflight.py` (브로커별 mock/live 경로 및 실주문 플래그 판정)
- 생활금융 회귀 테스트 추가: `tests/test_life_finance_assistant.py` → **9 passed**
- 증권 안정성 재검증: `tests/test_stock_analysis_service.py` → **35 passed**, `tests/test_stock_order_guardrails.py` → **12 passed**
- 증권 통합 회귀 재검증: `tests/test_stock_integration.py` → **50 passed, 6 skipped**
- 무키(non-key) 증권 고도화 테스트 추가: `tests/test_stock_nonkey_hardening.py` → **2 passed**
- 무키(non-key) 증권 점검 스크립트 추가: `scripts/stock_nonkey_hardening_check.py` → **PASS**
- 실API(키움 Live/실계좌) 고도화는 환경 제약(Windows + pykiwoom, 실계정/API 키)으로 이번 사이클 실행 불가, 후속 스프린트로 이월
- **[2026-04-28 최신]** 생활금융 Phase 1 완료: 신용도/위험도 UI + 개인화 점수 조정 + AI 상담 강화 + 회귀 테스트 16개 통과
- **[2026-04-28 최신]** 증권사 api_type/api_version 방어 검증 완료: `ExchangeFactory.validate_stock_broker_api_combo()` 추가, 설정 저장 경로에서도 조합 불일치 차단
- **[2026-04-28 최신]** 전체 테스트: **197 passed, 6 skipped**
- **[2026-04-28 최신]** 증권 REST 인증 정합성 보완: `id/password` 입력을 `app_key/app_secret`로 폴백 전달하도록 어댑터 생성 경로 정리
- **[2026-04-28 최신]** D1 preflight 인증 판정 보완: 신한/미래에셋은 `app_key/app_secret` 또는 `id/password` 중 하나 충족 시 통과
- **[2026-04-28 최신]** 증권 통합 회귀 추가 반영: `tests/test_stock_integration.py` → **61 passed, 6 skipped**, 전체 **199 passed, 6 skipped**
- **[2026-04-29 최신]** 증권 자동매매 경로 가드레일 강제 적용: `StockAnalysisService.run_auto_trade_cycle()`에서 `evaluate_stock_order_guardrails()`를 주문 직전에 실행하도록 반영
- **[2026-04-29 최신]** 대시보드 자동매매 루프에서 가드레일 정책 전달 추가: `dashboard_modern.py` → `run_auto_trade_cycle(..., guardrails=...)`
- **[2026-04-29 최신]** 회귀 검증 완료: `tests/test_stock_analysis_service.py` → **39 passed**, `tests/test_stock_integration.py` → **61 passed, 6 skipped**
- **[2026-04-29 최신]** 증권 자동매매 손실 가드 추가: 연속 손실, 일일 손실, 종목별 쿨다운 기준으로 자동주문을 차단하는 `auto_risk_policy` 경로 반영
- **[2026-04-29 최신]** 증권 자동매매 기본 설정 확장: `stock_auto_trading.risk_guard_enabled`, `max_consecutive_losses`, `daily_max_loss`, `cooldown_sec_per_symbol` 기본값 추가
- **[2026-04-29 최신]** 손실 가드 회귀 검증 완료: `tests/test_stock_analysis_service.py + tests/test_stock_integration.py` → **102 passed, 6 skipped**
- **[2026-04-29 최신]** 증권 자동청산 정책 엔진 추가: `trading/stock_exit_policy.py`에서 익절/손절/ETF 위험경보/신호반전 기반 청산 판단을 단일 정책으로 관리
- **[2026-04-29 최신]** 증권 자동매매에 자동청산 사이클 연동: `run_auto_trade_cycle()`이 신규 진입 전 기존 포지션의 자동청산을 먼저 수행하도록 보강
- **[2026-04-29 최신]** 대시보드 자동매매 상태 피드백 강화: 차단 사유를 `guardrail_blocked`, `auto_risk_blocked`, `live_order_blocked`, `exit_policy_triggered` 유형으로 집계해 상태 메시지에 노출
- **[2026-04-29 최신]** 대시보드 자동매매 정책 UI 추가: interval/threshold/수량/손실가드/익절손절/ETF 청산 기준을 화면에서 저장 가능하도록 반영
- **[2026-04-29 최신]** D1 preflight 자동매매 정책 검증 강화: 잘못된 threshold, 수량, 주문수, 익절/손절 퍼센트 설정을 `BLOCKED`로 판정하도록 보강
- **[2026-04-29 최신]** 증권 최종 회귀 검증 완료: `tests/test_stock_analysis_service.py + tests/test_stock_integration.py + tests/test_stock_live_readiness_scripts.py` → **113 passed, 6 skipped**
- **[2026-04-29 최신]** 증권 지원 모드 매트릭스 점검 추가: `scripts/stock_supported_mode_matrix_check.py`에서 키움/신한/미래에셋/한국투자증권의 지원 `api_type/api_version` 전체 조합 유효성 검증
- **[2026-04-29 최신]** 전체 브로커 readiness 실행기 확장: `scripts/stock_live_readiness_run.py --all-supported-brokers`로 키움/신한/미래에셋/한국투자증권 일괄 점검 + mock hardening + 브로커별 drill 자동 순회
- **[2026-04-29 최신]** all-supported 모드에서 PRECHECK BLOCKED는 경고 처리 후 후속 단계 계속 실행하도록 보강(비엄격 모드)
- **[2026-04-29 최신]** 증권 회귀 재검증 완료: `tests/test_stock_live_readiness_scripts.py + tests/test_stock_analysis_service.py + tests/test_stock_integration.py` → **116 passed, 6 skipped**
- **[2026-04-29 최신]** 배포 게이트 자동화 1차 완료: `scripts/release_gate.py` 추가 및 `build_safe.py`에 게이트 연동(`--gate-profile`, `--skip-gate`)
- **[2026-04-29 최신]** 리스크 거버넌스 1차 완료: `trading/stock_risk_governance.py` 추가(주/월 손실 한도, 글로벌 킬스위치, 종목 집중도)
- **[2026-04-29 최신]** 실행 품질 계측 1차 완료: 주문 시도마다 latency/slippage/success 저장(`stock_execution_metrics`), 품질점수(`quality_score`) 계산 및 KPI 이벤트 발행
- **[2026-04-29 최신]** 장애 복구/중복 방지 1차 완료: 런타임 상태 동기화 스냅샷(`stock_runtime_sync`) + 주문 idempotency 키 저장/검사(`stock_order_idempotency`)
- **[2026-04-29 최신]** 운영 문서 표준화 1차 완료: `docs/operations/ONCALL_RUNBOOK.md`, `docs/operations/INCIDENT_RESPONSE_SCENARIOS.md`, `docs/operations/BROKER_SWITCH_PROCEDURE.md`, `docs/operations/DEPLOY_GATE_AUTOMATION.md`
- **[2026-04-29 최신]** 증권/게이트 회귀 재검증 완료: `tests/test_release_gate.py + tests/test_stock_risk_governance.py + tests/test_stock_live_readiness_scripts.py + tests/test_stock_analysis_service.py + tests/test_stock_integration.py` → **121 passed, 6 skipped**
- **[2026-04-29 최신]** 거버넌스 심화 1차 완료: `daily_max_loss`를 `stock_risk_governance` 엔진으로 통합하고 `broker_overrides`로 브로커별 일/주/월 손실 한도 및 집중도 오버라이드 지원
- **[2026-04-29 최신]** 브로커 복구 자동화 추가: `scripts/stock_broker_recovery.py`에서 preflight → mode matrix → readiness 체인을 브로커별/전체(`--all`)로 실행 가능
- **[2026-04-29 최신]** 실행 품질 대시보드 반영: `dashboard_modern.py`에서 최근 7일 주문 성공률/평균 지연/평균 슬리피지 요약 표시
- **[2026-04-29 최신]** preflight 거버넌스 검증 보강: `broker_overrides`의 손실 한도/집중도 값 범위와 타입을 `BLOCKED`로 판정하도록 강화
- **[2026-04-30 최신]** 거래소 준비도 진단 고도화: `scripts/exchange_readiness_check.py`에 `root_cause`/`action` 기반 자동 원인 분류와 요약 출력 추가
- **[2026-04-30 최신]** 거래소 준비도/복구 테스트 보강: `tests/test_exchange_readiness_check.py`, `tests/test_stock_broker_recovery.py`, `tests/test_stock_live_readiness_scripts.py` 반영
- **[2026-04-30 최신]** 전체 회귀 재검증 완료: **230 passed, 6 skipped**
- **[2026-04-30 최신]** 운영 전환 게이트 분리: `release_gate --profile prekey`(키 입력 전 완료), `stock_keyday_one_shot.py`(키 입력 당일 원샷), `release_gate --profile release`(배포 직전 엄격)
- **[2026-04-30 최신]** 기준선 명확화: 배포 가능 판정과 수익률 고도화(백테스트/오케스트레이션/실행 최적화)는 별도 트랙으로 분리

### 🟢 2026-04-28 생활금융 Phase 1 실행 시작 공지

**상태**: 즉시 실행 개시 (오늘부터 5월 10일까지)  
**목표**: AI 어시스턴트 개인화 상담 강화  
**기간**: 1~2주 (1차 사이클)  
**계획 문서**: [LIFE_FINANCE_PHASE1_ACTION_20260428.md](docs/LIFE_FINANCE_PHASE1_ACTION_20260428.md)  

**액션**:
1. 신용도/위험도 입력 UI 추가 (신용도: 좋음/보통/낮음, 위험도: 회피/보수/공격)
2. 개인화 점수 계산 로직 (신용도별 금리 조정 시뮬레이션)
3. AI 상담 강화 (자연어 응답: "신용도 좋으면 금리 얼마나 내려?" → 맞춤 답변)
4. 통합 테스트 + 사용자 메뉴얼 업데이트

**예상 효과**:
- 사용자가 AI와 대화하며 금융 상담 받는 경험 제공
- 더미 데이터 명시하여 규제 위험 제로
- 사용자 피드백 수집으로 향후 전략 수립 자료 확보

**회귀 테스트 현황**: 170 passed, 6 skipped (Phase 0 완료 기준)

---

### 2026-04-28 운영 점검 결과 (환경/거래소)

- 증권 D1 사전점검: READY_FOR_NEXT_STEP
  - 핵심 파일: OK (`exchange_factory`, `stock_analysis_service`, `stock_guardrails_test`, `stock_integration_test`)
  - 현재 증권 설정: `kiwoom=openapi/live_api 후보`, 전역 실주문 플래그 `enable_stock_live_order=false`, 브로커 플래그 `allow_live_order=false`
  - 결론: 실행 경로는 정상이나, 안전정책상 실주문은 의도적으로 차단 상태
- 증권사 어댑터 단위 테스트 재확인
  - 키움 백엔드 테스트: 6 passed
  - 신한 REST 어댑터 테스트: 8 passed
  - 미래에셋 REST 어댑터 테스트: 10 passed
- 거래소 준비도 점검 결과(실계정 인증 기준)
  - binance: validate=true, balance_status=success
  - upbit/bithumb/bybit/okx: 키 형식은 있으나 인증 실패 또는 연결 실패
  - bitget: key_ready=false + client_unavailable
- 신규 실연동 점검 체인 추가
   - `scripts/stock_d1_preflight.py`: api 조합 + 자격증명 + OS 제약 차단 판정
   - `scripts/stock_live_smoke_check.py`: live 준비 브로커만 연결/잔고/포지션/미체결 smoke 점검
   - `scripts/stock_live_order_drill.py`: 기본 dry-run, 명시 시 실제 주문/취소 drill
   - `scripts/stock_live_readiness_run.py`: preflight -> smoke -> order drill 전체 실행기

### 키움이 제한돼도 다른 거래소가 동작하는 이유

- 구조 분리: 거래소별 어댑터가 독립되어 있어 하나의 브로커 제약이 전체를 막지 않음
- 키움 제약: OpenAPI+ 직접 연결은 Windows + pykiwoom 제약이 있어 macOS에서 실주문 검증이 제한됨
- 타 증권사 경로: 신한/미래에셋은 REST 기반으로 OS 제약이 낮고, 어댑터 테스트가 통과하여 코드 경로 자체는 정상
- 암호화폐 경로: 증권 경로와 별도 계층으로 동작하며, 현재 binance는 인증/잔고 조회까지 정상

### 키움/신한/미래에셋/한국투자증권 구현 방식이 다른 이유

- 키움: OpenAPI+ 및 pykiwoom 기반 경로가 핵심이라 Windows 의존성이 큼
- 신한/미래에셋: 공식 REST(Open Trading/SOL) 경로로 플랫폼 의존성이 상대적으로 낮음
- 결론: 원래 API 제공 방식/SDK 제약이 달라 구현 방식이 분기되는 것이 정상

### 다른 증권사 추가 가능 여부

- 가능. 현재 구조는 `StockExchange` 인터페이스 + `ExchangeFactory` 어댑터 등록 방식이라 확장 가능
- 절차:
   1. 새 어댑터 클래스 구현 (`connect/get_balance/get_positions/place_order/get_open_orders` 등)
   2. `ExchangeFactory._stock_adapters` 및 `SUPPORTED_API_VERSIONS` 등록
   3. `settings_template.json`의 `stock_broker_configs` 기본값 추가
   4. UI 설정/선택 항목 반영 + 통합/백엔드 테스트 추가

### 여러 증권사 동시 이용 가능 여부 및 권장

- 가능. `enabled_stock_brokers` 배열로 복수 활성화가 가능하고, UI/AI 컨텍스트에서도 복수 브로커를 순회 가능
- 권장 운영:
   - 안정화/운영 초기: 1개 브로커 집중(장애 원인 분리, 체결검증 단순화)
   - 확장 단계: 2개 이상 브로커 병행(리스크 분산/백업 경로 확보)
   - 자동매매는 브로커별 정책/가드레일을 먼저 고정한 뒤 병행 권장

### 키 기반 검증을 잠시 패스할 때 가능한 완료 범위

- 완료 가능:
  - 분석/가드레일/통합 회귀 테스트
  - mock 기반 주문·포지션·분석·UI 흐름 검증
  - 문서/체크리스트/사전점검 자동화
- 보류 필요:
  - 실주문 체결 확인
  - 실계정 잔고/포지션 정합성 검증
  - 브로커별 운영 API 한도/권한 이슈 검증

### 필요한 추가 설정/준비물

- 공통
  - 유효한 실계정 API 키/시크릿(거래소별 추가 필드 포함)
  - 거래소별 권한(조회/주문) 및 IP 화이트리스트 확인
- 증권 실주문 전환 시
  - 전역: `enable_stock_live_order=true`
  - 브로커별: `stock_broker_configs.<broker>.allow_live_order=true`
  - 브로커별 `api_type/api_version` 조합과 계좌 필드 확인
- 키움 실검증 시
  - Windows 환경 + pykiwoom + 실계좌 로그인 가능 상태

### 다음 권장 작업 순서 (실행형)

1. 키/권한/클라이언트 정합성 정리
    - bitget 클라이언트 가용성 복구 및 누락 키 보완
    - upbit/bithumb/bybit/okx 인증 실패 원인(API 권한/IP/만료) 정리
2. 증권 D1 실환경 검증
    - Windows에서 키움 live_api 주문/체결 1회 검증
    - 플래그 ON/OFF에 따른 차단/허용 동작 증적 로그 확보
3. 회귀 및 판정
    - stock_analysis_service, stock_order_guardrails, stock_integration 재실행
    - 빌드/배포 체크리스트와 문서 상태 동기화 후 배포 가능 여부 최종 판정

이 정정 섹션은 하단 레거시 기술보다 우선한다.

---

## 📊 1. 현재 기능별 개발 상태 (정직한 평가)

### ✅ **완성된 기능들**

| 기능 | 상태 | 설명 | 파일 |
|------|------|------|------|
| **암호화폐 거래** | ✅ 완성 (운영 중) | 6개 거래소, 자동신호, 자동주문, TP/SL, 모니터링 | `trading/unified_trader.py`, `trading/trader.py` |
| **기본 기술분석** | ✅ 완성 | 30개+ 지표 (RSI, MACD, BB, SMA/EMA, ATR, 거래량) | `trading/analyzer.py` |
| **AI 신호 생성** | ✅ 완성 | LONG/SHORT/HOLD + 신뢰도 + 근거 설명 | `trading/analyzer.py` |
| **AI 어시스턴트** | ✅ 완성 | 실시간 상담, 거래 설명, 기술분석 설명 | `trading/ai/openai_client.py` |
| **포지션 모니터링** | ✅ 완성 | 실시간 PnL, 동적 TP/SL, 청산 자동화 | `trading/unified_trader.py` |
| **거래 기록** | ✅ 완성 | SQLite DB에 모든 거래 저장 | `trading/recorder.py` |
| **AI 학습 시스템** | ✅ 완성 | 거래소별 학습 데이터 저장, 신호기준 자동조절 | `trading/exchange_learning_manager.py` |
| **주식 종목 검색** | ✅ 완성 | 코드/종목명 검색, 분석 카드 표시 | `ui/dashboard_modern.py` |
| **주식 분석/설명 흐름** | ✅ 완성 | 종목 검색/분석 + AI 어시스턴트 + 기록 확인 | `ui/dashboard_modern.py` |
| **주문 가드레일** | ✅ 완성 | 장시간/수량/금액/일일한도 검사 | `trading/stock_order_guardrails.py` |
| **자산 통합 MVP** | ✅ 완성 | 총자산, 자산군비중, 리스크 요약 | `ui/dashboard_modern.py` |
| **생활금융 확장 (Phase3)** | ✅ 완성 | 거래/목표/분석/차트/음성입력 + 대출·보험·예적금 비교 + AI 어시스턴트 | `trading/life_finance.py`, `trading/life_finance_products.py`, `trading/life_finance_assistant.py`, `ui/widgets/life_finance_widget.py` |
| **설정 자동화** | ✅ 완성 | 모든 설정이 JSON에 저장/복원 | `config/settings.py` |
| **데이터 메뉴얼** | ✅ 완성 | 사용자 메뉴얼 데이터 준비 | `data/nwsoft/user_manual_data.json` |

---

### 🚧 **부분 완성된 기능들**

| 기능 | 현재 상태 | 문제점 | 완성까지 |
|------|---------|--------|---------|
| **주식 자동거래** | 상시 운영(안전정책형) | 기본 디폴트 실주문 차단 상태에서 사용자 설정(opt-in) 기반 실주문 허용 | 운영 파라미터 고도화 |
| **ETF 분리 실행** | 1차 분기 반영 후 운영 중 | 자산/브로커별 파라미터 세분화 필요 | 고도화 스프린트 |
| **증권사 실연동** | 상시 운영 가능(정책형 제어) | OS/브로커 조합별 편차 관리와 운영 가드레일 정교화 필요 | 상시 점검 |
| **차액거래** | 코드 기반이 없음 | 기능 자체 설계 필요 | 후속 스프린트 |

---

### ❌ **아직 계획 단계인 기능들**

| 기능 | 계획 위치 | 상태 | 개발 시점 |
|------|---------|------|---------|
| **금융사기 탐지** | `docs/BUSINESS_PROPOSAL_2026.md` 위험보호 도메인 | R&D 기획 | 추후 R&D 과제 |
| **부동산 분석** | `docs/BUSINESS_PROPOSAL_2026.md` | R&D 기획 | 추후 R&D 과제 |

---

## 🗺️ 2. 계획된 기능들의 위치

### 보험비교, 대출비교 등은 어디에 있는가?

```
📍 계획 위치:
├─ docs/UPDATE_PLAN.md
│  └─ "## Phase F — 생활금융 확장 (다음 단계, R&D 고도화)"
│     ├─ 금융상품 비교 및 선택 (대출/보험/예금/적금)
│     ├─ 금융 이상/위험 탐지 (금융사기)
│     ├─ 개인 맞춤형 재정 관리
│     └─ 취약층 금융 접근성 고도화
│
├─ docs/BUSINESS_PROPOSAL_2026.md
│  ├─ "4. 생활금융 의사결정 보조 시스템 R&D"
│  │  ├─ 대출 상품 비교 및 위험 평가 엔진
│  │  ├─ 보험 선택 보조 시스템
│  │  ├─ 예금/적금/채권 상품 비교
│  │  └─ 개인 맞춤형 재정 관리
│  │
│  └─ "5. 위험보호 도메인 R&D"
│     ├─ 금융사기 탐지 및 경고 시스템
│     └─ 거래 이상 감지 시스템
│
└─ docs/ARCHITECTURE.md
   └─ "Domain Layer"
      ├─ Asset Decision Domain (암호화폐/주식/ETF) ✅
      ├─ Life Finance Domain (대출/보험) ⏳ R&D
      ├─ Risk Protection Domain (사기탐지) ⏳ R&D
      └─ Accessibility Domain (고령층/음성) ⏳ R&D

📝 현재 상태:
• 생활금융 도메인에서 1차 서비스 구현 완료 (대출/보험/예적금 비교)
• R&D 문서 축은 유지하되, 기초 서비스는 코드/UI/AI 연동까지 반영 완료
• 우선순위: 다음 사이클은 상품 데이터 소스 고도화와 추천 정확도 개선
```

---

## 📈 3. 완성도 평가 및 문제점

### 🎯 현재 완성도 (전체 대비)

```
암호화폐 기능:        ████████████████████ 100% (핵심 기능 완성, AlphaArena 지표 배열 일부 고도화 여지 있음)
주식 기능:           ████████████████░░░░ 80% (AUTO 루프 O, 실API 경로 O, 실환경 검증 대기)
ETF 기능:            ████████████░░░░░░░░ 60% (지표분석/점수화 O, 실데이터 소스 고도화 예정)
자산 통합:           ████░░░░░░░░░░░░░░░░ 20% (MVP만)
생활금융:            ████████████████░░░░ 80% (Phase3 완료, 실데이터 고도화 필요)
보험/대출/예적금:    ██████████████░░░░░░ 70% (1차 엔진/UI/AI 완료)

전체 프로젝트:       ████████████░░░░░░░░ 60% (암호화폐 완성 + 주식 AUTO 경로 확보)
```

### 🔍 주요 문제점

#### 문제 1: 주식 자동거래가 Mock 상태
```
현재 동작:
사용자 "시작" → 신호 생성 → 환경/설정에 따라 Mock 또는 live_api 경로

현재 남은 제약:
- macOS + 키움 OpenAPI 실환경 제약으로 운영 검증은 주로 Mock 경로
- 실주문은 feature flag(`enable_stock_live_order`/`allow_live_order`)로 기본 차단

원인:
- 실주문 경로 코드는 있으나(어댑터/서비스), 운영 환경과 플래그가 보수적으로 설정됨

해결:
Windows+pykiwoom 실환경에서 live_api 경로 검증 + feature flag 정책 최종 확정
```

#### 문제 2: ETF와 주식이 분리되지 않음
```
현재 동작:
증권 서비스 → 단일 "주식" 컨텍스트 → 주식/ETF 혼합

문제점:
사용자가 "주식만" 또는 "ETF만" 보기 선택은 가능하지만
내부적으로는 동일 알고리즘 사용

필요:
- 주식: 기술분석 중심 (RSI, MACD 등)
- ETF: 지수 추적 오차 + 리밸런싱 중심
분리된 알고리즘 1차 반영 + 테스트 보강을 D1 기준으로 판정
```

#### 문제 3: 증권사 어댑터가 부분적으로만 연동
```
현재 상태:
- api_type (mock/openapi/rest) 선택 가능
- api_version 선택 가능
- 하지만 실API 경로는 일부만 구현

영향:
- Kiwoom: 실API 연동 중
- Shinhan: 부분 연동
- MiraeAsset: 계획 단계

해결 필요:
이번 사이클은 Kiwoom 1차 경로 확보까지, 나머지 증권사는 후속 스프린트로 분리
```

#### 문제 4: 금융상품 비교의 데이터 소스 고도화 필요
```
현재:
- 기본 비교 엔진/AI/UI는 구현 완료
- 샘플/규칙 기반 비교 로직 중심
- 실시간 외부 상품 데이터 연동은 미적용

개발 필요 시점:
후속 스프린트에서 외부 데이터 연동/추천 정확도/설명 가능성 강화
```

---

## 🚀 4. 다음 단계 (우선순위 순)

### **D0-D1 (최우선): 배포 차단 원인 제거** ⚠️ 현재 사이클 필수
```
목표: 오늘과 내일 안에 "실행 가능 경로"와 "배포 차단 여부"를 명확히 판정

작업 목록:
1️⃣ D0 오늘
   - Kiwoom 자동주문 제어 지점과 Mock 차단 지점 확정
   - 문서/인앱 메뉴얼/상태 문구 동기화
   - 가드레일/브로커 키/표시 모드 테스트 보강

2️⃣ D1 내일
   - Kiwoom 실주문 또는 feature flag 분기 1차 연결
   - ETF/주식 신호 분기 1차 반영
   - 회귀 테스트 및 수동 검증으로 실행 가능/불가 판정

완료 기준:
- 사용자가 눌렀을 때 Mock인지 실주문 가능 경로인지 코드상 명확할 것
- ETF와 주식의 설명/신호 분기가 최소 1차 반영될 것
- 테스트와 문서가 같은 상태를 말할 것
```

### **후속 스프린트 1: 증권 실연동 확장**
```
목표: 신한/미래에셋 포함 실주문/잔고/포지션 경로 검증 확대

작업 목록:
1️⃣ 증권사별 주문/잔고/포지션 실API 검증
2️⃣ 오류 복구/재시도 로직 정리
3️⃣ 회귀 테스트와 운영 로그 기준선 확보
```

### **후속 스프린트 2: 사용자 체감 고도화**
```
목표: 자동완성/즐겨찾기/최근검색, 자산통합 심화, 생활금융 심화 반영

작업 목록:
1️⃣ 종목 검색 고도화
2️⃣ 자산 통합 상관관계/리밸런싱 제안
3️⃣ 생활금융 고도화 (상품 데이터 실연동, 추천 정교화, 설명 강화)
```

### **후속 스프린트 3: 차액거래/생활금융 R&D 준비**
```
목표: 바로 배포할 기능이 아니라 데이터 구조와 외부 소스 정리

작업 목록:
1️⃣ 차액거래용 가격 감시 데이터 구조
2️⃣ 보험/대출/예적금 비교용 외부 데이터 스키마/수집 파이프라인
3️⃣ 인앱 설명/FAQ/질문 흐름 초안

상태: 코어 비교 기능 코드는 완료, 이번 사이클에서는 실데이터 확장 착수 준비 수행
```

---

## 📦 5. 배포까지 필수 완료 사항

### ✅ 배포 전 체크리스트

```
필수 (반드시 완료):
[ ] D1 완료: Kiwoom 1차 실행 경로 또는 feature flag 경로 판정
[ ] D1 완료: ETF/주식 분기 1차 반영
[x] D1 완료: 회귀 테스트/문서/인앱 메뉴얼 상태 동기화
[x] 통합 테스트: 증권 핵심 회귀 85 passed, 6 skipped
[ ] 가드레일 테스트: 14개 테스트 모두 통과
[ ] 배포 체크리스트 (DEPLOY_CHECKLIST.md) 항목 모두 확인
[ ] 사용자 문서 완성
[x] 대시보드 메뉴얼 UI 구현 또는 기존 인앱 메뉴얼 문구 확정
[ ] PyInstaller 빌드 성공 (build_safe.py)

선택사항 (원하면 포함):
[ ] 후속 스프린트: 차액거래
[ ] 후속 스프린트: 생활금융 R&D

현재 진행도:
✅ 암호화폐 (완성)
✅ 자산 통합 MVP (완성)
✅ 생활금융 Phase3 (완성)
✅ 주식/ETF (상시 운영 + 안전정책형)
✅ 보험/대출/예적금 비교 (1차 구현 완료)

최신 기준 보정:
✅ 주식 검색 고도화(1차+2차) 완료
✅ 자산 통합 확장(상관관계/리밸런싱 1차) 완료
🚧 남은 핵심: 증권 운영 파라미터/가드레일 고도화, 생활금융 실데이터 연동/추천 고도화
```

---

## 📋 6. 현재 개발된 기능이 완벽한가?

### 암호화폐 거래 → **완벽함** ✅
```
상태: 프로덕션 운영 중
- 6개 거래소 동시 운영
- 모든 신호 생성 + 자동 주문
- TP/SL 자동 설정 + 모니터링
- 포지션 기록 + 학습 반영
- 가드레일 완성

개선 여지: 거의 없음 (안정화 단계)
```

### 주식/ETF 기능 → **상시 운영(안전정책형)** ✅
```
완성된 부분:
- 검색/분석 ✅
- AI 어시스턴트 기반 조절/해석 ✅
- 기본 기록 ✅
- 실주문 경로 + 정책형 차단/허용 플래그 ✅

운영 원칙:
- 신규 사용자 기본값은 실주문 차단(안전 디폴트)
- 실제 거래 필요 사용자는 설정에서 실주문 허용 후 live_api 경로 사용
- 내부 운영 기준 약 30명 테스터가 블록체인/증권 경로를 사용 중

결론: 현재는 "미완료 검증 단계"가 아니라 "상시 운영 + 운영 고도화 단계"로 보는 것이 정확하다.
```

### 자산 통합, 생활금융 → **혼합 상태(자산통합 MVP / 생활금융 Phase3)** 🚧
```
완성된 부분:
- 자산 통합 기본 화면/데이터 표시 ✅
- 생활금융 거래/목표/분석/차트/음성입력 ✅
- 생활금융 금융상품 비교(대출/보험/예적금) + AI 분기 ✅

미완성 부분:
- 자산 통합 심화 분석
- 생활금융 외부 실데이터 연동
- 추천 정확도/설명가능성 고도화

결론: 생활금융은 서비스 단계, 자산 통합은 MVP에서 운영형으로 확장 필요
```

---

## 🎯 7. 최종 권장 사항

### 배포 시나리오

#### **시나리오 A: 48시간 스프린트 후 배포 판정 (권장)** ⭐⭐⭐
```
로드맵:
1. D0-D1 완료
   - Kiwoom 1차 실행 경로 판정
   - ETF/주식 1차 분기 반영
   - 테스트/문서/인앱 메뉴얼 동기화

2. 배포 체크리스트 확인
   - 문서 완성
   - 인앱 메뉴얼 또는 대시보드 메뉴얼 확정
   - 빌드 성공

3. 배포 또는 보류 판정
   - 실행 경로가 확보되면 제한적 배포
   - 정책형 실주문 제어(enable_stock_live_order / allow_live_order) 상태를 릴리스 노트에 명확히 표기

⏱️ 소요시간: 1-2일 + 판정

장점:
- 지금 바로 막힌 지점을 제거할 수 있음
- 배포 가능/불가가 문서가 아니라 코드 기준으로 결정됨

단점:
- 후속 스프린트 항목은 남음
```

#### **시나리오 B: 지금 바로 배포 (비권장)**
```
현재 상태로 배포하면:
- 암호화폐: 정상
- 주식: Mock 거래 (실제 안 됨)
- 사용자가 "주식 시작"을 누르면 화면만 업데이트, 실제 주문 안 됨

결과:
❌ 사용자 불만족 + 신뢰도 하락
❌ "주식은 안 되는 건가?" 혼란
```

---

## 💡 8. 즉시 해야 할 일

### 우선순위 1 (D0 오늘): 경계 확정 + 문서 동기화
```
[x] Kiwoom Mock/실주문 경계 확정
   - `trading/exchanges/exchange_factory.py`의 `api_type` 분기 확인 (mock/live)
   - `trading/stock_analysis_service.py`의 `execution_mode` 및 `allow_live_order` 차단 확인
[x] ETF 분기 제어 지점 확정
   - `trading/stock_analysis_service.py`의 `normalize_asset_mode/asset_mode_matches` 및 자동매매 필터 확인
[x] 문서/인앱 메뉴얼/체크리스트 동기화
   - 본 문서 및 생활금융 가이드 최신 상태 반영
```

### 우선순위 2 (D1 내일): 실행 경로 반영
```
1. Windows+pykiwoom 실환경에서 Kiwoom live_api 주문/체결 검증
2. ETF/주식 분리 시그널의 운영 파라미터 조정
3. 테스트 작성

즉시 가능한 사전점검(현재 환경):
- `python scripts/stock_d1_preflight.py`
- `python -m pytest tests/test_stock_analysis_service.py -q`
- `python -m pytest tests/test_stock_order_guardrails.py -q`
- `python -m pytest tests/test_stock_integration.py -q`
```

### 우선순위 3 (D1 마감): 판정
```
1. 증권사 연결 테스트
2. 주문 체결/차단 테스트
3. 가드레일 재검증
4. 빌드/배포 가능 여부 판정
```

---

## 📊 요약 테이블

| 기능 | 현재 | 배포 필수 | 우선순위 | 소요기간 |
|------|------|---------|---------|---------|
| 암호화폐 | ✅ 완성 | ✅ | P0 | 0주 |
| 주식 자동거래 | ✅ 상시 운영(정책형) | ✅ | P0 | 운영 중 |
| ETF 분리 | ✅ 운영 중(1차 반영) | ✅ | P0 | 고도화 스프린트 |
| 증권사 실연동 | ✅ 운영 가능(정책형 제어) | ✅ | P0 | 상시 점검 |
| 자산 통합 심화 | ❌ 계획 | ❌ | P2 | 후속 스프린트 |
| 생활금융 심화 | 🚧 Phase3 완료, 데이터 고도화 필요 | ❌ | P2 | 후속 스프린트 |
| 보험/대출/예적금 비교 | ✅ 1차 구현 완료 | ❌ | P3 | 고도화 스프린트 |
| 차액거래 | ❌ 계획 | ❌ | P2 | 착수 준비만 |

---

## 🎬 결론

```
현재 상태:
- 암호화폐 기능 완성 (100%)
- 주식/ETF 상시 운영(기본 안전 디폴트 + opt-in 실주문)
- 생활금융 Phase3 완료 (금융상품 비교 포함)

배포 가능 시점:
- ✅ 현재: 증권 기능은 이미 운영 가능하며 정책형 실주문 제어를 적용 중
- ✅ 추가 고도화: 브로커/OS 편차 대응과 가드레일 튜닝을 지속

다음 단계:
1. 증권 운영 파라미터(자산/브로커/세션별) 세분화
2. 가드레일/회귀/수동 시나리오 정기 검증 체계 유지
3. 브로커별 운영 편차 대응(신한/미래에셋/키움)
4. 생활금융 실데이터 연동 및 추천 고도화
5. 접근성/초보자 모드(원버튼 AI 실행 + 음성 + AI 상담 설정 가이드) 단계적 적용
```

---

**이 문서는 2026-04-27 기준으로 작성되었습니다.**
**최신 진행 상황은 UPDATE_PLAN.md와 STOCK_ETF_CURRENT_STATUS_20260118.md를 참고하세요.**
