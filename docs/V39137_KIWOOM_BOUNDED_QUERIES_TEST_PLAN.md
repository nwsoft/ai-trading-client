# v3.9.1.37 Kiwoom Bounded Queries & Session Recovery Patch

제품 3.9.1.37 / updater 3.9.137. 공개 기반 v3.9.1.36 stable/latest.
현재는 소스 후보이며 기존 공개 설치기·manifest·latest.yml은 교체하지 않습니다.

## 로그 근거와 수정 범위

- [사용자 로그 분석](V39137_KIWOOM_USER_LOG_ANALYSIS.md): 21:37:31 KST 종목 정보 RPC 이후 진행 중단, 21:39:04 수동 재연결 차단. 최초 TR 반환 코드/콜백은 기존 로그에 없어 서버 장애나 조회 제한을 단정하지 않습니다.
- pykiwoom의 무제한 TR 대기를 내부 제한시간으로 바꾸고 즉시 거부·파싱 실패·늦은 응답을 분리합니다. TR 간격 250ms, -200 응답 시 60초 조회 보류를 빠르게 반환합니다. 지연 중 재로그인/자동 주문 재시도는 하지 않습니다.
- 연속 opt10001 조회는 1초 이내 성공 응답만 공유합니다. 조회 실패를 종목명만으로 정상 반환하지 않고 공통 증권 분석의 오류를 유지합니다.
- 계좌 목록·잔고/보유종목/미체결 출력·거래내역 입력·ETF TR 계약을 수정하고 로그인 비밀번호를 계좌 조회에 전달하지 않습니다.
- 매뉴얼·업데이트 내역은 37 후보와 36/35 공개 이력을 분리합니다.

## 자동 검증

- [x] UPDATE-AUTO (2026-09-17): 업데이트 채널 수정 후 전체 Python **2,494 passed / 8 skipped / 3 subtests passed**, 실제 Provider 회귀 **4 passed**, 관련 집중 **51 passed**. 공개 서버 stable/latest→v36/latest.yml 200·정확한 설치기 URL 확인. Web 52 modules·문서·매뉴얼·구문 검사 PASS. 아래 AUTO 행은 키움 수정 직후의 이전 실행 기록입니다.

- [x] AUTO: macOS Python 전체 **2,491 passed / 8 skipped / 3 subtests passed** (기존 Starlette deprecation warning 1건). 키움·증권 분석·빌드 집중 **135 passed / 3 subtests passed**. 개발 릴리스 게이트 PASS (증권 176 passed / 6 skipped, 4기관 mock 경로).
- [x] WEB: Node **22.23.1** Web production **52 modules** 빌드, 문서 정합 PASS 및 11개 매뉴얼 정본 재추출. 500kB 초과 번들 경고는 남음. 초기 Windows용 node_modules의 macOS 선택 의존성 누락을 로컬 설치로 보완했으며 package-lock 계약은 변경하지 않음.

복합 조회는 RPC별 공통 제한시간을 공유하며 부모 RPC 제한 2초 전에 조회 대기를 종료하도록 했습니다. 부모 프로세스의 통신 실패도 자식 전용 환경변수 없이 진단 파일에 기록합니다. 조회 실패를 포함한 분석 주기는 정상 완료 문구 대신 경고와 최초 오류를 유지합니다.

## Windows / 실제 계정 필수 검증

- [ ] RELEASE-SOURCE: 비밀정보를 제외한 실제 37 빌드 입력을 검토·커밋·원격 게시. source_revision 및 Git/로컬/빌드 fingerprint 일치, 새 태그의 정확한 커밋 연결. 기존 36 이하 태그 불변.
- [ ] ROLLBACK: 37 설치 후 보존한 36으로의 운영자 수동 복구 절차와 사용자 설정·전략·원장 보존 검증. 자동 다운그레이드는 허용하지 않음.

- [ ] WIN-BUILD: x64 엔진·x86 NoahAIKiwoomHost.exe·설치기를 37 소스로 새 빌드. PE/리소스 버전/SHA/source fingerprint 확인.
- [ ] WIN-UPGRADE: v3.9.1.36→37 설치·자동 업데이트·종료·재시작·롤백. 기존 설정·전략·PAPER 원장 보존.
- [ ] UPDATE-CHANNEL: stale Atom 첫 항목과 무관하게 stable/latest→정확한 latest.yml→새 설치기를 선택. 공개 파일 누락/네트워크 장애 시 안전한 실패. 36의 채널 오류가 지속될 경우 37 공식 설치기를 통한 1회 수동 업데이트 검증. [업데이트 원인 분석](V39137_UPDATER_CHANNEL_INCIDENT.md).
- [ ] KIWOOM-E2E: 해당 Windows 환경에서 로그인→잔고/보유종목/미체결→8개 종목 정보/시세/일봉→PAPER 실행. 단일 호스트 유지, 중복 로그인 없음, 과부하/무응답 후 정상 조회 회복. 호스트 로그에 host_version=3.9.1.37, tr_submit/callback/complete 및 rpc_complete 확인. 장중·장외를 분리 확인.
- [ ] KIS-E2E: KIS·신한·미래에셋의 시세 실패 시 분석 오류, 정상 시 주식/ETF PAPER·일봉 전략검증 회귀.
- [ ] BITHUMB-E2E: 빗썸 기존 KRW PAPER·통계 회귀.
- [ ] RECONCILE-E2E: 주문 결과 불명확 차단 유지, 실제 주문 재전송 없음. LIVE/PAPER 원장 불혼입.
- [ ] SPOT-FUTURES-PAPER: 국내 현물·해외 선물 기존 PAPER 계약 회귀.
- [ ] REPORT-E2E: 매뉴얼/업데이트 내역 37/36/35 표시, 최초 조회 실패와 수동 재연결 상태 구분.
- [ ] SOAK: Windows 24시간 PAPER 운용. 호스트 재시작/중복 로그인 루프·계정 혼입·포지션 유실 없음.
- [ ] RELEASE: 위 결과를 기록한 새 v3.9.1.37 자산만 게시하고 원격 SHA·업데이트 경로 확인.

자동 테스트는 Windows OCX 및 사용자 계정 재현을 대체하지 않습니다. 원시 OCX 호출 자체의 멈춤은 외부 RPC 제한과 안전 차단 대상으로 남습니다.
