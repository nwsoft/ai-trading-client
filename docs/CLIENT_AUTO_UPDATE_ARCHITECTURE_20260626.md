# NoahAI Client 자동업데이트 아키텍처 제안 (2026-06-26)

## 1. 목적

이 문서는 GitHub Release + update.exe 배포 구조를 기준으로,
NoahAI Client의 주기적 업데이트 확인 및 자동업데이트 도입 가능성을
코드 현황 기반으로 정리한 실행 설계서다.

## 2. 가능 여부 판정

판정: 조건부 가능

조건:
- 클라이언트 내 업데이트 확인 훅은 이미 존재한다.
  - api/backend_api.py: check_for_updates() -> /api/updates/check
  - docs/INSTALLATION.md: 자동 업데이트 동선 문구 존재
- 그러나 현재 워크스페이스에는 실제 update.exe와 업데이트 오케스트레이션 엔진이 없다.
- 따라서 구현 전략은 "현재 훅 재사용 + 업데이트 엔진 신규 도입"이 합리적이다.

## 3. 현재 상태 (코드 근거)

- 업데이트 체크 API 호출 지점 존재:
  - api/backend_api.py
- 사용자 식별/세션 식별 데이터는 token.json 기반으로 확보 가능:
  - user_status_manager.py
  - path_utils.py
- 배포 게이트 체계 존재:
  - build_safe.py -> scripts/release_gate.py 연계
- 부재 항목:
  - update.exe 바이너리/실행 래퍼
  - 릴리즈 메타데이터(manifest) 검증 로직
  - 다운로드 무결성/서명 검증 로직
  - 실패 복구/자동 롤백 로직

## 4. 목표 아키텍처

### 4-1. 구성요소

- ClientApp
  - 현재 실행 중인 메인 앱
- UpdateOrchestrator (신규)
  - 버전 비교, 정책 판정, 다운로드/검증/실행 제어
- update.exe (배포 산출물)
  - 실제 교체/패치 적용 담당 (프로세스 외부 실행)
- Release Manifest (GitHub Release 자산)
  - 버전, 채널, sha256, 최소지원버전, 강제여부 포함
- Policy Source
  - backend /api/updates/check 또는 GitHub 메타데이터 직접 조회

### 4-2. 데이터 흐름

1. 앱 시작 후 지연(예: 15~60초) 뒤 업데이트 체크
2. 이후 주기 체크(기본 6시간, 실패 시 지수 백오프)
3. 원격 manifest 수신
4. 버전/채널/롤아웃/호환성 판정
5. 패키지 다운로드
6. sha256 + 코드서명 검증
7. 사용자 승인 정책에 따라 update.exe 실행
8. 재시작 후 health check
9. 실패 시 자동 롤백

## 5. 릴리즈 메타데이터 스키마 (권장)

예시 파일명: release-manifest.json

```json
{
  "version": "3.8.9.24",
  "channel": "stable",
  "released_at": "2026-06-26T09:00:00Z",
  "min_supported_version": "3.8.9.20",
  "mandatory": false,
  "rollout_percent": 25,
  "package": {
    "url": "https://github.com/<org>/<repo>/releases/download/v3.8.9.24/AITrading-win-x64.zip",
    "size": 123456789,
    "sha256": "<hex>"
  },
  "updater": {
    "url": "https://github.com/<org>/<repo>/releases/download/v3.8.9.24/update.exe",
    "sha256": "<hex>",
    "code_sign_required": true
  },
  "notes_url": "https://github.com/<org>/<repo>/releases/tag/v3.8.9.24"
}
```

## 6. 업데이트 체크 주기/백오프 정책

- 기본 주기: 6시간
- 앱 시작 시 즉시 체크 금지: 초기 15~60초 랜덤 지연
- 실패 백오프: 5분 -> 15분 -> 60분 -> 6시간
- 네트워크/서버 오류는 사용자 팝업 최소화(로그만 기록)

## 7. 트리거 조건 (update.exe 실행 조건)

모든 조건 충족 시에만 실행:
- 원격 version > 로컬 version
- channel 일치 (stable/beta/dev)
- rollout_percent 대상 사용자 포함
- min_supported_version 이상
- 디스크 여유 공간 기준 충족
- sha256 검증 성공
- code signing 검증 성공

## 8. 단계적 배포 (Staged Rollout)

권장 방식:
- bucket = hash(user_id or machine_fingerprint) % 100
- bucket < rollout_percent 일 때만 신규 버전 노출

장점:
- 동일 사용자는 반복 체크 시 항상 동일 판정
- 장애 시 rollout_percent 즉시 축소 가능

## 9. 사용자 알림 UX 정책

- 선택 업데이트 (기본)
  - 지금 설치 / 다음에 알림 / 오늘은 건너뛰기
- 강제 업데이트 (보안/치명 버그)
  - 유예 시간 후 설치 강제
  - 진행 중 거래/학습 작업 감지 시 안전 정지 후 적용
- 배경 다운로드 + 명시적 재시작 권장

## 10. 무결성/보안 정책

필수:
- HTTPS 강제
- 패키지 sha256 검증
- update.exe 코드서명 검증 (Windows Authenticode)
- 릴리즈 자산 권한 최소화(배포 전용 토큰/워크플로우)

권장:
- 서명 인증서 핀닝 또는 발급자 화이트리스트
- min_supported_version 아래 버전은 직접 패치 금지, 전체 설치 경로로 우회

## 11. 실패 복구/롤백

- 적용 전 이전 버전 백업 보관
- 재시작 후 health check 실패 시 자동 롤백
- 연속 실패 N회(예: 2회) 시 자동업데이트 잠금 + 수동 업데이트 안내
- 롤백 이벤트를 서버로 전송해 배포 중단 판단 근거로 사용

## 12. 관측성 (Telemetry)

이벤트 권장:
- update_check_started
- update_check_failed
- update_available
- update_download_started
- update_download_failed
- update_verify_failed
- update_install_started
- update_install_succeeded
- update_install_failed
- update_rollback_applied

필수 태그:
- user_id
- current_version
- target_version
- channel
- rollout_bucket
- error_code

## 13. 도입 단계

### MVP (1~2주)

- /api/updates/check 응답 스키마 고정
- 버전 비교 + 알림 UX만 적용 (다운로드/설치 수동)

### Pilot (2~3주)

- 배경 다운로드 + sha256 검증 + update.exe 실행
- 소수 롤아웃(5~10%)

### GA (2주)

- 단계적 배포 자동화
- 강제 업데이트 정책
- 자동 롤백/관측 대시보드

## 14. 구현 체크리스트

- [ ] api/backend_api.py: 업데이트 응답 스키마 파싱 확장
- [x] 업데이트 오케스트레이터 모듈 신규 추가 (`utils/auto_update_manager.py`)
- [x] 버전 파서(semver/패치 버전 비교) 추가
- [x] 다운로드/검증/서명검증 모듈 추가 (release-manifest sha256 검증)
- [x] UI 설정: 자동업데이트 on/off, 주기/다운로드/종료시적용 옵션 추가
- [x] 장애 복구: 롤백 루틴 구현 (적용 스크립트 내 롤백)
- [x] docs/CHANGELOG.md 동기화

## 15. 결론

GitHub/update.exe 구조에서 주기적 업데이트 확인과 자동업데이트는 구현 가능하다.
다만 현 상태는 "체크 훅만 존재" 단계이므로,
보안 검증(sha256+서명)과 롤백 내구성을 포함한 업데이트 엔진을 추가해야
운영 가능한 수준이 된다.

## 16. 빌드/업로드 자동화 운영안 (수동 업로드 대체)

현재 운영에서 `AITrading.exe + version.txt`를 수동 업로드 중이라면,
다음 자동화로 관리 비용을 크게 줄일 수 있다.

운영 정책(고정):
- SaaS 구축 완료 전까지는 Windows 클라이언트만 공식 지원한다.
- 개발 환경이 macOS여도 배포 산출물은 Windows 빌드에서 생성한 `AITrading.exe`를 기준으로 한다.
- 자동 릴리즈 파이프라인도 Windows 자산 업로드를 단일 기준으로 유지한다.

- 워크플로우: `.github/workflows/windows-release.yml`
  - 트리거: `v*` 태그 푸시 또는 수동 실행(workflow_dispatch)
  - 처리: Windows 빌드 -> 배포 자산 생성 -> GitHub Release 업로드
- 자산 생성 스크립트: `scripts/generate_release_assets.py`
  - `version.txt` 자동 생성 (`config/app_version.py` 기준)
  - `release_notes.md` 자동 생성 (`docs/CHANGELOG.md` 최신 섹션 추출)
  - `release-manifest.json` 생성 (exe sha256/다운로드 URL 포함)

업로드 산출물:
- `deploy/AITrading.exe`
- `deploy/version.txt`
- `deploy/release_notes.md`
- `deploy/release-manifest.json`

권장 운영 방식:
1. 배포 버전 반영 (`config/app_version.py`, `docs/CHANGELOG.md`)
2. 태그 생성/푸시 (`vX.Y.Z.W`)
3. GitHub Actions가 릴리즈를 자동 생성/업로드
4. 클라이언트는 GitHub Release 최신 버전 확인 버튼으로 검증

즉, 매번 웹에서 수동 업로드할 필요 없이 태그 기반 릴리즈로 일원화할 수 있다.

---
문서 상태: draft v1.0
