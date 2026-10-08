# NoahAI Client v3.9.2.8 수정·검증 완료 보고

소스 수정·로컬 검증·커밋 완료. Windows 설치본 인수는 미실시이며 공개 버전은 v3.9.2.7이다. GitHub push·PR·릴리스 게시 및 LIVE 주문·기관 계정 변경을 수행하지 않았다.

- 공개 기준: `release/v3.9.2.7-windows-20261007-now` / `1c23b1e4947514906c1eb11050873a5c74ce39b0`. 읽기 fetch로 확인했으며 해당 브랜치 이후 두 결함의 수정 커밋은 없었다.
- main: `bd2fe406ec3de3f185447cb7c14e8dddb37830a4` (2025-05-02). 공개 .7 소스와 달라 기반으로 사용하지 않았다.
- 별도 작업 브랜치: `release/v3.9.2.8-paper-recovery-20261008`.
- 수정 커밋: `7aeb12ea74c9d69a36681d044723de3c00d395b8`. 아래 검증 보고·로그는 후속 로컬 증빙 커밋으로 보존한다.
- 실제 작업트리: `/Users/playone/.codex/worktrees/noahai-v3928-paper-recovery`. 기존 동기화 작업 폴더와 .7 Git 작업트리의 기존 파일을 덮어쓰지 않았다.
- 제품·엔진 소스/Windows PE/화면: **3.9.2.8**; updater **3.9.208**; UI 빌드 **3.9.2.8-ui.20261008.1**. 설치 engine의 버전 확인은 미실시다.
- Windows 릴리스 입력 소스 지문: `26f1a004684dd65449f6c6b6d877ede21df29fcd2a2142a29ef6bbf689c9f3cf`. 실제 빌드한 renderer의 source hash·version·현재성은 [renderer-identity.json](renderer-identity.json)에 있다.

## 수정 전 실패 → 수정 후 통과

| 결함 | 공개 .7의 실제 재현 | .8 결과 |
| --- | --- | --- |
| Unified 부분청산 원장 4계약 저장 뒤 snapshot OSError | 성공 True; 메모리 6 / 디스크·재시작 10; 완료 index 소실. 110 → 120 재요청은 동일 event_id 2행을 남겼고 자금 대조에서 conflict | 성공 False/보류; 재시작 6·완료 index 0; 원래 110 청산 1행만 유지. 재요청·반복 복구로 수량/손익/마진 중복 없음 |
| 해외 선물 계약 단위 없음, 저장된 valid 문자열 | 사용자 합성 행 valid / 초기 1000 → 가용 1020 | 원본 그대로 legacy_unverified. 검증 승률·손익에서 제외하고 가용자금 미확정으로 진입 보류 |
| 추가 Binance 별도 PAPER 저장 순서 | 원장 실패에도 보유량 제거·성공 통계 1; snapshot 실패에도 메모리/디스크 불일치 | 원장 확정과 보유 snapshot 저장 후 성공 처리. 실패·실제 강제 종료·가격 변경 재요청의 단 한 번 복구 |
| 손상 snapshot 복원 실패 후 빈 메모리 저장 가능성 | 공개 .7 복원 실패 뒤 _persist가 손상 파일을 빈 보유 자료로 덮어씀 | 디스크 재검증 실패를 유지하고 빈 보유량으로 덮어쓰지 않음. 신규 PAPER·새 평가 우회 거절 |

[기준 .7의 두 실패 테스트](before-failures.txt), [수정 전 구조화 재현](before-reproduction.json), [수정 후 재현](after-reproduction.json), [Binance 수정 전](binance-before-reproduction.json) / [수정 후](binance-after-reproduction.json). [손상 snapshot 수정 전](corrupt-snapshot-before.json) / [수정 후](corrupt-snapshot-after.json)도 보존했다. 다른 가격의 중복은 .7 close 함수 자체의 반환 실패가 아니라 실제 원장 2행 및 자금 대조 conflict로 재현됐다.

복구는 `close_recovery` 전후 수량/완료 상태, outcome digest, event_id, 원장 prefix checkpoint를 검증한다. 저장 오류만 반환하고 끝내지 않고 같은 프로세스·재시작에서 이미 확정된 청산을 먼저 적용한다. 적용 근거가 부족한 .7 기록·손상·충돌은 원본을 보존해 차단한다. 현재 시장 정보·예정 notional로 과거 단위를 추정하지 않는다. [상세 설계·기존 사용자 처리](../../docs/V3928_PAPER_RECOVERY.md).

## 회귀 및 실제 화면

| 검사 | 결과 | 증거 |
| --- | --- | --- |
| 집중 계산/청산/세션/보존 | **171 passed**, 실패 0 | [focused-final](focused-final.txt) |
| 전체 Python | **5,522 passed / 11 skipped / 3 subtests passed**, 실패 0 | [full-final](full-final.txt) |
| Node/Electron | **79 passed** | [node-final](node-final.txt) |
| TypeScript/Vite 빌드 | PASS; 기존 chunk 크기 안내 1건 | [build](webui-build.txt) |
| 실제 빌드 renderer, API 완전 대체 fixture | **43 checks PASS**, page error 0 | [결과](ui/result.json), [복구 보류 화면](ui/close-recovery-capital.png) |
| 문서·소스·동기화·parity·엔진 spec | PASS | [docs](docs-final.txt), [source](source-audit.txt), [sync](sync-final.txt), [parity](parity-final.txt), [engine spec](engine-spec-final.txt) |

부분·전체청산 모두 원장 실패/원장 후 snapshot 실패/두 저장 사이 실제 `os._exit`/재시작/같은·다른 가격 재요청/복구 반복을 검증했다. 파일 교체 실패·교체 후 fsync 실패와 torn/conflict/해시 변조도 포함했다. 계약 0.01/0.1/1/10/100/1000/100000 × LONG/SHORT × 상승/하락의 실제 4+6 청산, 동일 단위의 가치·손익·비용, 레버리지 중복 곱 방지·AI 실제 가격·미확인 신규 진입 보류를 유지했다. 국내 현물과 Binance의 base-quantity 청산도 별도로 통과했다.

명시 확인·기관 정지·메모리/디스크 보유·영속 예약 없음·계정/기관/통화 격리, 재시작/반복 클릭/설정 변경 후 평가 구간·확인 손실 유지, 손상·충돌·미확정 주문·LIVE 우회 거절을 유지했다. 복구 보류 화면은 가용자금을 0의 정상 잔고로 표시하지 않고 미확인으로 표시하며 새 PAPER 평가 버튼을 제공하지 않는다.

11개 skip은 Windows PE 1, opt-in 없는 LIVE 주식 6/Binance 2, 비배포 private fixture 2다. 제공받은 지원 복제 자료는 별도의 실제 복제 점검으로 검증했다. 기존 의존성의 deprecation warning 2건은 남아 있다. 이 결과는 외부 기관이나 Windows 설치 인수를 대신하지 않는다.

## 데이터 보존·복구·롤백

지원 자료 `data/261006_Teayu` 전체 **10,125파일 / 29,146,484,324바이트**를 원본 DB를 열지 않고 별도 비공개 backup으로 보존했다. 원본 전후 파일 SHA-256 동일, DB 11개의 `integrity_check=ok`, 모든 기존 행 hash/count 동등, 핸들 종료 후 backup manifest 재대조도 통과했다. 자격정보·고객 행 원문과 대용량 상세 manifest는 Git/bundle에 넣지 않았다. [집계 보존 증거](support-preservation.json).

복제 원장 **33,347행** 중 계약 단위 없는 기존 valid **11,394행**을 미확정으로 분리했다. valid 30,251 → 18,857; 미확정 3,091 → 14,485; invalid 5 유지. 원장 prefix·포지션 파일 보존, Unified 8포지션/Binance 2포지션 복원 성공. [복제 복원 및 판정 집계](support-recovery-audit.json). 복원이 성공해도 과거 미확정 손익을 검증 자금으로 되살리는 것은 아니므로 기존 해외 선물 자금은 대조/보류될 수 있다.

합성 PAPER 형식 시험에서는 최신 .8 backup에 추가 DB 행·원장·보유량·실제 session store·설정·전략·자격정보·예약을 보존한 뒤, 공개 .7의 실제 loader/serializer → .8 복귀를 검증했다. 수량 **10 → 6 → 6**, 부분청산 이벤트 **1회**, DB **1 → 2행 유지**, session ID 유지, 확인 손실 **-75 유지**, 가용자금 **924.1736 → 924.1736 USDT**. 업그레이드 전 backup만 복원하지 않았다. [롤백 증거](rollback-evidence.json). 사용한 .7 포지션 source fixture의 SHA-256은 `03add635fcc2ab6ac89363ea77516ecb38b4a1812e1bc7cc9e3fb6813705cab4`이며 기준 Git blob과 byte 동일하다.

## 미실시와 Windows 인수

Windows 실행 환경/.8 설치기가 없으므로 아래는 **모두 미실시**다.

- .7 → .8 수동 설치 및 실제 자동 업데이트.
- 실제 Windows 계정 경로·정지 확인·backup 및 DB/키/전략 설치 인수.
- 실제 설치 engine/화면 .8 버전 확인, Windows 저장 장애/재시작/전원 손실.
- .8 → .7 설치 롤백 → .8 재설치 후 새 기록 보존.
- 실제 PAPER 24시간/72시간 운용 및 외부 기관 인수.

[Windows 인계 절차](WINDOWS_HANDOFF.md)와 [설치본 인수 checklist](../../docs/DEPLOY_CHECKLIST.md)를 사용자 Windows PC에서 수행해야 한다. 이번 작업의 완료 범위는 수정·로컬 시험·문서·로컬 커밋이다. .8 설치/공개 릴리스를 완료했다고 판정하지 않는다.

기존 사용자는 원본을 삭제하지 않고 업데이트한다. .8에서 발생하는 확정 청산/snapshot 장애는 근거가 있으면 자동 대조된다. 이미 .7에서 생긴 불명확한 잔여 수량·계약 근거 없는 과거 손익은 업데이트만으로 소급 복구된다고 보장하지 않는다. 보류 사유를 확인하고 최신 원장·보유 자료를 함께 보존한다. 새 PAPER 평가는 명시 확인·정지·flat·예약 없음 조건과 기존 .7 보호를 통과한 경우에만 가능하며 손실 초기화나 저장 충돌 해제 수단으로 사용하지 않는다.
