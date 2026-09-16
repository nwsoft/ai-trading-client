# v3.9.1.37 업데이트 채널 선택 오류 수정

## 사용자 증상과 재현 (2026-09-17 KST)

Windows v3.9.1.36 설정 화면에서 업데이트 확인 시 v3.9.0.10/latest.yml을 요청해 404.
사용자의 오류 시각은 2026-09-16 23:37:54 KST이며 키움 연결 장애와 별개입니다.

인증 없는 공개 HTTP 조회로 다음 상태를 확인했습니다.

- GitHub releases.atom의 첫 entry: v3.9.0.10. 공개 릴리스 목록 API도 옛 목록을 반환했습니다.
- GitHub releases/latest (Accept: application/json) 및 REST latest: v3.9.1.36 stable.
- v3.9.1.36/latest.yml: HTTP 200, updater 3.9.136, NoahAI-3.9.1.36-Setup.exe와 SHA-512 포함.

앱은 allowPrerelease=true를 사용했고, 설치된 electron-updater의 GitHubProvider는
현재 SemVer에 prerelease 접미사가 없는 이 조합에서 Atom 첫 entry를 선택합니다.
따라서 올바른 stable latest가 있어도 옛 단일 EXE 릴리스에 없는 latest.yml을 조회했습니다.
피드와 latest 응답이 불일치한 서버 측 원인(캐시 등)은 확인하지 않았습니다.
404의 인증 토큰 문구는 라이브러리 공통 설명이며 사용자 자격증명 문제의 증거가 아닙니다.

### 후속 조사: 목록 정렬의 근본 원인 확인

2026-09-17 추가 조사에서 v3.9.1.36의 GitHub created_at은 **2025-05-01T18:33:47Z**,
published_at은 **2026-09-16T11:46:32Z**임을 확인했습니다. v3.9.1.x 태그들은
동일한 과거 커밋 `bd2fe406ec3de3f185447cb7c14e8dddb37830a4`를 가리키고,
현재 원격 main도 이 커밋입니다. 반면 v3.9.0.10은 2026-08-13 커밋을 가리킵니다.
따라서 v 접두사가 원인이 아니며 이전의 캐시 추정은 확정 원인으로 사용하지 않습니다.
GitHub의 created_at은 게시일이 아닌 릴리스 대상 커밋 날짜입니다.

배포 스크립트의 `gh release create`가 `--target` 없이 실행되어 원격 기본 브랜치의
오래된 커밋을 태그 대상으로 사용합니다. 최신 빌드 파일 업로드와 소스 커밋 게시가
분리된 상태가 원인입니다. 기존 v36 manifest에도 source_worktree_dirty=true,
source_archive_authoritative=false이므로 기록된 revision만으로 빌드 소스를 재현했다고 볼 수 없습니다.

v36에 `gh release edit --latest`를 재적용했으나 latest는 v36, 목록/Atom 첫 항목은
여전히 v3.9.0.10입니다. Latest 표시만 재지정해서는 정렬을 복구할 수 없습니다.
기존 태그 이동·삭제·재생성이나 날짜 조작은 수행하지 않았습니다.
근본 재발 방지는 실제 빌드 입력과 일치하는 소스 커밋을 확보·게시하고,
새 릴리스 태그를 그 커밋에 명시적으로 연결한 뒤 목록/Atom/latest/metadata를 함께 검증하는 것입니다.
기존 v36 정렬 복구는 정확한 v36 빌드 소스 확인 및 공개 태그 이력 변경 승인이 필요합니다.

사용자 결정: **37부터 정상화하며 36 이하 태그는 보존**합니다.
37 게시 절차에 커밋/빌드 입력 일치·원격 커밋 존재·기존 태그 충돌·커밋 날짜 검사를 추가했고,
Windows/macOS 모두 검증된 SHA를 `--target`으로 전달합니다. stable 게시 이후에는
공개 목록/Atom/Latest/Windows 업데이트 메타데이터가 같은 버전인지 검사합니다.
현재 macOS 동기화 작업 폴더에는 `.git`이 없어 여기서 실제 소스 커밋/게시를 완료한 상태는 아닙니다.
정확한 Git 작업 사본에서 검토·커밋한 소스로 Windows를 새 빌드해야 합니다.

## 수정

- 일반 설치본 allowPrerelease=false, allowDowngrade=false. 앱 이름의 Beta와 GitHub prerelease를 분리합니다.
- 저장한 확인 주기·자동 다운로드·종료 설치 설정 및 엔진 안전 종료 절차는 유지합니다.
- 파일 누락·무결성/서명 실패·확인 실패를 한국어로 안내합니다. UI에 HTTP 헤더·내부 경로·스택을 그대로 노출하지 않습니다.
- 사전공개 테스트본은 수동 설치용이며 일반 설치본이 자동 선택하지 않습니다.
- 이미 배포한 36 바이너리는 바뀌지 않습니다. 피드 문제가 유지되면 36은 37도 자동 발견하지 못할 수 있어 **37 정식 설치기 공개 후 공식 파일로 1회 수동 업데이트**하는 경로를 검증해야 합니다. 기존 버전에 가짜 latest.yml을 추가하거나 36 설치기를 덮어쓰지 않습니다.

## 검증

tests/updater-channel.test.cjs는 실제 설치된 GitHubProvider를 사용해 옛 옵션의 404 경로를 재현하고,
수정 옵션에서 stale Atom→stable latest→정확한 metadata/installer URL 선택을 검증합니다.
metadata 누락 시 구버전으로 우회하지 않는 검사와 오류 문구 검사 포함 **4개 통과**.
실제 공개 endpoint를 같은 Provider로 읽는 검사는 메타데이터만 조회하며 설치기를 내려받거나 실행하지 않습니다.

실제 서버 확인 결과: Atom 200 → stable latest 200 → **v3.9.1.36/latest.yml 200**, updater **3.9.136**, 표시 **3.9.1.36**, 설치기 **NoahAI-3.9.1.36-Setup.exe**로 선택됐습니다.
테스트에 필요한 잠금 버전 Node 의존성 설치를 Windows 전체 Python 회귀보다 먼저 실행하도록 빌드 순서를 조정했습니다. pending 빌드 manifest가 후보 버전으로 바뀌어도 매뉴얼은 previous_published_asset의 공개 버전을 유지합니다.

실제 Windows 36→37 설치·자동 다운로드·안전 종료·설치·재시작 E2E는 미완료입니다.

업데이트 채널 수정 시점 자동 검증: Python **2,494 passed / 8 skipped / 3 subtests passed** (기존 경고 1건), Node Provider 회귀 **4 passed**, 관련 집중 회귀 **51 passed**, Node 22.23.1 Web production **52 modules**, 문서 정합·11개 매뉴얼 추출·Electron/PowerShell 구문 검사 PASS. 번들 크기 경고는 남습니다. 공개 v36 manifest 및 latest.yml 해시는 변경하지 않았습니다.

37부터 적용하는 소스/태그 검증 추가 후 최종 검증 (2026-09-17 KST): Python **2,510 passed / 8 skipped / 3 subtests passed**, 기존 Starlette 경고 1건. 배포 출처·워크플로·업데이트 채널 집중 회귀 **35 passed**, Windows 게시 스크립트 PowerShell 구문 검사 및 문서 정합 PASS. 임시 Git 저장소로 수정·미추적·삭제·줄바꿈 불일치 입력 차단을 검증했고, 원격 응답 모의 검사로 오래된 커밋·태그 충돌·공개 목록/Atom/Latest/메타데이터 불일치 차단을 검증했습니다. 실제 37 소스 커밋 게시, Windows 빌드, 릴리스 게시 및 공개 정렬 검증은 아직 수행하지 않았습니다.

출처: [GitHub Atom](https://github.com/nwsoft/ai-trading-client/releases.atom),
[공개 stable](https://github.com/nwsoft/ai-trading-client/releases/latest),
[36 업데이트 메타데이터](https://github.com/nwsoft/ai-trading-client/releases/download/v3.9.1.36/latest.yml).
