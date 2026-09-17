# NoahAI 빌드·릴리즈 가이드

현행 소스 후보: **3.9.1.38** / Electron updater: **3.9.138**. 공개 stable/latest는 **v3.9.1.37**이며 기존 v37 자산·태그·manifest는 불변입니다. 과거 설명은 [보존본](archive/build/BUILD_GUIDE_PRE_V39135.md)에 있으며 아래 명령만 현행입니다.

## 공통 원칙

- **v3.9.1.37부터 태그 대상 필수:** 빌드 입력을 검토·비밀정보 제외 후 Git에 커밋하고 해당 커밋을 원격에 게시합니다. 기본 브랜치의 오래된 HEAD에 태그를 자동 생성하지 않습니다. 기존 v37 이하 태그·설치 파일은 보존합니다.
- 매뉴얼·기관 레지스트리 생성 결과도 커밋에 포함한 뒤 새 체크아웃에서 빌드합니다. `.gitattributes`의 LF 줄바꿈을 적용해 커밋 내용과 실제 빌드 입력 바이트가 일치해야 합니다. `git add .`로 계정 데이터·자격증명·로그·DB·설치기를 일괄 공개하지 마세요.
- 게시 전 `verify_release_provenance.py`가 manifest의 source_revision=HEAD, 커밋/로컬/빌드 fingerprint 일치, 원격 커밋 존재, 기존 태그 불충돌, 커밋 날짜를 검사합니다. 미커밋·미추적·삭제된 빌드 입력도 차단합니다. 관련 없는 생성 산출물은 소스 변경으로 간주하지 않습니다.
- Windows와 macOS 모두 검증된 `--target`으로만 새 태그를 만들고 업로드 전에 태그를 다시 대조합니다. 이미 있는 태그가 다르면 자동 이동·삭제하지 않습니다.
- stable 게시 후 공개 목록 첫 항목·Atom 첫 항목·Latest·latest.yml/설치기 이름이 같은 버전인지 확인합니다. 전파 지연 등으로 불일치하면 **게시되었지만 검증 미완료**로 실패 처리하며 삭제/재태깅하지 않습니다. `python scripts/verify_release_provenance.py --phase published`로 읽기 전용 재확인합니다.

- `config/app_version.py`, `webui/package.json`·lock의 updater 버전, Windows 리소스 버전이 일치해야 합니다. 변환식은 `A.B.C.D → A.B.(C*100+D)`입니다.
- 소스 테스트 통과, 패키지 실행, 실제 계정 연결, 장시간 PAPER 검증은 서로 다른 증거입니다. [v3.9.1.38 검증 계획](V39138_STRATEGY_REPLAY_LIVE_HISTORY_TEST_PLAN.md)의 실제 확인한 행만 `[x]`로 표시합니다.
- 소스 fingerprint는 `scripts/release_source_fingerprint.py`로 계산합니다. 변경된 소스에 이전 바이너리·해시를 재사용하지 않습니다.
- 사용자 `data/Teayu`·API 키·원장은 빌드 입력이나 공개 릴리즈에 포함하지 않습니다. 빌드되는 data는 공개 금융상품 카탈로그뿐입니다.
- `deploy/release-manifest.json`은 Windows 산출물 명세입니다. macOS는 `deploy/mac-release/release-manifest-mac.json`을 사용하며 서로 덮어쓰지 않습니다.
- 이미 게시된 파일은 덮어쓰지 않습니다. 일반 사용자 배포는 stable/latest, 별도 테스트 후보만 명시적인 prerelease를 사용합니다. 외부 실계정·장시간 검증이 남아 있어도 자동 회귀·엔진·키움 x86·해시 검증을 통과한 운영자 배포는 pending 상태를 manifest에 남기고 stable/latest로 게시합니다. macOS 무서명 파일은 계속 수동 테스트용입니다.
- 서명 없는 macOS 파일에 Gatekeeper 우회나 격리 속성 제거를 권장하지 않습니다. Developer ID 서명·공증 완료 전에는 일반 사용자용 정식 설치본으로 안내하지 않습니다.

## 자동 업데이트 계약

- 3.9.1.38 일반 설치본은 GitHub stable/latest만 조회하고 prerelease·다운그레이드를 허용하지 않습니다. 앱의 Beta 명칭은 사전공개 채널 선택을 뜻하지 않습니다. 테스트 prerelease는 수동 설치용입니다. Windows에는 `latest.yml`, macOS에는 `latest-mac.yml`과 해당 플랫폼 설치 자산을 같은 버전·같은 Release에 함께 게시해야 합니다.
- `백그라운드 업데이트 확인`이 ON이면 로그인 후 15초 뒤 첫 확인을 하고, 이후 사용자가 저장한 1~72시간 주기로 확인합니다. OFF여도 `지금 버전 확인`은 사용할 수 있습니다.
- `업데이트 자동 다운로드`가 ON이면 새 버전을 발견한 뒤 다운로드합니다. OFF이면 알림만 표시하고 사용자가 다운로드 버튼을 눌러야 합니다.
- Windows에서 `종료 시 자동 설치`가 ON이고 다운로드가 완료된 상태라면, 정상 종료 시 거래 엔진·기록의 안전 종료가 성공한 뒤 설치합니다. OFF이면 업데이트 화면의 `설치·재시작`을 사용합니다. 안전 종료 실패 시에는 설치하지 않습니다.
- macOS 자동 업데이트는 앱 코드서명이 필요합니다. 현재 서명 없는 테스트 DMG/ZIP은 같은 Release에서 수동 다운로드·설치만 가능하며, 설정 스위치만으로 이 제약을 우회할 수 없습니다.
- 이미 게시된 `v3.9.1.35` 자산에는 게시 후 수정한 종료 설치·prerelease 조회 패치가 들어 있지 않습니다. 다만 stable/latest 전환으로 v3.9.1.34 Windows 설치본은 v3.9.1.35를 확인·다운로드할 수 있습니다. 같은 버전 자산을 교체하지 말고 다음 제품 버전으로 패치를 빌드·게시한 뒤 이전 설치본에서 1회 실제 업데이트를 검증합니다.
- v3.9.1.38은 새 x64 엔진·x86 키움 호스트·Electron 설치기로만 빌드합니다. 공개 v3.9.1.37의 설치기·blockmap·`latest.yml` 이름이나 해시를 복사·교체하지 않습니다.

## Windows PC 준비

1. 프로젝트 폴더에서 `git rev-parse --show-toplevel`, `git status --short`로 저장소와 사용자 변경을 확인합니다. 동기화 폴더의 복사본을 사용할 경우 원본 소스·fingerprint를 담당자와 대조하세요. 다른 PC의 `.venv`·`node_modules`를 재사용하지 않습니다.
2. Windows 10/11 x64, Python 3.11 x64, Python 3.11 x86, Node >=22.12, Git, GitHub CLI, Visual Studio Build Tools/VC143 CRT를 준비합니다.
3. 개발 환경을 설치합니다. 아래는 프로젝트 루트에서 실행합니다.

```powershell
py -3.11-64 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements_windows.txt
py -3.11-32 -m pip install -r requirements_kiwoom_x86.txt
npm --prefix webui ci --include=optional
gh auth status
```

`py -3.11-32` 대신 별도 x86 환경을 쓸 때는 `NOAHAI_PYTHON_X86`에 해당 python.exe의 절대경로를 지정합니다. 일반 사용자는 x86 Python을 설치할 필요가 없습니다. 호스트 EXE가 설치기에 포함됩니다.

## Windows 빌드 → 실제 검증 → 릴리즈

```powershell
# 1. 전체 자동 검사와 두 아키텍처 빌드
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1

# 2. 일반 사용자용 stable/latest 게시
powershell -ExecutionPolicy Bypass -File .\scripts\release_windows.ps1

# 3. 자동업데이트에 노출하지 않을 테스트 후보만 명시적으로 prerelease 게시
powershell -ExecutionPolicy Bypass -File .\scripts\release_windows.ps1 -AllowPendingExternalGates
```

일반 사용자용 빌드·stable/latest 게시를 한 번에 수행하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_and_release_windows.ps1
```

테스트 후보를 한 번에 만들 때만 `-AllowPendingExternalGates`를 붙입니다. 직접 stable/latest를 게시하는 정본은 `scripts/publish_web_ui_windows_release.ps1 -ConfirmExternalGates -AllowPendingExternalGates -PublishStableWithPendingExternalGates`입니다. `SkipTests`, `SkipEngineBuild`, `AllowMissingKiwoomHost`는 공식 릴리즈에서 사용하지 않습니다.

산출물:

```text
deploy/web-engine/NoahAIEngine.exe                 x64
deploy/web-engine/NoahAIKiwoomHost.exe             x86, PE 0x14c
deploy/web-release/NoahAI-3.9.1.38-Setup.exe
deploy/web-release/NoahAI-3.9.1.38-Setup.exe.blockmap
deploy/web-release/latest.yml                      updater 3.9.138
deploy/release-manifest.json
```

빌드 전 `deploy/release-manifest.json`이 v3.9.1.37을 가리키는 것은 정상입니다. 이 파일은 공개 증거이며 Windows v38 빌드가 성공해 새 해시를 계산하기 전 문서 편집만으로 v38 값이나 가짜 해시를 넣지 않습니다. 빌드 스크립트가 새 산출물에서 v38 manifest를 생성한 뒤 설치기·blockmap·`latest.yml`과 함께 검증합니다.

### v3.9.1.38 추가 화면 확인

1. Strategy Studio 과거재생에서 검증 캔들, 모든 진입·청산 화살표, 선택 거래 이름·원본 가격, 청산 기준 수익률 곡선과 거래표를 확인합니다.
2. 코인과 주식·ETF 각각 500봉 검증을 실행하고 기관·자산·통화·비용·전략 버전이 결과와 일치하는지 확인합니다. 국내 현물 신규 SHORT는 계속 차단되어야 합니다.
3. 7개 코인 거래소와 4개 증권사에서 PAPER는 `가상 포지션`·`가상 거래 통계`, LIVE는 상품에 맞는 `포지션/보유자산`·`실거래 통계`를 표시하는지 확인합니다.
4. 기관별 거래내역은 PAPER/LIVE 모두 기본 접힘이며 모드·기관 전환 시 다시 접혀야 합니다. LIVE 탭 선택만으로 실행 모드가 바뀌어서는 안 됩니다.
5. LIVE 종료 원장의 확정·미확정·외부·가져오기·통화 불명·조회 실패를 구분하고 PAPER/LEARNING 기록이나 다른 기관·계정 기록이 섞이지 않는지 확인합니다.
6. 공개 v3.9.1.37 설치본에서 v3.9.1.38을 확인·다운로드하고 거래 엔진 안전 종료 뒤 설치·재시작되는지 확인합니다. 설정, 계정 자격정보, 전략 버전, 검증 결과와 PAPER/LIVE 원장을 대조합니다.

### 키움 10054 확인 순서

1. 패키지 호스트의 PE x86·버전·SHA를 manifest와 대조합니다. x64 엔진 성공은 x86 호스트 연결 성공이 아닙니다.
2. 설치본에서 연결하고 사용자 logs의 `kiwoom_host_events.jsonl`을 확인합니다. `adapter_import → adapter_ready → rpc_connect → activex_registry → activex_construct → activex_ready` 중 마지막 단계가 중단 지점입니다. API 키·비밀번호·계좌 응답을 이 로그에 쓰지 않습니다.
3. `activex_registration_missing`이면 동일 PC의 32비트 OpenAPI+ 등록과 KOA Studio 로그인부터 확인합니다. `activex_construct`에서 프로세스가 종료되면 Windows 이벤트 뷰어의 응용 프로그램 오류에서 종료 시각·오류 모듈·코드를 수집합니다.
4. 준비 완료 응답 전 타임아웃, 로그인 실패, RPC 종료를 구분합니다. 10054만 보고 인터넷 장애나 재설치로 단정하지 않습니다.
5. 주문 응답 미확정은 자동 재전송하지 않습니다. PAPER로 로그인·시세·잔고·종료/재시작을 검증한 뒤 LIVE 권한을 별도로 확인합니다.

## macOS arm64 빌드

이 스크립트는 현재 Python/Node 아키텍처가 arm64인 Apple Silicon Mac에서 실행합니다. Intel/universal 빌드를 검증한 것으로 표시하지 않습니다. 키움 OpenAPI+는 macOS에서 지원하지 않습니다.

```bash
# 새 환경은 Python 3.13 arm64로 생성합니다. Windows의 NumPy/Pandas 고정값을 Mac 3.13 환경에 혼용하지 않습니다.
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements_macos.txt
# Node >=22.12가 PATH에 있어야 합니다.
.venv/bin/python scripts/build_macos.py
```

고정 의존성/OCR·PDF·자료 가져오기 사전 검사·전체 Python 회귀·매뉴얼/문서 검사·locked npm 설치·Web 빌드·PyInstaller 엔진·bootstrap smoke·Electron DMG/ZIP·패키지 엔진 smoke를 순서대로 수행합니다. macOS 엔진은 `deploy/mac-engine/noahai-engine`이며 Windows 엔진 폴더를 참조하지 않습니다.

```text
deploy/mac-release/NoahAI-3.9.1.38-arm64.dmg
deploy/mac-release/NoahAI-3.9.1.38-arm64.zip
deploy/mac-release/latest-mac.yml
deploy/mac-release/release-manifest-mac.json
```

기본은 서명 없는 로컬 테스트 후보입니다. 정식 서명 빌드는 Developer ID를 Keychain에 설치하고 `CSC_NAME` 및 Apple 공증용 환경을 준비한 뒤 `--signed`로 실행합니다. 인증서·Apple 비밀값은 문서·로그·명령행에 넣지 않습니다. `codesign --verify --deep --strict` 및 `spctl --assess`를 통과하지 않으면 서명 배포로 인정하지 않습니다.

Windows와 macOS는 같은 제품 버전의 **공용 GitHub Release 태그 `v3.9.1.38`**를 사용합니다. Windows는 `latest.yml`, macOS는 `latest-mac.yml`을 읽으므로 플랫폼별 자동업데이트 자산이 충돌하지 않습니다. DMG·ZIP과 두 blockmap, `latest-mac.yml`, Mac manifest를 Windows 설치기와 같은 릴리즈에 게시합니다.

`scripts/publish_macos.py`는 공용 릴리즈가 이미 있으면 Mac 자산만 추가하고 원격 SHA-256을 검증합니다. Windows 릴리즈가 아직 없으면 같은 `v3.9.1.38` 태그의 draft를 만들며, 별도 `-macos-candidate` 태그는 만들지 않습니다. 같은 이름의 원격 자산이 다르면 덮어쓰지 않고 새 제품 버전을 요구합니다. 새 릴리즈에서 서명 없는 Mac 자산을 stable 릴리즈에 추가하는 작업은 스크립트가 차단합니다. v3.9.1.37 이하의 기존 Mac 자산은 과거 공개·수동 테스트 기록이며 v3.9.1.38 자동업데이트 증거로 승계하지 않습니다.

```bash
.venv/bin/python scripts/publish_macos.py
```

## 검증 문서 업데이트

`docs/TEST_STATUS.md`, `docs/DEPLOY_CHECKLIST.md`, 현재 버전 TEST_PLAN, 인앱 매뉴얼을 함께 갱신합니다. 문서 체크 표시를 빌드 통과를 위해 임의로 바꾸지 않습니다. `python scripts/doc_consistency_check.py`와 매뉴얼 재추출을 다시 실행하고, 패키지 입력이 바뀌었으면 재빌드합니다.
