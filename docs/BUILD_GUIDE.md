## 2026-10-14 - v3.9.2.14 증권 무거래·전략 운용 피드백 후속 (소스 후보)

현재 소스 후보 버전: **v3.9.2.14**
현재 공개 버전: **v3.9.2.13**
현재 소스 후보: v3.9.2.14 · 현재 공개 기반: v3.9.2.13 · Stock Analysis History and Strategy Controls · updater 3.9.214 · renderer 3.9.2.14-ui.20261014.2.

공개 v3.9.2.13은 GitHub 최신판 `33d351c0b606a619f16c00fc7b6e99aa10086dad`이며 이번 .14는 별도 후속 후보다. .13에서 이미 제공하던 전략 승인/PAPER 시작·일시정지/이어가기·검증 후 적용/해제를 새 기능처럼 중복 구현하지 않는다. 최신 공개 소스에서 증권 일봉 연결 누락과 PAPER 청산 손익 필드 불일치를 재현해 수정했다. 키움의 전일가 입력 누락도 공식 OpenAPI+ 전일가 함수로 보완했다. 기존 거래 임계값과 주문 전 위험 검사는 유지한다. 이번 후속에서 PAPER 관찰 목표와 최종 적용 조건을 분리한다.

증권 4기관(키움·한국투자·미래에셋·신한)의 실제 `get_daily_candles`를 기본 분석에 연결한다. 완료 일봉의 시간순·유한 양수 종가와 실제 최근 20봉 평균 거래량을 사용하고, 실패/부족은 `technical_history`로 표시한다. 증권 PAPER TP/SL은 최신 가격과 비용을 반영한 `net_pnl_percent`를 공통 청산 정책의 `pnl_rate`에 전달한다. 평가 실패는 `paper_exit_valuation_unavailable`로 보존한다. 실제 계정의 무거래 원인을 발견된 결함만으로 단정하지 않는다.

PAPER 시험 기간은 1·3·7일 중 선택하는 관찰 목표다(기본 7일). 승인 후 바로 시작하며 목표 도달 시 화면에서 검토를 안내하고 검증은 계속한다. 사용자가 직접 일시정지하며 자동 적용하지 않는다. 최종 적용은 기간과 별도로 실제 원장의 유효 청산 최소 3건·비용/손익 대조·위험 근거 기록 및 위반 없음·실행 규칙·사용자 확인을 검사한다. 최소 3건과 선택 기간은 통계적 충분성이나 수익을 보장하지 않는다. 정상 신호 대기에도 표본은 늘지 않을 수 있다. 기본 자동매매는 독립적으로 실행된다.

시간은 두 값으로 구분한다. **등록 후 경과**는 일시정지를 뺀 허용 구간의 달력 시간으로 앱 종료 시간이 포함된다. **실제 진입 후보 규칙 평가시간**은 정상 완료된 후보 평가 호출 구간을 중복 없이 합산한 시간이다. 대기·오프라인·보유시간은 합산하지 않으며 과거 실행시간을 추정하지 않는다. 미기록/집계 실패는 0으로 표시하지 않는다. 최근 평가 시각은 사용자 시간대로 표시한다.

적용된 전략의 기존 「적용 해제」를 「전략 적용 일시정지」로 명확히 안내하고 검증 버전의 재적용을 연결한다. 신규 진입 풀에서 그 전략만 제외하며 보유 포지션 청산계획·원장·검증 근거를 보존한다. 기본 AI·다른 전략은 계속 거래할 수 있다. 기관 전체 중지와 다르며 시간 지정 자동 만료/자동 재개는 미구현이다. 새 상태머신·LIVE 우회 권한은 만들지 않는다. 내장 어시스턴트에 1·3·7일/시간 구분/일시정지·증권 무거래 안내를 추가한다.

[테스터 인수와 실행 기준](DEPLOY_CHECKLIST.md) · [검증 근거](../reports/v39214-paper-trial-20261014/validation.json). Windows .14 빌드·게시·실기관/OCX·고객 계정 복구·다른 배포 사용자의 반응은 확인되지 않았다. 고객이 키움·한국투자 모두 PAPER라고 확인했다(2026-10-14). 최근 진입 보류 문구는 전달 대기이며 개별 무거래 원인 확정·복구 확인은 아직 아니다. 아래 .13 이하 상태·수치는 해당 당시 이력이다.

원본 정합성 후속(2026-10-14): 공개 .13과 다른 두 파일을 원본 보존 후 .14 기준으로 맞췄다. 진단 파일의 `entry_activity`·23개 사유 코드 삭제와 `monitored_cycle()` 호출 계약 불일치, 화면의 `newPaperSession` callback 삭제가 확인됐다. 원본의 미추적 `test_entry_diagnostics_startup.py` 3개 검사에서 실패 주기를 정상 완료로 집계하지 않는 수정의 필요성이 확인됐다. 이 동작과 `tests/__init__.py`·`pytest.ini`의 기존/패키지형 test import 호환 설정을 보존하고 선택 source 호출 계약·23개 진단·무거래 함수는 공개 구현과 병합했다. 화면의 삭제된 callback은 복구했다. 과거 UI 회귀의 .8 고정 버전 검사는 현재 package 버전에 맞추고 출력 폴더를 분리했다. 누가/어떤 동기화 작업이 바꿨는지는 비 Git 원본에 기록이 없어 미확정이다. 이전 절차의 동기화 철회는 당시 이력이며 이번 최종 결과는 `reports/v39214-paper-trial-20261014/handoff.json`이다.

원본 폴더의 제품 소스·릴리스 입력은 검증한 .14 Git 작업트리와 같게 동기화한다. 고객 설정·원장·키·공개 .13 설치기/manifest는 복사 대상으로 삼지 않는다. 원본은 Git 저장소가 아니므로 **Windows 공식 빌드·게시에는 아래의 깨끗한 Git 복원본을 사용한다.** 원본의 `.venv`, `node_modules`, `dist`, `deploy/release-manifest.json`을 새 빌드 폴더로 가져오지 않는다. .13 manifest 원본은 저장소의 hash-pinned archive와 복구 스크립트로 준비한다.

### 3.9.2.14 Windows에서 사용할 소스와 명령

전달 자료는 동기화 폴더의 `reports/v39214-paper-trial-20261014/` 안에 있는 **`handoff.json`과 `v39214-paper-trial.bundle`**이다. 앞선 candidate/reconciled bundle은 이전 이력이다. 이번 PAPER 기간 선택 후속을 포함한 paper-trial bundle을 사용한다. 아래 `$handoffPath`만 해당 Windows PC의 실제 파일 경로로 바꾼다. PowerShell 5.1 호환 명령이며 네이티브 명령 실패 때 즉시 중단한다. `C:\NoahAI\client-v39214`는 새 폴더여야 한다. 기존 저장소를 reset/clean하지 않는다.

```powershell
$ErrorActionPreference = "Stop"
function Invoke-CandidateChecked([scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $LASTEXITCODE" }
}
$handoffPath = "D:\SynologyDrive\Works\noahai_client\reports\v39214-paper-trial-20261014\handoff.json"
$handoffPath = (Resolve-Path -LiteralPath $handoffPath).Path
$handoff = Get-Content -LiteralPath $handoffPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($handoff.source_version -ne "3.9.2.14") { throw "Wrong handoff version" }
$bundlePath = Join-Path (Split-Path -Parent $handoffPath) $handoff.bundle
if ((Get-FileHash -LiteralPath $bundlePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $handoff.bundle_sha256) { throw "Bundle hash mismatch" }
$buildRoot = "C:\NoahAI\client-v39214"
if (Test-Path -LiteralPath $buildRoot) { throw "Use a new empty build path" }
New-Item -ItemType Directory -Path (Split-Path -Parent $buildRoot) -Force | Out-Null
Invoke-CandidateChecked { git clone --filter=blob:none --no-checkout https://github.com/nwsoft/ai-trading-client.git $buildRoot }
Set-Location -LiteralPath $buildRoot
Invoke-CandidateChecked { git fetch origin $handoff.public_commit }
Invoke-CandidateChecked { git bundle verify $bundlePath }
$branchRef = "{0}:refs/heads/{0}" -f $handoff.branch
Invoke-CandidateChecked { git fetch $bundlePath $branchRef }
Invoke-CandidateChecked { git switch $handoff.branch }
$actualCommit = (Invoke-CandidateChecked { git rev-parse HEAD } | Out-String).Trim()
if ($actualCommit -ne $handoff.source_commit) { throw "Candidate commit mismatch" }
if ((Invoke-CandidateChecked { git status --porcelain } | Out-String).Trim()) { throw "Build source is dirty" }
```

Windows 10/11 x64, Python **3.11 x64·x86**, Node **22.12 이상**, Git·GitHub CLI, Visual Studio Build Tools/VC143 CRT를 준비한다. 같은 PowerShell 창에서 이어서 실행한다. `NOAHAI_PYTHON_X86`가 기존 다른 환경을 가리키면 올바른 3.11 x86 실행파일로 조정해야 한다. 아래는 기본 Python Launcher의 x86을 사용하는 경우다.

```powershell
Invoke-CandidateChecked { py -3.11-64 -m venv .venv }
$env:Path = (Resolve-Path .venv\Scripts).Path + ";" + $env:Path
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Invoke-CandidateChecked { python -c "import struct,sys; assert sys.version_info[:2]==(3,11) and struct.calcsize('P')==8" }
Invoke-CandidateChecked { python -m pip install -r requirements_windows.txt }
Invoke-CandidateChecked { py -3.11-32 -m pip install -r requirements_kiwoom_x86.txt }
$env:NOAHAI_PYTHON_X86 = (Invoke-CandidateChecked { py -3.11-32 -c "import sys; print(sys.executable)" } | Out-String).Trim()
$env:NOAHAI_CANDIDATE_HANDOFF = $handoffPath
Invoke-CandidateChecked { python -c "import json,os; from pathlib import Path; from scripts.verify_release_provenance import verify_source; h=json.load(open(os.environ['NOAHAI_CANDIDATE_HANDOFF'],encoding='utf-8')); print(verify_source(Path('.'),dict(source_revision=h['source_commit'],source_fingerprint=h['source_fingerprint'])))" }
Invoke-CandidateChecked { python scripts/restore_previous_release_asset.py }
Invoke-CandidateChecked { powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1 }
```

빌드 스크립트가 locked npm 설치·Node/Python 전체 검사·skip 감사·문서·source·npm 감사·x64 엔진·키움 x86 호스트·IPC smoke·Electron 설치기·PE/아이콘·메타데이터를 검사한다. `SkipTests`, `SkipEngineBuild`, `SkipNpmCi`, `AllowMissingKiwoomHost`를 사용하지 않는다. 기본 자동 검사만으로 실제 OCX 로그인·기관 PAPER 운용·24/72h가 통과한 것은 아니다. Windows 검사 수는 해당 PC의 `reports/windows-full-tests.xml`과 `reports/windows-skipped-tests.json`에 기록된 결과를 따른다.

성공 산출물은 `deploy/web-release/NoahAI-3.9.2.14-Setup.exe`, 같은 이름의 `.blockmap`, `latest.yml`(updater **3.9.214**), `deploy/release-manifest.json`이다. manifest의 `version`, `source_revision`, `source_fingerprint`, `automated_checks_passed=true`, 실제 PE/호스트 검증과 파일 해시를 확인한다. 이전 .13 설치기는 자동 복구/해시 검사하여 보존한다. 격리 Windows에서 설치·시작·종료·PAPER 주문 모드와 기존 기록 보존을 확인한다. 고객 설정/실계좌 주문을 시험하지 않는다.

**배포 명령:** 아래는 stable/latest를 실제로 게시한다. 이번 Mac 작업에서는 실행하지 않는다. 빌드한 동일 커밋을 원격에 먼저 올려야 출처 검증이 통과한다. 빌드 뒤 소스를 수정했다면 커밋·재빌드부터 다시 진행한다.

```powershell
Invoke-CandidateChecked { gh auth status --hostname github.com }
Invoke-CandidateChecked { git push -u origin $handoff.branch }
Invoke-CandidateChecked { powershell -ExecutionPolicy Bypass -File scripts/release_windows.ps1 }
```

게시 스크립트는 원격 커밋/태그·해시·설치기·blockmap·latest/manifest를 검증하고 stable/latest를 갱신한다. 이미 공개된 .14의 태그/설치기를 임의로 교체하지 않는다. 스크립트가 `SUCCESS`를 출력하고 공개 latest/list/Atom·업데이트 SHA512 대조가 통과해야 게시 완료다. 도중 실패하면 출력 원인을 확인하고 실패한 부분부터 대응하며 기존 태그를 강제로 옮기지 않는다.

테스터는 로컬 .14 설치기 공유 또는 게시 후 설치본으로 키움·한국투자 PAPER와 24/72h를 검증한다. 이 검증을 위해 배포 전 72시간 대기할 필요는 없다. 실제 인수의 정상/실패/NOT_RUN 기준은 [DEPLOY_CHECKLIST의 .14 절](DEPLOY_CHECKLIST.md)을 따른다. 게시 스크립트는 남은 외부 인수를 `pending`으로 표시할 수 있으며 자동 완료로 바꾸지 않는다.

## 2026-10-12 — v3.9.2.13 Windows 빌드·stable/latest 게시

최신 사용자 명시 요청으로 .13 전체 Windows 빌드와 `nwsoft/ai-trading-client` 정식 stable/latest 게시를 승인했다. 아래 소스 전용·push 제외 기록은 작성 당시 이력이다. 공개 .12 기반 인계 커밋 `385da2e`를 고유 작업트리에 복원하고 동기화 안정성을 60초 이상 확인한다. 공개 manifest 원본 보존 규칙을 유지한다.

Node >=22.12, Python 3.11 x64 및 `NOAHAI_PYTHON_X86`의 Python311-32, 실제 CCXT 4.5.50/aiohttp 3.14.5 환경에서 `powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`을 생략 옵션 없이 실행한다. 실제 설치기·PE·7개 아이콘·추출 payload·엔진·renderer·출처 검증 후 정확한 소스 브랜치를 push하고 `scripts/release_windows.ps1`로 게시한다. 공개 네 파일을 다시 다운로드해 SHA256 및 updater SHA512를 대조한다. 결과 정본: `reports/v39213-windows-publication-20261012.json`.

체크리스트는 빌드 입력 시점의 ID·상태·개수 snapshot이며 실제 자동 빌드/게시 결과는 실행 보고서에 별도로 기록한다. 수동 설치/자동 업데이트/롤백·OCX/기관·실마이크·24/72h·외부 인수 완료를 주장하지 않는다. 실행 중인 사용자 앱 설치, 실주문, 서버 배포, 유료 서명은 실행 범위에 없다.

## 2026-10-12 — v3.9.2.13 배포 인수 상태 정합성 (소스 후보 이력)

현재 소스 후보 버전: **v3.9.2.13**
현재 공개 버전: **v3.9.2.12**
현재 소스 후보: v3.9.2.13 · 현재 공개 기반: v3.9.2.12 · updater 3.9.213 · renderer 3.9.2.13-ui.20261012.1.

공개 .12는 2026-10-12 11:21:46 KST 게시된 5a645b455b9800696b5cad6f1b06946fb2d32623이다. .13은 별도 후속 후보이며 새 Windows 빌드·게시·설치는 미실시다. 기존 .12의 거래 보호·PAPER 안내·내 돈 계획과 Windows junction 보호를 유지한다. 수정 범위는 인수 체크리스트의 ID·상태·미완료 개수를 같은 원본에서 생성하는 빌드/게시 계약, .12 공개 원본 보존 및 .13 버전·안내 정합성이다.

외부 인수 ‘9개’는 공개 .12 당시 미완료 체크리스트 줄 수이며 6개 일반 범주와 다른 목록이었다. 현재 재확인한 .12 SDK·빌드·게시 근거 3개와 실제 테스터 인수 6개를 구분한다. 완료하지 않은 설치/기관/장시간 검증을 통과로 승계하지 않는다. [정확한 9항목·실행/정상/실패 기준](DEPLOY_CHECKLIST.md#acceptance-v39213), [검증 근거](../reports/v39213-acceptance-20261012/validation.json).

Windows 인계: 공개 .12를 덮어 빌드하지 않고 별도 .13 소스/출력으로 빌드한다. 최종 로컬 커밋과 소스 지문은 `reports/v39213-acceptance-20261012/handoff.json`에서 확인한다. 후보 bundle은 공개 .12 커밋을 가진 저장소에서만 적용하는 증분 Git 자료이며 기존 .12 후보 bundle은 계속 폐기 상태다. `git bundle verify` → 별도 작업 브랜치/작업트리 복원 → 커밋/지문 대조 → `python scripts/restore_previous_release_asset.py` → 검사 생략 없는 `scripts/build_web_ui_windows.ps1` 순서다. 사용자 변경이 있는 체크아웃을 reset/clean하지 않는다. 이전 .12 설치기는 해시 고정 보존한다. 이번 작업은 push·태그·게시를 수행하지 않는다.

아래 .12 이하의 후보·공개·미게시 상태와 검사 수치는 해당 작성 당시 이력이다.

## 2026-10-12 공개 .12 확인 후 빌드 기준 정정

정식 공개판은 **3.9.2.12**, 게시 커밋은 `5a645b455b9800696b5cad6f1b06946fb2d32623`이다. Windows 쪽에서 거래소/주문 보호, 공개 manifest 원본 보존, PAPER 도움말 LF 출력 및 로그 junction 보호를 이미 포함해 게시했다. 이 Mac 작업에서 이를 새로 배포한 것으로 보고하지 않는다. 게시 중 준비했던 이전 .12 인계 helper는 철회·비활성화했으며 동일 버전의 다른 설치기를 만들지 않는다.

추가 작업은 테스트·문서뿐이며 제품 버전을 올리지 않는다. 원본의 `.gitattributes`·Windows workflow를 게시 소스와 맞춰 릴리스 입력 지문 `bce466226f9949bd6a2819c819ab50da18edb143336421eeb1b20b290d16d62e`를 확인했다. 현재 테스터는 공개 .12로 설치·업데이트·복원·24/72h PAPER 인수를 진행한다. 후속 런타임 수정이 생기면 다음 버전 후보로 분리한다. 아래 .12 빌드 준비/미게시 표기는 과거 이력이다. [게시 후 검증](../reports/v39212-post-release-audit-20261012/validation.json).

## 2026-10-12 — 3.9.2.12 Windows 정식 빌드·게시

최신 사용자 요청은 전체 자동 검사 후 stable/latest 게시를 명시적으로 승인한다. 아래 소스 전용·미게시 문장은 작성 당시 이력이다. 문서의 `fix/v3.9.2.12-exchange-controls-20261012` 브랜치는 로컬·원격에 없어, 공개 `.11` 커밋 `baa3b1754c188f579169639ba52cbe908f938931`에서 고유 작업트리 `release/v3.9.2.12-windows-20261012-now`를 만들고 60초 이상 안정 확인한 최신 동기화 입력을 반영한다.

Node >=22.12, x64 Python과 Python311-32를 준비하고 `ccxt==4.5.50`을 실제 설치한다. Windows aiohttp 핀은 CCXT 최소 요구 조건을 충족하는 3.14.5로 맞춘다. `scripts/build_windows.ps1`를 생략 옵션 없이 실행하고 실제 엔진 내부 CCXT·PE·아이콘·설치기 추출·renderer·해시를 검증한 뒤 정확한 소스 커밋을 push하고 `scripts/release_windows.ps1`로 게시한다. 실제 결과는 `reports/v39212-windows-publication-20261012.json`에 기록한다. 실행 중인 앱 설치·실계좌/주문·서버 배포는 제외하며 OCX·실제 설치/업데이트/롤백·마이크·24/72h·외부 인수는 미실시 대기다.

현재 공개판은 **3.9.2.11**, 새 소스 후보는 **3.9.2.12 / updater 3.9.212 / renderer 3.9.2.12-ui.20261012.2**다. 거래소 변경·주문 제출 보호와 기존 PAPER/내 돈 계획 수정을 함께 포함한다. Git 작업 브랜치 `fix/v3.9.2.12-exchange-controls-20261012`의 최신 로컬 커밋을 사용한다. Mac 원본 폴더에는 동일 릴리스 입력을 동기화했으며 SOURCE_IDENTITY와 [실행 증거](../reports/exchange-audit-20261012/validation.json)를 대조한다. 이 후보의 원격 푸시·게시·운영 배포는 실행하지 않았다. 아래 .11 이하의 게시 승인·산출물은 당시 이력이다.

Windows에서 `powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`를 **생략 옵션 없이** 실행한다. 이는 빌드 경로이며 게시 스크립트를 자동 승인하는 문장이 아니다. ccxt==4.5.50 실제 설치·동결, 전체 검사/Windows PE, x64 엔진·x86 키움 호스트·NSIS, UI 지문·설치/업데이트/복원을 확인한다. 이전 공개 .11 manifest/설치기를 .12로 재명명하지 않는다. Mac의 TypeScript/Vite·모의 주문·공개 REST·headless 화면 통과는 Windows 산출물 인수를 대신하지 않는다.

새 설치본 기본 확인 → 테스터 전달 → 24/72h PAPER 운용 검증 순서다. 배포 전에 테스터의 72h를 요구하지 않는다. 인증 데모/실기관 검증은 자격증명·권한을 갖춘 별도 환경에서 진행하며 이번 점검에서는 실계정 주문·취소·청산을 수행하지 않았다. [수정·미실시 경계](TRADING_FLOW.md#exchange-change-audit-20261012) · [배포 체크리스트](DEPLOY_CHECKLIST.md).

## 2026-10-11 — v3.9.2.11 Windows 즉시 빌드·정식 게시

최신 명시 요청은 Codex의 Windows 전체 빌드와 `nwsoft/ai-trading-client` stable/latest 게시를 승인하며 아래 과거 소스 전용·사용자 게시 담당 기록을 이번 실행에 한해 대체한다. 공개 기반은 .10, 제품/PE .11, updater 3.9.211, renderer 정본은 `webui/src/uiBuild.ts`의 `3.9.2.11-ui.20261011.4`다.

깨끗한 .10 기반 작업트리에서 최신 동기화 입력을 커밋하고 `scripts/build_windows.ps1`를 생략 옵션 없이 실행한다. 빌드 통과 후 해당 브랜치를 push하고 `scripts/release_windows.ps1`로 게시한다. 실제 결과는 `reports/v39211-windows-publication-20261011.json`을 따른다. 실행 중인 클라이언트에 설치하지 않는다. 실제 설치/업데이트/롤백·OCX·실계좌·실마이크·24/72시간·외부 인수는 미실시 대기이며 stable 게시의 추가 선행 조건으로 바꾸지 않는다. 외부 사이트/허브 서버는 배포하지 않는다. 아래 내용은 작성 당시 이력이다.

## 2026-10-10 — v3.9.2.11 거래 신뢰성·통합 금융비서 연결

현재 소스 후보 버전: **v3.9.2.11**
현재 공개 버전: **v3.9.2.10**
현재 소스 후보: v3.9.2.11 · 현재 공개 기반: v3.9.2.10. 제품/엔진/PE 3.9.2.11, updater 3.9.211, renderer 3.9.2.11-ui.20261010.2.

**통합 금융비서 내부 연결:** 상단 「내 금융비서」에서 저장 근거 브리핑·거래 진단·보유 종목 자료·계획 재점검을 읽고 기존 금융 비교·저장·상담 준비와 전략 초안 검토로 이어간다. 같은 입력 지문의 저장 전략 재생 비교, 같은 통화의 배분 가정·비용 비교, 음성 입력 후 조건 검토를 추가한다. 외부 기관 계약·개인 견적·실접수·송금/가입 실행은 별도다. [범위·기술·인수 정본](V39211_FINANCIAL_COMPANION_PLAN.md).


OKX·Bybit·Bitget의 공개 선물 목록 조회 의존성을 분리하고 제한 재시도·원인 분류를 보완했다. Upbit 중복 종목 ID의 시세 해석과 Bitget 비암호화폐 상품 필터를 수정했다. 과거 PAPER 원장의 자금 대조 차단·별도 새 평가 준비 안내, 신뢰도 등 진입 보류 사유·실제 수치·기준을 연결하고 7개 암호화폐 기관의 장시간 무거래·주기 갱신 지연을 메인 거래 현황과 기관 운용 요약에 표시한다.

3.9.2.11 빌드 입력에는 위 버전 설정·11탭 매뉴얼과 기존 거래 엔진 수정이 함께 포함되어야 한다. `SOURCE_IDENTITY.json`은 Git 없는 Mac 수정본의 지문을 기록하며 Git 커밋을 대신하지 않는다. Windows의 깨끗한 실제 작업트리에서 입력 지문·제품/PE 3.9.2.11·updater 3.9.211·renderer 태그를 대조한 뒤 빌드한다. 공개 .10 manifest와 설치기를 .11로 재명명하지 않는다. `deploy/release_notes.md`는 다음 .11 빌드용 초안이며 `deploy/release-manifest.json`은 보존된 공개 .10 증거다. [빌드 인계와 업데이트/롤백 조건](V39211_TRADING_ENTRY_UPDATE.md).

공개 v3.9.2.10의 빌드·게시 이력은 보존한다. 이번 v3.9.2.11은 후속 수정 소스와 문서·매뉴얼 정리 단계이며 새 Windows 설치기 빌드·공개 게시는 아직 수행하지 않았다. 아래 이전 버전의 후보·미게시·실행 승인·검증 수치는 각 작성 당시 이력이다. 과거 승인을 이번 버전의 게시 완료 근거로 사용하지 않는다.

---

## 2026-10-10 — v3.9.2.10 전략 스튜디오 작업 선택·학습 안내 통합

당시 소스 후보 버전: **v3.9.2.10** · 당시 공개 버전: **v3.9.2.9**.
당시 소스 후보: v3.9.2.10 · 당시 공개 기반: v3.9.2.9. 제품/엔진/PE 3.9.2.10, updater 3.9.210, renderer 3.9.2.10-ui.20261010.1.
공개 v3.9.2.9는 2026-10-10(KST) 빌드·게시 완료되었으며 이번 변경은 별도 v3.9.2.10으로 묶는다. 공개 기반 커밋은 `52fb7df23dcdc8bab2df0cd287abf86acba1fcba`이다.

기본 작업을 전략 사용하기·내 전략 만들기·공유하기로 나누고, 따라하기·멘토·Level 안내·검증 원리·허브 상세 설명은 학습·고급 안내에 보존했다. 작업 이동 시 작성 초안을 유지하고, 보완·멘토 후보·AI 전달 초안은 작성 화면으로 이동한다. 검증 상세와 여러 버전 관리는 펼쳐 볼 수 있다. 기존 Level 기능 게이트·승인·PAPER/LIVE 보호·원본과 검증 이력은 유지하며 매매 엔진·PAPER 계산을 변경하지 않는다.

현재 무료 공유이며 유료 판매·제작자 정산은 준비 중이다. 허브 첫 화면·제출·학습 안내 템플릿은 인접 daltrading 소스에서 별도 검증했고 클라이언트 설치기만으로 서버에 배포되지 않는다. 사용자 최신 요청은 점검·수정·전체 Windows 빌드 후 stable/latest 공개 릴리스를 승인한다. 이 절 작성 시 설치기 빌드·공개 게시는 준비 중이며, 최종 결과는 reports/v39210-windows-publication-20261010.json으로 확인한다. 실제 설치 업데이트/롤백·OCX·실계좌·장시간 운용은 별도 인수이며 미실시를 통과로 표시하지 않는다.

## 2026-10-08 — v3.9.2.8 Windows 즉시 빌드·stable/latest 게시 승인

사용자는 이 세션에서 Codex가 즉시 Windows v3.9.2.8을 전체 빌드하고 nwsoft/ai-trading-client에 stable/latest로 게시하도록 명시적으로 승인했다. 이 승인은 아래의 날짜별 소스 전용·게시 금지 지시를 이번 실행에 한해 대체한다. 공개 빌드 기준은 v3.9.2.7, 제품 3.9.2.8 / updater 3.9.208 / renderer 3.9.2.8-ui.20261008.3이다. 원격 최신 .8과 실제 로컬 소스를 비교하고 60초 동기화 안정 확인 후 정확한 커밋의 격리 작업트리에서 검사 생략 없이 빌드한다.

자동 회귀·x64 엔진·x86 호스트·bootstrap/IPC·PE 정본 아이콘·공개 네 파일의 해시·소스 태그 검증은 이번 실행 범위다. 수동 OCX 로그인, LIVE 계정, 실제 설치/자동 업데이트/롤백, 24/72시간 운용 및 외부 서비스 인수는 미실시 상태를 유지한다. 실행 중인 사용자 거래 클라이언트에 설치하지 않는다. 허브 서버 배포는 별도 요청이 필요하다. 실제 결과는 reports/v3928-windows-publication-20261008.json에 기록하며 아래 기록은 당시 이력으로 보존한다.

## 2026-10-08 — v3.9.2.8 실제 빌드 폴더 반영·업데이트 카드 정합성 (소스 후보·미배포)

당시 소스 후보 **v3.9.2.8** / updater **3.9.208**, 공개 기반 **v3.9.2.7**, 실제 renderer 식별자 **3.9.2.8-ui.20261008.3**. 별도 Git 작업트리만 수정했던 인계 누락을 바로잡아 사용자 `noahai_client/` 폴더에도 코드·버전·CHANGELOG·UPDATE_PLAN·11탭 매뉴얼을 반영했다. 데이터·자격정보·기존 설치기는 동기화 대상에서 제외하고 교체 전 소스 파일은 별도 백업했다.

업데이트 탭 안내 카드의 오래된 `3.9.1.40`과 예전 변경 설명을 제거했다. 카드 버전·변경 제목·요약을 매뉴얼 정본에서 읽으므로 후속 버전도 정본과 함께 갱신된다. .8 최신 업데이트는 PAPER 청산 복구와 전략 평가 입력 보호를 함께 안내한다. 원본 규칙·IR·승인·LIVE 보호는 유지한다. 현재 Windows 설치본 빌드·OCX/실계좌·설치 인수·공개 릴리스는 수행하지 않았다.

### Windows 빌드 시 실제 Git 소스 신원

Mac 동기화 폴더에는 `.git`이 없다. 파일을 복사해도 Windows 저장소의 HEAD는 자동으로 .8 커밋으로 바뀌지 않는다. `verify_release_provenance.py`는 실제 Git 커밋·깨끗한 빌드 입력·소스/manifest 지문 일치를 요구하므로 이전 .7 HEAD 또는 Git 없는 폴더로 공개 게이트를 우회하지 않는다. Windows 저장소에서 최신 작업 브랜치를 fetch하고 기존 폴더를 덮어쓰지 않는 새 작업트리로 빌드한다(아래 경로가 있으면 다른 새 경로 사용).

```powershell
git fetch origin
git worktree add --detach ..\noahai_client_3928_build origin/release/v3.9.2.8-retrained-evaluation-20261008
Set-Location ..\noahai_client_3928_build
git rev-parse HEAD
# Python/Node >=22.12와 x86 Kiwoom 환경을 준비한 뒤 검사 생략 없이 실행
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

현재 동기화 소스·매뉴얼·화면 빌드는 .8이다. 실행 중인 .7 앱/이미 설치된 .7 EXE는 파일 동기화로 교체되지 않으므로 종료 후 새 소스로 재실행하거나 사용자 Windows 빌드/설치가 필요하다. 공개 게시 명령은 이번 작업에서 실행하지 않는다.

## 2026-10-08 — v3.9.2.8 전략 개선 평가 입력 보호 (후속 소스·공개 미배포)

2026-10-08 빌드 폴더 인계 보완: 별도 Git 작업트리의 .8 수정이 사용자 `noahai_client/` 폴더에 반영되지 않았던 상태를 확인했다. 대상 기존 파일을 별도 백업하고 .8 코드·config/package/화면 버전·업데이트 문서·11탭 매뉴얼 JSON을 동기화한다. 대시보드 「최신 업데이트」에 PAPER 복구와 전략 평가 입력 보호를 함께 반영한다. 이 폴더 반영과 설치본 배포는 별개이며 Windows Git 커밋/소스 신원은 현지에서 확인한다. 실행 결과는 TEST_STATUS의 폴더 동기화 절에 기록한다.

당시 소스 후보: **v3.9.2.8** · updater **3.9.208** · 당시 공개 기반: **v3.9.2.7**. 화면 빌드 식별자: `3.9.2.8-ui.20261008.2`. 제품·엔진·Windows PE·updater 버전은 기존 .8 정본을 유지한다.

공개 .7 태그/브랜치 `1c23b1e4947514906c1eb11050873a5c74ce39b0`와 원격을 새로 fetch했다. main `bd2fe406`은 공개 소스와 다르다. 기존 .8 `7aeb12e`·`534d9de`·`95d35ca`를 보존해 `release/v3.9.2.8-retrained-evaluation-20261008`에서 후속 수정한다. 객체형 EMA 건너뛰기 `f209608`과 기관의 주식 매수가능금액 조회 `aec9421`은 이미 포함돼 있어 중복 수정하지 않았다.

규칙·기본 봉·추가 시간봉 전체의 엄격 JSON 입력 해시를 재생 전에 검증한다. NaN/±∞ 또는 직렬화 불가 입력은 `input_evidence_not_supported`와 해시 없음·재생 0회로 보고하며 후보 승인·자동 적용·LIVE 승격을 허용하지 않는다. 값을 임의 치환하거나 해시에서 제거하지 않는다. 기존의 깊이 우선 첫 수치 조건 탐색·시간 분리·비용 2배·12회/15초 보호를 유지한다.

이번 후속 지시는 **커밋·작업 브랜치 push까지 승인**한다. PR 생성·공개 릴리스·태그 게시·설치기 배포·Windows workflow 실행은 포함하지 않는다. 아래 PAPER 준비 단계의 push 제외와 .7 게시 승인은 당시 이력이다. Windows/OCX·실계좌·설치 업데이트/롤백·24/72시간 인수는 새 증거가 없어 미실시를 유지한다.

### 최신 작업 브랜치에서 Windows 인계

기존 PAPER 단계 zip/bundle의 `95d35ca`는 이번 평가 수정을 포함하지 않는다. 새 원격 작업 브랜치의 최종 커밋을 확인한 별도 checkout을 사용한다. `.venv`, `node_modules`, `dist`는 빌드 PC에서 준비하며 로컬 환경 링크는 Git에 포함하지 않는다. `git fetch origin` 후 `origin/release/v3.9.2.8-retrained-evaluation-20261008`를 별도 worktree로 열고 `scripts/build_windows.ps1`의 검사를 전부 실행한다. Windows 설치기 빌드·배포 명령은 이번 Mac 작업에서 실행하지 않는다.

## 2026-10-08 — v3.9.2.8 PAPER 청산 복구·계약 근거 보호 (이전 준비 단계 기록)

당시 소스 후보: v3.9.2.8 · updater 3.9.208. 현재 공개 기반: v3.9.2.7.
당시 소스 후보 버전: **v3.9.2.8** · 당시 공개 버전: **v3.9.2.7**.

공개 .7 커밋 `1c23b1e4947514906c1eb11050873a5c74ce39b0`에서 별도 .8 브랜치로 수정·시험·로컬 커밋한다. main을 기반으로 하지 않는다. 청산 원장의 확정 이벤트와 잔여 수량·완료 상태를 재시작 때 대조하고, 계약 단위 없는 해외 선물 과거 기록은 미확정으로 분리한다. [수정·복구·보존 증거 및 남은 인수](V3928_PAPER_RECOVERY.md).

이번 지시는 GitHub push·PR·공개 릴리즈 배포를 포함하지 않는다. 아래 .7의 즉시 게시 승인·후보 표기는 당시 이력이며 .8에는 적용하지 않는다. Windows 설치본 수동/자동 업데이트·롤백·24/72시간 운용은 실제 환경이 없어 미실시다. 로컬 자동 검사를 설치본 인수로 표시하지 않는다.

### .8 로컬 Git bundle 인계와 Windows 미실시 인수

`reports/v3928/COMPLETION.md`의 수정·검증 결과와 `reports/v3928/WINDOWS_HANDOFF.md`의 절차를 검토합니다. 인계 zip/bundle은 Mac 동기화 작업 폴더의 `reports/v3928-handoff/`에 따로 생성하며 공개 .7 커밋을 prerequisite로 사용합니다. GitHub push·PR·릴리스 게시 없이 사용자의 Windows 저장소에서 새 .8 작업트리를 만듭니다. main 및 기존 .7 빌드 폴더를 덮어쓰지 않습니다.

실제 계정 경로·engine recorder DB·포지션 저장 경로를 확인하고 모든 관련 writer를 정지한 뒤 최신 backup을 확보합니다. 외부 저장 경로가 있으면 같은 정지 구간에 별도로 백업합니다. Windows에서 검사를 생략하지 않고 `scripts/build_windows.ps1`로 .8 설치기를 생성한 후 수동/자동 업그레이드·복구·최신 기록을 보존한 롤백·24/72시간 PAPER 인수를 수행합니다. 현재 Mac 검사 결과를 Windows 설치기 인수로 승계하지 않습니다. 공개 게시 명령은 이번 지시에서 실행하지 않습니다.

## 2026-10-07 — v3.9.2.7 Windows 공개 게시 최신 승인

사용자는 이 세션에서 Codex의 즉시 Windows 전체 빌드와 nwsoft/ai-trading-client v3.9.2.7 stable/latest 공개 게시를 명시적으로 승인했습니다. 이 승인은 아래의 소스 준비만 허용했던 이전 담당·게시 제한을 대체합니다. 제품 3.9.2.7 / updater 3.9.207, 공개 빌드 기준 v3.9.2.6을 사용합니다. 검사 생략 없이 x64 엔진, x86 Kiwoom 호스트, bootstrap/IPC, 실제 PE 정본 아이콘, 공개 자산 해시와 정확한 소스 태그를 검증합니다.

수동 OCX 로그인·LIVE 계정·실제 설치 업데이트/롤백·장시간 운용·외부 서비스 인수는 증거가 없는 한 미완료입니다. 허브 파서 패치는 별도 서버 변경이며 이번 클라이언트 공개로 배포되지 않습니다. 아래 문장은 당시의 인계 이력으로 보존합니다. 최종 게시 증거는 reports에 기록합니다.

## 2026-10-07 — v3.9.2.7 전략 업로드·PAPER 계산 수정 (소스 후보·미배포)

당시 소스 후보: v3.9.2.7 · updater 3.9.207. 현재 공개 기반: v3.9.2.6.
당시 소스 후보 버전: **v3.9.2.7**
당시 공개 버전: **v3.9.2.6**

Windows 빌드·릴리즈·게시 담당은 사용자입니다. Codex는 수정·로컬 검증·배포 준비만 수행합니다. 허브 파서 패치는 별도 서버 반영이 필요합니다. [수정 원인·기존 사용자 재개·검증 경계](V3927_FEEDBACK_PATCH.md). 아래 버전별 후보·미배포 표기는 당시 이력입니다.

현재 승인 범위에서는 Codex가 GitHub 빌드 workflow를 실행하거나 설치 파일/릴리스를 게시하지 않습니다. 아래 .6의 과거 게시 승인 문장은 당시 이력이며 이번 .7에는 적용하지 않습니다. 사용자는 현행 소스에서 `scripts/build_windows.ps1`로 빌드하고 설치본 인수 후 `scripts/release_windows.ps1`로 게시합니다. 검사를 생략하는 옵션은 사용하지 않습니다.

### .7 Windows 소스 인계

`reports/v3927-handoff/`의 Git bundle과 `WINDOWS_HANDOFF.txt`를 Windows로 가져옵니다. bundle은 공개 `v3.9.2.6` 태그를 기반으로 하며 원격 저장소에 push하지 않은 로컬 수정입니다. 인계 안내의 SHA-256·커밋·소스 지문과 대조한 별도 작업트리에서 기존 Windows 환경을 준비합니다. Node는 package.json의 `>=22.12.0`을 사용합니다. 이 안내는 빌드·배포를 자동 실행하지 않습니다.

새 작업트리에 없는 생성 manifest는 빌드 스크립트가 버전·해시를 고정한 공개 .6 manifest로 준비합니다. 이전 공개 .6 설치기도 해시·크기를 검증한 뒤 확보합니다. 새 .7 manifest와 인수 결과는 사용자의 Windows 빌드에서 생성합니다. Git 외부에 보관한 과거 Mac 충돌 파일은 새 PC의 빌드 입력이 아니므로 없다고 빌드를 막지 않습니다. 활성 소스의 충돌 파일 검사는 계속 적용하고, 과거 보관 폴더가 있으면 전체 파일과 해시를 검사합니다.

## 2026-10-06 — v3.9.2.6 전략 스튜디오·자율주행 후속 (개발 진행·미배포)

당시 소스 후보: v3.9.2.6 · updater 3.9.206. 현재 공개 기반: v3.9.2.5.
당시 소스 후보 버전: **v3.9.2.6** · 당시 공개 버전: **v3.9.2.5**

3.9.2.5는 빌드·릴리스·배포 완료한 공개 버전으로 보존합니다. 이후 로그·배분 정정, 코인/주식 종목 선택, 시작 버튼 기반 자율주행과 전략 스튜디오의 남은 고도화를 3.9.2.6으로 진행합니다. [실행 원장·완료 조건](UPDATE_PLAN.md#v3926-autonomous-studio-release). 새 Windows 설치본·공개 게시·실환경 인수는 아직 완료하지 않았습니다. 아래 날짜별 소스/후보/배포 표기는 당시 이력입니다.

### 2026-10-06 현재 Windows 게시 승인

사용자는 이 세션에서 v3.9.2.6을 즉시 Windows 빌드하고 stable/latest GitHub 릴리스로 공개하도록 Codex에 명시적으로 승인했다. 아래 사용자만 게시한다는 지침은 이 승인 이전의 인계 이력이며 이번 실행에는 적용하지 않는다. 전체 자동 검증과 x64 엔진·x86 Kiwoom 호스트·bootstrap/IPC·실제 PE 아이콘 검증을 통과한 정확한 소스 커밋으로 게시한다. 새로운 로컬 승인 변경을 보존하고 동기화 안정성을 최소 60초 확인한다. 실계좌·OCX 로그인·실제 설치 업그레이드/롤백·장시간 운용 인수는 수행 증거가 없으면 계속 미완료로 남긴다. 게시 결과는 reports에 별도로 기록한다.

Windows 검증 중 source-map-js 1.2.1의 high 취약점(GHSA-68fv-2mgg-jv7q)이 확인되어 lockfile을 수정 버전 1.2.2로 갱신했다. 정수 밀리초와 고정 시계로 통합 노출 테스트를 재현 가능하게 정정했으며 같은 시각의 접수 후 예약은 계속 차단한다. 런타임 안전 조건은 변경하지 않았다. 수정 후 전체 자동 빌드를 다시 수행한다.

### .6 Windows 빌드·릴리스 담당 (현재 승인 이전 이력)

사용자 결정에 따라 Windows PC의 빌드·릴리스·배포는 사용자가 담당한다. Codex는 소스·로컬 검사·문서와 릴리스 브랜치를 준비하며 GitHub 자동 후보 빌드/공개 게시를 대신 실행하지 않는다. 후보 workflow는 수동 요청만 지원한다. 기존 `.5` Git 작업트리를 덮어쓰지 않고 원격 `.6` 브랜치에서 새 작업트리를 준비한다. 기존 Windows Git 저장소에서 아래 순서로 진행한다(새 경로가 이미 있으면 다른 빈 경로 사용).

```powershell
git fetch origin
git worktree add --detach ..\noahai_client_release_3926 origin/release/v3.9.2.6-20261006
Set-Location ..\noahai_client_release_3926
# 기존 Windows 가상환경/Node 및 x86 Python을 준비한 뒤 실행
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
# 자동 검사·산출물 확인 후 DEPLOY_CHECKLIST의 설치/운영 인수를 진행
# 현재 상태만으로 즉시 공개하지 않으며, 인수 결과 확인 후 사용자가 게시
powershell -ExecutionPolicy Bypass -File .\scripts\release_windows.ps1
```

`reports/v3926-candidate-source.json`은 Codex 로컬 인계 기록이며 Git 저장소의 필수 파일이 아니다. Windows 작업트리의 실제 소스 신원은 다음 명령으로 확인하고 인계 커밋/지문과 대조한다.

```powershell
git rev-parse HEAD
.\.venv\Scripts\python.exe .\scripts\release_source_fingerprint.py --root .
```

검사를 생략하지 않고 미확정 주문·원장·기존 키/설정·전략을 보존한다. 로컬 검사 통과를 Windows 산출물 통과로 승계하지 않는다. 수동 검사가 끝나기 전 새 Windows 설치본/공개 게시를 완료로 표시하지 않는다.

Mac 로그인 이후 전체 사용자 과업도 아직 인수하지 않았다. 후보 빌드가 가능한 상태와 일반 공개 배포 준비 완료는 구분하며 [상태 재확인](UPDATE_PLAN.md#v3926-autonomous-studio-release)과 [인수 목록](DEPLOY_CHECKLIST.md)을 확인한다.

### .6 깨끗한 Windows 환경의 재현 빌드

GitHub Windows runner와 새 PC는 이전 설치기가 없는 경우 `scripts/restore_previous_release_asset.py`로 공개 .5 설치기를 확보합니다. `config/published_release_baselines.json`의 버전·파일명·크기·SHA-256과 대조한 뒤 원자적으로 보관하며 기존 파일이 다르면 덮어쓰지 않습니다. 이미 게시된 .5 자산이나 manifest를 수정하지 않습니다. Python 자료·시험·생성 JSON의 UTF-8 인코딩을 명시해 한국어/영어 Windows 기본 인코딩 차이를 제거합니다. 시험·엔진·x86 호스트·PE·bootstrap/IPC 검사를 생략하지 않습니다.

## 2026-10-05 — v3.9.2.5 생활금융 비교·후속 관리 (공개 Windows 릴리스)

현재 소스 기준: v3.9.2.5 · updater 3.9.205. 현재 공개 기반: v3.9.2.5 (2026-10-05 공개 게시·2026-10-06 GitHub latest 재확인).
현재 소스 기준 버전: **v3.9.2.5**

현행 Windows 실행 명령은 `powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1`와 검증 후 `scripts/release_windows.ps1`입니다. 아래 v3.9.1.45 등 버전별 설명은 과거 기록이며 현행 버전은 이 상단과 `config/app_version.py`를 따릅니다. Windows에서 사용자 담당자가 검증 후 게시할 때 stable/latest를 갱신하며 수동 OCX 로그인·실계좌·설치/롤백·외부 서비스 인수는 자동 빌드/게시와 별도로 미검증 상태를 유지합니다.

공개 v3.9.2.4 이후 수정입니다. 상황별 진입, 목적 필터, 관심 보험 근거 설명, 비상금·보장·대환·사용 날짜 비교, 암호화 계획과 공통 조건, 자료 피드 갱신/복구, 상담 회신 견적, 기록 수정·가져오기를 구현합니다. [반영 범위·검증·운영 연결 인수](V3925_LIFE_FINANCE_COMPLETION.md). **3.9.2.5 Windows 설치기·blockmap·latest.yml·release-manifest.json은 2026-10-05 공개 게시되었습니다.** 아래 날짜별 후보/미게시 문장은 당시 이력입니다.


2026-10-06 공개 신원 대조: [GitHub 릴리스](https://github.com/nwsoft/ai-trading-client/releases/tag/v3.9.2.5)의 latest·게시 시각·4개 자산 digest를 보관된 게시 보고서와 대조했습니다. 설치본 게시와 실제 금융사·상담사 연결, 기관별 실계좌·장시간 인수는 별도입니다. [거래 화면·전략·문서 재감사](TEST_STATUS.md#v3925-trading-document-audit-20261006).

## 2026-10-04 — Windows 아이콘 누락 재발 방지

Windows/NSIS 아이콘은 추적된 루트 `icon.ico`, Mac 아이콘은 루트 `icon.png`를 사용합니다. 무시되는 `webui/build` 자산은 빌드 입력으로 사용하지 않습니다. 기존 NoahAI 파랑·보라·분홍 로고를 그대로 사용하며 새 로고를 생성하지 않습니다.

`scripts/verify_branding.py`는 빌드 전 파일 존재·정본 SHA-256·이미지 디코딩·ICO의 16/32/48/256 크기·패키징 경로를 검사합니다. Electron beforePack에서도 같은 검사를 실행하므로 직접 패키징도 누락 시 실패합니다. 소스 fingerprint에는 두 루트 아이콘, public PNG, 검사기와 Electron hook이 포함됩니다.

빌드 후 `win-unpacked/NoahAI.exe`와 버전별 Setup.exe의 실제 PE 아이콘 그룹 및 모든 이미지 payload를 정본 ICO와 대조합니다. 기본 Electron/NSIS 아이콘이나 잘린 리소스이면 빌드와 게시가 실패합니다. 증거는 `deploy/branding-verification.json`과 release-manifest의 `verification.branding`에 기록하며 게시 직전 다시 검사합니다. `python -m pytest -q tests/test_branding.py`는 누락·잘못된 이미지·기본 아이콘·패키징 경로·fingerprint 변경을 검사합니다.

전체 Python 및 Node 회귀, Web typecheck/build와 dependency audit, x64 엔진·x86 키움 호스트 빌드/스모크는 생략하지 않습니다. OCX 로그인·실계좌·설치 업그레이드·장시간 운용은 별도 실제 증거가 있을 때만 통과로 기록합니다. 이전 3.9.2.3 게시 자산은 교체하지 않습니다.

## 2026-10-04 — Mac 로컬 실행 복구

3.9.2.3 소스에 3.9.2.2 화면이 남아 실행이 종료되던 경로를 수정했다. 로컬 실행기가 설치된 호환 Node로 오래된 화면을 자동 재빌드하고 검증한 뒤 실행한다. Mac 의존성은 기존 lockfile로 복원했다. 바탕화면 `NoahAI.app`은 현재 작업본 실행기에 연결했다. 실제 Electron 화면 준비 이벤트·엔진 health 3.9.2.3, 누락 빌드 자동 복구, Node 계약 73개 통과. Finder/아이콘 시각 인수는 native UI 도구 장애로 미검증. [상세 원인·검증](V3923_MAC_LOCAL_LAUNCH_FIX.md). 공개 설치기·거래 정책·계정 자료는 변경하지 않았다.

## 2026-10-03 — v3.9.2.3 Windows 릴리스 후보

당시 소스 후보 버전: **v3.9.2.3** · updater **3.9.203**. 현재 공개 기반: v3.9.2.2. 공개 v3.9.2.2 자산은 보존하며 새 설치본은 전체 자동 검증 후 게시한다. 수익성 재진단·생활금융 조건 계산·암호화 보관·상담 연결 준비를 포함한다. 실계좌·OCX 로그인·전문가·실제 공급사/상담사 인수와 설치 업그레이드·장시간 운용은 미완료다. 아래 후보·미게시 설명은 작성 당시 이력이다.

## 2026-09-24 - v3.9.1.47 Strategy Repair and Reconciliation Diagnostics Patch (미배포 소스 후보)

당시 소스 후보 v3.9.1.47 / updater 3.9.214 · 공개 v3.9.1.46. 전략 등록·기존 버전 보완 및 손익 대조 차단 안내 개선. 원문 실행값의 저장 단계 변형을 제거하고 미완성 초안 보관과 기존 버전의 원문 재분석/명시적 기본 AI 진입 전환을 제공합니다. 기존 성과는 새 버전에 승계하지 않습니다. 손익 확인 실패의 일반 409/워커 장애 안내를 구체화하고 복구 대상과 위험 검사 대상의 불일치를 보강하며 거래별 미확정 사유를 표시합니다. 미확정 손익 무시·자동 LIVE 재개는 제공하지 않습니다.

소스 검증: 전체 회귀 3,736 통과·9 제외·3 subtests 통과. 코인/증권 브라우저 신규 등록·명시적 기존 버전 전환·미완성 초안 보관 6경로 통과(실제 로컬 컴파일러/검증기, 저장 API fixture). 숫자 30.0/30 직렬화 차이의 오차단과 기존 고정 TP/SL 불러오기 충돌도 수정했습니다. Windows 설치본·실계좌·9월 24일 미대조 1건은 미검증입니다. 현재 data/Teayu-001이 없어 고객 사본 회귀 1개도 제외됐습니다. 설치기 빌드·게시를 하지 않았고, 미확정 손익의 조건부 LIVE 재개는 구현하지 않았습니다. 상세 범위는 TEST_STATUS와 최신 V39147 검증 원장을 따릅니다. 아래 이전 수치는 이력입니다.

## v3.9.1.46 빌드 후보 — 2026-09-23

제품 3.9.1.46 / updater 3.9.146. 설치기 예정명 NoahAI-3.9.1.46-Setup.exe. 공개 v3.9.1.45 자산·manifest는 덮어쓰지 않습니다. 아래 이전 버전 명령은 이력이며 현재 package.json과 config/app_version.py를 정본으로 사용합니다. Windows 설치본·기관별 시작→관찰→실채널 수신은 미검증입니다. 이번 작업에서는 설치기를 만들거나 게시하지 않았습니다.

# NoahAI 빌드·릴리즈 가이드 — 현재 v3.9.1.45

현재 제품 **3.9.1.45**, Electron updater **3.9.145**, 설치기 **NoahAI-3.9.1.45-Setup.exe**. 공개 기반은 **v3.9.1.44**(사용자 확인 및 로컬 공개 manifest)이며 게시 직전에 원격 최신 상태를 다시 확인합니다.

오늘 지표 저장·조회·UI 안내 및 시장국면·알림 변경을 새 빌드에 포함합니다. `trading/indicator_evidence.py`, 두 거래 엔진의 학습 기록, `query_services`, 평가기, 알림·국면 관련 소스, 새 버전 package/lock/inventory, 재추출한 11탭 매뉴얼을 같은 소스 fingerprint로 묶습니다. [최신 변경](CHANGELOG.md) · [시험 경계](TEST_STATUS.md).

공개 v44의 `deploy/release-manifest.json`, `deploy/version.txt`, 해시와 기존 릴리스 자산은 덮어쓰지 않습니다. Windows에서 실제 v45 설치기·blockmap·latest.yml을 만든 후 자산 생성 도구로 새 manifest와 해시를 생성합니다. 기존 EXE의 이름·버전만 바꿔 배포하지 않습니다. 이 Mac 작업에서는 Client 설치기 빌드·게시를 하지 않으며 사용자가 수행합니다.

추가 Windows 확인: v43/v44 계정 업데이트 → 기존 학습 기록 보존 → 새 분석 생성 → RSI·MACD·추세와 모드/기관 확인 → 재시작 후 재조회. 기술점수 미산출은 별도 안내로 구분하고, 매매 정책·PnL 보호·국면 기본 300초/2회/600초가 유지되는지 확인합니다. 실제 메신저 전달·기관 계좌·장시간 운용은 로컬 모의시험과 별도입니다.

아래 v44 이하 인계는 상속 기능과 당시 기록입니다. 버전·자산 이름은 위 v45 기준 및 `config/app_version.py`/`webui/package.json`이 우선합니다.

## 과거 v44 복구 추가 인계

새 빌드에는 `binance_history_recovery`, `record_recovery`, `record_recovery_adapters`, 복구 UI·체결 상세·최신 매뉴얼을 함께 포함합니다. [추가 검증 보고](../reports/v39144-recovery-completion-verification.md)를 확인하고 Windows 설치본에서 설정 창 닫기 후 계속 진행, 앱 종료·재시작 이어하기, 기존 캐시 이관, 분할 청산과 계정 격리를 확인하세요. 이 버전은 Binance 전체 구간 복구를 증권사 지원으로 확대했다고 주장하지 않습니다.

## 당시 인계: 3.9.1.44 / updater 3.9.144

v44는 증거 보존형 학습 저장소·판단 DB 인덱스·공통 이벤트·유지관리 변경입니다. [v44 계획](V39144_STORAGE_TEST_PLAN.md)과 [검증 보고](../reports/v39144-storage-verification.md)를 먼저 확인하세요. 아래 v42/v43 자료는 상속 기능이며 해당 버전의 과거 미완료 게이트를 통과로 승계하지 않습니다. 고객 원본 DB는 수정하지 않았습니다. Client 설치기 빌드·배포는 사용자가 수행합니다.

v44 추가 게이트: Windows에서 기존 계정 업데이트 → 유지관리 저장소 최적화 → 재시작 → 학습·XAI·리포트 확인, 7기관 장시간 실행, 절전·강제 종료·디스크 부족·백신 잠금 시험. `deploy/release-manifest.json`과 `deploy/version.txt`는 이전 v43 산출물 증거이므로 이 소스 변경에서 수정하지 않습니다. 새 Windows 빌드가 v44 이름·실제 해시·fingerprint를 재생성해야 합니다. 공개 기반 상수 v42 및 문서의 과거 공개 설명은 현재 GitHub 게시 상태를 재확인한 결과가 아닙니다.

## v3.9.1.44 빌드 인계 — 2026-09-21

영어 베타 추가 이후의 소스로 빌드합니다. `webui/src/i18n/*.json`, `web_platform/display_preferences.py`, `web_platform/english_guide.py`와 재생성된 한국어 매뉴얼을 포함해야 합니다. [언어 범위/시험](V39142_ENGLISH_IMPLEMENTATION_PLAN.md) 및 [최종 보고](../reports/v39142-english-verification.md)를 확인합니다. Windows에서 기본 한국어 → English → 재시작 → 한국어, 계정별 보존, 100/125/150% 배율, 전략 입력/모드/손익 불변을 확인합니다. 번역은 표시만 변경하며 엔진 알림·고급 설명 전체 완역은 아닙니다.

언어 UI 후속도 포함합니다: 로그인 폼 하단, 설정 → 일반 → 표시 언어. Electron main/preload의 시스템 언어 전달 변경은 개발 앱 완전 종료 후 재실행해야 반영됩니다. 저장값 없는 한국어/영어 OS 첫 실행, 명시 선택 우선, 미지원 OS 언어의 한국어 fallback을 각각 확인합니다. 국가/IP 조회는 없습니다.

제품 3.9.1.44 / updater 3.9.144. 공개 v3.9.1.43 설치기·태그·latest.yml·manifest는 보존합니다. **이번 작업에서는 Client 설치기 빌드·릴리스를 하지 않으며 사용자가 수행합니다.** [V39142_REMOTE_CONTROL_PLAN.md](V39142_REMOTE_CONTROL_PLAN.md)의 최종 소스 시험과 미완료 Windows/실기관 게이트를 확인하세요. `web_platform/remote_control.py`, 원격 monitor/gateway/UI, 승인·명령 회귀 및 재생성한 매뉴얼을 포함한 fingerprint로 새 Windows 빌드를 식별합니다. daltrading 서버 배포 완료는 설치본 제어 검증 완료가 아닙니다.

# NoahAI 빌드·릴리즈 가이드

현행 소스 후보: **3.9.1.45** / Electron updater: **3.9.145**. 공개 stable/latest의 실제 버전은 게시 직전 원격에서 재확인하며, 기존 자산·태그·manifest는 불변입니다. 과거 설명은 [보존본](archive/build/BUILD_GUIDE_PRE_V39135.md)에 있으며 아래 명령만 현행입니다.

**v45 신규 빌드 필요:** [v45 검증 계획](V39145_INDICATOR_TEST_PLAN.md) 및 상속 원격 기능의 [검증 계획](V39142_REMOTE_CONTROL_TEST_PLAN.md)을 따릅니다. 기존 v42/v43 자산을 이름만 바꾸거나 재사용하지 않습니다. 현재 Mac 동기화 작업본에는 Git 이력과 Windows 도구가 없으므로 검토된 소스 커밋을 정식 Windows 빌드 환경에 전달해야 합니다. 이전 PnL 미완료 검증도 완료로 승계하지 않습니다.

## 공통 원칙

### 상속 기능의 입력 및 서버 선행 조건

[KPI·원격 실행 계획](V39141_REMOTE_KPI_IMPLEMENTATION_PLAN.md)과 [검증 보고](../reports/v39141-remote-kpi-verification.md)를 함께 확인합니다. `api/telemetry_batch.py`, `web_platform/remote_monitor.py`, `trading/remote_entry_pause.py`, 새 설정 UI 및 재생성한 매뉴얼을 포함한 **새 소스 fingerprint**로 빌드합니다. 시장 트렌드만 들어 있던 이전 v42 fingerprint는 재사용하지 않습니다.

**추가 배포 차단 게이트:** [DB 기반 PnL 조사](V39141_PNL_GUARDRAIL_FEEDBACK.md). `trading/binance_close_evidence.py`, `trading/daily_risk_basis.py`와 새 계산 경로가 포함된 소스를 다시 식별합니다. 특정 사용자 과거 40건 복구는 필수 조건이 아니지만 기존 미대조 기록을 가진 사용자의 안전한 업데이트 처리·실기관/Windows·계좌 일별 대조는 미완료입니다. 빌드 성공은 이 게이트를 해제하지 않습니다.

daltrading 서버의 `docs/V39141_REMOTE_KPI_DEPLOYMENT.md`에 따라 DB 분리/복원과 relay를 먼저 검증합니다. Client는 구형 서버에 개별 KPI로 호환하지만 원격 베타는 서버 활성화가 필요합니다. Windows에서 모바일 로그인과 PC 인증 공존, 오프라인/만료, 신규 제출 정지·보호 청산 유지·PC 재개를 확인한 뒤 20→100→300명으로 확대합니다. 소스 통과가 Windows 설치본·운영 DB 이관 완료를 뜻하지 않습니다.

- **v3.9.1.37부터 태그 대상 필수:** 빌드 입력을 검토·비밀정보 제외 후 Git에 커밋하고 해당 커밋을 원격에 게시합니다. 기본 브랜치의 오래된 HEAD에 태그를 자동 생성하지 않습니다. 기존 v37 이하 태그·설치 파일은 보존합니다.
- 매뉴얼·기관 레지스트리 생성 결과도 커밋에 포함한 뒤 새 체크아웃에서 빌드합니다. `.gitattributes`의 LF 줄바꿈을 적용해 커밋 내용과 실제 빌드 입력 바이트가 일치해야 합니다. `git add .`로 계정 데이터·자격증명·로그·DB·설치기를 일괄 공개하지 마세요.
- 게시 전 `verify_release_provenance.py`가 manifest의 source_revision=HEAD, 커밋/로컬/빌드 fingerprint 일치, 원격 커밋 존재, 기존 태그 불충돌, 커밋 날짜를 검사합니다. 미커밋·미추적·삭제된 빌드 입력도 차단합니다. 관련 없는 생성 산출물은 소스 변경으로 간주하지 않습니다.
- Windows와 macOS 모두 검증된 `--target`으로만 새 태그를 만들고 업로드 전에 태그를 다시 대조합니다. 이미 있는 태그가 다르면 자동 이동·삭제하지 않습니다.
- stable 게시 후 공개 목록 첫 항목·Atom 첫 항목·Latest·latest.yml/설치기 이름이 같은 버전인지 확인합니다. 전파 지연 등으로 불일치하면 **게시되었지만 검증 미완료**로 실패 처리하며 삭제/재태깅하지 않습니다. `python scripts/verify_release_provenance.py --phase published`로 읽기 전용 재확인합니다.

- `config/app_version.py`, `webui/package.json`·lock의 updater 버전, Windows 리소스 버전이 일치해야 합니다. 변환식은 `A.B.C.D → A.B.(C*100+D)`입니다.
- 소스 테스트 통과, 패키지 실행, 실제 계정 연결, 장시간 PAPER 검증은 서로 다른 증거입니다. [v3.9.1.45 검증 계획](V39145_INDICATOR_TEST_PLAN.md)의 실제 확인한 행만 `[x]`로 표시합니다.
- 소스 fingerprint는 `scripts/release_source_fingerprint.py`로 계산합니다. 변경된 소스에 이전 바이너리·해시를 재사용하지 않습니다.
- 사용자 `data/Teayu`·API 키·원장은 빌드 입력이나 공개 릴리즈에 포함하지 않습니다. 빌드되는 data는 공개 금융상품 카탈로그뿐입니다.
- `deploy/release-manifest.json`은 Windows 산출물 명세입니다. macOS는 `deploy/mac-release/release-manifest-mac.json`을 사용하며 서로 덮어쓰지 않습니다.
- 이미 게시된 파일은 덮어쓰지 않습니다. 일반 사용자 배포는 stable/latest, 별도 테스트 후보만 명시적인 prerelease를 사용합니다. 외부 실계정·장시간 검증이 남아 있어도 자동 회귀·엔진·키움 x86·해시 검증을 통과한 운영자 배포는 pending 상태를 manifest에 남기고 stable/latest로 게시합니다. macOS 무서명 파일은 계속 수동 테스트용입니다.
- 서명 없는 macOS 파일에 Gatekeeper 우회나 격리 속성 제거를 권장하지 않습니다. Developer ID 서명·공증 완료 전에는 일반 사용자용 정식 설치본으로 안내하지 않습니다.

## 자동 업데이트 계약

- 3.9.1.45 일반 설치본은 GitHub stable/latest만 조회하고 prerelease·다운그레이드를 허용하지 않습니다. 앱의 Beta 명칭은 사전공개 채널 선택을 뜻하지 않습니다. 테스트 prerelease는 수동 설치용입니다. Windows에는 `latest.yml`, macOS에는 `latest-mac.yml`과 해당 플랫폼 설치 자산을 같은 버전·같은 Release에 함께 게시해야 합니다.
- `백그라운드 업데이트 확인`이 ON이면 로그인 후 15초 뒤 첫 확인을 하고, 이후 사용자가 저장한 1~72시간 주기로 확인합니다. OFF여도 `지금 버전 확인`은 사용할 수 있습니다.
- `업데이트 자동 다운로드`가 ON이면 새 버전을 발견한 뒤 다운로드합니다. OFF이면 알림만 표시하고 사용자가 다운로드 버튼을 눌러야 합니다.
- Windows에서 `종료 시 자동 설치`가 ON이고 다운로드가 완료된 상태라면, 정상 종료 시 거래 엔진·기록의 안전 종료가 성공한 뒤 설치합니다. OFF이면 업데이트 화면의 `설치·재시작`을 사용합니다. 안전 종료 실패 시에는 설치하지 않습니다.
- macOS 자동 업데이트는 앱 코드서명이 필요합니다. 현재 서명 없는 테스트 DMG/ZIP은 같은 Release에서 수동 다운로드·설치만 가능하며, 설정 스위치만으로 이 제약을 우회할 수 없습니다.
- 이미 게시된 `v3.9.1.35` 자산에는 게시 후 수정한 종료 설치·prerelease 조회 패치가 들어 있지 않습니다. 다만 stable/latest 전환으로 v3.9.1.34 Windows 설치본은 v3.9.1.35를 확인·다운로드할 수 있습니다. 같은 버전 자산을 교체하지 말고 다음 제품 버전으로 패치를 빌드·게시한 뒤 이전 설치본에서 1회 실제 업데이트를 검증합니다.
- v3.9.1.45은 새 x64 엔진·x86 키움 호스트·Electron 설치기로만 빌드합니다. 공개 v3.9.1.44의 설치기·blockmap·`latest.yml` 이름이나 해시를 복사·교체하지 않습니다.

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

## Windows 빌드 → 자동 검증 → 릴리즈

```powershell
# 1. 전체 자동 검사와 두 아키텍처 빌드
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1

# 2. 일반 사용자용 stable/latest 게시
powershell -ExecutionPolicy Bypass -File .\scripts\release_windows.ps1

# 3. 빌드와 stable/latest 게시를 한 번에 수행
powershell -ExecutionPolicy Bypass -File .\scripts\build_and_release_windows.ps1
```

일반 사용자용 빌드·stable/latest 게시를 한 번에 수행하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_and_release_windows.ps1
```

`build_and_release_windows.ps1`은 전체 회귀, Web 빌드와 감사, x64 엔진 smoke, 키움 x86 PE·인증 IPC, NSIS 설치기, 해시·업데이트 메타데이터와 Git provenance가 모두 통과해야 게시합니다. 실계좌 주문, 키움 OCX 로그인, 실제 업그레이드 조작과 장시간 운용은 빌드 시스템이 재현할 수 없는 external validation으로 manifest에 기록하지만 stable 릴리즈를 차단하지 않습니다. 별도 확인·override 옵션은 필요하지 않습니다. `SkipTests`, `SkipEngineBuild`, `AllowMissingKiwoomHost`는 공식 릴리즈에서 사용하지 않습니다.

산출물:

```text
deploy/web-engine/NoahAIEngine.exe                 x64
deploy/web-engine/NoahAIKiwoomHost.exe             x86, PE 0x14c
deploy/web-release/NoahAI-3.9.2.14-Setup.exe
deploy/web-release/NoahAI-3.9.2.14-Setup.exe.blockmap
deploy/web-release/latest.yml                      updater 3.9.214
deploy/release-manifest.json
```

현재 .14 빌드 전 `deploy/release-manifest.json`이 공개 .13을 가리키는 것은 정상입니다. Windows 빌드 성공 전 공개 원본에 .14 값이나 가짜 해시를 넣지 않습니다. 복구 스크립트가 hash-pinned .13 원본을 준비하고 빌드 스크립트가 실제 .14 산출물에서 새 manifest를 생성해 설치기·blockmap·`latest.yml`과 함께 검증합니다. 아래 v3.9.1.x 항목들은 해당 버전 당시의 이력입니다.

### v3.9.1.45 추가 확인

**현재 배포 보류:** [v45 검증 계획](V39145_INDICATOR_TEST_PLAN.md)의 Windows 외부 게이트와 [거래 기록 복구 계획](V39143_RECORD_RECOVERY_PLAN.md)의 미완료 항목을 확인합니다. 버튼/자동시험 통과를 과거 40건 복구 또는 전 기관 일별 계좌 대조 완료로 해석하지 않습니다. 로컬 공개 manifest는 v44이며 이번 작업에서 설치기 생성·게시를 수행하지 않았습니다.

v44 추가 인수시험: 유지관리의 한/영 설명·기록 충돌 경고·보관 로그 용량·압축 실패 재시도를 확인합니다. 테스트 계정의 닫힌 로그 압축 전후 내용이 같고 활성 로그는 유지되며, 예산 초과 후 공간 확보 시 기록이 재개되어야 합니다. 증권/ETF의 청산 XAI에 주문 ID와 실행 모드가 연결되는지, 타임아웃을 실주문 없음으로 잘못 표시하지 않는지도 확인합니다. 기존 고객 원본으로 파괴 시험을 하지 않습니다.

유지관리 시험: 설정 → 업데이트에서 거래 기록 점검·복구를 실행하고 진행/실패/이어하기/미확정 사유, 한국어·영어, 재시작 후 상태, 최초 백업과 변경 기록을 확인합니다. 실제 주문은 제출하지 않으며 PAPER/통계 표시 기준/손실 한도가 유지되어야 합니다. 실행 중 워커는 복구된 근거로 기존 정책을 재평가하므로 결과 확인 전 신규 거래를 원하지 않으면 기존 신규 진입 일시정지를 사용합니다.

Binance 시험: 청산 ID 누락뿐 아니라 기존 ID의 분할 청산·수량 불일치를 포함합니다. 주문·체결·Algo·income 수집 구간이 증가하고, 조회량 제한 후 설정 창을 닫아도 앱 실행 중 추가 클릭 없이 이어지는지 확인합니다. 독립된 진입·청산 구간이 증명되면 원래 거래 행·체결 원장·순손익이 일치해야 합니다. 음수 손익을 양수로 바꾸거나 미대조를 삭제하지 않아야 하며, 타임아웃/혼합 진입/포지션 변경/보존기간 초과는 구체적 사유가 남아야 합니다. 사용자 API 키는 개발자에게 전달하지 않고 설치된 연결로 조회합니다. 최신 회귀와 고객 DB 사본 시험은 [추가 검증 보고](../reports/v39144-recovery-completion-verification.md)를 따르며 실제 고객 API 정산 완료와 구분합니다.

먼저 [v42 필수 점검](V39142_REMOTE_CONTROL_TEST_PLAN.md)의 기간별 시장 트렌드·데이터 경계·화면 근거 XAI·빈 상태와 Windows DPI를 확인합니다. v41의 AlphaArena·전략 스튜디오/설정 및 아래 거래·검증 항목도 회귀 확인합니다.

1. Strategy Studio 과거재생에서 검증 캔들, 모든 진입·청산 화살표, 선택 거래 이름·원본 가격, 청산 기준 수익률 곡선과 거래표를 확인합니다.
2. 코인과 주식·ETF 각각 500봉 검증을 실행하고 기관·자산·통화·비용·전략 버전이 결과와 일치하는지 확인합니다. 국내 현물 신규 SHORT는 계속 차단되어야 합니다.
3. 7개 코인 거래소와 4개 증권사에서 PAPER는 `가상 포지션`·`가상 거래 통계`, LIVE는 상품에 맞는 `포지션/보유자산`·`실거래 통계`를 표시하는지 확인합니다.
4. 기관별 거래내역은 PAPER/LIVE 모두 기본 접힘이며 모드·기관 전환 시 다시 접혀야 합니다. LIVE 탭 선택만으로 실행 모드가 바뀌어서는 안 됩니다.
5. LIVE 종료 원장의 확정·미확정·외부·가져오기·통화 불명·조회 실패를 구분하고 PAPER/LEARNING 기록이나 다른 기관·계정 기록이 섞이지 않는지 확인합니다.
6. Binance TP/SL 청산 직후 해당 거래의 주문 ID·실현손익·수수료가 확정 대조되는지, 같은 종목 연속 2건의 첫 손익이 유지되는지 확인합니다. 모호한 수동 체결을 섞으면 자동 연결되지 않아야 합니다.
7. 시장 트렌드에서 코인/주식 각각 오늘·7일·30일을 전환하고 시장 폭 원형 그래프, 미니 추세선, 거래량·변동성, 데이터 누락 안내와 두 AI 질문 버튼을 확인합니다. 주식 장기 기간은 선택 증권사 일봉을 순차 조회하며 실패 종목을 당일 수익률로 대체하지 않아야 합니다.
8. 공개 v3.9.1.44 설치본에서 v3.9.1.45을 확인·다운로드하고 거래 엔진 안전 종료 뒤 설치·재시작되는지 확인합니다. 설정, 계정 자격정보, 전략 버전, 검증 결과와 PAPER/LIVE 원장을 대조합니다.

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
deploy/mac-release/NoahAI-3.9.1.45-arm64.dmg
deploy/mac-release/NoahAI-3.9.1.45-arm64.zip
deploy/mac-release/latest-mac.yml
deploy/mac-release/release-manifest-mac.json
```

기본은 서명 없는 로컬 테스트 후보입니다. 정식 서명 빌드는 Developer ID를 Keychain에 설치하고 `CSC_NAME` 및 Apple 공증용 환경을 준비한 뒤 `--signed`로 실행합니다. 인증서·Apple 비밀값은 문서·로그·명령행에 넣지 않습니다. `codesign --verify --deep --strict` 및 `spctl --assess`를 통과하지 않으면 서명 배포로 인정하지 않습니다.

Windows와 macOS는 같은 제품 버전의 **공용 GitHub Release 태그 `v3.9.1.45`**를 사용합니다. Windows는 `latest.yml`, macOS는 `latest-mac.yml`을 읽으므로 플랫폼별 자동업데이트 자산이 충돌하지 않습니다. DMG·ZIP과 두 blockmap, `latest-mac.yml`, Mac manifest를 Windows 설치기와 같은 릴리즈에 게시합니다.

`scripts/publish_macos.py`는 공용 릴리즈가 이미 있으면 Mac 자산만 추가하고 원격 SHA-256을 검증합니다. Windows 릴리즈가 아직 없으면 같은 `v3.9.1.45` 태그의 draft를 만들며, 별도 `-macos-candidate` 태그는 만들지 않습니다. 같은 이름의 원격 자산이 다르면 덮어쓰지 않고 새 제품 버전을 요구합니다. 새 릴리즈에서 서명 없는 Mac 자산을 stable 릴리즈에 추가하는 작업은 스크립트가 차단합니다. v3.9.1.42 이하의 기존 Mac 자산은 과거 공개·수동 테스트 기록이며 v3.9.1.45 자동업데이트 증거로 승계하지 않습니다.

```bash
.venv/bin/python scripts/publish_macos.py
```

## 검증 문서 업데이트

`docs/TEST_STATUS.md`, `docs/DEPLOY_CHECKLIST.md`, 현재 버전 TEST_PLAN, 인앱 매뉴얼을 함께 갱신합니다. 문서 체크 표시를 빌드 통과를 위해 임의로 바꾸지 않습니다. `python scripts/doc_consistency_check.py`와 매뉴얼 재추출을 다시 실행하고, 패키지 입력이 바뀌었으면 재빌드합니다.
