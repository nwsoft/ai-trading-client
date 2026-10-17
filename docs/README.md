## 2026-10-17 — v3.9.2.17 PAPER 원장 연속 운용·백그라운드 대조 (소스 후보·미배포)

현재 소스 후보 버전: **v3.9.2.17**
현재 공개 버전: **v3.9.2.16**
현재 소스 후보: v3.9.2.17 · 현재 공개 기반: v3.9.2.16 · updater 3.9.217 · renderer 3.9.2.17-ui.20261017.1.

공개 v3.9.2.16은 `8b4f62b24df04cfe427d46eb2f55dfef24ff1b28`이며 아래 .16 이하 후보·미게시·검증 표시는 당시 이력이다. .17 Windows 빌드·설치·게시·실기관 인수는 아직 수행하지 않았다. 이번 인계의 정본은 `reports/v39217-paper-maintenance-20261017/handoff.json`과 같은 폴더의 `validation.json`이다.

누적 한도 제거·원본 보존·백그라운드/기관 순차 점검·선택 전략 도구 발견성·GPT-6 Luna 기존 호환 재검증을 반영한다. [CHANGELOG](CHANGELOG.md)와 [BUILD_GUIDE](BUILD_GUIDE.md)를 따른다.

## 2026-10-16 — v3.9.2.16 PAPER 기간 선택 위치·버전 안내 (로컬 수정 후보)

현재 소스 후보 버전: **v3.9.2.16** · 현재 공개 버전: **v3.9.2.15**
현재 소스 후보: v3.9.2.16 · 현재 공개 기반: v3.9.2.15 · updater 3.9.216 · renderer 3.9.2.16-ui.20261016.3.

공개 .15 `9e9fcc3dc3c21e36518081a0d349df91f0dd145c`는 2026-10-15 18:01:11 KST 게시됐다. 공개 .14는 `d8e698f5dd181ec5effffb045c5f51e999a4a72b`다. 아래의 후보/미게시 문장은 작성 당시 이력이며 현재 공개 상태를 뜻하지 않는다. 이번 수정은 공개 .15를 덮어쓰지 않는 별도 .16 소스 후보다. Windows .16 빌드·게시·실기관 인수는 미실시다.

실제 Mac Electron 앱의 빌드 화면 + 실제 로컬 FastAPI/전략 저장 경로에서 PAPER 1·3·7일 선택과 시작/일시정지/기간 변경/재개를 확인한다. 시험 계정·별도 데이터 경로·Detached runtime을 사용하며 실주문/실기관 인증·고객 설정 변경은 하지 않는다. .14/.15의 기간 선택 기능은 존재하고 기간 저장 실패는 현재 재현되지 않았다. 다만 첫 화면에 선택 위치 안내가 없고 스크롤 아래의 버전 카드 안에 있어 찾기 어렵다. .16에서는 전략 사용하기 첫 화면에 기간 설명과 「기간 선택 위치로 이동」을 추가한다. 현재 검색 목록의 변경 가능한 버전으로 이동하고, 모두 실행 중이면 해당 안내를 보여주며 자동 정지/기간 저장을 하지 않는다. 빈 목록은 저장 또는 검색 초기화 안내를 표시한다.

이번 직접 재실행 시험에서 macOS에 남은 프로세스가 이미 닫힌 창에 접근하는 `Object has been destroyed` 오류도 발견했다. .16은 닫힌 창 참조를 정리하고 재실행 시 창의 생존 여부·gateway 준비·종료 상태를 확인한다. 새 거래 엔진을 중복 기동하지 않는다. Windows 빌드의 Node 검사에 Electron 창 수명주기 검사도 포함한다. Mac 종료·재실행과 단위 검사는 별도 근거로 기록하며 Windows 확인을 대신하지 않는다.

최신 근거: `reports/v39215-paper-trial-review-20261016/validation.json`. 실제 데스크톱 확인과 모의 React/단위 검사, Windows 설치본·실거래 검증은 구분한다. 기존 1·3·7일의 저장·일시정지·재개·최종 적용 안전 검사는 유지한다.

2026-10-16 20:32 사용자 예제 피드백 추가: 「추세 따라가기」의 예전 멘토/기존 화면 원문과 Web 예제가 달랐다. .16은 관리 템플릿의 실제 수치·방향·시간봉·사용자 위험예산을 원문으로 생성하고 Web JSON도 같은 정본에서 내보낸다. 코인은 LONG/SHORT, 주식은 명시적인 LONG/1d/1배 프로토타입이다. 기존 저장 전략·승인·PAPER 표본은 마이그레이션하지 않는다. 새 예제의 고정 TP/SL은 원래 ATR/스윙·동적 손익비 전략과 다르며 수익 검증 전략이 아니다.

사용자의 원문은 그대로 보존한다. LONG/SHORT별 EMA 비교·RSI 범위와 「15m (완성된 봉 기준)」을 보존하고, 연결된 제외 시장(횡보·고변동)을 허용 시장으로 잘못 추출하던 결함을 수정한다. ATR/스윙 손절은 없다고 안내하지 않고 실행 수치 미정으로, 손익비 1.8은 익절 1.8%가 아닌 목표가 정의 필요로 안내한다. 평균 거래량 기간·방향별 EMA 청산·HIGH 적용 범위·큰 시간대/유동성/스프레드 필터는 임의로 만들거나 삭제하지 않으며 미정/미지원이면 실행 차단과 행별 질문을 유지한다. 원문에 고정 비율만 넣어도 나머지 미정 조건을 통과시키지 않는다. 새 예제와 원문을 같은 전략으로 표시하지 않는다.

이번 추가 검증: `reports/v39216-preset-feedback-20261016/validation.json`. 이 보고서와 최신 handoff가 이전 .16 기간 선택 점검의 인계 파일을 대체한다. 공개 .15 자산은 보존하며 Windows .16 설치/실기관/24·72h 검증은 별도다.


## 2026-10-15 — v3.9.2.15 사용자 피드백 수정 (소스 후보)

현재 소스 후보 버전: **v3.9.2.15** · 현재 공개 버전: **v3.9.2.14**
현재 소스 후보: v3.9.2.15 · 현재 공개 기반: v3.9.2.14 · updater 3.9.215 · renderer 3.9.2.15-ui.20261015.3.

3.9.2.15 추가 수정: 증권 분봉 전략을 평가 엔진에 실제 연결했습니다(키움 opt10080/32bit IPC, 한국투자 실전 과거/모의 당일 분봉). 완료봉·누락·페이지/캐시·실패 복구를 검사하고 서버 설정·기존 규칙/권한·주문 모드를 자동 변경하지 않습니다. 키움 TR은 연결 끊김/서버 거부/콜백 유실을 구분하고 불충분한 RPC 예산에서는 제출하지 않으며, 연속 무응답 뒤 조회를 30초 대기합니다. 주문 재전송·자동 재로그인으로 우회하지 않습니다. 모의 서버의 분봉 표본 부족, 미래에셋/신한 분봉, 증권 분봉 기간 지정 재생 및 실제 Windows OCX 인수는 별도 한계입니다. 최신 검증은 `reports/v39215-intraday-20261015/validation.json`, 동일 Windows 소스는 기존 handoff/bundle을 갱신합니다.


공개 .14의 `d8e698f5dd181ec5effffb045c5f51e999a4a72b`를 기준으로 수정한다. 공개 설치기·manifest는 덮어쓰지 않으며 아래 .14 이하 내용은 당시 이력이다. 이번 변경은 새 .15 후보이며 Windows 설치·실기관/OCX·24/72h·푸시·게시·운영 배포 완료를 의미하지 않는다.

| 피드백 | 확인과 반영 |
| --- | --- |
| 코인 국면이 일반에 머묾 | 오늘 시장 트렌드와 대표 코인 단기 국면의 집계 차이, 추세·RSI·거래량 동시 조건을 설명한다. Binance 기본 단기 추세 ±1%, CCXT 경로 ±3% 등 기존 기준을 유지하며 실제 지표·임계값·계산 시각을 운용 요약에 추가한다. 일반을 실패나 오늘 보합으로 표시하지 않는다. |
| 일반·심층 어시스턴트 연결 실패 | 공통 답변 경로가 설치 엔진에서 제외된 `ui.ai_custom_guidance`를 import하던 결함을 UI 제외 조건에서 재현했다. `trading.ai_custom_guidance`로 정본을 옮기고 구형 UI는 재노출한다. 예상 밖 오류에도 CORS·지원 코드·요청 ID를 유지한다. |
| 예제의 필수 조건 누락 | 화면 기본 예제 4개를 숫자·단위·진입·청산 규칙이 있는 명시적 학습용 LONG 프로토타입으로 제공한다. 원문 전략이나 검증된 수익 전략으로 가장하지 않는다. 증권 예제는 일봉을 사용한다. |
| 기술점수 미산출 | 빠른 선정은 티커 우선이며 RSI 자료가 없으면 기술점수가 None이다. 이유와 실시간 분석 경로를 표시하며 0점이나 고정 점수로 채우지 않는다. |
| 거래소별 승률 | PAPER는 유효 가상 청산, LIVE는 대조 완료 청산을 분모로 기관·통화별 승률을 추가한다. 표본 없음/미대조는 미확정이다. |
| 증권 선정 종목 | 실제 워커가 선정·평가한 종목·점수·사유·시각을 해당 기관의 종목정보에 표시한다. 현재 보유/신규 진입 확정과 구분하며, 기록이 없으면 코인 후보로 채우지 않는다. |
| 증권 학습 화면 | 증권 전용 추가 안내 행을 고려해 모니터는 내용 높이, AI 판단·학습 근거는 남은 높이를 사용한다. 코인 학습 배치는 별도로 유지한다. |
| 전략 등록·관리 | 미적용/내용 확인·승인 필요/PAPER 검증 필요 필터, 명시적 선택 내용 승인, 새 버전 위치 이동, 파일별 독립 초안 저장, 단일 기관 선택, 파일 명시 메타데이터·이름 연결을 추가한다. 버전별 LIVE 성과는 실제 귀속 청산만 기관·통화별로 조회한다. |

TXT/Pine은 파일당 1MB·최대 10개를 순차 분석하고 파일별 이름·기관·규칙을 검토한 뒤 준비 완료 초안만 저장한다. 실제 사용자 파일 10개의 로컬 컴파일과 최종 실행 준비 검사를 별도로 확인한다. 일괄 분석은 묶음 자료를 한 전략으로 합치는 기존 방식과 구분한다. 실패/보완 항목은 개별 표시하고 저장 응답 유실은 자동 재전송하지 않는다. 내용 승인·PAPER 시작·최종 적용은 합치지 않는다. 명시 거래소/국면 기준/우선순위는 결정형 컴파일러가 읽으며 없거나 모호한 값은 추정하지 않는다. 선언한 범위의 수정은 원문 재분석 또는 명시적 사용자 재정의가 필요하다.

검증 정본은 `reports/v39215-feedback-20261015/validation.json`, Windows 소스는 같은 폴더의 `handoff.json`·`v39215-feedback.bundle` 및 [BUILD_GUIDE](BUILD_GUIDE.md)를 따른다. 공유 데이터는 읽기 전용으로 확인하며 키·계정·원장·고객 전략 원문을 문서/테스트 fixture로 복사하지 않는다. 설치본 의존성 제외 재현과 실제 Windows 빌드·기관 인수는 구분한다.


2026-10-15 배포 전 추가 점검: 공유 설정은 복사본에서 주요 거래 값과 자격증명 저장 필드 50개가 보존됐고, 기존 전략 70개·적용 2개·PAPER 등록 63개의 규칙/권한을 유지했다. 증권 전략 10개의 분봉 공급 누락은 이번 후속에서 키움 opt10080·한국투자 분봉 REST와 실제 평가 엔진을 연결해 보완했다. 완료봉 시험 자료에서는 10개 모두 시간봉 자료 없음 단계를 통과했으며 원문·권한을 자동 변경하지 않는다. 실제 기관의 자료 확보·진입 조건·위험 검사는 별도이며 PAPER 통과나 주문 발생을 보장하지 않는다. 코인 60개 범위와 증권 10개 범위는 분리된다.

한국투자의 .14 저장 판단 224건 중 합의 제한 172건은 HOLD였고, 52건은 매도 신호였다. HOLD를 매수 합의 실패로 설명하지 않도록 순서를 수정하고, 일반 주식 SELL 합의는 매수 매력도 점수의 반대 방향을 사용한다. 코인 기본 합의·ETF 위험 계산·국면·손실/수량/주문 권한 검사는 유지한다. 명시적 cooldown 0이 60으로 대체되는 결함과 주문 결과의 사유 누락도 수정한다. 키움은 저장된 연결 플래그 외에 현재 OCX 연결을 확인한다. Windows 실제 복호화/로그인·TR 응답 회복은 미확인이다.

압축 포함 로그 430개·104,564,619줄을 읽었으며 읽기 실패는 없었다. 로그 행/재시도는 고유 장애 수가 아니다. 날짜만으로 버전을 단정하지 않고 DB의 .13/.14 app_version 및 새 호스트 구간을 구분한다. .13 장시간 무응답과 .14 키움 성공 255회·시간 초과 44회가 공존하므로 외부 장애가 모두 복구됐다고 쓰지 않는다. 원문 로그·키·계좌·원장·전략 내용은 공개하지 않는다. 최신 추가 검증은 `reports/v39215-upgrade-audit-20261015/validation.json`, 빌드 인계의 최신 커밋은 기존 handoff.json을 따른다. 앞선 .15 3b700df 검증은 이전 후보 이력이다.


## 2026-10-14 - v3.9.2.14 증권 무거래·전략 운용 피드백 후속 (소스 후보)

현재 소스 후보 버전: **v3.9.2.14**
작성 당시 공개 버전: **v3.9.2.13**
현재 소스 후보: v3.9.2.14 · 현재 공개 기반: v3.9.2.13 · Stock Analysis History and Strategy Controls · updater 3.9.214 · renderer 3.9.2.14-ui.20261014.3.

공개 v3.9.2.13은 GitHub 최신판 `33d351c0b606a619f16c00fc7b6e99aa10086dad`이며 이번 .14는 별도 후속 후보다. .13에서 이미 제공하던 전략 승인/PAPER 시작·일시정지/이어가기·검증 후 적용/해제를 새 기능처럼 중복 구현하지 않는다. 최신 공개 소스에서 증권 일봉 연결 누락과 PAPER 청산 손익 필드 불일치를 재현해 수정했다. 키움의 전일가 입력 누락도 공식 OpenAPI+ 전일가 함수로 보완했다. 기존 거래 임계값과 주문 전 위험 검사는 유지한다. 이번 후속에서 PAPER 관찰 목표와 최종 적용 조건을 분리한다.

증권 4기관(키움·한국투자·미래에셋·신한)의 실제 `get_daily_candles`를 기본 분석에 연결한다. 완료 일봉의 시간순·유한 양수 종가와 실제 최근 20봉 평균 거래량을 사용하고, 실패/부족은 `technical_history`로 표시한다. 증권 PAPER TP/SL은 최신 가격과 비용을 반영한 `net_pnl_percent`를 공통 청산 정책의 `pnl_rate`에 전달한다. 평가 실패는 `paper_exit_valuation_unavailable`로 보존한다. 실제 계정의 무거래 원인을 발견된 결함만으로 단정하지 않는다.

PAPER 시험 기간은 1·3·7일 중 선택하는 관찰 목표다(기본 7일). 승인 후 바로 시작하며 목표 도달 시 화면에서 검토를 안내하고 검증은 계속한다. 사용자가 직접 일시정지하며 자동 적용하지 않는다. 최종 적용은 기간과 별도로 실제 원장의 유효 청산 최소 3건·비용/손익 대조·위험 근거 기록 및 위반 없음·실행 규칙·사용자 확인을 검사한다. 최소 3건과 선택 기간은 통계적 충분성이나 수익을 보장하지 않는다. 정상 신호 대기에도 표본은 늘지 않을 수 있다. 기본 자동매매는 독립적으로 실행된다.

시간은 두 값으로 구분한다. **등록 후 경과**는 일시정지를 뺀 허용 구간의 달력 시간으로 앱 종료 시간이 포함된다. **실제 진입 후보 규칙 평가시간**은 정상 완료된 후보 평가 호출 구간을 중복 없이 합산한 시간이다. 대기·오프라인·보유시간은 합산하지 않으며 과거 실행시간을 추정하지 않는다. 미기록/집계 실패는 0으로 표시하지 않는다. 최근 평가 시각은 사용자 시간대로 표시한다.

적용된 전략의 기존 「적용 해제」를 「전략 적용 일시정지」로 명확히 안내하고 검증 버전의 재적용을 연결한다. 신규 진입 풀에서 그 전략만 제외하며 보유 포지션 청산계획·원장·검증 근거를 보존한다. 기본 AI·다른 전략은 계속 거래할 수 있다. 기관 전체 중지와 다르며 시간 지정 자동 만료/자동 재개는 미구현이다. 새 상태머신·LIVE 우회 권한은 만들지 않는다. 내장 어시스턴트에 1·3·7일/시간 구분/일시정지·증권 무거래 안내를 추가한다.

[테스터 인수와 실행 기준](DEPLOY_CHECKLIST.md) · [검증 근거](../reports/v39214-paper-trial-20261014/validation.json). Windows .14 빌드·게시·실기관/OCX·고객 계정 복구·다른 배포 사용자의 반응은 확인되지 않았다. 고객이 키움·한국투자 모두 PAPER라고 확인했다(2026-10-14). 최근 진입 보류 문구는 전달 대기이며 개별 무거래 원인 확정·복구 확인은 아직 아니다. 아래 .13 이하 상태·수치는 해당 당시 이력이다.

## 2026-10-12 — v3.9.2.13 배포 인수 상태 정합성 (소스 후보)

현재 소스 후보 버전: **v3.9.2.13**
작성 당시 공개 버전: **v3.9.2.12**
현재 소스 후보: v3.9.2.13 · 현재 공개 기반: v3.9.2.12 · updater 3.9.213 · renderer 3.9.2.13-ui.20261012.1.

공개 .12는 2026-10-12 11:21:46 KST 게시된 5a645b455b9800696b5cad6f1b06946fb2d32623이다. .13은 별도 후속 후보이며 새 Windows 빌드·게시·설치는 미실시다. 기존 .12의 거래 보호·PAPER 안내·내 돈 계획과 Windows junction 보호를 유지한다. 수정 범위는 인수 체크리스트의 ID·상태·미완료 개수를 같은 원본에서 생성하는 빌드/게시 계약, .12 공개 원본 보존 및 .13 버전·안내 정합성이다.

외부 인수 ‘9개’는 공개 .12 당시 미완료 체크리스트 줄 수이며 6개 일반 범주와 다른 목록이었다. 현재 재확인한 .12 SDK·빌드·게시 근거 3개와 실제 테스터 인수 6개를 구분한다. 완료하지 않은 설치/기관/장시간 검증을 통과로 승계하지 않는다. [정확한 9항목·실행/정상/실패 기준](DEPLOY_CHECKLIST.md#acceptance-v39213), [검증 근거](../reports/v39213-acceptance-20261012/validation.json).

아래 .12 이하의 후보·공개·미게시 상태와 검사 수치는 해당 작성 당시 이력이다.

## 2026-10-12 - v3.9.2.12 PAPER 복구 안내·내 돈 계획 저장 경합 수정

현재 소스 후보 버전: **v3.9.2.12**
작성 당시 공개 버전: **v3.9.2.11**
현재 소스 후보: v3.9.2.12 · 현재 공개 기반: v3.9.2.11 · updater 3.9.212 · renderer 3.9.2.12-ui.20261012.2. Windows 새 빌드·게시·설치 인수는 미실시.

전략 PAPER 검증 OFF와 거래소 자동매매 정지의 차이를 설명하고, 전략 삭제 없이 과거 원장을 보존하는 새 평가 준비 순서를 안내한다. 이 사용법 질문은 서버·외부 AI 연결 없이 내장 도움말로 답한다. 실제 앱에서 발견한 보관함 busy/locked 오인으로 저장 입력이 지워지는 경합을 수정했다. 실주문 검사를 자동 켜지 않으며 제외된 11개 검사와 Windows 필수 PE 검사를 감사한다.

[3.9.2.12 인수 정본](V39212_FEEDBACK_AND_RELEASE_PLAN.md). 아래 .11 이하의 수치·미배포 표기는 해당 당시 이력이다.

2026-10-11 후속 구현: 자산 통합 → **내 돈 계획**에서 월 예산·수동 자산/원화 부채·비상금·반복 지출·목표별 세후/비용/물가/하락 가정·절세 조건을 연결하고, 검토한 계획을 암호화 저장해 월 실제 기록과 재점검한다. 현재 renderer `3.9.2.11-ui.20261011.4`, Web 추가 기능 `portfolio.plan` 포함 36개. [구현·사용법·한계](V39211_WEALTH_PLANNING.md)와 [현재 검증](../reports/v39211-wealth-planning-20261011/validation.json)을 따른다. 실제 금융기관 자동 수집·개인별 최적 절세·가입/주문·Windows 빌드·배포 완료는 별도다. 아래 수치는 해당 당시 소스의 이력이다.

## 2026-10-10 — v3.9.2.11 거래 신뢰성·통합 금융비서 연결

현재 소스 후보 버전: **v3.9.2.11**
작성 당시 공개 버전: **v3.9.2.10**
현재 소스 후보: v3.9.2.11 · 현재 공개 기반: v3.9.2.10. 제품/엔진/PE 3.9.2.11, updater 3.9.211, renderer 3.9.2.11-ui.20261011.4.

OKX·Bybit·Bitget의 공개 선물 목록 조회 의존성을 분리하고 제한 재시도·원인 분류를 보완했다. Upbit 중복 종목 ID의 시세 해석과 Bitget 비암호화폐 상품 필터를 수정했다. 과거 PAPER 원장의 자금 대조 차단·별도 새 평가 준비 안내, 신뢰도 등 진입 보류 사유·실제 수치·기준을 연결하고 7개 암호화폐 기관의 장시간 무거래·주기 갱신 지연을 메인 거래 현황과 기관 운용 요약에 표시한다.

[3.9.2.11 변경·배포 인계 정본](V39211_TRADING_ENTRY_UPDATE.md) · [사용자 안내](USER_GUIDE.md) · [검증 결과](TEST_STATUS.md) · [현재 패치 인수 체크리스트](DEPLOY_CHECKLIST.md).

공개 v3.9.2.10의 빌드·게시 이력은 보존한다. 이번 v3.9.2.11은 후속 수정 소스와 문서·매뉴얼 정리 단계이며 새 Windows 설치기 빌드·공개 게시는 아직 수행하지 않았다. 아래 이전 버전의 후보·미게시·실행 승인·검증 수치는 각 작성 당시 이력이다. 과거 승인을 이번 버전의 게시 완료 근거로 사용하지 않는다.

[3.9.2.11 통합 금융비서 개발·인수 원장](V39211_FINANCIAL_COMPANION_PLAN.md): 오늘의 브리핑, 거래 진단, 금융 비교 연결, 전략 실험·배분 가정·재점검·음성 입력 범위.


---

## 2026-10-10 — v3.9.2.10 전략 스튜디오 작업 선택·학습 안내 통합

당시 소스 후보 버전: **v3.9.2.10** · 당시 공개 버전: **v3.9.2.9**.
당시 소스 후보: v3.9.2.10 · 당시 공개 기반: v3.9.2.9. 제품/엔진/PE 3.9.2.10, updater 3.9.210, renderer 3.9.2.10-ui.20261010.1.
공개 v3.9.2.9는 2026-10-10(KST) 빌드·게시 완료되었으며 이번 변경은 별도 v3.9.2.10으로 묶는다. 공개 기반 커밋은 `52fb7df23dcdc8bab2df0cd287abf86acba1fcba`이다.

기본 작업을 전략 사용하기·내 전략 만들기·공유하기로 나누고, 따라하기·멘토·Level 안내·검증 원리·허브 상세 설명은 학습·고급 안내에 보존했다. 작업 이동 시 작성 초안을 유지하고, 보완·멘토 후보·AI 전달 초안은 작성 화면으로 이동한다. 검증 상세와 여러 버전 관리는 펼쳐 볼 수 있다. 기존 Level 기능 게이트·승인·PAPER/LIVE 보호·원본과 검증 이력은 유지하며 매매 엔진·PAPER 계산을 변경하지 않는다.

현재 무료 공유이며 유료 판매·제작자 정산은 준비 중이다. 허브 첫 화면·제출·학습 안내 템플릿은 인접 daltrading 소스에서 별도 검증했고 클라이언트 설치기만으로 서버에 배포되지 않는다. 사용자 최신 요청은 점검·수정·전체 Windows 빌드 후 stable/latest 공개 릴리스를 승인한다. 이 절 작성 시 설치기 빌드·공개 게시는 준비 중이며, 최종 결과는 reports/v39210-windows-publication-20261010.json으로 확인한다. 실제 설치 업데이트/롤백·OCX·실계좌·장시간 운용은 별도 인수이며 미실시를 통과로 표시하지 않는다.

## 2026-10-08 — v3.9.2.8 PAPER 청산 복구·계약 근거 보호 (소스 후보·미배포)

당시 소스 후보: v3.9.2.8 · updater 3.9.208. 현재 공개 기반: v3.9.2.7.
당시 소스 후보 버전: **v3.9.2.8** · 당시 공개 버전: **v3.9.2.7**.

공개 .7 커밋 `1c23b1e4947514906c1eb11050873a5c74ce39b0`에서 별도 .8 브랜치로 수정·시험·로컬 커밋한다. main을 기반으로 하지 않는다. 청산 원장의 확정 이벤트와 잔여 수량·완료 상태를 재시작 때 대조하고, 계약 단위 없는 해외 선물 과거 기록은 미확정으로 분리한다. [수정·복구·보존 증거 및 남은 인수](V3928_PAPER_RECOVERY.md).

이번 지시는 GitHub push·PR·공개 릴리즈 배포를 포함하지 않는다. 아래 .7의 즉시 게시 승인·후보 표기는 당시 이력이며 .8에는 적용하지 않는다. Windows 설치본 수동/자동 업데이트·롤백·24/72시간 운용은 실제 환경이 없어 미실시다. 로컬 자동 검사를 설치본 인수로 표시하지 않는다.

## 2026-10-07 — v3.9.2.7 전략 업로드·PAPER 계산 수정 (소스 후보·미배포)

당시 소스 후보: v3.9.2.7 · updater 3.9.207. 현재 공개 기반: v3.9.2.6.
당시 소스 후보 버전: **v3.9.2.7**
당시 공개 버전: **v3.9.2.6**

Windows 빌드·릴리즈·게시 담당은 사용자입니다. Codex는 수정·로컬 검증·배포 준비만 수행합니다. 허브 파서 패치는 별도 서버 반영이 필요합니다. [수정 원인·기존 사용자 재개·검증 경계](V3927_FEEDBACK_PATCH.md). 아래 버전별 후보·미배포 표기는 당시 이력입니다.

## 2026-10-06 — v3.9.2.6 전략 스튜디오·자율주행 후속 (개발 진행·미배포)

당시 소스 후보: v3.9.2.6 · updater 3.9.206. 현재 공개 기반: v3.9.2.5.
당시 소스 후보 버전: **v3.9.2.6** · 당시 공개 버전: **v3.9.2.5**

3.9.2.5는 빌드·릴리스·배포 완료한 공개 버전으로 보존합니다. 이후 로그·배분 정정, 코인/주식 종목 선택, 시작 버튼 기반 자율주행과 전략 스튜디오의 남은 고도화를 3.9.2.6으로 진행합니다. [실행 원장·완료 조건](UPDATE_PLAN.md#v3926-autonomous-studio-release). 새 Windows 설치본·공개 게시·실환경 인수는 아직 완료하지 않았습니다. 아래 날짜별 소스/후보/배포 표기는 당시 이력입니다.

## 2026-10-05 — v3.9.2.5 생활금융 비교·후속 관리 (공개 Windows 릴리스)

현재 소스 기준: v3.9.2.5 · updater 3.9.205. 현재 공개 기반: v3.9.2.5 (2026-10-05 공개 게시·2026-10-06 GitHub latest 재확인).
현재 소스 기준 버전: **v3.9.2.5**

공개 v3.9.2.4 이후 수정입니다. 상황별 진입, 목적 필터, 관심 보험 근거 설명, 비상금·보장·대환·사용 날짜 비교, 암호화 계획과 공통 조건, 자료 피드 갱신/복구, 상담 회신 견적, 기록 수정·가져오기를 구현합니다. [반영 범위·검증·운영 연결 인수](V3925_LIFE_FINANCE_COMPLETION.md). **3.9.2.5 Windows 설치기·blockmap·latest.yml·release-manifest.json은 2026-10-05 공개 게시되었습니다.** 아래 날짜별 후보/미게시 문장은 당시 이력입니다.


2026-10-06 공개 신원 대조: [GitHub 릴리스](https://github.com/nwsoft/ai-trading-client/releases/tag/v3.9.2.5)의 latest·게시 시각·4개 자산 digest를 보관된 게시 보고서와 대조했습니다. 설치본 게시와 실제 금융사·상담사 연결, 기관별 실계좌·장시간 인수는 별도입니다. [거래 화면·전략·문서 재감사](TEST_STATUS.md#v3925-trading-document-audit-20261006).

## 2026-10-04 — v3.9.2.4 상황 기반 탐색·선택형 AI 판단 (소스 후보)

당시 소스 후보: v3.9.2.4 · updater 3.9.204. 현재 공개 기반: v3.9.2.3 (사용자 배포 확인).
당시 소스 후보 버전: **v3.9.2.4**

공개 v3.9.2.3 이후 변경은 v3.9.2.4로 배포합니다. 상황부터 상품 찾기, 기존 지원 모델 선택·질문 분류·검토 후 적용, Mac 소스 실행 복구를 포함합니다. [구현·검증·남은 인수](V3924_FINANCE_DECISION_UPDATE_PLAN.md). v3.9.2.4 설치본은 아직 게시하지 않았습니다. 아래 날짜별 후보·공개 상태는 당시 기록입니다.

## 2026-10-03 — v3.9.2.3 Windows 릴리스 후보

당시 소스 후보 버전: **v3.9.2.3** · updater **3.9.203**. 현재 공개 기반: v3.9.2.2. 공개 v3.9.2.2 자산은 보존하며 새 설치본은 전체 자동 검증 후 게시한다. 수익성 재진단·생활금융 조건 계산·암호화 보관·상담 연결 준비를 포함한다. 실계좌·OCX 로그인·전문가·실제 공급사/상담사 인수와 설치 업그레이드·장시간 운용은 미완료다. 아래 후보·미게시 설명은 작성 당시 이력이다.

## 2026-10-03 — 공개 자산 확인과 차기 구현 상태

현재 공개 기반: v3.9.2.2 · 당시 공개 버전: **v3.9.2.2**. 공개 v3.9.2.2는 GitHub latest의 게시 시각·자산 digest와 기존 manifest를 대조했습니다. 차기 v3.9.2.3의 로컬 구현·시험·남은 인수는 [구현 현황](V3923_IMPLEMENTATION_STATUS.md)에서 구분합니다. 차기 설치본은 아직 게시하지 않았습니다. 아래 날짜별 후보·미게시 설명은 작성 당시 이력입니다.

**최신 변경 기록:** [v3.9.2.3 차기 수정 내역](CHANGELOG.md) · [코드 이력](CODE_CHANGE_LOG.md) · [업데이트 요약](../RELEASE_NOTES.md). 거래 검증·생활금융·상담 연결 준비는 로컬 구현됐으며 아래 초기 감사의 미구현 표기는 당시 이력입니다. 최신 시험/잔여 인수는 [TEST_STATUS](TEST_STATUS.md)와 [구현 현황](V3923_IMPLEMENTATION_STATUS.md)을 따릅니다.

## 2026-10-03 — 3.9.2.3 계획 재검증과 고객 거래 차단

[수익성 차단 피드백·확인된 결함·고객 대응·P0 인수](V3923_PROFITABILITY_FEEDBACK_REVIEW.md) · [생활금융 계획의 추가 요구와 출시 우선순위](V3923_LIFE_FINANCE_PRODUCT_INTELLIGENCE_PLAN.md). 기존 회귀 109개 PASS와 별도로 새 결함을 격리 재현했다. 계획·가이드/인앱 설명 정정이며 거래 코드 수정·고객 복구·3.9.2.3 배포는 미완료다.

## 2026-10-02 — 차기 3.9.2.3 생활금융 실행 계획

[현황 감사·대출/보험/예적금 전체 기능 원장·DB/갱신·AI 추천/설계·기관 연결](V3923_LIFE_FINANCE_PRODUCT_INTELLIGENCE_PLAN.md) · [실행 상태](UPDATE_PLAN.md#v3923-life-finance). 질문별 고정 안내와 샘플 비교의 한계를 직접 재현하고 차기 개발 요구로 등록했다. 기능 구현·배포 완료가 아니며 배포 버전 변경 없음. 3.9.2.2 선행 구현/인수 경계는 아래 문서에서 유지한다.

## 2026-10-02 - 문서 동기화 (배포 버전 변경 없음)

현재 **3.9.2.2 보험 이해·사실 비교는 소스 후보에 구현**했다. Windows·전문가 인수와 외부 상담 연계는 완료되지 않았다. 공개 기반 v3.9.2.1과 구분하며 기존 문서에 통합했다.

- [보험 상세 설계·범위 A/B·데이터/사업 조건](LIFE_FINANCE_PRODUCT_COMPARISON_ANALYSIS_20260429.md#v3922-insurance-plan)
- [개발 순서](UPDATE_PLAN.md#v3922-insurance) · [시스템 경계](ARCHITECTURE.md#v3922-insurance-boundary)
- [검증 상태](TEST_STATUS.md#v3922-insurance-validation) · [출시 조건](DEPLOY_CHECKLIST.md#v3922-insurance-release)
- [현재 생활금융 사용법과 보험의 한계](LIFE_FINANCE_GUIDE.md)

## 2026-10-01 — v3.9.2.1 어시스턴트 안내·JEV 검토 (소스 후보)

당시 소스 후보 버전: **v3.9.2.1** (updater 3.9.201). 현재 공개 기반: v3.9.2.0. 기존 공개 자산은 변경하지 않고 3.9.2.1 설치기와 자동 업데이트 자산을 새로 생성한다.

공통 오류/기능 안내, KO/EN 라우팅, 선택적 과거재생 안내, 최신 빠른 질문을 보강한다. JEV는 첨부 근거 검토와 조건부 개발 계획이며 실행 Provider 미통합이다. 거래 규칙·승인·비용 한도를 변경하지 않는다. 정본: docs/V3921_ASSISTANT_UPDATE_PLAN.md, docs/V3921_JEV_EVALUATION.md. 최신 시험은 TEST_STATUS, Windows 배포는 DEPLOY_CHECKLIST를 따른다. 아래 이전 버전 섹션은 이력이다.


## 2026-10-01 — 선행 소스 후보 v3.9.2.0 / 당시 공개 v3.9.1.50

[통합 계획](UPDATE_PLAN.md)·[검증 기록](TEST_STATUS.md)·[Windows 인수](DEPLOY_CHECKLIST.md)를 따릅니다. 고객 포털 noahai.net 통합과 공개 50 후속 OKX/키움 수정을 포함하며 Windows 설치기 게시와 웹 운영 배포는 별도로 확인합니다.

## 2026-09-30 — 당시 소스 후보 v3.9.1.50 / 공개 v3.9.1.49

사용자가 49 배포 완료를 확인했습니다. [50 계획](V39150_VISUAL_OVERVIEW_PLAN.md), [시험 기록](TEST_STATUS.md), [Windows 인수](DEPLOY_CHECKLIST.md)가 후속 정본입니다. 아래 49 이하의 현재/후보/미완료는 당시 이력이며 현행 판정은 이 절을 우선합니다.

## 2026-09-29 — v3.9.1.49 통합 업데이트

당시 소스 후보는 49이며 공개 v3.9.1.48의 종목·비용·입력 계약을 유지합니다. [통합 계획](UPDATE_PLAN.md#v39149-operations-summary), [현행 구조](ARCHITECTURE.md), [사용 안내](USER_GUIDE.md), [실제 시험 결과](TEST_STATUS.md), [Windows 확인](DEPLOY_CHECKLIST.md)이 정본입니다. 아래 '현재' 버전은 당시 기록으로, 현행 배포 완료를 뜻하지 않습니다.

## 2026-09-24 - v3.9.1.47 Strategy Repair and Reconciliation Diagnostics Patch (당시 소스 후보)

당시 소스 후보 v3.9.1.47 / updater 3.9.147 · 공개 v3.9.1.46. 전략 등록·기존 버전 보완 및 손익 대조 차단 안내 개선. 원문 실행값의 저장 단계 변형을 제거하고 미완성 초안 보관과 기존 버전의 원문 재분석/명시적 기본 AI 진입 전환을 제공합니다. 기존 성과는 새 버전에 승계하지 않습니다. 손익 확인 실패의 일반 409/워커 장애 안내를 구체화하고 복구 대상과 위험 검사 대상의 불일치를 보강하며 거래별 미확정 사유를 표시합니다. 미확정 손익 무시·자동 LIVE 재개는 제공하지 않습니다.

소스 검증: 전체 회귀 3,736 통과·9 제외·3 subtests 통과. 코인/증권 브라우저 신규 등록·명시적 기존 버전 전환·미완성 초안 보관 6경로 통과(실제 로컬 컴파일러/검증기, 저장 API fixture). 숫자 30.0/30 직렬화 차이의 오차단과 기존 고정 TP/SL 불러오기 충돌도 수정했습니다. Windows 설치본·실계좌·9월 24일 미대조 1건은 미검증입니다. 현재 data/Teayu-001이 없어 고객 사본 회귀 1개도 제외됐습니다. 설치기 빌드·게시를 하지 않았고, 미확정 손익의 조건부 LIVE 재개는 구현하지 않았습니다. 상세 범위는 TEST_STATUS와 최신 V39147 검증 원장을 따릅니다. 아래 이전 수치는 이력입니다.

## 현재 v3.9.1.46 소스 후보 / 공개 v3.9.1.45

v46은 기관별 시작·보호주문·전략 귀속·알림 진단 수정이며 미배포입니다. [실제 검증 경계](../reports/v39145-cross-venue-feedback-audit-20260923.md). 아래 이전 후보 문구는 작성 당시 이력입니다.

[원격 사용법](REMOTE_MANAGEMENT_GUIDE_V39142.md) · [실행 계획·시험](V39142_REMOTE_CONTROL_PLAN.md). Client 빌드·릴리스는 사용자가 수행합니다. 이전 버전 문서는 당시 상태를 보존합니다.

# NoahAI Client 공식 문서

당시 공개 버전: **v3.9.1.44** · updater **3.9.144** · stable/latest.  
설치기·blockmap·`latest.yml`·`release-manifest.json` 게시가 확인됐습니다. 특수 Windows 환경·기관별 실계정·장시간 운용 검증은 공개 배포와 분리해 계속 관리합니다.

당시 소스 후보: **v3.9.1.41** · updater **3.9.141** · **Windows 새 빌드·게시 미완료**. [v41 시장 트렌드/XAI 검증 계획](V39141_MARKET_TREND_XAI_TEST_PLAN.md). [PnL 재감사](V39139_PNL_TRUST_AUDIT.md)에서 주문 소유권·실계정 미완료 게이트를 확인하세요.

## 현재 제품·서비스 정본 (2026-09-18)

v41에는 시장 트렌드/XAI 외에 KPI 경량화와 내 PC 원격 상태·신규 제출 일시정지 베타를 포함합니다. [진행·배포 게이트](V39141_REMOTE_KPI_IMPLEMENTATION_PLAN.md) · [원격 사용 가이드](REMOTE_MANAGEMENT_GUIDE_V39141.md) · [소스 검증 보고](../reports/v39141-remote-kpi-verification.md). 운영 데이터 이관과 Windows 배포는 미완료입니다.

NoahAI Client는 검증을 마치고 무료·유료 서비스 중입니다. Strategy Studio는 현재 제공 중이고, Strategy Hub는 무료 공개 테스트 중입니다. 코인·증권·ETF를 제공하며 생활금융은 현금흐름·목표·보안 경고·세금 계산·금융상품 비교부터 단계적으로 제공합니다. 유료 전략 Marketplace와 결제·정산은 아직 별도 후속 단계입니다.

[v3.9.1.38 검증·배포 원장](V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md) · [과거재생 계약](STRATEGY_REPLAY_VISUALIZATION_20260917.md) · [거래내역 계약](SOURCE_TRADE_HISTORY_20260917.md)



## 이전 버전 기록 · v3.9.1.34 검증 후보

당시 소스 후보 버전: **v3.9.1.34** · 현재 공개 안정판: **v3.9.1.33**. 제품 3.9.1.34 / updater 3.9.134입니다. 키움 x86 호스트 분리·패키지 포함·PE/SHA 검증과 릴리스 채널 정책을 강화했습니다.

[v3.9.1.34 검증 게이트](V39134_KIWOOM_X86_RELEASE_INTEGRITY_TEST_PLAN.md). 외부 게이트 미완료 게시물은 prerelease이며 안정판 v3.9.1.33과 자동 업데이트 채널을 변경하지 않습니다.

## v3.9.1.32 소스 후보 · 공개 v3.9.1.31

v3.9.1.32는 국면 재선정 대기를 실제 변경 알림과 분리하고, 저장한 업데이트 확인 주기를 앱 공통 타이머로 실행합니다. Coinone의 미제공 활성 상태를 중단으로 오해하던 후보 수집을 수정하고, KIS·미래에셋의 주식/ETF 목록을 공식 공개 마스터로 분리합니다. 네 증권사 워커의 후보 없음·분석 완료·오류를 해당 기관 로그로 전달합니다. 주문 권한·TP/SL·점수 없는 진입 차단은 유지합니다.

[근본 원인·회귀·배포 게이트](V39132_RUNTIME_RECOVERY_TEST_PLAN.md)

## 이전 문서 인덱스 (당시 기준)

> 기준: 2026-09-14 · v3.9.1.31 소스 후보 · 공개 v3.9.1.30 Windows 자산 보존  
> 이 파일은 문서 진입점입니다. 현재 상태는 아래 정본 문서로 판단하고, `docs/archive/`와 `data/**/reports/`는 제품 설명 정본으로 사용하지 않습니다.

> UI-neutral 엔진과 Web 컴포넌트의 소스 연결은 기존 화면·동작의 1:1 완료를 뜻하지 않습니다. 현재 제품 기능 원장 35개는 모두 소스 연결 상태이며 `source_connected_parity_open` 32개, `source_connected_external_e2e_open` 3개입니다. 완료 판정은 `WEB_UI_1_TO_1_PARITY_EXECUTION_PLAN_v3.9.1.0.md`의 모든 필수 행이 `[x] VERIFIED`인지로만 판단합니다.

## 먼저 읽을 문서

| 목적 | 정본 |
|---|---|
| 전체 문서 지도 | `MASTER_DOCUMENTATION.md` |
| 버전별 변경 | `CHANGELOG.md` |
| v3.9.1.41 시장 트렌드 그래프·근거형 XAI 검증 | `V39141_MARKET_TREND_XAI_TEST_PLAN.md` |
| v3.9.1.39 외부 청산 체결·손익 복구 검증 | `V39139_EXTERNAL_CLOSE_RECONCILIATION_TEST_PLAN.md` |
| v3.9.1.38 전략 과거재생·기관별 거래내역 검증 | `V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md` |
| v3.9.1.31 메뉴얼 정합·가독성 배포 점검 | `DEPLOY_CHECKLIST.md`, `tests/test_v39128_version_and_quick_start.py` |
| v3.9.1.30 통계·시간봉·UI·증권 연결 검증 | `V39130_STRATEGY_VENUE_CONSISTENCY_TEST_PLAN.md` |
| v3.9.1.29 전략 공용계층·운용용량·Coinone 검증 | `V39129_FAIR_STRATEGY_COMMONS_POSITION_CAP_COINONE_TEST_PLAN.md` |
| Marketplace 유료화·포인트·결제·수수료·정산 | `STRATEGY_MARKETPLACE_POINTS_AND_LICENSE_PLAN.md` |
| 과거 버전별 릴리스 원장 | `archive/release/` (현재 상태 판단에 사용하지 않음) |
| 거래소·증권사 온보딩 완료 기준 | `ARCHITECTURE.md`, `EXCHANGE_SEPARATION_GUIDELINES.md`, `BROKER_EXPANSION_ROADMAP.md` |
| 사용자 사용법 | `USER_GUIDE.md` |
| 레퍼럴 신청·승인·연결·귀속·등급 제한 | `daltrading/REFERRAL_MEMBERSHIP_OPERATIONS_20260727.md` (관련 저장소 정본) |
| 앱 안의 쉬운 설명 | 레거시 정본 `ui/widgets/user_manual_widget.py` → 빌드 산출 `USER_MANUAL_SECTIONS.json` → Web `ManualCenter` |
| 개발 계획·완료/미완료 | `UPDATE_PLAN.md` |
| 기술 구조·책임 경계 | `ARCHITECTURE.md` |
| UI 플랫폼 전환 단계·백업·롤백 | `UPDATE_PLAN.md`의 2026-08-13 UI 플랫폼 전환 계획 |
| 레거시/새 UI 디자인 기준 | `UI_DESIGN_GUIDE.md` |
| 거래 실행 흐름 | `TRADING_FLOW.md` |
| 개발 규칙 | `DEV_GUIDE.md` |
| 빌드 | `BUILD_GUIDE.md` |
| 배포 전후 점검 | `DEPLOY_CHECKLIST.md` |
| 최신 테스트 근거 | `TEST_STATUS.md` |
| Web UI 현재 완성/배포 판정 | `WEB_UI_1_TO_1_PARITY_EXECUTION_PLAN_v3.9.1.0.md` |
| Web UI 구조 이전 현황 요약 | `WEB_UI_MIGRATION_STATUS_v3.9.1.0.md` |
| 로그인부터 5개 서비스·설정·매뉴얼 전체 1:1 실행 원장 | `WEB_UI_1_TO_1_PARITY_EXECUTION_PLAN_v3.9.1.0.md` |
| Web UI 테스터 실행 절차 | `WEB_UI_TESTER_RUNBOOK_v3.9.1.0.md` |
| v3.9.0.9 설정·탭·종료 반복 장애 근본 원인 | `archive/history/INCIDENT_260812_V3909_UI_SETTINGS_ROOT_CAUSE.md` |
| v3.9.0.10 설정·탭 렌더·프라이빗 전략 관리 | `archive/history/INCIDENT_260813_V39010_SETTINGS_TAB_STRATEGY_MANAGEMENT.md` |
| Fix 2 업데이트 상태 머신 근본 원인 | `archive/history/INCIDENT_260811_V3908_FIX2_UPDATER_UI_ROOT_CAUSE.md` |
| 활성 소스·격리 정본 | `SOURCE_QUARANTINE_MANIFEST_20260801.md` |
| v3.9.0.5 거래·AI·설정 통합 감사 | `INTEGRATED_AUDIT_v3.9.0.5_20260731.md` |
| v3.9.0.5 설정 정본·실행 모드 | `SETTINGS_REFERENCE_v3.9.0.5.md` |
| AI 엔진/API 사용자 사용법 | `AI_API_USER_GUIDE.md` |
| AI Provider 기술 정본 | `AI_API_ARCHITECTURE.md` |
| v3.9.0.3 AI 엔진 확장 범위 | `AI_ENGINE_EXPANSION_PLAN_v3.9.0.3.md` |
| AI 커스텀·어시스턴트 수동 QA | `AI_CUSTOM_ASSISTANT_TEST_RUNBOOK_v3.9.0.2.md` |
| AI 커스텀 핵심 고도화·시장 검증 | `AI_CUSTOME_UPDATE_PLAN.md` |
| Strategy Studio 마스터 플랜 | `NOAHAI_STRATEGY_STUDIO_MASTER_PLAN.md` |
| Strategy Studio 제품 로드맵 | `AI_CUSTOM_STRATEGY_OS_PRODUCT_ROADMAP.md` |
| 기술 백서 | `NOAHAI_TECHNICAL_WHITEPAPER.md` |
| 사업 설명 | `BUSINESS_PROPOSAL_2026.md` |

## v3.9.1.0 Web UI 전환 기록 · 현재 배포 판정 아님

v3.9.1.0은 `web_platform/`의 계정 범위 Application Services/Gateway, UI-neutral `HeadlessTradingRuntime`, `webui/`의 React/Vite·Electron을 연결한 전환 기준선입니다. 당시 1:1 화면·동작·Windows E2E가 닫히지 않아 `pending_windows_rebuild`였다는 기록은 보존하지만, 현재 공개판은 v3.9.1.30이고 소스 후보는 v3.9.1.31입니다. 현행 배포 신원은 `deploy/release-manifest.json`과 `V39130_STRATEGY_VENUE_CONSISTENCY_TEST_PLAN.md`, 환경별 남은 검증은 `TEST_STATUS.md`를 따릅니다.

## v3.9.0.10 AI 커스텀 관리·런타임 무결성

v3.9.0.10은 3.9.0.9 기능을 유지하면서 설정 `copy` 회귀, 최신 탭 렌더 병합·위젯 소유권 검사, 프라이빗 전략 수정본/비활성 삭제 관리를 추가한 중요 패치입니다. Windows 새 빌드 전 상태는 `pending_windows_rebuild`입니다.

## v3.9.0.9 AI 커스텀 고도화·안정화

- Noah Strategy IR·원본 근거·Level 1/2/3·초보자/일반/고급/실험실 프로필
- PnL·MDD·월/연도 표, 백테스트 최소 필터와 PAPER 전진검증 분리
- Expression Graph·제한형 사용자 지표·.noahstrategy·품질/감사·서명 webhook 게이트
- 대시보드 매뉴얼과 AI 어시스턴트 제품 지식 동기화
- Windows 설치본·실제 TradingView/webhook·장시간 PAPER/LIVE는 `pending_windows_rebuild` 및 외부 검증 전

## v3.9.0.7 레퍼럴 귀속 권한

- 사용자별 거래소 UID 제출과 운영자 `verified` 판정을 daltrading에서 관리
- 레퍼럴 허용 거래소는 `전역 활성 ∩ 사용자별 verified`
- NoahAI 설정의 미승인 API 입력·거래소 선택과 실행 시작을 fail-closed 차단
- 유료 등급은 레퍼럴 귀속 게이트 면제
- Windows 자산과 운영 Affiliate E2E는 `pending_windows_rebuild`

## v3.9.0.7 Fix Patch 3 Windows 네이티브 런타임 보강

- PyQt5·Kiwoom은 유지하고 중첩/구형 `MSVCP140*.dll`/`VCRUNTIME140*.dll`만 수집에서 제거
- 공식 VC143 x64 단일 세트의 ONNX 링커 하한·버전 통일·필수 DLL·완성 EXE SHA-256 검증
- RapidOCR/ONNX를 실제 차트 OCR 요청 시점까지 지연 로드
- Windows EXE·SHA-256·설치·제보 PC 검증 전까지 `pending_windows_rebuild`

## v3.9.0.7 Fix Patch 2 안정성 보강

- 로그인·상태 응답 로그에서 이메일·세션 ID·토큰·UID·레퍼럴 코드/URL 원문 제거
- 회원등급·정책 버전·허용/귀속 건수만 allowlist 요약으로 기록
- Windows 활성 로그 직접 삭제를 제거하고 25MB 회전·7개 백업·14일 보관 통일
- 이전 실행 PID 확인을 `psutil.pid_exists()`로 처리
- 설정창 진단 기본 접힘·하단 버튼 우선 배치·생성 완료 후 모달 잠금으로 빈 화면과 강제 재시작 방지
- Windows EXE·SHA-256·설치 검증 전까지 `pending_windows_rebuild`

## v3.9.0.5 Fix Patch 5 최종 정합 소스

- 거래소 계좌 표시를 현물 `보유자산`과 선물 `포지션`으로 분리하고 빈 상태·오류·캐시를 각각 표시
- PAPER 엔진의 분리된 가상 포지션을 표시하고 `PAPER`·가상 미실현 PnL·실잔고 미사용으로 LIVE 계좌와 구분
- Binance 실시간 포지션 정본, Bithumb 주문 ID 체결 복구, CCXT 확정 체결 원장 유지
- 증권 4개 공식 계약·설정 이전·어댑터·LIVE AND 권한 완성
- 대시보드 정의 전용 메서드 23개와 레거시 테마 소스를 복구 가능한 외부 격리로 이동
- `scripts/active_source_audit.py`, `verify_build_includes.py`, 전체 pytest, 문서 정합 검사를 배포 전 게이트로 사용
- Windows 신규 EXE는 아직 생성하지 않았으며 manifest는 `pending_windows_rebuild`

## v3.9.0.5 Update Patch 1 기반 변경

- Bybit가 최신 설정 대신 이전 PAPER 상태로 시작하던 런타임 설정 동기화 누락 수정
- Bithumb의 정상 `closed` 체결 판정과 앱 거래 기록·통계 연결 수정
- 모든 지원 암호화폐 거래소의 새 주문 실제 체결 원장 기록과 NoahAI 완료 거래 통계 분리. 과거·수동 가져오기는 거래소 기능 상태를 표시
- 주식/증권·자산 통합 화면 복귀 후 거래소 잔고 UI 갱신 큐 복원
- 거래소별 전역 읽기 조회 병합, UI 큐 1,024개 상한·최신값 병합
- 앱 실행 약 15초 뒤 최초 자동업데이트 확인, 이후 설정 주기·수동 확인, 동일 버전 Fix Patch SHA 감지
- 인증서 없이 GitHub HTTPS + manifest SHA-256 필수 검증. 무서명 Windows 평판 경고 가능성은 별도 안내
- 현재 공개 Fix Patch 1 EXE와 Update Patch 1 재빌드 대상을 배포 manifest에서 명시적으로 분리

- 설정 정본·LEARNING/PAPER/LIVE·분석 범위와 실주문 권한·레거시 정리: `SETTINGS_REFERENCE_v3.9.0.5.md`
- AI 제공사: OpenAI·DeepSeek·Anthropic Claude·Google Gemini·Kimi 정식 선택 및 작업별 Provider/모델 배치
- 사용자 설정: API 키 보안 저장, 작업별 `{provider, model}`, 기존 문자열 자동 이전, 동적 모델 목록, 기준일 가격·공식 링크
- 모델 안전: 권장·계정 확인·미리보기·비권장·종료 구분, 종료/capability 불일치 저장 차단
- AI 커스텀 전사: 분석 Provider와 독립된 OpenAI transcription 프로필, 다중 화자 모델 선택
- 실연결 검증: 설정의 `실제 API 기능 검증`과 Windows 후보 빌드의 테스터별 Provider 키 E2E
- 주문 범위: 화면·분석·학습과 실제 주문 거래소 분리, 명시적 빈 주문 목록은 주문 0개
- 안정성: 숨은 탭 callback/API 조회 중지, 완료 작업 정리, UI 로그 회전
- 업데이트 P0: 포지션·주문 사전점검, TP·SL 또는 청산 체결 확인, manifest SHA-256, 영속 저널, health check·자동 복원·거래 재개 잠금
- 비용 제어: 시장분석 15분 상태 캐시·영속 호출예산, 포지션 크기 15분 캐시, 손실패턴 5분 캐시, 실패 120초 쿨다운
- 자산 후보: 거래소 지원 마켓 fail-closed, KOSPI·KOSDAQ·ETF 거래대금 우선·자산 모드별 균형 후보
- 검증: 전체 `1,200 passed, 6 skipped`; Windows 서명본·실제 API 키·거래소 실연결·장시간 실행 결과는 소스 회귀와 별도로 확인
- Teayu_02 운영 준비 상태: 암호화폐 6개 거래소와 AI Provider는 인증·IP·키 재입력 게이트 미통과
- Teayu_02 keyring·Binance 로딩·비정상 종료 조사: `archive/history/INCIDENT_260729_TEAYU_02.md`
- 사용자 안내: `AI_API_USER_GUIDE.md`, `USER_GUIDE.md`, 앱 `사용자 매뉴얼 → 업데이트`
- 기술 정본: `AI_API_ARCHITECTURE.md`, `AI_ENGINE_EXPANSION_PLAN_v3.9.0.3.md`

## v3.9.0.2 AI 커스텀·레퍼럴·거래 통계 고도화

- 회원 운영: `레퍼럴` 무료회원, 서버 관리형 해외 제휴 거래소 정책, 동시 실행 거래소 KPI
- 레퍼럴 통합 운영 정본: `daltrading/REFERRAL_MEMBERSHIP_OPERATIONS_20260727.md` — 거래소별 신청·링크 발급, NoahAI 연결, UID 귀속 확인, 현재 강제 범위와 P0 보완
- 처음 사용: 앱 `AI 커스텀 → 처음 사용법 AI에게 묻기`
- 결과 설명: 앱 `AI 커스텀 → 이 결과 AI에게 묻기`
- 실행 범위: SMA/EMA 20·50·200, ADX, ATR, 실제 Pine 교차, 비용 반영 검증, 코인 명시 청산
- 어시스턴트 안전: 허용 설정 최종확인, 저장 재검증, 사용자별 감사로그, 보호 작업 미실행
- 화면·사용법: 공통 기능 탭 스킨, 금융 인텔리전스 초보자 절차·AI 질문, 거래 통계 단일 스크롤
- 운용 지표: 거래 통계·AI 리포트의 통화별 실제 체결금액과 검증 가능한 평균 보유시간
- 최신 검증: 전체 `1,079 passed, 6 skipped`, daltrading `20 passed`, 문서 정합성 PASS
- 배포 경계: Windows 신규 EXE·실화면, 실제 YouTube URL, 실계좌 장시간 검증은 남음
- 구조·국면 추천·안전 경계: `AI_CUSTOM_STRATEGY_ARCHITECTURE.md`
- 대화형 전략·초보자 프리셋 후보: `AI_CUSTOM_CONVERSATIONAL_PRESETS_PLAN_v3.9.0.3.md`
- 사용자 사용법: `USER_GUIDE.md`, `AI_ASSISTANT_GUIDE.md`
- 테스트 순서·QA 계정 규칙: `AI_CUSTOM_ASSISTANT_TEST_RUNBOOK_v3.9.0.2.md`
- Strategy IR v1·Level 1/2/3 사용자 시험과 피드백: `AI_CUSTOM_FEATURE_TEST_AND_FEEDBACK_GUIDE_20260809.md`
- 완료·후속 범위: `UPDATE_PLAN.md`

## v3.9.0.1 금융 인텔리전스

- 사용자 동선: `USER_GUIDE.md`와 앱의 `사용자 매뉴얼 → 금융 인텔리전스`
- 기능·메뉴·데이터 상태: `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md`
- 검증 범위: `FINANCIAL_INTELLIGENCE_TEST_CHECKLIST_20260723.md`
- 릴리스 준비: `BUILD_GUIDE.md`, `DEPLOY_CHECKLIST.md`, `TEST_STATUS.md`

## 기능별 상세 정본

| 영역 | 정본 | 보충 |
|---|---|---|
| AlphaArena | `ALPHA_ARENA_DEVELOPMENT.md` | 과거 설계·검토본은 `archive/alpha_arena/` |
| 코인 선정 | `COIN_SELECTION_GUIDE.md` | 실행 흐름은 `TRADING_FLOW.md` |
| 대시보드 잔고·포지션 | `DASHBOARD_POSITION_SYSTEM.md` | 과거 UI 초안은 `archive/dashboard/` |
| 증권·ETF | `STOCK_ETF_IMPLEMENTATION_STATUS_20260423.md` | 테스트는 `STOCK_ETF_TEST_CHECKLIST_20260118.md` |
| AI 커스텀 | `AI_CUSTOM_STRATEGY_ARCHITECTURE.md` | 고도화 결정은 `AI_CUSTOME_UPDATE_PLAN.md`, 제품 단계는 `AI_CUSTOM_STRATEGY_OS_PRODUCT_ROADMAP.md` |
| 금융 인텔리전스 | `FINANCIAL_INTELLIGENCE_EXPANSION_PLAN_20260723.md` | 검증 체크리스트와 함께 사용 |

## 실행과 빌드

개발 환경에서 실행:

```bash
python3 main.py
```

안전 빌드:

```bash
python build_safe.py --platform windows
python build_safe.py --platform macos
python build_safe.py --platform linux
```

Windows 공식 배포물은 Windows 빌드 환경에서 생성합니다. 현재 공개된 v3.9.0.5 Fix Patch 1 EXE는 이전 공개 자산으로 보존하고, 이번 Fix Patch 5 소스 manifest는 `pending_windows_rebuild`입니다. 새 EXE의 크기·SHA·서명·설치·로그인·자동업데이트 E2E를 검증한 뒤 Fix Patch 5로 배포합니다.

## 문서 관리 규칙

- 같은 주제의 새 Markdown을 만들지 말고 위 정본에 통합합니다.
- 완료 보고, 일회성 분석, 과거 검증, 동기화 충돌본은 `docs/archive/`에 보관합니다.
- 이전 릴리스 체크리스트는 `archive/release/`, 문제 분석·완료 보고는 `archive/history/`에서만 조회합니다.
- `data/**/reports/*.md`는 런타임이 만든 분석 산출물이며 공식 제품 문서 수에 포함하지 않습니다.
- 사용자 체감 변경은 `CHANGELOG.md`, `UPDATE_PLAN.md`, `USER_GUIDE.md`, 인앱 매뉴얼을 함께 맞춥니다.
- 구현 여부는 코드와 테스트를 먼저 보고, 사업 문서나 과거 계획 문서만으로 판단하지 않습니다.

세부 정책은 `DOCUMENTATION_POLICY.md`를 따릅니다.

- [3.9.2.11 생활·투자 통합 자산관리 재점검과 후속 개발](V39211_WEALTH_MANAGEMENT_AUDIT.md)
