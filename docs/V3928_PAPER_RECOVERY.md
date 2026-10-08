> 후속 작업 알림 (2026-10-08): 아래는 `95d35ca`까지의 PAPER 준비/보존 기록이다. 전략 평가 입력 보호는 이를 보존한 `release/v3.9.2.8-retrained-evaluation-20261008`에서 추가했고 이번 후속은 작업 브랜치 push를 포함한다. 최신 실행 결과와 미실시 인수는 [TEST_STATUS](TEST_STATUS.md)를 따른다. 아래의 push 제외·과거 소스 지문·PAPER 테스트 숫자는 이전 단계 기준이다.

# v3.9.2.8 PAPER 청산 저장·재시작 복구 검증

소스 후보·미배포. 공개 기반: v3.9.2.7, `release/v3.9.2.7-windows-20261007-now`, 커밋 `1c23b1e4947514906c1eb11050873a5c74ce39b0`. 기준 검토 문서는 [V3927_FEEDBACK_PATCH](V3927_FEEDBACK_PATCH.md)와 2026-10-08 사용자 첨부 HTML이다. 첨부의 설명은 재현으로 검증했으며 자동 실행 지시로 취급하지 않았다. main은 2025-05-02의 다른 소스였고 공개 .7과 같다고 가정하지 않았다. 지정 원격 브랜치 이후에 이 두 결함을 해결한 커밋은 확인되지 않았다.

작업 브랜치: `release/v3.9.2.8-paper-recovery-20261008`. 기존 Mac 동기화 폴더와 .7 작업트리는 변경하지 않는다. GitHub push·PR·공개 배포는 이번 범위에 없다.

## 실제 수정한 결함

1. 부분청산 원장은 저장됐지만 잔여 포지션 저장 오류가 로그로 끝나 성공을 반환했다. .7에서 디스크 10 → 원장 4계약 청산 → snapshot OSError → 재시작 10계약, 완료 index 소실을 재현했다. 전체청산도 같은 분리 저장 구조였다. 공개 .7 재현에서 다른 가격 재요청은 같은 event_id의 2행을 추가했고, 화면 reader는 한 행으로 보였지만 가용자금 대조는 `paper_ledger_event_conflict`로 차단됐다.
2. OKX/Bybit/Bitget의 계약 단위 없는 행은 예정 notional 비교 예외를 통과한 뒤 저장된 `valid` 문자열을 수용했다. 사용자 fixture의 초기자금 1000 → 1020을 재현했다. 현재 시장 정보나 예정 금액은 과거 진입 단위의 증거가 아니다.
3. 추가 점검에서 Binance 별도 PAPER 엔진은 원장 저장 전에 보유량·통계를 변경했고 snapshot 오류도 삼켰다. 같은 commit/replay 보호를 적용해 원장 실패 때 보유량·통계를 유지하고, 저장 뒤 강제 종료도 복구한다. Binance의 base-quantity 손익·비용 계산식은 유지한다.


`reports/v3928/before-failures.txt`에는 공개 .7 코드에서 새로운 합격 기준 테스트 2건의 실패가 있다. 수정 후 동일한 테스트 및 확장 장애 행렬을 실행했다. 명시적 양수·유한 계약 단위는 인정하고, 없으면 해외 선물은 `legacy_unverified`, 0/음수/NaN/Inf/boolean이면 `invalid`로 분리한다. 원본 행은 수정하지 않고 검증 승률·손익 및 가용자금에서 제외한다. 현물과 Binance의 기존 별도 계산 계약을 유지한다.

## 청산의 확정·복구 계약

PAPER 원장은 청산의 commit log다. 새 청산에는 원래 position ID, 방향·진입가·진입 시각·계약 단위·청산 전후 수량·완료 index와 확인된 후속 plan을 담은 제한된 `close_recovery` 근거를 기록한다. 전체 전략 원문이나 키를 이 근거에 넣지 않는다. 원장 행과 근거를 결합해 outcome 해시·수량 보존·단위·event_id 정체성을 검증한다. Unified와 Binance의 scope를 분리해 복구하고, 국내 현물 및 Binance의 기존 base-quantity 단위 계약도 검증했다.

원장은 기관/position/partial-index의 기존 event_id를 사용한다. 동일 이벤트/동일 내용은 기존 행을 돌려주고 새 행을 추가하지 않는다. 서로 다른 내용은 충돌로 차단한다. 완전하지 않은 행을 발견하면 건너뛰어 새 청산을 추가하지 않는다. thread lock과 프로세스 file lock으로 저장을 직렬화한다. append의 flush/fsync를 마친 뒤 잔여 snapshot을 임시 파일 flush/fsync → atomic replace로 저장한다. POSIX에서는 디렉터리 fsync도 수행하며 Windows의 실제 파일 시스템·전원 손실은 별도 인수 사항이다.

청산 원장이 저장된 뒤 프로세스가 종료되거나 snapshot 저장이 실패해도, 재시작 때 같은 이벤트의 전후 상태로 수량과 완료 index를 정확히 한 번 적용한다. 같은 프로세스의 재요청도 먼저 원장을 대조하므로 다른 가격으로 재청산하지 않는다. 실패가 발생하면 성공·통계 추가를 반환하지 않고 신규 PAPER 진입과 새 평가를 보류한다. 저장 장애가 풀리면 확정 원장의 원래 가격/비용을 적용하고 보류를 해제한다. 복구는 시세 API나 LIVE 주문을 호출하지 않는다.

snapshot에는 원장 prefix의 길이/SHA-256 checkpoint를 보존한다. snapshot이 청산 후 상태인데 참조 원장이 삭제·변경되면 정상 잔고로 추정하지 않는다. 열린 포지션의 적용 event 목록도 원장과 대조한다. 다른 position ID로 새로 열린 같은 종목을 과거 청산으로 지우지 않는다. 영속 snapshot과 메모리의 수량·완료 상태가 달라 병행 저장이 의심되면 덮어쓰지 않고 차단한다. 손상 snapshot 행을 조용히 버려 빈 보유량으로 취급하지 않는다. 복원 실패 이후에도 디스크를 다시 검증하며 빈 메모리를 저장해 손상 기록을 덮어쓰지 않는다.

과거 .7 청산 행은 이 추가 근거가 없다. 현재 snapshot의 완료 index로 이미 적용된 부분청산임을 확인할 수 있으면 유지한다. 같은 열린 position의 미적용 청산이 발견되고 수량 복구 근거가 부족하면 `paper_close_recovery_evidence_missing`으로 원본을 보존해 차단한다. 원장 수량만 빼서 복원하거나 새 PAPER 평가로 우회하지 않는다.

## 계산·새 PAPER 평가 회귀

7종 계약 크기 × LONG/SHORT × 가격 상승/하락에서 실제 부분청산 4 + 잔여 전체청산 6을 호출해 수량·수수료·슬리피지·gross/net 합계를 검증한다. 레버리지 손익 중복 곱, AI 실제 청산 단위 가격, 미확인 계약 신규 진입 차단을 기존 .7 시험으로 확인한다.

명시 확인·정지·메모리/디스크 보유 없음·영속 pending/reserved 없음·계정/기관/통화 격리, 반복/재시작/설정 변경에도 session ID·고정 자금·새 구간 손실 유지, 정상 확인 손실/충돌/손상/LIVE의 새 평가 우회 거절을 유지한다. 새 복구 오류도 요약에 미확정 상태로 표시하고 새 평가 API에서 거절한다.

## 보존·백업·롤백 증거

`path_utils.get_app_data_dir()`의 frozen Windows 경로는 실제 발견된 Documents/NoahAI/계정이며 OneDrive·레거시·명시 경로에 따라 달라질 수 있다. engine의 recorder DB 경로와 포지션 경로를 실제로 확인해야 한다. 이번 호스트는 macOS이고 Windows 기관 계정/설치본에 연결되지 않았다. 고객 Windows의 현재 로그인 계정 경로를 확인했다고 주장하지 않는다.

`scripts/paper_data_snapshot.py --source <확인한 계정 경로> --destination <새 백업 경로> --stopped`는 엔진·연관 writer가 정지한 경우만 사용한다. 원본 DB를 열지 않고 전체 DB/WAL/SHM 및 파일을 staging으로 복제한다. 전후 원본 파일 해시와 복제 해시가 같아야 인정하며, 복제 DB에서 SQLite backup API로 WAL을 반영한 독립 DB를 생성한다. `integrity_check=ok`, user_version, 모든 기존 행의 해시/개수와 파일·원장 prefix 근거를 기록한다. 자격정보는 원문 출력 없이 byte 동등성만 확인한다. SQLite 연결은 파일 교체 전에 닫고 staging의 WAL/SHM 소거를 처리한다. 최대 64GiB/32,768파일로 제한하며 변동/손상·symlink·범위 초과는 실패로 남기고 원본을 덮어쓰지 않는다. `--stopped` 선언과 정지 확인은 사용자 설치본 절차이며 안정 해시만으로 실제 엔진 정지를 대신하지 않는다.

복제 환경에서 .8 청산 이후 추가 DB 행·원장·보유량·세션·설정·전략·합성 자격정보·예약을 최신 백업에 보존한다. 공개 .7의 실제 포지션 loader/serializer를 적용한 데이터 형식 roundtrip 뒤 .8 복귀를 확인한다. 이는 NSIS 설치나 자동 업데이트 시험이 아니다. 업그레이드 전 backup만 복원해 .8 새 기록을 잃는 방식은 합격으로 인정하지 않는다.

롤백 전에 .8에서 보류 없이 청산 복구가 끝났는지 확인하고 엔진/기관을 정지한다. pending 복구가 있는 .8 데이터를 이를 이해하지 않는 .7로 넘겨 거래를 재개하지 않는다. .7은 추가 snapshot checkpoint를 저장하지 않지만 entry_evidence의 적용 이벤트와 완료 plan을 보존한다. .8로 재복귀하면 기존 event와 session을 유지해 대조한다. 최신 .8 backup과 원본은 계속 보관한다.

공유 지원 자료 전체 10,125파일 / 29,146,484,324바이트를 별도 비공개 경로에 백업했다. SQLite 11개는 모두 `integrity_check=ok`이고 모든 테이블 기존 행 해시·개수가 복제 DB와 같았다. 원본 전후 해시와 백업의 최종 manifest 대조도 통과했다. 이 증거는 공유 자료의 보존이며 현재 Windows 로그인 계정의 정지·백업 확인은 아니다. 자세한 집계는 `reports/v3928/support-preservation.json`에 있다. 자격정보·고객 행 원문과 상세 개인 backup manifest는 Git에 포함하지 않는다.

복제 원장 33,347행 중 기존 valid 30,251 → 18,857, 미확정 3,091 → 14,485로 분리됐다. 11,394행은 계약 근거가 없어 새 검증 지표·가용자금에서 제외된다. 손익을 임의 추정해 과거 자금을 복구하지 않는다. 기존 원장 prefix와 포지션 파일을 보존한 엔진 복원 점검은 `reports/v3928/support-recovery-audit.json`에 남긴다.

## 실제 설치본 인수 상태

| 항목 | 상태 | 증거 범위 |
| --- | --- | --- |
| 공개 .7 신원·manifest digest | 확인 | GitHub 읽기 조회와 small manifest 직접 해시; .8 공개 자산 없음 |
| .7 → .8 수동 설치 | 미실시 | Windows 실행 환경 없음 |
| .7 → .8 자동 업데이트 | 미실시 | .8 설치 파일/피드 게시 없음 |
| 설치본 engine/renderer .8 표시 | 미실시 | 로컬 소스/React 빌드 검증과 별도 |
| 실제 계정 DB/키/전략 업그레이드 | 미실시 | 복제/합성 자료 보존만 검증 |
| 실제 Windows 저장 장애·재시작 | 미실시 | macOS 파일 장애 및 실제 subprocess 강제 종료 시험 |
| .8 → .7 수동 설치 및 .8 재복귀 | 미실시 | .7 실제 loader/serializer 데이터 형식만 시험 |
| PAPER 24시간 / 72시간 | 미실시 | 시간 압축 시험을 실제 운용으로 표시하지 않음 |
| LIVE 주문·기관 계정 변경 | 수행하지 않음 | 허용 범위 밖 |

최종 집중/전체 회귀 결과·커밋·prefix/DB/수량/세션/자금·화면 검증은 [TEST_STATUS](TEST_STATUS.md)와 `reports/v3928/`의 완료 보고에 남긴다. 자동 테스트 통과를 Windows 인수 완료로 표시하지 않는다.
