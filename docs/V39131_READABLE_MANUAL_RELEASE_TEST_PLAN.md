# v3.9.1.31 사용자 메뉴얼 정본·검색 검증·배포 계약

범위: 소개부터 업데이트까지 11개 인앱 메뉴얼 탭, 전역 본문 검색, Windows 설치·업데이트·DPI 렌더링, v3.9.1.30 거래·전략·기관 계약 비회귀. 현재 공개 기준은 v3.9.1.30이며 이 문서의 미완료 외부 게이트를 소스 검사로 대체하지 않는다.

- [x] VERIFIED SOURCE-CANONICAL: `ui/widgets/user_manual_widget.py`에서 `docs/USER_MANUAL_SECTIONS.json`을 다시 생성해 11개 고유 탭·전체 184,233자·정본 완전 일치·U+FFFD/깨진 로그인 문구 0건을 확인.
- [x] VERIFIED SOURCE-CURRENT: 제품 3.9.1.31/공개 3.9.1.30, 7개 코인 거래소·4개 증권사, Coinone LIVE 차단, AlphaArena PAPER 전용/LIVE 실패 폐쇄, Strategy Studio 동적 기관 필터·과거 시세 재생 용어를 현재 사용법과 대조.
- [x] VERIFIED SOURCE-SEARCH: 11개 탭 전체 본문 인덱스, 일치 항목별 이전/다음 이동, 정확한 `<mark>` 스크롤, 탭 전환 후 검색 위치 유지 계약을 집중 회귀로 확인.
- [x] VERIFIED SOURCE-REGRESSION: 전체 Python `2,300 passed, 8 skipped`, 로컬 Node 20.11.0 production build 51 modules, production 의존성 취약점 0건, 문서/버전 정합·Web 표면 계약 PASS. 릴리스 요구 Node 22.12+에서 Windows 산출물을 다시 빌드한다.
- [ ] WIN-BUILD: v3.9.1.31 설치기·engine·blockmap·`latest.yml`·manifest를 새로 만들고 제품/updater 버전, 파일 크기, SHA-256/SHA-512, source fingerprint를 같은 산출물 묶음으로 확정.
- [ ] WIN-UPGRADE / ROLLBACK: 공개 v3.9.1.30→v3.9.1.31 업데이트·재시작·롤백에서 API 자격증명, 설정, 거래/PAPER 원장, 전략 버전·시도, Strategy Studio 작성 중 초안 보존.
- [ ] MANUAL-WINDOWS-E2E: Windows 100/125/150/175% DPI와 최소 지원 너비에서 11개 탭의 제목·본문·표·카드·긴 기관/모델명이 잘림·겹침 없이 보이고, 전체 검색의 첫/이전/다음 결과가 정확한 탭·문장으로 이동.
- [ ] KIWOOM-E2E: 메뉴얼의 Windows OpenAPI+ 제약·연결 상태·실패 안내가 실제 Windows 키움 로그인/조회/프로세스 복구 결과와 일치.
- [ ] KIS-E2E: 메뉴얼의 KIS 권한·토큰 제한·주식/ETF 조회·PAPER/LIVE 경계가 승인 QA 계정 결과와 일치.
- [ ] BITHUMB-E2E: 현물 LONG·시간봉·비용·통계·연결 안내가 실제 공개 시세 및 승인 QA 계정 동작과 일치.
- [ ] RECONCILE-E2E: 거래소·증권사 체결과 NoahAI 원장의 대조 완료/미확정, gross/net PnL, 수수료·세금 의미가 메뉴얼 및 화면과 일치.
- [ ] REPORT-E2E: 거래 카드·기간 통계·AI 리포트가 동일한 기관·기간·실행모드·기준통화를 사용하고 메뉴얼 설명과 일치.
- [ ] SPOT-FUTURES-PAPER: 국내 현물 LONG, 해외 선물 LONG/SHORT, 주식/ETF PAPER의 기관·통화·전략 버전 분리와 재시작 보존을 확인하며 PAPER 주문 API 호출은 0건.
- [ ] SOAK: 대표 코인 거래소와 사용 가능한 증권 QA 환경에서 24~72시간 PAPER·화면 전환·메뉴얼 검색을 병행해 로그·UI 자원·원장·검색 상태가 누적 손상되지 않는지 확인.

## 배포 판정

- 소스 후보 생성은 허용한다.
- `WIN-BUILD`, `WIN-UPGRADE / ROLLBACK`, `MANUAL-WINDOWS-E2E`는 v3.9.1.31 공개에 필수다.
- 기관별 외부 계정 항목은 사용할 수 없는 계정을 성공으로 꾸미지 않고 `PENDING` 또는 정확한 미지원 상태로 남긴다.
- 필수 항목이 미완료이거나 설치 자산 fingerprint가 현재 소스와 다르면 stable 게시를 중단한다.
- 과거 버전 기록은 삭제하지 않되, 현행 사용법은 각 탭 상단과 최신 업데이트 항목을 우선한다.
