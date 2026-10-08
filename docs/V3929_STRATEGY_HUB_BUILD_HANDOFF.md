# v3.9.2.9 Windows 빌드 인계

현재 공개판은 GitHub v3.9.2.8이다. v3.9.2.9는 제출 도움말·근거 상태 안내·버전·문서 수정 후보이며 Windows 설치기·공개 태그·GitHub 릴리스는 아직 없다. 사용자가 Windows PC에서 빌드·인수·릴리스한다. 이 문서는 Codex가 Windows 빌드나 공개 게시를 실행하도록 승인하지 않는다.

제품/엔진/PE 3.9.2.9, updater 3.9.209, renderer 3.9.2.9-ui.20261009.1. 기반은 공개 v3.9.2.8 태그 9714cc565a013f0fc1fb8931235809c132f66bc1. `.8` 공개 매니페스트를 고정하여 롤백 기반으로 보존했다. 해당 공개 매니페스트의 `source_worktree_dirty=true` 기록은 과거 공개 자산 정보이며 이번 소스의 깨끗한 커밋 검사로 대체하지 않는다.

허브 다중 기관 파서·조건 그래프 수용·미기록 표시 수정은 서버 배포로 따로 검증한다. 클라이언트 매매 로직은 변경하지 않았다. E0/E1은 성과 인증·순위가 아니며 운영자 입력 E2~E5를 자동 서명 검증·기관 체결 대조 완료로 설명하지 않는다. 결제·구독·포인트·환불·제작자 지급은 계획이다.

## Windows 작업

GitHub 준비 브랜치 `release/v3.9.2.9-strategy-hub-20261009`를 fetch하거나 동봉 Git bundle을 Windows로 복사한다. 기존 작업 저장소의 변경을 보존하고 새 작업트리에서 실행한다. bundle의 브랜치 이름과 커밋은 동봉 `source-identity.json`을 대조한다.

```powershell
git fetch C:\handoff\noahai-v3929.bundle release/v3.9.2.9-strategy-hub-20261009:refs/remotes/handoff/v3929
git worktree add --detach ..\noahai_client_3929_build refs/remotes/handoff/v3929
Set-Location ..\noahai_client_3929_build
git status --short
git rev-parse HEAD
# Node >=22.12, x64 Python과 별도 x86 Kiwoom 환경을 준비한다.
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

`SkipTests`, `SkipEngineBuild`, `AllowMissingKiwoomHost`를 사용하지 않는다. 빌드 후 `verify_release_provenance.py` 및 기존 릴리스 게이트를 통과하고 .8→.9 설치/업데이트, 허브 로그인·2단계 제출·비활성 가져오기, x86 OCX를 Windows에서 직접 인수한다. 전략 제출은 테스트 계정과 격리 환경에서 수행한다. 실제 계정·LIVE·장시간 인수는 별도이며 자동 테스트나 Mac 웹 빌드로 완료했다고 표시하지 않는다. 공개 자산 생성·릴리스 게시는 사용자가 인수한 뒤 실행한다.

검사 결과: Python 관련 회귀 162개, Node 46개, 웹 타입 검사·Vite 빌드·문서 정합성·11탭 매뉴얼 추출 통과. Windows 빌드 성공을 뜻하지 않는다. 공개 v3.9.2.8 자산과 자동 업데이트 채널은 이번 작업에서 교체하지 않는다.
