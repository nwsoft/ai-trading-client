# 빌드 가이드

> **정본 범위**: 이 문서가 빌드 명령·의존성·패키징·산출물 검증의 유일한 현행 가이드입니다.  
> 과거 경로 검증과 특정 버전 빌드 보고서는 `docs/archive/build/`에 보관하며, 현재 배포 판단에는 `DEPLOY_CHECKLIST.md`와 `TEST_STATUS.md`를 함께 사용합니다.

> **실제 배포 스펙**: `build_safe.py`가 런타임에 `aiautotrade_safe.spec`을 동적 생성하여 사용합니다.  
> `aiautotrade.spec`은 참고용이며 실 배포에 반영되지 않습니다.

> UI 정책: 본 프로젝트의 GUI는 CustomTkinter만 지원합니다. PyQt5/PySide6는 Windows 빌드에서 키움증권 OpenAPI+ 지원 목적으로만 포함됩니다 (레거시 UI 파일은 ImportError 스텁으로 남아 있습니다).

배포 대상 릴리스: `https://github.com/nwsoft/ai-trading-client/releases/tag/v3.9.0.8`

> v3.9.0.8 AI Custom Update Fix 1 manifest는 `pending_windows_rebuild`입니다. Windows에서 새로 빌드한 뒤 AI 커스텀 프로필·Level 전환·성과표·패키지·어시스턴트 지식과 기존 VC 런타임·Kiwoom·OCR·거래소 안전 회귀를 함께 검증해야 합니다. 직전 공개 v3.9.0.8 AI Custom Update 자산은 `deploy/previous/AITrading-v3.9.0.8-AI-Custom-Update.exe`에 보존했으며 비교·복구용 `previous_published_asset`으로만 사용합니다.

> 빌드 전 `.venv/bin/python scripts/active_source_audit.py`와 `.venv/bin/python verify_build_includes.py`를 모두 통과해야 합니다. 격리된 레거시 `theme_system`과 위젯/대시보드 보관본은 활성 소스·PyInstaller 입력에 포함하지 않습니다.

> 생활금융 기본 비교 데이터는 `data/finance_products`만 안전 빌드에 포함합니다. 계정·거래·사용자 설정 등 나머지 `data`는 계속 제외됩니다. 패키지 내 기본 데이터가 누락되거나 손상되면 앱 내장 예비 데이터로 폴백합니다.

> v3.9.0.5 배포 계약: v3.9.0.3 후보에서 추가된 필수 `keyring`·Windows 보안 저장소 의존성을 철회했습니다. `build_safe.py`와 두 requirements/spec에는 keyring이 없어야 하며 최종 사용자는 추가 패키지를 설치하지 않습니다.

## 🛠️ 개발 환경 설정

### 필수 요구사항
- **Python**: 3.11 이상 권장
- **PyInstaller**: 6.21.0 (`requirements_windows.txt` 고정)
- **Git**: 최신 버전
- **Windows VC143 CRT**: Visual Studio 2022 Build Tools의 최신 재배포 세트, 빌드 Python과 같은 x86/x64 아키텍처

참고
- 키움 OpenAPI+ 실연동 테스트는 Windows Python 3.11.x 32bit 권장(OCX/COM bitness 일치 필요)


### GitHub 자동 릴리즈 조건

- 태그 기반 자동 릴리즈(`v*`)를 사용하려면 현재 폴더가 Git 저장소 루트여야 합니다(`.git` 필요).
- `git rev-parse --is-inside-work-tree` 결과가 실패하면, 원격이 연결된 클라이언트 저장소 작업본에서 태그/푸시를 수행해야 합니다.
- 자동업데이트 기준 릴리즈 저장소는 `nwsoft/ai-trading-client` 단일 저장소로 운영합니다.
### 개발 도구
```bash
# 필수 패키지 설치 (macOS/Linux 개발환경)
pip install pyinstaller
pip install -r requirements.txt

# Windows 빌드 PC (1회만 실행)
pip install -r requirements_windows.txt
# 키움증권 OpenAPI+ 지원용 (pykiwoom은 PyQt5.QAxWidget 기반)
pip install pykiwoom PyQt5
# 음성 인식(pyaudio)이 실패할 경우
pip install pipwin && pipwin install pyaudio
```

### Fix Patch 3 VC 런타임 수집 정책

PyQt5는 키움 OpenAPI+의 `QAxContainer/QAxWidget` 때문에 필요합니다. PyQt5, Qt DLL, `pyi_rth_pyqt5`를 제거하지 않습니다. 대신 PyInstaller가 PyQt5·pandas·Python 경로에서 발견한 모든 `MSVCP140*.dll`/`VCRUNTIME140*.dll`을 수집 결과에서 제거하고, 공식 `Microsoft.VC143.CRT` 한 세트만 EXE 루트에 넣습니다.

빌더는 Visual Studio 2022 Build Tools의 최신 CRT를 자동 탐색합니다. 자동 탐색이 안 될 때만 다음처럼 공식 폴더를 지정합니다. DLL 파일을 임의 사이트에서 내려받아 지정하면 안 됩니다.

```powershell
$env:NOAHAI_VC_RUNTIME_DIR = "C:\Program Files\Microsoft Visual Studio\2022\BuildTools\VC\Redist\MSVC\<최신버전>\x64\Microsoft.VC143.CRT"
python build_safe.py --platform windows --gate-profile release
```

32비트 Python으로 빌드할 때는 같은 버전의 `x86\Microsoft.VC143.CRT`를 지정합니다. 다음 조건 중 하나라도 해당하면 빌드를 중단합니다.

1. `msvcp140.dll`, `msvcp140_1.dll`, `vcruntime140.dll`, `vcruntime140_1.dll` 누락
2. ONNX Runtime PE 링커(현재 고정본은 최소 14.40)보다 오래된 런타임
3. 같은 세트 안에서 버전 계열 혼합
4. 완성 EXE의 PyQt5·pandas 하위에 VC DLL 잔존
5. EXE 루트 런타임 SHA-256이 빌드에 선택한 공식 원본과 불일치

시스템 VC 재배포 패키지 설치만으로는 앱의 `_MEI` 하위 DLL이 먼저 선택되는 문제를 보장해서 막을 수 없습니다. 그래서 Fix Patch 3는 앱 로컬 패키징 자체를 단일 세트로 고정합니다.

### requirements 파일 구분
| 파일 | 용도 |
|---|---|
| `requirements.txt` | 개발/macOS 환경 공통 의존성 |
| `requirements_windows.txt` | Windows 배포 전용 (pykiwoom, PyQt5, win32-setctime 포함) |

`requirements_windows.txt`와 생성되는 spec에는 `keyring`, Windows Credential Manager backend, 관련 metadata 수집이 없어야 합니다.

## 🚀 빌드 방법

### 자동 빌드 (권장)

플랫폼을 명시하여 안전 빌드 스크립트를 실행하세요.

```bash
# Windows
python build_safe.py --platform windows

# macOS
python build_safe.py --platform macos

# Linux
python build_safe.py --platform linux
```

Windows 빌드 후 깨끗한 사용자 계정에서 다음을 반드시 확인합니다.

1. Python·pip·keyring이 설치되지 않은 상태에서도 AI API 키 저장 성공
2. 앱 종료·재시작 뒤 사용자별 로컬 키 복원
3. v3.9.0.3 `credential_ref`만 있는 설정에서도 일반 설정 저장 성공
4. 키를 다시 입력한 Provider는 로컬 키가 정본이 되고 과거 참조 제거
5. 설정·백업이 지원 로그 묶음과 배포 파일에 포함되지 않음
6. Binance 탭이 12초 안에 값 또는 명확한 연결·조회 상태 표시

참고
- `build_safe.py`의 기본 게이트 프로필은 `prekey`입니다 (`--gate-profile` 미지정 시).
- 즉, 기본 빌드에서도 `DOC_CONSISTENCY`/`SYNC_GUARD`가 실행되어 문서/버전 불일치가 있으면 빌드가 중단됩니다.

### Windows 원클릭 빌드 + 릴리스 (기본 운영 경로)

프로젝트 루트에서 아래 명령 하나만 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_release_windows.ps1
```

스크립트는 Tcl/Tk·VC143·GitHub 인증 사전점검, `prekey` 게이트, Windows EXE 빌드,
EXE 내부 Tkinter·VC 런타임·버전 검증, manifest 생성, GitHub 업로드, 원격 크기와
SHA-256 재검증을 순서대로 수행합니다. 어느 단계든 실패하면 성공으로 종료하지 않습니다.
검증이 끝나기 전에는 기존 `deploy/AITrading.exe`를 교체하지 않으며 GitHub 업로드도 시작하지 않습니다.

새 버전 태그가 아직 없고 작업 트리에 변경이 있으면, 빌드와 로컬 검증이 모두 성공한 뒤에만
`release: v<버전>` 커밋을 자동 생성합니다. 빌드 실패 시에는 커밋과 태그가 생성되지 않습니다.
이미 존재하는 태그는 자동으로 이동하지 않습니다.

빌드와 로컬 검증만 실행할 때:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_release_windows.ps1 -BuildOnly
```

같은 태그의 긴급 바이너리 교체처럼 작업 트리 변경을 의도적으로 허용할 때만 다음 옵션을 사용합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_release_windows.ps1 -AllowDirtyWorkingTree
```

`-AllowDirtyWorkingTree`는 일반 릴리스에 사용하지 않습니다. 새 버전에서는 검증된 소스를 자동 커밋하지만
`main`을 강제 push하지 않습니다. 실행 로그는 `deploy/build-release-YYYYMMDD-HHMMSS.log`에 기록됩니다.

Windows에서 `.git`이 없는 복사본 워크스페이스를 자주 빌드한다면 아래 래퍼를 권장합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_safe.ps1
```

옵션 예시:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_safe.ps1 -GateProfile prekey -ReadinessTimeoutSec 8
```

`git diff` 기준으로 엄격 비교가 필요할 때만 아래 옵션을 사용하세요.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_windows_safe.ps1 -GateProfile prekey -UseGitDiff
```

중요
- `scripts/build_windows_safe.ps1`는 빌드 게이트 + Windows EXE 빌드 자동화 스크립트이며, Git 태그 생성/푸시는 수행하지 않습니다.
- 기본 동작은 `SYNC_GUARD_CHANGED_FILES`를 주입하는 안정 모드이며, 로컬 Git 이력(`HEAD~1`)에 따른 변동으로 게이트가 흔들리는 문제를 줄입니다.
- 일반 운영자는 `build_windows_safe.ps1`와 `release_tag_push.ps1`를 따로 호출하지 않고 `build_release_windows.ps1`를 사용합니다.

### 태그 푸시 자동화 스크립트 (Windows)

태그 기반 GitHub 릴리즈를 한 번에 처리하려면 아래 스크립트를 사용합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release_tag_push.ps1 -Version 3.9.0.8 -Branch main -PushBranch
```

옵션
- `-Version`: 필수. `3.9.0.5` 또는 `v3.9.0.5` 모두 허용
- `-Branch`: 기본 `main`
- `-PushBranch`: 태그 push 전에 브랜치도 함께 push
- `-StrictBranchPush`: `-PushBranch` 실패 시 즉시 중단(기본은 경고 후 태그/릴리즈 업로드 계속)
- `-SkipCommit`: 커밋 없이 기존 HEAD 기준으로 태그만 생성/푸시
- v3.9.0.5 Update Patch 1는 인증서·Authenticode 옵션을 사용하지 않습니다. 릴리즈 스크립트가 GitHub HTTPS 다운로드 주소와 필수 SHA-256 manifest를 생성합니다.

보안 범위
- SHA-256이 누락되거나 실제 EXE와 다르면 자동업데이트가 적용되지 않습니다.
- 코드서명이 없으므로 Windows SmartScreen/Defender의 게시자 평판 경고는 나타날 수 있습니다.
- 자체서명 인증서는 무료지만 외부 사용자 평판 문제를 해결하지 않으므로 배포 정본으로 사용하지 않습니다.

#### 빠른 실행 레시피 (복붙용)

아래는 현장에서 가장 자주 쓰는 실행 패턴입니다.

1) **가장 안전한 기본 배포(권장)**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release_tag_push.ps1 -Version 3.9.0.8
```

- 태그 push + GitHub 릴리즈 에셋 업로드까지 수행
- 브랜치 push 충돌(non-fast-forward) 영향을 최소화

2) **브랜치도 같이 push (실패해도 릴리즈는 계속 진행)**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release_tag_push.ps1 -Version 3.9.0.8 -Branch main -PushBranch
```

- `main` push가 거절돼도 태그/릴리즈 업로드는 계속 진행

3) **브랜치 push 실패 시 즉시 중단(엄격 모드)**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release_tag_push.ps1 -Version 3.9.0.8 -Branch main -PushBranch -StrictBranchPush
```

- 팀 정책상 브랜치 push 성공이 필수일 때 사용

4) **이미 커밋한 상태에서 태그/릴리즈만 수행**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release_tag_push.ps1 -Version 3.9.0.8 -SkipCommit
```

- 로컬 변경 자동 커밋 없이 현재 HEAD 기준으로 태그/릴리즈 처리

5) **같은 태그에 재빌드 산출물만 덮어쓰기 업로드**

```powershell
python scripts/generate_release_assets.py --out-dir deploy --exe deploy/AITrading.exe --repo nwsoft/ai-trading-client
gh release upload v3.9.0.8 deploy/AITrading.exe deploy/version.txt deploy/release_notes.md deploy/release-manifest.json --repo nwsoft/ai-trading-client --clobber
```

- 태그를 새로 만들지 않고 릴리즈 에셋만 교체
- v3.9.0.8에서는 생성 후 manifest의 `release_label=v3.9.0.8 AI Custom Update Fix 1`, `build_status=built`, EXE `size>0`, 실제 SHA-256 일치를 확인한 뒤 업로드한다.

6) **원격 main 선행 커밋 때문에 `-PushBranch`가 막힐 때**

```powershell
git fetch origin
git rebase origin/main
git push origin main
```

재정렬 후 릴리즈를 다시 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/release_tag_push.ps1 -Version 3.9.0.8 -Branch main -PushBranch
```

주의
- 이 스크립트는 `.git`이 있는 실제 클라이언트 Git 작업본에서만 동작합니다.
- 스크립트 실행 시 `config/app_version.py`의 `RELEASE_VERSION`과 요청한 `-Version`이 다르면 즉시 실패합니다.
- 스크립트 실행 시 `scripts/doc_consistency_check.py`를 자동 실행하며, 문서/버전 불일치 시 태그를 생성하지 않습니다.
- 충돌 백업 파일(`*_Conflict.*`, `*.orig`)이나 미해결 merge 상태가 있으면 릴리즈 커밋 전에 즉시 실패합니다.

### 표준 빌드

#### 1. 단일 빌드 스크립트 사용
```bash
# Windows 빌드 머신에서 실행
python build_safe.py --platform windows --gate-profile release
```

직접 `pyinstaller`를 호출하면 release gate, 민감정보 제외, 플랫폼별 hidden import 정책을 건너뛰므로 지원하지 않습니다.

## 📁 빌드 설정

### aiautotrade.spec 파일
```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config', 'config'),
        ('trading/exchanges', 'trading/exchanges'),
        ('ui', 'ui'),
        ('icon.ico', '.'),
        ('icon.png', '.'),
  ],
  hiddenimports=[
        'websockets',
        'websocket',
        'websocket_client',
        'binance',
        'ccxt',
        'ccxt.binance',
        'ccxt.upbit',
        'ccxt.bithumb',
        'trading.exchange_manager',
        'trading.api_signal_manager',
        'trading.exchanges.base_exchange',
        'trading.exchanges.exchange_factory',
        'openai',
        'requests',
        'psutil',
        'sqlite3',
        'threading',
        'json',
        'datetime',
        'logging',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
  excludes=['PyQt5','PySide6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AITrading',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico'
)
```

참고
- `aiautotrade.spec`은 `build_safe.py`로 생성한 Windows 참고본이며 직접 수정하지 않습니다.
- 실제 빌드 시에도 같은 생성기가 임시 `aiautotrade_safe.spec`을 생성합니다.
- Python 패키지는 Analysis/hiddenimports로 수집하고 `datas`로 전체 소스 폴더를 중복 포함하지 않습니다.
- macOS에서 `win32_setctime`는 포함하지 않습니다. Windows 전용입니다.
- 동적 스펙에는 증권 어댑터 4종(키움/신한/미래에셋/한국투자증권) hidden import가 포함됩니다.

## 🔧 빌드 옵션

### 기본 옵션
- **--onefile**: 단일 실행 파일 생성
- **--windowed**: 콘솔 창 숨김 (GUI 앱)
- **--name**: 실행 파일 이름 지정
- **--icon**: 아이콘 파일 지정

### 고급 옵션
- **--add-data**: 추가 데이터 파일 포함
- **--hidden-import**: 숨겨진 모듈 명시적 포함
- **--exclude-module**: 불필요한 모듈 제외
- **--upx-dir**: UPX 압축 도구 경로

### 플랫폼별 옵션

#### Windows
```bash
# Windows 전용 옵션
--win-private-assemblies
--win-no-prefer-redirects
--version-file version.txt
```

#### macOS
```bash
# macOS 전용 옵션
--osx-bundle-identifier com.noahai.trading
--codesign-identity "Developer ID"
--entitlements-file entitlements.plist
```

#### Linux
```bash
# Linux 전용 옵션
--linux-binary-name AITrading
--linux-icon icon.png
```

## 📦 배포 패키지

### Windows 배포
```
AITrading_Windows/
├── AITrading.exe          # 메인 실행 파일
├── README.txt             # 사용법 안내
├── install_windows.bat    # 설치 스크립트
└── requirements_windows.txt # 의존성 목록
```

### macOS 배포
```
AITrading_macOS/
├── AITrading.app          # 앱 번들
├── README.txt             # 사용법 안내
└── install_macos.sh       # 설치 스크립트
```

### Linux 배포
```
AITrading_Linux/
├── AITrading              # 실행 파일
├── README.txt             # 사용법 안내
└── install_linux.sh       # 설치 스크립트
```

## 🔍 빌드 검증

### 기능 테스트
```bash
# 빌드된 실행 파일 테스트
./AITrading --test

# 또는 Python으로 테스트
python -m pytest tests/
```

### 성능 테스트
```bash
# 메모리 사용량 확인
python -m memory_profiler main.py

# 실행 시간 측정
python -m cProfile main.py
```

### 보안 검사
```bash
# 의존성 취약점 검사
pip install safety
safety check

# 코드 품질 검사
pip install flake8
flake8 .
```

## 🚨 문제 해결

### 키움증권 OpenAPI+ 연결 오류 (배포 후 사용자 환경)

배포된 실행 파일에서 키움증권 연결에 실패하는 경우, 원인은 **앱이 아닌 사용자 PC 환경**에 있습니다.

| 원인 | 증상 | 해결 |
|------|------|------|
| ① OpenAPI+ 미설치 | `QAxWidget has no attribute` | 키움증권 홈페이지(www1.kiwoom.com) → 다운로드 → Open API 설치 |
| ② OCX 미등록 | 동일 오류, 설치 후에도 반복 | OpenAPI+ 설치 파일을 **관리자 권한으로 실행**하여 재설치 |
| ③ OS 제약 | macOS/Linux에서 실행 | 키움 OpenAPI+는 **Windows 전용** COM/ActiveX 구조 — 해당 OS에서는 mock 모드만 사용 가능 |
| ④ 32/64-bit 불일치 | 연결 시도 자체 실패 | KOA Studio로 먼저 연결 테스트 → Python 비트와 동일한 OpenAPI+ 재설치 |
| ⑤ 계정/인증서 오류 | 로그인 실패 코드 | 계정 ID/비밀번호/공인인증서 비밀번호/계좌번호 재확인 |

> **앱 내 안내 경로**: 사용자 매뉴얼(증권/주식/ETF 탭 → 10번 연결 오류 자가 진단),  
> AI 어시스턴트에게 "키움 연결이 안 돼요"로 질문 시 단계별 안내 제공

#### 빌드 차원에서 할 수 있는 것 vs 없는 것

```
✅ 할 수 있는 것 (빌드/코드에서 처리됨)
  - pykiwoom, PyQt5, PyQt5.QAxContainer hiddenimport 포함 (build_safe.py)
  - 연결 실패 시 앱 크래시 없이 graceful fallback (lazy import)
  - 에러 코드별 사용자 친화 메시지 로그 출력 (kiwoom_stock_adapter.py)
  - mock 모드 자동 전환 (Windows 아닌 OS 감지 시)

❌ 할 수 없는 것 (사용자 PC 환경 의존)
  - 키움증권 OpenAPI+ COM 컴포넌트 설치/등록
  - KOA Studio 정상 동작 여부
```

### 일반적인 빌드 오류

#### 1. 모듈을 찾을 수 없음
```
ModuleNotFoundError: No module named 'xxx'
```
**해결방법**:
```bash
# hiddenimports에 모듈 추가
--hidden-import xxx

# 또는 requirements.txt에 패키지 추가
pip install xxx
```

#### 2. 데이터 파일을 찾을 수 없음
```
FileNotFoundError: [Errno 2] No such file or directory
```
**해결방법**:
```bash
# add-data에 파일 추가
--add-data "path/to/file;destination"
```

#### 3. 아이콘 파일 오류
```
OSError: cannot identify image file
```
**해결방법**:
- 아이콘 파일 형식 확인 (.ico, .png)
- 파일 경로 확인
- 파일 손상 여부 확인

### 빌드 최적화

#### 파일 크기 최적화
```bash
# UPX 압축 사용
--upx-dir /path/to/upx

# 불필요한 모듈 제외
--exclude-module tkinter
--exclude-module matplotlib
```

#### 실행 속도 최적화
```bash
# 바이트코드 최적화
--optimize 2

# 캐시 사용
--cache-path /tmp/pyinstaller-cache
```

## �️ 배포 게이트 (release_gate.py)

`build_safe.py` 실행 시 빌드 전에 `scripts/release_gate.py`가 자동으로 실행됩니다.  
이 워크스페이스처럼 `.git`이 없는 복사본에서 빌드할 때는 `SYNC_GUARD_CHANGED_FILES` 또는 `--changed-files`로 변경 파일 목록을 명시해야 `SYNC_GUARD`가 통과합니다.
PowerShell 예시:

```powershell
$env:SYNC_GUARD_CHANGED_FILES='docs/CHANGELOG.md,docs/USER_GUIDE.md,USER_GUIDE_AI_EXECUTION.md,ui/widgets/user_manual_widget.py'
python build_safe.py --platform windows
```

반복 실행 시에는 위 환경변수 수동 설정 대신 `scripts/build_windows_safe.ps1` 사용을 권장합니다.

게이트를 직접 실행하려면:

```bash
# 개발 환경 검증 (기본)
python scripts/release_gate.py --profile dev

# 키 입력 전 최종 완료용 (mock 하드닝 + 문서 정합성 포함)
python scripts/release_gate.py --profile prekey

# 배포 직전 엄격 검증 (실브로커 readiness 필수)
python scripts/release_gate.py --profile release
```

### 게이트 단계별 설명

| 단계 | 필수 | 설명 |
|------|------|------|
| `TEST_STOCK` | ✅ 항상 | 주식 관련 pytest 회귀 테스트 실행 |
| `MODE_MATRIX` | ✅ 항상 | 브로커×API 타입 조합 매트릭스 검증 |
| `MOCK_HARDENING` | prekey/release | 자격증명 없이 mock 완전 동작 확인 |
| `EXCHANGE_READINESS_REPORT` | prekey/release | 거래소 진단 보고서 |
| `DOC_CONSISTENCY` | prekey/release | 문서 정합성 검사 |
| `READINESS` | release만 필수 | 실브로커 준비도 (dev에서는 참고용) |

### ⚠️ 크로스 플랫폼 주의사항 (macOS ↔ Windows)

**문제**: macOS에서 개발 후 Windows에서 빌드하면 `TEST_STOCK` 단계가 실패할 수 있습니다.

**원인**: `release_gate.py`의 venv Python 경로가 플랫폼마다 다릅니다.

| 플랫폼 | venv Python 경로 |
|--------|------------------|
| macOS / Linux | `.venv/bin/python` |
| Windows | `.venv/Scripts/python.exe` |

**2026-04-30 수정 완료** — 탐지 우선순위를 아래와 같이 수정하여 두 플랫폼 모두 자동 처리됩니다:
```python
# scripts/release_gate.py
_venv_win  = ROOT / ".venv" / "Scripts" / "python.exe"   # Windows
_venv_unix = ROOT / ".venv" / "bin" / "python"            # macOS/Linux
python_cmd = str(
    _venv_win  if _venv_win.exists()  else
    _venv_unix if _venv_unix.exists() else
    sys.executable  # fallback: 시스템 Python
)
```

**macOS에서 패치 시 체크리스트**:
- [ ] `scripts/release_gate.py` python_cmd 탐지 로직에 `Scripts/python.exe` 경로가 포함되어 있는지 확인
- [ ] venv에 `pytest`가 설치되어 있는지 확인 (`python -m pytest --version`)
- [ ] Windows 환경에서 `python scripts/release_gate.py --profile dev` 실행하여 `PASS` 확인
- [ ] git 없는 복사본에서 빌드할 경우 `SYNC_GUARD_CHANGED_FILES`를 설정하여 `SYNC_GUARD` 입력을 제공했는지 확인

### macOS 개발 → Windows 빌드에서 문제가 반복되는 이유

핵심은 "소스코드 차이"보다 "실행 환경 차이"입니다.

1) Python/venv 경로 차이
- macOS/Linux: `.venv/bin/python`
- Windows: `.venv/Scripts/python.exe`
- 경로 탐지 로직이 누락되면 테스트/게이트 실행 자체가 실패할 수 있습니다.

2) 의존성 집합 차이
- macOS에서 `requirements.txt`만 맞춰도, Windows 빌드 시에는 `requirements_windows.txt`(pykiwoom/PyQt5/win32-setctime 포함)가 추가로 필요합니다.

3) 런타임 외부 컴포넌트 차이(키움 OpenAPI+)
- 키움은 Python 패키지만으로 끝나지 않고, 사용자 PC의 OCX/COM 설치/등록/비트수 일치가 필요합니다.
- 따라서 빌드 성공과 실브로커 연결 성공은 별개의 단계입니다.

4) `.git` 유무 차이
- 복사본 워크스페이스(`.git` 없음)에서는 `SYNC_GUARD_CHANGED_FILES`를 반드시 주입해야 strict gate를 통과합니다.

5) 문서-버전 정합성 차이
- `config/app_version.py`와 `docs/USER_GUIDE.md`의 버전 문구가 정확히 일치하지 않으면 `DOC_CONSISTENCY`에서 실패합니다.

### 게이트 로그 해석 기준 (중요)

- `[RELEASE_GATE] FAIL | DOC_CONSISTENCY`:
  - 실제 차단 원인입니다. 문서/버전 정합성 불일치 해결이 먼저입니다.
- `RequestsDependencyWarning`:
  - 경고이며 현재 게이트 차단 원인이 아닙니다.
- `[SMOKE] ... FAIL` 또는 키움 ActiveX 실패 로그:
  - `prekey` 프로필에서는 참고 출력일 수 있습니다(필수 실패로 집계되지 않음).
  - `release` 프로필에서는 strict 조건에 따라 차단될 수 있으므로 배포 직전에는 별도 점검이 필요합니다.

### 버전 정합성 상시 점검 절차 (항상 실행 권장)

태그 생성/푸시 전 아래 3단계를 고정 절차로 실행하세요.

```bash
# 1) 기준 버전과 핵심 문서 표기 정합성 검사 (실패 시 즉시 중단)
python scripts/doc_consistency_check.py

# 2) 배포 게이트 prekey 프로필 확인
python scripts/release_gate.py --profile prekey

# 3) 실제 Windows 빌드 래퍼 경로로 최종 확인
powershell -ExecutionPolicy Bypass -File scripts/build_windows_safe.ps1
```

문서 직접 확인(선택):

```bash
python -c "import pathlib; from config.app_version import RELEASE_VERSION as V; t=pathlib.Path('docs/USER_GUIDE.md').read_text(encoding='utf-8'); s=f'현재 배포 기준 버전: **v{V}**'; print('OK' if s in t else f'MISSING: {s}'); raise SystemExit(0 if s in t else 1)"
```

---

## �📋 빌드 체크리스트

### 빌드 전 확인사항
- [ ] 모든 의존성 설치 완료
- [ ] 설정 파일 업데이트
- [ ] 아이콘 파일 준비
- [ ] 테스트 코드 실행

### 빌드 후 확인사항
- [ ] 실행 파일 생성 확인
- [ ] 기능 테스트 완료
- [ ] 성능 테스트 완료
- [ ] 보안 검사 완료

### 배포 전 확인사항
- [ ] 사용자 가이드 업데이트
- [ ] 설치 스크립트 테스트
- [ ] 다중 플랫폼 테스트
- [ ] 버전 정보 업데이트

## 🔄 CI/CD 통합

### GitHub Actions
```yaml
name: Build and Release

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [windows-latest, macos-latest, ubuntu-latest]
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.8
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install pyinstaller
    
    - name: Build executable
      run: python build_safe.py
    
    - name: Upload artifacts
      uses: actions/upload-artifact@v2
      with:
        name: AITrading-${{ matrix.os }}
        path: dist/
```

### 자동화 스크립트
```bash
#!/bin/bash
# build_all.sh

echo "Building for all platforms..."

# Windows
echo "Building for Windows..."
python build_safe.py --platform windows

# macOS
echo "Building for macOS..."
python build_safe.py --platform macos

# Linux
echo "Building for Linux..."
python build_safe.py --platform linux

echo "Build complete!"
```
