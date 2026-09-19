# v3.9.1.32 Runtime Recovery & Scheduled Updates

기준일: 2026-09-15. 소스 후보 v3.9.1.32 / updater 3.9.132.
공개 자산: `deploy/release-manifest.json`의 v3.9.1.31을 보존한다. 이 문서는 새 Windows 설치기 배포 완료 증거가 아니다.

## 피드백과 근본 원인

| 항목 | 확인된 원인 | 수정 및 재발 방지 |
|---|---|---|
| normal → normal 반복 알림 | 국면 변경과 대기 중인 후보 재선정 재시도를 같은 분기로 처리 | Binance·통합 CCXT 경로의 실제 transition만 알림. 증권도 공통 helper로 초기/동일 상태 차단. 국면 안정화·재선정 정책은 유지 |
| 설정창에서만 업데이트 확인 | React 마운트 시 확인하지만 Electron 주기 타이머 없음 | main-process 단일 타이머, 저장된 1~72시간 주기, single-flight, 재시도, 로그아웃 정리, 구독 해제, 마지막 시도·다음 예약 표시 |
| Coinone 미진입 | CCXT `active=None`을 BREAK로 변환해 KRW 후보 전부 배제 | 명시적 False만 중단. 티커·캔들·점수·신호·위험 게이트는 유지. 미산출 fallback은 KRW 표기이며 진입 불가 |
| KIS 로그 부족 | 인증과 분석은 별도. 빈 유니버스 조기 반환이 해당 기관 로그에 미노출 | 4개 증권사 시작·빈 후보·주기 완료·오류·중지 상태를 공통 로그로 전달. 동일 상태는 5분 요약 |
| KIS 및 미래에셋 종목 목록 | KIS가 상속한 목록 경로는 KIS 개별 일봉 API로 직결. 미래에셋은 제휴 프로필 매핑이 있으면 정상적인 목록 경로이므로 구분 필요 | KIS 자동 목록과 제휴 목록 없는 경로는 공식 공개 KOSPI/KOSDAQ 마스터의 ST/EF 사용. 미래에셋 제휴 목록·NAV/추적오차 및 KIS 지정 ETF 목록은 보존. 전일 값은 후보 순위용이며 주문가는 별도 조회 |

## 읽기 전용 자료와 확인 경계

### 추가 점검 및 구현

최종 소스 검증: 전체 Python 2,400통과/8건너뜀, Node 타이머4통과, Node22.23.1 Web build51modules, 문서/메뉴얼11탭·11기관/9설정 표면 정합 통과. 상세 기준은 `TEST_STATUS.md`를 따른다.

- `tests/test_v39132_notification_audit.py`: 11개 기관 설정·별칭, 0초/0회, 부팅 직후 첫 알림, 계정 전환/발송 경합, 7거래소 시세 누락, 4증권사 국면 실패·복구, 빈 후보에서도 보유 서비스 호출, 실행 오류 알림, LIVE/PAPER 위험 알림 격리, 미래에셋 일봉 경로 분리를 검증한다.
- 증권 건수 집계의 임시 PnL 0원 및 기간 미확정 합계를 LIVE 위험 근거로 사용하지 않는다. 손익 검증 계약이 없는 어댑터는 `pnl_verified=false`이며 활성 손실 가드레일은 신규 진입을 보류한다. 손실률 미산출 시 경고율을 창작하지 않는다. 실제 증권 계정에서 이 상태를 해제하려면 해당 기관의 검증 가능한 일일 손익 근거가 필요하다.
- Discord 긴 알림은 [공식 content 제한](https://docs.discord.com/developers/resources/webhook#execute-webhook)에 맞춰 요약 표시 및 앱 전체 내용 안내를 사용한다. 임의 멘션은 차단한다. Telegram 대화방 조회 실패는 성공/빈 목록으로 숨기지 않는다.
- 소스·모의 테스트는 실제 메신저 수신이나 Windows/증권사 제휴 계약 확인을 대체하지 않는다.

- `data/Teayu` 원장·설정·로그만 조회했으며 파일·계정·API 키·전략·회원 권한을 변경하지 않았다. 사용자 키로 API를 호출하지 않았다.
- 공유 DB Coinone 후보 1,130개가 `fallback_unscored / candidate_evaluation_unavailable`였고 해당 분석 구간의 Coinone `trade_runtime` 결정은 없었다. 이는 단순 신호 대기와 다르다.
- 알림 스크린샷은 9월 11일 기록이다. v31 설치 직후 발생한 새로운 사건이라고 날짜를 바꾸어 해석하지 않는다. 현재 소스에도 해당 분기가 남아 있음을 별도로 확인했다.
- KIS 스크린샷 시점과 공유 로그의 마지막 시점이 같다고 가정하지 않는다. 잔고 표시만으로 분석·주문·체결 정상 여부를 확정하지 않는다.
- 2026-09-15 키 없는 공개 CCXT 4.5.50 조회: Coinone 363개 시장 모두 active=None. 수정 후 363개 KRW 후보 시장으로 정규화됨.
- 후속 공개 호출에서 CCXT Coinone의 `fetch_tickers(symbols)`가 첫 종목만 조회하는 별도 문제도 재현했다. 어댑터의 전체 KRW 스냅샷 후 로컬 필터로 보완했고 상위 5개 공개 후보 반환을 확인했다. 이는 상세 점수·PAPER 체결 완료를 뜻하지 않는다.
- 공식 KIS 공개 마스터 읽기: 정상 필터 후 KOSPI 1,698개(ETF 860), KOSDAQ 1,591개. 이는 시점별 목록이며 주문 가능·수익 보장 수치가 아니다.
- 원장 PnL·거래 수량·TP/SL·회원 정책·LIVE 승인 게이트는 변경하지 않는다. 후보 수집 복구로 향후 분석·진입 대상은 달라질 수 있다.

## 공통 계약

- `trading/notifications.py`: 실제 의미 변경만 발행. 관찰 heartbeat와 변경 알림 분리.
- `webui/electron/update-scheduler.cjs`: 앱 실행 중 타이머. 첫 저장 설정 반영 후 약 15초, 이후 설정 주기. 실시간 GitHub 푸시가 아님. 절전에서 돌아오면 밀린 횟수만큼 요청하지 않음. 수동 확인은 자동 OFF에서도 가능.
- 다운로드 자동화는 저장된 옵션을 따른다. 설치·재시작은 명시 확인 및 안전 종료 유지. 자동 강제 청산/자동 적용 기능을 새로 추가하지 않는다.
- `trading/exchanges/kis_market_master.py`: 공식 HTTPS 검증, 압축 다운로드 2MB/해제10MB 제한, 메모리 파싱만, 성공6시간·실패60초 캐시. 오래된 성공 캐시로 무한 진행하지 않음. 증권사 제휴 주문 API를 KIS 주문 API로 대체하지 않음.
- `trading/runtime_observability.py`: 기관별 상태 변화 즉시 표시, 동일 상태 최대5분 heartbeat. 알림 채널로 매 사이클 보내지 않음.
- 공개 마스터는 현재 실행기가 지원하는 6자리 숫자 종목코드·ST/EF만 후보로 반환한다. 다른 코드 형식과 ETN·펀드 지원을 이번 패치로 주장하지 않는다. 미래에셋의 계약된 stock_list/etf_info가 있으면 그 목록과 NAV/추적오차를 우선 보존하고, KIS 사용자 지정 ETF 목록도 유지한다.
- 메뉴얼 정본은 `ui/widgets/user_manual_widget.py`, 생성본은 `docs/USER_MANUAL_SECTIONS.json`. 업데이트·시작/설정·자산별 사용·증권 탭과 Web 업데이트 요약을 같이 갱신한다.

## 자동 검증

- `tests/test_v39132_feedback_contracts.py`: 11기관 동일 국면 차단, 7거래소 실제 재선정 분기, Coinone active null/false, KOSPI/KOSDAQ 고정폭 파싱, KIS/미래에셋 종목 API 분리, 4증권사 빈 유니버스 로그, 반복 로그 제한.
- `node --test webui/electron/update-scheduler.test.cjs`: 저장 주기·초기 확인·중복 요청·실패 재예약·OFF·로그아웃/종료·절전 복귀.
- 전체 pytest, Web production build, 문서 정합, 메뉴얼 재추출, Web 표면 감사는 최종 검증 결과를 `TEST_STATUS.md`에 기록한다.
- 최종 결과: Python2,329통과/8건너뜀, Node scheduler4통과, Node22.14.0 lockfile 기준 Web build51modules, 문서/정본/표면 감사PASS. Windows·실계정·지속 운용은 아래 미완료 게이트로 남긴다.

## 배포 및 외부 게이트

- [ ] WIN-BUILD: v32 엔진·설치기·제품/updater 버전과 해시 확인
- [ ] ROLLBACK: v31 백업 복구와 사용자 원장·설정 보존 확인
- [ ] WIN-UPGRADE: 설정창 미방문 주기 확인·업데이트 재시작
- [ ] KIWOOM-E2E / KIS-E2E / BITHUMB-E2E / SPOT-FUTURES-PAPER: 실제 기관 환경 확인
- [ ] REPORT-E2E / RECONCILE-E2E / SOAK: 채널·원장·24~72시간 확인

| ID | 요구 증거 | 상태 |
|---|---|---|
| WIN-BUILD | Node22.12+ / 새 엔진·설치기·버전32·해시 | 미완료 |
| WIN-UPGRADE | v31→v32 설정 유지, 설정창 미방문1시간 확인, 다운로드 후 안전 재시작, OFF·절전·오프라인 | 미완료 |
| KIWOOM-E2E | Windows OCX 실제 연결, 시작·분석·중지 로그 | 미완료 |
| KIS-E2E | 사용자 실계정, 공개 마스터 접근, 장중 후보·분석·PAPER 이벤트 | 미완료 |
| BITHUMB-E2E | 기존 현물 후보·캔들·PAPER 유지 | 미완료 |
| RECONCILE-E2E | 기존 실체결 대조·원장 보존 | 이번 패치 변경 없음 / 외부 확인 별도 |
| SPOT-FUTURES-PAPER | 7거래소 후보·분석·PAPER와 4증권사 기관 분리 | 합성 테스트 / 실제 장중 운용 미완료 |
| REPORT-E2E | 실제 알림 채널의 동일국면0회·실제변경1회와 업데이트 통지 | 미완료 |
| SOAK | 24~72시간 타이머·로그·Coinone/KIS PAPER 연속 운용 | 미완료 |

테스트 통과를 ‘모든 계정·기관에 더 이상 버그 없음’으로 표현하지 않는다. Coinone 진입을 강제하거나 실제 주문으로 검사하지 않는다.

## 공식 계약 근거

- [KIS KOSPI master](https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/kis_kospi_code_mst.py)
- [KIS KOSDAQ master](https://github.com/koreainvestment/open-trading-api/blob/main/stocks_info/kis_kosdaq_code_mst.py)
