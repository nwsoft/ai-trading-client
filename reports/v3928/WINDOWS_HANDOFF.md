# v3.9.2.8 Windows 인계

이 묶음은 소스·검증 자료다. .8 설치기/자동 업데이트 피드/공개 릴리스가 아니다. 사용자 Windows PC의 빌드·인수·게시를 대신 실행하지 않는다. 현재 공개 기준은 v3.9.2.7 / `1c23b1e4947514906c1eb11050873a5c74ce39b0`이다.

## 1. 기존 작업을 보존해 소스를 가져오기

Mac 동기화 폴더의 `reports/v3928-handoff/noahai-v3928-preparation-20261008.zip`를 Windows로 가져온다. 함께 제공한 `SHA256SUMS.txt`와 `SOURCE_IDENTITY.json`의 bundle hash/최종 로컬 커밋/소스 지문을 확인한다. 깨끗한 디렉터리에서 압축을 풀고 기존 Git 저장소에서 prerequisite인 공개 .7을 읽기 fetch한다. 아래 이름/경로가 이미 있으면 새 이름을 사용하며 강제 overwrite/reset하지 않는다.

```powershell
git fetch origin tag v3.9.2.7
git rev-parse v3.9.2.7
# 반드시 1c23b1e4947514906c1eb11050873a5c74ce39b0인지 확인
Get-FileHash C:\handoff\v3928\noahai-v3928.bundle -Algorithm SHA256
git bundle verify C:\handoff\v3928\noahai-v3928.bundle
git fetch C:\handoff\v3928\noahai-v3928.bundle release/v3.9.2.8-paper-recovery-20261008:refs/remotes/noahai-local/v3928
git worktree add -b review/v3.9.2.8-20261008 ..\noahai_client_3928 refs/remotes/noahai-local/v3928
Set-Location ..\noahai_client_3928
git rev-parse HEAD
# 기존 Windows venv/Node >=22.12와 x86 Kiwoom Python을 준비한 뒤
.\.venv\Scripts\python.exe .\scripts\release_source_fingerprint.py --root .
```

fresh bundle import의 commit/소스 지문 동등성은 Mac에서 검증했다. Windows의 줄바꿈·도구·실제 산출물은 현지에서 다시 검증한다. bundle에는 고객 데이터/키/개인 상세 backup manifest/node_modules/dist/설치기가 없다. `config/published_release_manifests/v3.9.2.7.json`은 이전 공개 manifest의 고정 입력이며 새 .8 manifest는 Windows 빌드가 생성한다.

## 2. 실제 데이터 경로·정지·일관된 backup

현재 로그인 계정의 `get_app_data_dir()`, engine recorder DB 경로, PAPER 포지션 저장 경로를 설치본에서 확인한다. Documents/NoahAI/계정은 OneDrive·레거시·명시 경로에 따라 달라질 수 있다. 공용 루트만 보고 실제 계정 경로로 판단하지 않는다. 앱·엔진·기관 worker 및 관련 writer를 모두 종료한 뒤 backup한다. 외부 포지션/예약/전략 경로가 있으면 같은 정지 구간에 함께 보존한다.

```powershell
# 경로는 실제 설치 계정을 확인한 값으로 교체. backup은 원본 밖의 새 경로.
.\.venv\Scripts\python.exe .\scripts\paper_data_snapshot.py --source "<확인한 계정 폴더>" --destination "<새 backup 폴더>" --stopped
```

`--stopped`는 caller의 정지 확인 선언이다. backup 도구 자체가 Windows engine PID 정지를 증명하지 않는다. SQLite DB/WAL/SHM을 원본에 쓰지 않고 staging에서 backup API로 합치며 integrity/모든 행 hash/count/파일 hash를 기록한다. 변동/손상/symlink/64GiB·32,768파일 초과는 미승인 backup으로 남긴다. 실패를 성공 backup으로 표시하지 않는다. 원본과 최신 backup을 보관하고 자격정보 원문을 로그/게시 자료에 넣지 않는다.

## 3. .8 빌드와 설치 인수

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

검사 생략 옵션을 사용하지 않는다. 빌드 후 실제 .8 installer digest, manifest/provenance, x64 engine/x86 Kiwoom host PE·bootstrap/IPC·아이콘과 engine/renderer 버전을 확인한다. source/runtime gate의 최신 결과와 빌드 로그를 보관한다.

PAPER만 사용하는 복제 계정에서 .7 → .8 수동 설치·자동 업데이트, DB/원장 prefix/보유 수량/완료 index/예약/설정/전략/자격정보/세션 ID/가용자금 보존, 종료·강제 종료·저장 장애·반복 복구를 확인한다. 자동 업데이트에는 검토 가능한 .8 자산/피드가 필요하며 현재 공개 .7 피드로 .8 인수가 완료됐다고 표시하지 않는다. LIVE 권한이나 실제 기관 계정을 바꾸지 않는다.

## 4. 최신 기록을 유지한 설치 롤백·재복귀

.8에서 확정 청산의 복구 보류가 남아 있으면 먼저 .8에서 해결하고 엔진/기관을 정지한다. .7은 새 복구 근거를 재생하지 못하므로 pending .8 상태를 .7에서 거래 재개하지 않는다. .8에서 새로 생긴 DB/원장/보유량/세션을 포함한 최신 backup을 별도로 확보한 후 .8 → .7 수동 설치 → .8 재복귀를 수행한다.

기존 행 hash 포함 관계와 신규 행 존재, prefix의 동일성, 수량·청산 이벤트·마진·session ID·확인 손실·가용자금을 대조한다. 업그레이드 전 backup만 복원해 .8의 새 기록이 없어지는 경우는 실패다. Mac의 공개 .7 loader/serializer 형식 시험은 설치 롤백을 대신하지 않는다.

## 5. PAPER 24시간 / 필요 시 72시간

설치 .8 engine PID와 실제 gateway를 확인한 PAPER 전용 복제 계정에서 시행한다. 기존 `scripts/runtime_soak_monitor.py --help`의 필수 경로·token 환경변수·sources를 현지 설정하고 `--require-paper --duration-min 1440`으로 관찰한다. 이상/누수/저장 불일치가 있으면 72시간으로 확대해 원인 수정 후 재검증한다. gateway token은 명령 문자열/공유 로그에 쓰지 않고 지정 환경변수로 전달한다. 시간 압축 fixture를 실제 24시간 운용으로 표시하지 않는다.

최종 인수 checklist는 `docs/DEPLOY_CHECKLIST.md`의 v3.9.2.8 블록을 사용한다. 현재 이 항목들은 미실시다. 결과를 검토하기 전 공개 배포 완료로 표현하지 않는다. 이번 Codex 지시에는 push·PR·공개 게시가 포함되지 않는다.
