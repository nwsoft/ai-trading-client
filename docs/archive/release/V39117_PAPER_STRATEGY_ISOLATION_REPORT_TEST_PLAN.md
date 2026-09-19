# v3.9.1.17 전략 의미 보존·PAPER 격리·리포트 정산 검증 원장

상태: `pending_windows_rebuild` · `publish_ready=false`

> 공개 v3.9.1.17 Windows 자산은 2026-09-01에 생성됐습니다. 아래 2026-09-02 OKX 후속 소스는 해당 자산보다 새로우므로 같은 버전 자산을 덮어쓰지 않으며 다음 불변 버전 빌드 전까지 별도 후보입니다.

## 확인된 장애와 인과 근거

- Teayu의 마지막 NoahAI 청산은 2026-08-29 21:47경이며 첫 PAPER 관찰 등록은 같은 시각 직후 시작됐다.
- 이후 DB에는 `AI 커스텀 후보 차단: no_strategy_matched_current_scope_regime_and_entry`가 25,201건 기록됐고 분석·학습은 계속됐지만 신규 주문과 청산은 없었다.
- 등록된 PAPER 후보 6개 중 독립 전략 5개는 `entry_signal`과 `executable_entry`가 비어 있었고 나머지 1개도 TP/SL 실행 단위 계약을 충족하지 못했다.
- 공통 선언형 엔진이 PAPER 후보 불일치를 최종 적용 전략 불일치와 같은 전역 HOLD로 반환한 것이 근본 원인이다.
- AI 리포트는 SQL 요약 청산 수와 손익을 정상 계산하면서도 상세 영역은 청산 원장이 아니라 별도 AI 분석 로그만 렌더링해 빈 화면이 됐다.

## 소스 자동 검증

- [x] PAPER 후보만 평가했고 일치하지 않으면 Binance 기본 LONG 신호 유지
- [x] 같은 계약을 Upbit·Bithumb·Bybit·Bitget·OKX에도 적용
- [x] 최종 적용 전략 불일치는 기존처럼 HOLD/fail-closed 유지
- [x] 독립 전략의 방향·선언형 진입조건 누락 시 PAPER 시작 거부
- [x] 실행 준비 미완료 전략은 PAPER뿐 아니라 사용자 승인·과거검증·최종 적용 전부터 차단
- [x] TP/SL 저장 단위 누락·오류 시 PAPER 시작 거부
- [x] `confirm`의 NoahAI 스마트 청산 상속과 전략 자체 TP/SL 책임을 후보 실행계약에서 분리
- [x] 독립 LONG/SHORT 양방향 조건을 분리 평가하고 한 방향만 일치할 때만 후보 생성
- [x] confirm 원문의 LONG/SHORT 방향을 보존하고 반대 NoahAI 기본 신호 승인 차단
- [x] 자연어 양방향 전략을 LONG/SHORT별 조건으로 분리하며 분리 실패 시 실행 차단
- [x] Pine RSI 별칭과 지원 가능한 AND 복합조건 해석, 미해석 별칭 실패 폐쇄
- [x] 단위 없는 TP/SL 추정 금지와 사용자 입력값 무음 상한 보정 제거
- [x] 저장·PAPER·주문 직전 TP/SL 공통 범위(TP 0.05~5%, SL 0.05~3%) 적용
- [x] 저장 직전 최종 편집본 서버 재검증 및 이전 분석 결과의 준비 상태 재사용 차단
- [x] Web 8문항 AI 멘토가 공통 계약을 통과한 관리형 선언 규칙·TP/SL·위험 초안을 불러오며 자동 저장·승인·PAPER·LIVE를 수행하지 않음
- [x] 외부 LLM의 원문 미근거 실행 조건·TP/SL·비중 제안을 실행 정본에서 제외하고 거절 경로를 XAI에 기록
- [x] 원문 분석 뒤 실행 조건·TP/SL 편집 시 source-grounding 해시 불일치로 최종 저장 차단
- [x] `request.security`·동적 `input.*`·사용자 함수·컬렉션·rolling state·position price 동적 청산 Pine을 명시적 미지원으로 차단
- [x] Upbit·Bithumb KRW 현물, Binance·Bybit·OKX·Bitget USDT 선물의 거래소별 과거검증 분리
- [x] Teayu 저장 전략을 읽기 전용으로 재현해 기본 `noah_base` 복귀 확인
- [x] 리포트 요약 청산 수와 상세 `trade_log` 행이 같은 workspace 응답에 존재
- [x] 상세 행에 거래소·종목·방향·손익·손익률·수수료·진입가·청산가 포함
- [x] 미래 시각 행 제외·로컬 naive/UTC 혼합·100+건 상세 페이지·전체 체크섬 회귀
- [x] KRW·USDT 손익·수수료를 환율 근거 없이 단일 숫자로 합산하지 않음
- [x] 6개 거래소×LEARNING/PAPER에서 실계좌 잔고 조회·손실 경고·가드레일 중단 알림 0건
- [x] LIVE 빈/무효 잔고를 100% 손실로 추정하지 않고 `risk_data_unavailable`로 신규 진입 보류
- [x] 6개 거래소 LIVE 청산 원장을 `exchange`·`execution_mode=live`로 필터하고 KRW/USDT 분리
- [x] 출금·입금 등 순수 잔고 변화를 NoahAI 거래 손실로 오인하지 않음
- [x] 외부 알림에 `[LIVE]`·거래소를 표시하고 거래소별 ON/OFF를 소실 없이 적용
- [x] 전략 의미·멘토·source-grounding 집중 회귀 `12 passed`
- [x] LIVE 손실·알림 모드/거래소 격리 집중 회귀 `41 passed`
- [x] 전체 Python 회귀 `1,981 passed, 8 skipped` (2026-09-02 OKX·Bybit·Bitget·국내 현물 거래대금 단위 후속 회귀 포함)
- [x] Web UI production build 49 modules
- [x] 문서·버전 정합 검사
- [x] daltrading 가이드·허브·제출 역할 정렬 운영 배포 및 공개 URL 확인 (`c12cac8`)
- [x] NoahAI Labs Strategy Studio·LLM 정본·v3.9.1.16 공개/v3.9.1.17 후보 경계 운영 배포 및 공개 URL 확인 (`c21cfb1`)
- [x] Teayu 원장에서 OKX 약 1분 반복 세션이 모두 `candidate_evaluation_unavailable / fallback_unscored`였음을 읽기 전용 확인
- [x] OKX `quoteVolume=None` 파생 ticker를 원문 `volCcy24h×last` USDT 거래대금으로 복원하고 계약 수 `vol24h`를 오인하지 않는 결정적 회귀
- [x] 동일 미산출 실패 원장 기본 15분 중복 억제와 60초→최대 15분 점진 재시도 회귀

## Windows·실사용 배포 게이트

- [ ] `WIN-BUILD`: Windows 엔진·Web assets·설치기·blockmap·`latest.yml`의 v3.9.1.17 버전과 SHA 일치
- [ ] `WIN-UPGRADE`: v3.9.1.16→v3.9.1.17 업데이트 후 설정·자격증명·전략·PAPER 원장 보존과 롤백
- [ ] `KIWOOM-E2E`: 조회 전용 COM 연결·안전 종료·재시작과 NoahAI 소유 자식 프로세스 0개
- [ ] `KIS-E2E`: 토큰 재사용·조회·종료 기존 계약 유지
- [ ] `BITHUMB-E2E`: KRW 현물 소유 LONG·청산·종목별 체결 원장과 PAPER 전략 격리 확인
- [ ] `RECONCILE-E2E`: 주문 모호 상태를 재주문하지 않고 client order ID로 대조
- [ ] `SPOT-FUTURES-PAPER`: Upbit·Bithumb LONG/관리 LONG 청산과 해외 선물 LONG/SHORT·기준통화 분리
- [ ] 기존 미구조화 PAPER 후보가 삭제되지 않고 `실행 규칙 미구조화`로 표시
- [ ] `MENTOR-E2E`: Level 1~4별 질문→관리형 실행 초안 불러오기→최종검증의 클릭 순서와 자동 실행 0건
- [ ] `SOURCE-E2E`: 한국어 단방향·양방향, Pine 별칭·복합조건, 단위 누락 전략의 화면 경고와 실행 차단
- [ ] `VENUE-REPLAY-E2E`: 6개 거래소 결과에 실제 venue·현물/선물·봉·기준통화가 표시되고 원장과 일치
- [ ] 기존 후보가 불일치해도 6개 거래소에서 기본 NoahAI 후보 분석이 계속됨
- [ ] 실행 가능한 독립 PAPER 전략은 일치 시 전략 ID·버전이 원장에 귀속됨
- [ ] 최종 적용 전략의 조건 불일치는 기본 전략으로 우회하지 않고 HOLD 유지
- [ ] `REPORT-E2E`: 오늘·주간·월간 리포트에서 요약 건수·상세 기간·KRW/USDT 합계가 같은 청산 원장과 일치
- [ ] Discord·Telegram 리포트 발송은 같은 통화별 집계이며 거래 루프를 지연하지 않음
- [ ] `ALERT-MODE-E2E`: 6개 거래소 LEARNING·PAPER 30분에서 실계좌 손실 알림 0건, LIVE 합성 손실에서만 `[LIVE]` 긴급 알림
- [ ] `ALERT-DATA-E2E`: LIVE 인증·시간·빈 잔고 장애가 100% 손실이 아닌 위험 데이터 확인 실패로 수신되고 기존 포지션 보호 유지
- [ ] `ALERT-VENUE-E2E`: 거래소별 ON/OFF 저장·재시작·Telegram/Discord 실제 수신과 KRW/USDT 표시 대조
- [ ] `SOAK`: 24~72시간 6개 거래소 PAPER에서 반복 전역 HOLD, 원장 손상, worker 잔류 0건
- [ ] `OKX-SELECTION-E2E`: 실제 OKX ticker에서 숫자 점수 후보가 생성되고 3시간/확정 국면 변경 전 1분 성공 세션 반복이 0건
- [ ] `SELECTION-FAILURE-E2E`: 강제 미산출 장애에서 즉시 1회 뒤 점진 재시도, 동일 실패 DB 저장 기본 15분, 회복 뒤 `scored` 전환 확인

이 문서의 외부 항목을 완료하기 전에는 소스 회귀 통과를 공개 설치본 해결로 표현하지 않는다.
